"""The application session: single writer of state, one worker thread (AD-3, AD-24).

It loads the model found by the diagnostic, then runs bare-LLM turns: render
the prompt through the model's own template, attribute its tokens, refuse an
overflowing call, stream the completion, and emit the counter and gauge
figures. Nothing crosses its boundary as an exception (AD-16).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from wavestack import config
from wavestack.context.render import RenderedContext, render_context
from wavestack.context.segments import Part, SegmentKind, SegmentLabels, load_labels
from wavestack.context.window import OUTPUT_RESERVE, effective_window, gauge
from wavestack.models.capabilities import Capabilities, ChannelSplitter, capabilities_for
from wavestack.models.discovery import ModelCandidate
from wavestack.models.engine import CancelToken, Engine, LlamaCppEngine
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import scoped

DELTA_INTERVAL_S = 0.05  # AD-2: model_delta grouped every 50 ms at most

_CORE_HARNESS = {
    "id": "core.harness",
    "kind": "harness",
    "hosting": "local",
    "label_fr": "Harnais WaveStack",
    "wanted": True,
    "available": True,
    "reason_fr": None,
}
_CORE_MODEL = {
    "id": "core.model",
    "kind": "model",
    "hosting": "local",
    "label_fr": "Modèle",
    "wanted": True,
    "available": True,
    "reason_fr": None,
}

_SERVER_ONLY_FR = (
    "Envoi indisponible : seul un serveur local (Ollama ou llama-server) a été trouvé, et son "
    "adaptateur arrive au palier 2. Indiquez le chemin d'un fichier GGUF sur la page de "
    "diagnostic."
)
_LOAD_FAILED_FR = (
    "Envoi indisponible : le modèle n'a pas pu être chargé. Choisissez un autre fichier GGUF "
    "sur la page de diagnostic."
)
_OVERFLOW_STRATEGIES_FR = [
    "Fenêtre glissante : ne garder que les échanges les plus récents.",
    "Compaction : résumer les anciens échanges en quelques lignes.",
    "Retrait des anciens résultats d'outils.",
    "Lazy loading : ne charger la documentation des outils qu'à la demande.",
]


class SendRefused(Exception):
    def __init__(self, reason_fr: str) -> None:
        super().__init__(reason_fr)
        self.reason_fr = reason_fr


def first_model_path(candidates: list[ModelCandidate]) -> str | None:
    """The first usable candidate with a file path; a server alone gives none (palier 2)."""
    return next((c.path for c in candidates if c.status == "found" and c.path), None)


def _fr(n: int) -> str:
    return f"{n:,}".replace(",", "\u202f")  # narrow no-break space, French style


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


class AppSession:
    """The only session once WaveStack has a confirmed model."""

    def __init__(
        self,
        cfg: config.Config | None = None,
        engine_factory: Callable[..., Engine] = LlamaCppEngine,
    ) -> None:
        self.cfg = cfg or config.load_config()
        self._engine_factory = engine_factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wavestack-worker")
        self._lock = threading.Lock()
        self.state = "diagnostic"
        self.reason_fr: str | None = "Diagnostic de démarrage en cours."
        self._engine: Engine | None = None
        self._caps: Capabilities | None = None
        self._window = self.cfg.context_window
        self._labels: SegmentLabels | None = None
        self._turns = 0
        self._cancel: CancelToken | None = None

    # ---------- state ----------

    def _set_state(self, state: str, reason_fr: str | None = None) -> None:
        with self._lock:
            self.state, self.reason_fr = state, reason_fr
        get_journal().emit("session_state", {"state": state, "reason_fr": reason_fr})

    def emit_initial(self) -> None:
        get_journal().emit("session_state", {"state": self.state, "reason_fr": self.reason_fr})
        self._emit_architecture()

    def _emit_architecture(self) -> None:
        get_journal().emit(
            "architecture_changed", {"nodes": [_CORE_HARNESS, _CORE_MODEL], "edges": []}
        )

    def _error(self, message_fr: str, exc: BaseException | str, effect_fr: str) -> None:
        cause = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
        get_journal().emit(
            "harness_error", {"message_fr": message_fr, "cause": cause, "effect_fr": effect_fr}
        )

    def join(self) -> None:
        """Wait until the worker has run everything submitted so far."""
        self._executor.submit(lambda: None).result()

    def close(self) -> None:
        self.stop()
        self._executor.shutdown(wait=True, cancel_futures=True)
        if self._engine is not None:
            self._engine.close()
            self._engine = None

    # ---------- model load ----------

    def boot(self, model_path: str | None) -> Future[None]:
        """Load `model_path` on the worker thread: `model_load` → `idle`, then `context_preview`."""
        return self._executor.submit(self._boot, model_path)

    def _boot(self, model_path: str | None) -> None:
        if model_path is None:
            self._set_state("idle", _SERVER_ONLY_FR)
            self._emit_architecture()
            return
        try:
            self._set_state("model_load", f"Chargement du modèle {Path(model_path).name}…")
            self._emit_architecture()
            if self._engine is not None:
                self._engine.close()
                self._engine = None
            engine = self._engine_factory(model_path, n_ctx=self.cfg.context_window)
            caps = capabilities_for(engine.metadata())
            if caps.incompatible_reason:
                engine.close()
                self._error(
                    "Modèle incompatible.", caps.incompatible_reason, "Aucun tour possible."
                )
                self._set_state("idle", caps.incompatible_reason)
                return
            self._engine, self._caps = engine, caps
            self._window = effective_window(self.cfg.context_window, caps.native_context)
            self._labels = self._load_labels()
        except Exception as exc:  # noqa: BLE001 - AD-16
            self._error("Le modèle n'a pas pu être chargé.", exc, "Aucun tour possible.")
            self._set_state("idle", _LOAD_FAILED_FR)
            return
        self._set_state("idle")
        self._emit_preview()

    def _load_labels(self) -> SegmentLabels:
        try:
            return load_labels()
        except Exception as exc:  # noqa: BLE001 - AD-19: invalid content is traced, not fatal
            self._error(
                "Le fichier des libellés de segments est invalide.",
                exc,
                "Les types de segment s'affichent sous leur nom technique.",
            )
            return SegmentLabels(kinds={k: k.value for k in SegmentKind}, groups={})

    # ---------- rendering ----------

    def _render(self, message: str, call_id: str | None) -> tuple[RenderedContext, dict[str, Any]]:
        assert self._engine is not None and self._caps is not None and self._labels is not None
        meta = self._engine.metadata()
        template_vars: dict[str, Any] = {}
        if self._caps.reasoning_variable:
            template_vars[self._caps.reasoning_variable] = False  # no reasoning brick yet
        rendered = render_context(
            self._engine,
            self._caps.chat_template or "",
            [{"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, message)]}],
            call_id=call_id,
            special_tokens=meta.special_tokens,
            bos_token=meta.bos_token,
            eos_token=meta.eos_token,
            add_generation_prompt=True,
            **template_vars,
        )
        payload = gauge(
            rendered.segments,
            window=self._window,
            reserve=OUTPUT_RESERVE,
            near_limit_ratio=self.cfg.near_limit_ratio,
            labels=self._labels,
        )
        return rendered, payload

    def _emit_preview(self) -> None:
        """AD-9: the next-turn gauge, rendered without any message."""
        try:
            _, payload = self._render("", None)
        except Exception as exc:  # noqa: BLE001 - AD-16
            self._error(
                "L'aperçu du contexte n'a pas pu être calculé.",
                exc,
                "La jauge reste vide jusqu'au premier tour.",
            )
            return
        get_journal().emit("context_preview", payload)

    # ---------- intentions ----------

    def send(self, message: str) -> str:
        """Intention class (b): refused outside `idle`, with the reason."""
        with self._lock:
            if self.state != "idle" or self._engine is None or self.reason_fr:
                raise SendRefused(self._refusal_reason())
            self._turns += 1
            turn_id = f"t{self._turns}"
            cancel = self._cancel = CancelToken()
            # Switched under the lock, so a second `send` racing this one is refused.
            self.state, self.reason_fr = (
                "turn",
                "Un tour est en cours : attendez sa fin ou arrêtez-le.",
            )
        get_journal().emit("session_state", {"state": self.state, "reason_fr": self.reason_fr})
        self._executor.submit(self._run_turn, turn_id, message, cancel)
        return turn_id

    def _refusal_reason(self) -> str:
        if self.state == "turn":
            return "Un tour est déjà en cours : attendez sa fin ou cliquez sur « Arrêter »."
        if self.reason_fr:
            return self.reason_fr
        return "Aucun modèle n'est chargé : terminez le diagnostic de démarrage."

    def stop(self) -> bool:
        """Intention class (c): arms the turn's `CancelToken`; no effect outside a turn."""
        with self._lock:
            if self.state != "turn" or self._cancel is None:
                return False
            self._cancel.cancel()
            return True

    # ---------- turn ----------

    def _run_turn(self, turn_id: str, message: str, cancel: CancelToken) -> None:
        started = time.monotonic()
        status = "error"
        journal = get_journal()
        with scoped(turn_id=turn_id, context_id="main", trigger="user"):
            try:
                journal.emit("turn_started", {"replay_of": None, "message": message}, actor="user")
                status = self._turn(turn_id, message, cancel)
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(
                    "Le tour s'est interrompu sur une erreur.",
                    exc,
                    "Le tour est terminé ; WaveStack reste utilisable.",
                )
            finally:
                journal.emit(
                    "turn_ended",
                    {"status": status, "duration_ms": _ms(time.monotonic() - started)},
                )
                with self._lock:
                    self._cancel = None
                self._set_state("idle")

    def _turn(self, turn_id: str, message: str, cancel: CancelToken) -> str:
        call_id = f"{turn_id}.main.c1"
        with scoped(call_id=call_id, step_id=f"{turn_id}.main.s1", component="core.model"):
            rendered, payload = self._render(message, call_id)
            get_journal().emit("context_rendered", payload)
            if payload["overflow"]:
                self._emit_overflow(payload)
                return "overflow"
            return self._call_model(rendered, cancel)

    def _emit_overflow(self, payload: dict[str, Any]) -> None:
        used, usable = payload["used"], payload["usable"]
        get_journal().emit(
            "context_overflow",
            {
                "used": used,
                "usable": usable,
                "message_fr": (
                    f"Le contexte compte {_fr(used)} tokens pour {_fr(usable)} utilisables "
                    f"(fenêtre de {_fr(payload['window'])} moins {_fr(payload['reserve'])} "
                    f"réservés à la réponse). Cause : le message à lui seul est trop long. "
                    f"Pour continuer la démo : raccourcissez le message et renvoyez-le."
                ),
                "strategies_fr": _OVERFLOW_STRATEGIES_FR,
            },
        )

    def _call_model(self, rendered: RenderedContext, cancel: CancelToken) -> str:
        assert self._engine is not None and self._caps is not None
        journal = get_journal()
        started = time.monotonic()
        journal.emit(
            "model_call_started",
            {"phase_label": f"Lecture du contexte ({_fr(len(rendered.ids))} tokens)"},
        )
        tags = self._caps.reasoning_tags
        splitter = ChannelSplitter(
            tags, in_reasoning=bool(tags) and rendered.prompt.rstrip().endswith(tags[0])
        )
        raw: list[str] = []
        channels: dict[str, list[str]] = {"reasoning": [], "text": []}
        pending: list[tuple[str, str]] = []
        first_at: float | None = None
        last_flush = started
        output_tokens = 0
        stop_reason = "stop"

        def flush() -> None:
            nonlocal last_flush
            while pending:
                channel = pending[0][0]
                text = ""
                while pending and pending[0][0] == channel:
                    text += pending.pop(0)[1]
                journal.emit("model_delta", {"channel": channel, "text": text}, actor="model")
            last_flush = time.monotonic()

        def take(parts: list[tuple[str, str]]) -> None:
            for channel, text in parts:
                channels[channel].append(text)
                pending.append((channel, text))

        def end(reason: str) -> None:
            ended = time.monotonic()
            first = first_at or ended
            journal.emit(
                "model_call_ended",
                {
                    "raw_output": "".join(raw),
                    "reasoning": "".join(channels["reasoning"]),
                    "text": "".join(channels["text"]),
                    "tool_calls": [],
                    "prompt_tokens": len(rendered.ids),
                    "output_tokens": output_tokens,
                    "prompt_ms": _ms(first - started),
                    "gen_ms": _ms(ended - first),
                    "stop_reason": reason,
                    "duration_ms": _ms(ended - started),
                },
                actor="model",
            )

        try:
            for fragment in self._engine.complete(
                rendered.ids, self._caps.stop_sequences, OUTPUT_RESERVE, cancel
            ):
                output_tokens = fragment.output_tokens
                if first_at is None and output_tokens:
                    first_at = time.monotonic()
                    journal.emit("model_first_token", {}, actor="model")
                raw.append(fragment.text)
                take(splitter.feed(fragment.text))
                if fragment.stop_reason:
                    stop_reason = fragment.stop_reason
                if pending and time.monotonic() - last_flush >= DELTA_INTERVAL_S:
                    flush()
            take(splitter.flush())
            flush()
        except Exception:
            flush()
            end("error")
            raise
        end(stop_reason)

        if stop_reason == "length":
            journal.emit(
                "output_truncated",
                {
                    "channel": splitter.channel,
                    "output_tokens": output_tokens,
                    "max_tokens": OUTPUT_RESERVE,
                },
            )
            return "limit"
        return "cancelled" if stop_reason == "cancelled" else "completed"
