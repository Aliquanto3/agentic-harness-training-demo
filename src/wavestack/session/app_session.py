"""The application session: single writer of state, one worker thread (AD-3, AD-24).

It loads the model found by the diagnostic, then runs turns: freeze a
`TurnState` (AD-17), render the prompt through the model's own template with
the effective bricks' segments, attribute its tokens, refuse an overflowing
call, stream the completion, and emit the counter and gauge figures. It alone
holds the bricks' `wanted`, the system prompt and the history (AD-3), and
computes availability in one place (AD-12). Nothing crosses its boundary as an
exception (AD-16).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

from wavestack import config
from wavestack.bricks.contract import (
    BrickContent,
    BrickDeclaration,
    load_brick_content,
    load_default_system_prompt,
)
from wavestack.bricks.registry import BRICKS, check_unique_ids
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
# The heaviest harness-controlled segment names the cause (message first on ties).
_OVERFLOW_CAUSES_FR = {
    SegmentKind.USER_MESSAGE: (
        "Cause : le message à lui seul est trop long. "
        "Pour continuer la démo : raccourcissez le message et renvoyez-le."
    ),
    SegmentKind.HISTORY: (
        "Cause : l'historique de la conversation occupe la plus grande part du contexte. "
        "Pour continuer la démo : videz la conversation ou raccourcissez le message."
    ),
    SegmentKind.SYSTEM_PROMPT: (
        "Cause : le prompt système occupe la plus grande part du contexte. "
        "Pour continuer la démo : raccourcissez le prompt système ou rétablissez le prompt "
        "par défaut."
    ),
}
_OVERFLOW_STRATEGIES_FR = [
    "Fenêtre glissante : ne garder que les échanges les plus récents.",
    "Compaction : résumer les anciens échanges en quelques lignes.",
    "Retrait des anciens résultats d'outils.",
    "Lazy loading : ne charger la documentation des outils qu'à la demande.",
]


class Exchange(NamedTuple):
    """One `completed` turn of the active branch, as stored for the history (AD-4, AD-17)."""

    turn_id: str
    user: str
    text: str
    reasoning: str


@dataclass(frozen=True)
class TurnState:
    """What a turn reads for all its calls, frozen at its start (AD-17)."""

    history: tuple[Exchange, ...]
    system_prompt: str
    effective: frozenset[str]  # brick ids, `wanted` and `available`


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
        bricks: list[BrickDeclaration] | None = None,
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
        # Bricks: in memory only, every launch starts as the bare LLM (no persistence).
        self._bricks = check_unique_ids(BRICKS if bricks is None else bricks)
        self._wanted: set[str] = set()
        self._history: list[Exchange] = []
        self._custom_prompt: str | None = None  # None: the default from content/
        self._content: dict[str, BrickContent] = {}
        self._content_errors: dict[str, str] = {}
        self._default_prompt = ""
        self._load_content()
        # Configuration frozen by the last `send`: `pending` is measured against it.
        self._sent: tuple[frozenset[str], str] = (frozenset(), self._default_prompt)

    # ---------- state ----------

    def _set_state(self, state: str, reason_fr: str | None = None) -> None:
        with self._lock:
            self.state, self.reason_fr = state, reason_fr
        get_journal().emit("session_state", {"state": state, "reason_fr": reason_fr})

    def emit_initial(self) -> None:
        get_journal().emit("session_state", {"state": self.state, "reason_fr": self.reason_fr})
        self._emit_architecture()
        self._emit_bricks()

    def _emit_architecture(self) -> None:
        """AD-12: a component is drawn as soon as its brick is `wanted`, even unavailable."""
        with self._lock:
            wanted = [b for b in self._bricks.values() if b.id in self._wanted]
        nodes: list[dict[str, Any]] = [_CORE_HARNESS, _CORE_MODEL]
        edges: list[dict[str, Any]] = []
        drawn = {n["id"] for n in nodes} | {c.id for b in wanted for c in b.components}
        for brick in wanted:
            available, reason_fr = self._availability(brick.id)
            for component in brick.components:
                hosting = "network" if component.hosting == "network_service" else "local"
                nodes.append(
                    {
                        "id": component.id,
                        "kind": "brick",
                        "hosting": hosting,
                        "label_fr": self._label(brick.id),
                        "wanted": True,
                        "available": available,
                        "reason_fr": reason_fr,
                    }
                )
                edges += [
                    {"from": component.id, "to": target, "crosses_boundary": hosting == "network"}
                    for target in component.edges_to
                    if target in drawn  # e.g. a `file.*` node not emitted yet
                ]
        get_journal().emit("architecture_changed", {"nodes": nodes, "edges": edges})

    def _pending_ids(self) -> set[str]:
        """Bricks whose effect on the next turn differs from what the last `send` froze."""
        with self._lock:
            sent_wanted, sent_prompt = self._sent
            pending = set(self._wanted) ^ sent_wanted
            prompt = self._custom_prompt or self._default_prompt
            if "system_prompt" in self._wanted and prompt != sent_prompt:
                pending.add("system_prompt")
        return pending

    def _emit_bricks(self) -> None:
        pending = self._pending_ids()
        with self._lock:
            wanted = set(self._wanted)
            custom = self._custom_prompt
        bricks = []
        for brick in self._bricks.values():
            available, reason_fr = self._availability(brick.id)
            content = self._content.get(brick.id)
            bricks.append(
                {
                    "id": brick.id,
                    "label_fr": self._label(brick.id),
                    "category": brick.category,
                    "category_fr": content.category_fr if content else brick.category,
                    "hosting_fr": content.hosting_fr if content else "",
                    "explanation_fr": content.explanation_fr if content else "",
                    "wanted": brick.id in wanted,
                    "available": available,
                    "reason_fr": reason_fr,
                    "pending": brick.id in pending,
                }
            )
        text = custom if custom is not None else self._default_prompt
        get_journal().emit(
            "bricks_changed",
            {
                "bricks": bricks,
                "system_prompt": {"text": text, "is_default": text == self._default_prompt},
            },
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
            self._emit_bricks()
            return
        try:
            self._set_state("model_load", f"Chargement du modèle {Path(model_path).name}…")
            self._emit_architecture()
            self._emit_bricks()
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
        self._emit_architecture()  # availability may depend on the loaded model's capabilities
        self._emit_bricks()
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

    def _load_content(self) -> None:
        """AD-19: an invalid file makes its brick unavailable with the reason, never a crash."""
        for brick_id in self._bricks:
            try:
                self._content[brick_id] = load_brick_content(brick_id)
            except Exception as exc:  # noqa: BLE001
                self._content_errors[brick_id] = (
                    f"Le fichier content/bricks/{brick_id}.yaml est absent ou invalide : "
                    "corrigez-le puis relancez WaveStack."
                )
                self._error(
                    f"L'explication de la brique « {brick_id} » est invalide.",
                    exc,
                    "La brique est indisponible ; le reste de WaveStack fonctionne.",
                )
        if "system_prompt" not in self._bricks:
            return
        try:
            self._default_prompt = load_default_system_prompt()
        except Exception as exc:  # noqa: BLE001
            self._content_errors["system_prompt"] = (
                "Le prompt système par défaut (content/prompts/system.md) est absent ou vide : "
                "corrigez-le puis relancez WaveStack."
            )
            self._error(
                "Le prompt système par défaut est illisible.",
                exc,
                "La brique « Prompt système » est indisponible ; le reste fonctionne.",
            )

    # ---------- bricks (AD-12) ----------

    def _label(self, brick_id: str) -> str:
        content = self._content.get(brick_id)
        return content.label_fr if content else brick_id

    def _availability(self, brick_id: str) -> tuple[bool, str | None]:
        """The single point computing `available` and its French reason (AD-12)."""
        brick = self._bricks.get(brick_id)
        if brick is None:
            return False, f"La brique « {brick_id} » n'existe pas dans cette version."
        with self._lock:
            wanted = set(self._wanted)
        for dep in brick.requires:
            if dep not in wanted or not self._availability(dep)[0]:
                return False, f"Nécessite la brique « {self._label(dep)} » : activez-la d'abord."
        missing = [c for c in brick.capabilities if not getattr(self._caps, c, None)]
        if missing:
            return False, (
                "Le modèle chargé n'offre pas ce dont la brique a besoin "
                f"({', '.join(missing)}) : choisissez un autre modèle."
            )
        if brick_id in self._content_errors:
            return False, self._content_errors[brick_id]
        return True, None

    def _effective(self) -> frozenset[str]:
        with self._lock:
            wanted = set(self._wanted)
        return frozenset(b for b in wanted if self._availability(b)[0])

    def build_turn_state(self, origin_turn: str | None = None) -> TurnState:
        """AD-17: the conversational snapshot (branch history) plus the current configuration.

        `origin_turn` (replay, story 9) keeps the branch up to, not including, that turn.
        """
        with self._lock:
            history = list(self._history)
            prompt = self._custom_prompt
        if origin_turn is not None:
            ids = [e.turn_id for e in history]
            history = history[: ids.index(origin_turn)] if origin_turn in ids else history
        return TurnState(
            history=tuple(history),
            system_prompt=prompt if prompt is not None else self._default_prompt,
            effective=self._effective(),
        )

    # ---------- rendering ----------

    @staticmethod
    def _messages(state: TurnState, message: str) -> list[dict[str, Any]]:
        """AD-4 slots: system message, history, then the turn's user message.

        Every brick off gives the bare LLM's single user message, byte for byte.
        """
        messages: list[dict[str, Any]] = []
        if "system_prompt" in state.effective:
            part = Part(
                SegmentKind.SYSTEM_PROMPT,
                state.system_prompt,
                "system_prompt",
                "system_prompt.prompt",
            )
            messages.append({"role": "system", "content": [part]})
        if "short_memory" in state.effective:
            for ex in state.history:
                memory = ("short_memory", "short_memory.history")
                messages.append(
                    {"role": "user", "content": [Part(SegmentKind.HISTORY, ex.user, *memory)]}
                )
                answer: dict[str, Any] = {
                    "role": "assistant",
                    "content": [Part(SegmentKind.HISTORY, ex.text, *memory)],
                }
                if ex.reasoning:
                    # ponytail: passed as a plain template variable, so a template that keeps
                    # past reasoning counts it as `template`; attribute it once one does.
                    answer["reasoning_content"] = ex.reasoning
                messages.append(answer)
        messages.append({"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, message)]})
        return messages

    def _render(
        self, state: TurnState, message: str, call_id: str | None
    ) -> tuple[RenderedContext, dict[str, Any]]:
        assert self._engine is not None and self._caps is not None and self._labels is not None
        meta = self._engine.metadata()
        template_vars: dict[str, Any] = {}
        if self._caps.reasoning_variable:
            template_vars[self._caps.reasoning_variable] = False  # no reasoning brick yet
        rendered = render_context(
            self._engine,
            self._caps.chat_template or "",
            self._messages(state, message),
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
        """AD-9: the next-turn gauge, rendered without any message. Runs on the worker."""
        if self._engine is None:
            return  # no model: nothing to preview
        try:
            _, payload = self._render(self.build_turn_state(), "", None)
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
        state = self.build_turn_state()  # frozen now: a later toggle waits for the next turn
        had_pending = bool(self._pending_ids())
        with self._lock:
            self._sent = (frozenset(self._wanted), self._custom_prompt or self._default_prompt)
        if had_pending:  # « Prend effet au prochain tour » is over for what this turn reads
            self._emit_bricks()
        self._executor.submit(self._run_turn, turn_id, message, cancel, state)
        return turn_id

    def set_brick(self, brick_id: str, wanted: bool) -> None:
        """Class (a): accepted at any time, effective from the next turn. `KeyError` if unknown."""
        if brick_id not in self._bricks:
            raise KeyError(brick_id)
        with self._lock:
            if (brick_id in self._wanted) == wanted:
                return
            if wanted:
                self._wanted.add(brick_id)
            else:
                self._wanted.discard(brick_id)
        self._emit_bricks()
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    def save_system_prompt(self, text: str | None) -> dict[str, Any]:
        """Class (a): `None` (or a blank text) restores the default. Returns the saved state."""
        text = (text or "").strip() or None
        with self._lock:
            self._custom_prompt = text
        self._emit_bricks()
        self._executor.submit(self._emit_preview)
        saved = text if text is not None else self._default_prompt
        return {"text": saved, "is_default": saved == self._default_prompt}

    def clear_conversation(self) -> None:
        """Class (b): empties the active branch; bricks and system prompt are untouched."""
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            self._history.clear()
        get_journal().emit("conversation_cleared", {})
        self._executor.submit(self._emit_preview)

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

    def _run_turn(self, turn_id: str, message: str, cancel: CancelToken, state: TurnState) -> None:
        started = time.monotonic()
        status = "error"
        journal = get_journal()
        with scoped(turn_id=turn_id, context_id="main", trigger="user"):
            try:
                journal.emit("turn_started", {"replay_of": None, "message": message}, actor="user")
                status, text, reasoning = self._turn(turn_id, message, cancel, state)
                if status == "completed":  # AD-17: recorded even with short memory off
                    with self._lock:
                        self._history.append(Exchange(turn_id, message, text, reasoning))
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

    def _turn(
        self, turn_id: str, message: str, cancel: CancelToken, state: TurnState
    ) -> tuple[str, str, str]:
        """Returns `(status, text, reasoning)`."""
        call_id = f"{turn_id}.main.c1"
        with scoped(call_id=call_id, step_id=f"{turn_id}.main.s1", component="core.model"):
            rendered, payload = self._render(state, message, call_id)
            get_journal().emit("context_rendered", payload)
            if payload["overflow"]:
                self._emit_overflow(payload)
                return "overflow", "", ""
            return self._call_model(rendered, cancel)

    def _emit_overflow(self, payload: dict[str, Any]) -> None:
        used, usable = payload["used"], payload["usable"]
        tokens = dict.fromkeys(_OVERFLOW_CAUSES_FR, 0)
        for segment in payload["segments"]:
            if segment["kind"] in tokens:
                tokens[segment["kind"]] += segment["tokens"]
        cause = _OVERFLOW_CAUSES_FR[max(tokens, key=tokens.__getitem__)]  # ties: the message
        get_journal().emit(
            "context_overflow",
            {
                "used": used,
                "usable": usable,
                "message_fr": (
                    f"Le contexte compte {_fr(used)} tokens pour {_fr(usable)} utilisables "
                    f"(fenêtre de {_fr(payload['window'])} moins {_fr(payload['reserve'])} "
                    f"réservés à la réponse). {cause}"
                ),
                "strategies_fr": _OVERFLOW_STRATEGIES_FR,
            },
        )

    def _call_model(self, rendered: RenderedContext, cancel: CancelToken) -> tuple[str, str, str]:
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
            return "limit", "", ""
        status = "cancelled" if stop_reason == "cancelled" else "completed"
        return status, "".join(channels["text"]), "".join(channels["reasoning"])
