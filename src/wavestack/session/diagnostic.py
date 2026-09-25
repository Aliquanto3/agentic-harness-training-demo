"""Minimal diagnostic session (AD-3).

Before a model is confirmed usable, WaveStack has exactly one session state:
`diagnostic`. It only handles the `select_model` intention. Later stories add
the other states (`idle`, `turn`, ...); this module is not to be pre-built
for them.

Startup rule (story 1b): the saved `selected_model` if still usable; else the
only usable file; with several, block until the user picks one. Once a file is
handed out for loading, a new choice is only saved for the next launch (AD-21:
no hot model switch before palier 2).
"""

from __future__ import annotations

import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import psutil
from pydantic import SecretStr

from wavestack import config
from wavestack.cloud import (
    CloudContent,
    chat_fields,
    disclosure,
    fill,
    load_cloud_content,
    warning_fr,
)
from wavestack.config import CloudModel
from wavestack.context.render import render_chat_body
from wavestack.context.segments import Part, SegmentKind
from wavestack.models import discovery, probe
from wavestack.models.engine import CancelToken
from wavestack.models.openai_chat import ChatBody, OpenAIChatEngine, ProviderError, run_call
from wavestack.net.factory import create_client
from wavestack.net.guard import NetworkBlocked
from wavestack.session.effects import ApiKeySet, SettingWrite, apply_setting
from wavestack.tools.parser import tool_call_id
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import scoped

# ponytail: fixed threshold, revisit once AD-8's measured memory budget lands
MEMORY_WARN_MB = 1024
NETWORK_CHECK_TIMEOUT = 3.0
PROBE_TIMEOUT_S = 120
SEARCHED_SOURCES_FR = (
    "dossier de modèles WaveStack, Ollama, LM Studio, cache Hugging Face, serveur local"
)


@dataclass
class DiagnosticResult:
    ready: bool
    blocking_checks: list[str] = field(default_factory=list)
    candidates: list[discovery.ModelCandidate] = field(default_factory=list)
    model_path: str | None = None  # the file the caller must load now, if any
    saved: bool = False  # `select_model`: the choice was recorded in settings.json
    message_fr: str | None = None  # `select_model`: the outcome, in French
    cloud_model: CloudModel | None = None  # the cloud model the caller must boot now, if any


class Refused(Exception):
    """A diagnostic intention refused with its French reason; nothing was written."""

    def __init__(self, reason_fr: str) -> None:
        super().__init__(reason_fr)
        self.reason_fr = reason_fr


CloudFactory = Callable[[CloudModel, SecretStr], OpenAIChatEngine]


class DiagnosticSession:
    """The only session that exists while WaveStack has no confirmed model."""

    def __init__(
        self, cfg: config.Config, port: int, cloud_factory: CloudFactory | None = None
    ) -> None:
        self.cfg = cfg
        self.port = port
        selected = cfg.selected_model or {}
        self.selected_model_path: str | None = (
            selected["ref"] if selected.get("kind") == "file" else None
        )
        self.selected_cloud: str | None = (
            selected["ref"] if selected.get("kind") == "cloud" else None
        )
        self.booted_path: str | None = None  # set once a file is handed out for loading
        self.booted_cloud: str | None = None  # set once a cloud model is handed out
        self.state = "diagnostic"
        self.last_result: DiagnosticResult | None = None
        self._lock = threading.Lock()
        self._tests = 0  # « Tester » runs, for their `diag.{n}` ids (AD-21)
        self._cloud_factory = cloud_factory or (
            lambda entry, key: OpenAIChatEngine(
                entry,
                key,
                connect_timeout_s=cfg.cloud_connect_timeout_s,
                read_timeout_s=cfg.cloud_read_timeout_s,
            )
        )
        self._emit_state("Diagnostic de démarrage en cours.")

    def _emit_state(self, reason_fr: str) -> None:
        get_journal().emit("session_state", {"state": self.state, "reason_fr": reason_fr})

    def _emit_check(
        self,
        check: str,
        status: str,
        message_fr: str,
        action_fr: str | None = None,
        *,
        blocking: bool,
    ) -> None:
        get_journal().emit(
            "diagnostic_check",
            {
                "check": check,
                "status": status,
                "message_fr": message_fr,
                "action_fr": action_fr,
                "blocking": blocking,
            },
        )

    def check_memory(self) -> None:
        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        if available_mb < MEMORY_WARN_MB:
            self._emit_check(
                "memory",
                "warn",
                f"Mémoire disponible faible : {available_mb:.0f} Mo.",
                "Fermez des applications avant de continuer.",
                blocking=False,
            )
        else:
            self._emit_check(
                "memory", "ok", f"Mémoire disponible : {available_mb:.0f} Mo.", blocking=False
            )

    def check_port(self) -> None:
        self._emit_check("port", "ok", f"Port {self.port} réservé pour WaveStack.", blocking=False)

    def check_network(self) -> None:
        with scoped(origin="diagnostic"):
            client = create_client(timeout=NETWORK_CHECK_TIMEOUT)
            try:
                client.head(f"https://{self.cfg.connectivity_probe_host}")
            except (httpx.HTTPError, NetworkBlocked):
                # AD-16: no exception crosses the session boundary. A host
                # refused by the guard (e.g. outside the allow-list in tests)
                # is reported exactly like an unreachable one.
                self._emit_check(
                    "network",
                    "warn",
                    "Accès réseau indisponible.",
                    "Les briques hors ligne restent utilisables sans réseau.",
                    blocking=False,
                )
            else:
                self._emit_check("network", "ok", "Accès réseau disponible.", blocking=False)
            finally:
                client.close()

    def _probe_candidate(self, candidate: discovery.ModelCandidate) -> None:
        assert candidate.path is not None
        proc = None
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "wavestack.models.probe", candidate.path],
                capture_output=True,
                text=True,
                timeout=PROBE_TIMEOUT_S,
            )
            last_line = proc.stdout.strip().splitlines()[-1]
            result = probe.ProbeResult.model_validate_json(last_line)
        except Exception as exc:  # noqa: BLE001 - any probe failure marks the file incompatible
            # Only a native crash of the load says something about the file. Exit code 1 is
            # a Python error (config, guard...); no process or a timeout, the environment.
            if proc is not None and proc.returncode not in (0, 1):
                self._persist(
                    lambda: probe.record_failure(
                        candidate.path, "La sonde n'a pas pu confirmer ce fichier."
                    )
                )
            get_journal().emit(
                "harness_error",
                {
                    "message_fr": f"La sonde du modèle a échoué pour {candidate.path}.",
                    "cause": str(exc),
                    "effect_fr": "Le fichier est marqué incompatible.",
                },
            )
            candidate.status = "incompatible"
            candidate.reason = "La sonde n'a pas pu confirmer ce fichier."
            return

        if result.ok:
            candidate.architecture = result.architecture
            self._persist(lambda: probe.record_success(result))
            return

        get_journal().emit(
            "harness_error",
            {
                "message_fr": f"Modèle incompatible : {result.reason}",
                "cause": result.reason,
                "effect_fr": "Le fichier est marqué incompatible.",
            },
        )
        candidate.status = "incompatible"
        candidate.reason = result.reason
        self._persist(
            lambda: probe.record_failure(
                candidate.path, result.reason or "La sonde n'a pas pu confirmer ce fichier."
            )
        )

    def _persist(self, write: Callable[[], None]) -> bool:
        """AD-16: a settings.json write failure is traced, never fatal. True if written."""
        try:
            write()
            return True
        except OSError as exc:
            get_journal().emit(
                "harness_error",
                {
                    "message_fr": "Impossible d'écrire le fichier de réglages settings.json.",
                    "cause": str(exc),
                    "effect_fr": "Le diagnostic continue ; ce réglage ne sera pas mémorisé.",
                },
            )
            return False

    def _handle_unexpected(self, exc: Exception) -> DiagnosticResult:
        """AD-16: no exception crosses the session boundary, not even an unforeseen one."""
        get_journal().emit(
            "harness_error",
            {
                "message_fr": "Une erreur inattendue a interrompu le diagnostic.",
                "cause": str(exc),
                "effect_fr": "Le contrôle est marqué en échec, non bloquant.",
            },
        )
        self._emit_check(
            "model",
            "fail",
            "Le diagnostic du modèle a échoué de façon inattendue.",
            "Réessayez, ou signalez le problème si cela persiste.",
            blocking=False,
        )
        self.last_result = DiagnosticResult(ready=False, candidates=[])
        return self.last_result

    def check_model(self) -> DiagnosticResult:
        with self._lock:
            try:
                return self._check_model_locked()
            except Exception as exc:  # noqa: BLE001 - AD-16: never let the thread die silently
                return self._handle_unexpected(exc)

    def _discover(
        self, explicit_path: str | None, probe_only: set[str] | None = None
    ) -> list[discovery.ModelCandidate]:
        """Every candidate, architecture from the probe cache. Unprobed files are probed
        in a child process, all of them or only those in `probe_only`."""
        candidates = discovery.discover(explicit_path)
        for candidate in candidates:
            if candidate.status != "found" or not candidate.path:
                continue
            entry = probe.probed_entry(candidate.path)
            if entry is not None:
                candidate.architecture = entry.get("architecture")
            elif (failed := probe.failed_entry(candidate.path)) is not None:
                # Remembered failure: no reprobe, same reason.
                candidate.status, candidate.reason = "incompatible", failed.get("reason")
            elif probe_only is None or candidate.path in probe_only:
                self._probe_candidate(candidate)
        return candidates

    def _hand_out(
        self,
        chosen: discovery.ModelCandidate,
        candidates: list[discovery.ModelCandidate],
        notice_fr: str = "",
    ) -> DiagnosticResult:
        """`chosen` is the file to load now; from here on, choices wait for the next launch."""
        self.booted_path = chosen.path
        self._emit_check(
            "model",
            "warn" if notice_fr else "ok",
            f"{notice_fr}Modèle retenu : {chosen.name} ({chosen.path}).",
            blocking=False,
        )
        self.last_result = DiagnosticResult(
            ready=True, candidates=candidates, model_path=chosen.path
        )
        return self.last_result

    def _check_model_locked(self) -> DiagnosticResult:
        for error_fr in self.cfg.cloud_models[1]:  # AD-20: left out, never blocking
            self._emit_check("cloud", "warn", error_fr, blocking=False)
        saved = self.selected_model_path
        candidates = self._discover(saved)
        notice_fr = ""
        if self.selected_cloud:
            entry = self.cfg.cloud_model(self.selected_cloud)
            reason = self._cloud_refusal(entry, self.selected_cloud)
            if entry is not None and reason is None:  # AD-21: no request, no new warning
                self.booted_cloud = entry.id
                self._emit_check(
                    "model",
                    "ok",
                    f"Modèle retenu : {entry.model} chez {entry.provider} (modèle cloud, choisi "
                    "lors d'un lancement précédent).",
                    blocking=False,
                )
                self.last_result = DiagnosticResult(
                    ready=True, candidates=candidates, cloud_model=entry
                )
                return self.last_result
            notice_fr = f"Le modèle cloud enregistré n'est plus utilisable : {reason} "
        if saved:
            chosen = _usable(candidates, saved)
            if chosen:
                return self._hand_out(chosen, candidates)
            notice_fr = f"Le modèle enregistré n'est plus utilisable : {saved}. "

        files = [c for c in candidates if c.status == "found" and c.path]
        distinct = {c.path for c in files}  # several Ollama tags may share one blob
        if len(distinct) == 1:
            return self._hand_out(files[0], candidates, notice_fr)
        if len(distinct) > 1:
            self._emit_check(
                "model",
                "warn",
                f"{notice_fr}Plusieurs modèles trouvés : choisissez-en un.",
                "Cliquez sur « Choisir » en face d'un modèle, ou indiquez le chemin d'un "
                "fichier GGUF.",
                blocking=True,
            )
            self.last_result = DiagnosticResult(
                ready=False, blocking_checks=["model"], candidates=candidates
            )
            return self.last_result

        servers = [c for c in candidates if c.status == "server"]
        if servers:
            self._emit_check(
                "model",
                "warn" if notice_fr else "ok",
                f"{notice_fr}Serveur local trouvé : {servers[0].server_url}.",
                blocking=False,
            )
            self.last_result = DiagnosticResult(ready=True, candidates=candidates)
            return self.last_result

        if candidates:
            details = "; ".join(
                f"{c.source} ({c.path or c.server_url or '?'}) : {c.reason or c.status}"
                for c in candidates
            )
        else:
            details = "aucun candidat trouvé dans ces emplacements"
        self._emit_check(
            "model",
            "fail",
            f"{notice_fr}Aucun modèle utilisable trouvé. Emplacements recherchés : "
            f"{SEARCHED_SOURCES_FR}.",
            f"{details}. Indiquez le chemin d'un fichier GGUF ou copiez-en un dans le "
            f"dossier de modèles.",
            blocking=True,
        )
        self.last_result = DiagnosticResult(
            ready=False, blocking_checks=["model"], candidates=candidates
        )
        return self.last_result

    def select_model(self, path: str) -> DiagnosticResult:
        """Intention `select_model` (AD-3, class a): exactly this file, or its reason."""
        with self._lock:
            try:
                return self._select_model_locked(_normalize(path))
            except Exception as exc:  # noqa: BLE001 - AD-16: never let the thread die silently
                return self._handle_unexpected(exc)

    def _select_model_locked(self, path: str) -> DiagnosticResult:
        # Probe only the chosen file, and none once a model is loaded: a probe loads full
        # weights, next to the loaded model's. The next launch's probe decides then.
        loaded = self.booted_path is not None or self.booted_cloud is not None
        candidates = self._discover(path, probe_only=set() if loaded else {path})
        previous = self.last_result or DiagnosticResult(ready=False, blocking_checks=["model"])
        known = {c.path: c for c in previous.candidates if c.status == "incompatible"}
        for candidate in candidates:  # keep earlier probe failures of the unprobed others
            if candidate.path != path and candidate.path in known:
                candidate.status, candidate.reason = "incompatible", known[candidate.path].reason
        chosen = _usable(candidates, path)
        if chosen is None:
            listed = next((c for c in candidates if c.path == path), None)
            reason = (listed.reason if listed else None) or "Fichier introuvable."
            # Nothing saved, nothing loaded: the diagnostic stays as it was.
            self.last_result = DiagnosticResult(
                ready=previous.ready,
                blocking_checks=previous.blocking_checks,
                candidates=candidates,
                message_fr=f"Modèle non retenu ({path}) : {reason}",
            )
            return self.last_result

        self.selected_model_path, self.selected_cloud = chosen.path, None
        saved = self._save_choice("file", chosen.path)
        if not loaded:
            result = self._hand_out(chosen, candidates)
            result.saved = saved
            result.message_fr = f"Modèle choisi : {chosen.name}. Chargement en cours." + (
                "" if saved else " Ce choix n'a pas pu être mémorisé pour les prochains lancements."
            )
            return result
        self.last_result = DiagnosticResult(
            ready=previous.ready,
            blocking_checks=previous.blocking_checks,
            candidates=candidates,
            saved=saved,
            message_fr=(
                f"Choix enregistré : {chosen.name}, pris en compte au prochain lancement."
                if saved
                else f"Choix non enregistré ({chosen.name}) : settings.json n'a pas pu être écrit."
            ),
        )
        return self.last_result

    def _save_choice(self, kind: str, ref: str) -> bool:
        """AD-20: `selected_model = {kind, ref}`, by the single applier (AD-23)."""
        value = {"kind": kind, "ref": ref}
        return self._persist(lambda: apply_setting(SettingWrite(key="selected_model", value=value)))

    def hand_to(self, app_session: Any, result: DiagnosticResult, *, launch: bool = False) -> None:
        """Boot the model `result` hands out on `app_session`: the cloud model, else the file.
        At launch (`launch`), a ready result without file still boots (a server only), so the
        session leaves `diagnostic` with its reason. The same path for the cli and the web."""
        if result.cloud_model is not None:
            future = app_session.boot_cloud(result.cloud_model)
        elif result.model_path or (launch and result.ready):
            future = app_session.boot(result.model_path)
        else:
            return
        future.add_done_callback(lambda _: self.boot_finished(app_session.model_loaded))

    def boot_finished(self, loaded: bool) -> None:
        """A load that failed frees the choice: the next `select_model` loads again."""
        if not loaded:
            with self._lock:
                self.booted_path = self.booted_cloud = None

    # ---------- cloud models (story 11, AD-20, AD-21) ----------

    def _cloud_refusal(self, entry: CloudModel | None, model_id: str) -> str | None:
        """Why `entry` can be neither tested nor chosen, in French; `None` when it can."""
        if entry is None:
            return f"le modèle cloud « {model_id} » n'est pas déclaré (ou est désactivé)."
        if config.cloud_key(entry) is None:
            content = self._cloud_content()
            if config.api_key_host_changed(entry):
                return content.host_changed_fr if content else "Clé à ressaisir."
            return fill(content.no_key_fr, entry, content) if content else "Clé absente."
        return config.cloud_unavailable_fr(entry)

    def _cloud_content(self) -> CloudContent | None:
        try:
            return load_cloud_content()
        except Exception as exc:  # noqa: BLE001 - AD-19: traced, never fatal
            get_journal().emit(
                "harness_error",
                {
                    "message_fr": "Le fichier content/cloud.yaml est absent ou invalide.",
                    "cause": str(exc),
                    "effect_fr": "Les modèles cloud s'affichent sans leurs textes.",
                },
            )
            return None

    def cloud_rows(self) -> dict[str, object]:
        """`/api/diagnostic`: each declared cloud model, its key state (never the key), why
        its buttons are disabled, its mentions and the warning's text; and the common texts."""
        content = self._cloud_content()
        rows = []
        for entry in self.cfg.cloud_models[0]:
            reason = self._cloud_refusal(entry, entry.id)
            rows.append(
                {
                    "id": entry.id,
                    "provider": entry.provider,
                    "model": entry.model,
                    "host": entry.host,
                    "disclosure": disclosure(entry),
                    "training_fr": (
                        content.training_fr.get(entry.training, entry.training)
                        if content
                        else entry.training
                    ),
                    "key_set": config.cloud_key(entry) is not None,
                    "disabled_fr": reason,
                    "selected": entry.id == self.selected_cloud,
                    "loaded": entry.id == self.booted_cloud,
                    "test_hint_fr": fill(content.test_hint_fr, entry, content) if content else "",
                    "warning": warning_fr(entry, content) if content else None,
                }
            )
        return {"models": rows, "key_hint_fr": content.key_hint_fr if content else ""}

    def select_cloud(self, model_id: str, acknowledged: bool) -> DiagnosticResult:
        """Intention `select_model{kind: cloud}` (AD-21): refused without the warning's
        confirmation or a usable key, nothing written then (`Refused`). Before any model is
        loaded, the caller boots it; after, it is saved for the next launch."""
        with self._lock:
            entry = self.cfg.cloud_model(model_id)
            if entry is not None and not acknowledged:
                raise Refused(
                    "Choix refusé : avertissement non confirmé. Lisez l'avertissement, puis "
                    "cliquez sur « Utiliser ce modèle »."
                )
            reason = self._cloud_refusal(entry, model_id)
            if entry is None or reason is not None:
                raise Refused(f"Choix refusé : {reason}")
            loaded = self.booted_path is not None or self.booted_cloud is not None
            self.selected_cloud, self.selected_model_path = entry.id, None
            saved = self._save_choice("cloud", entry.id)
            previous = self.last_result or DiagnosticResult(ready=False)
            label = f"{entry.model} chez {entry.provider}"
            if not loaded:
                self.booted_cloud = entry.id
                self._emit_check(
                    "model", "ok", f"Modèle retenu : {label} (modèle cloud).", blocking=False
                )
                self.last_result = DiagnosticResult(
                    ready=True,
                    candidates=previous.candidates,
                    saved=saved,
                    cloud_model=entry,
                    message_fr=f"Modèle choisi : {label}. Préparation en cours."
                    + ("" if saved else " Ce choix n'a pas pu être mémorisé."),
                )
                return self.last_result
            self.last_result = DiagnosticResult(
                ready=previous.ready,
                blocking_checks=previous.blocking_checks,
                candidates=previous.candidates,
                saved=saved,
                message_fr=(
                    f"Prochain lancement : {label}. Le changement de modèle à chaud n'existe "
                    "pas encore."
                    if saved
                    else f"Choix non enregistré ({label}) : settings.json n'a pas pu être écrit."
                ),
            )
            return self.last_result

    def set_api_key(self, model_id: str, key: SecretStr) -> dict[str, object]:
        """Intention `set_api_key` (AD-20): saved with the host declared now, by the single
        applier. The answer never carries what it received (AD-15)."""
        entry = self.cfg.cloud_model(model_id)
        if entry is None:
            raise Refused(f"Le modèle cloud « {model_id} » n'est pas déclaré (ou est désactivé).")
        if not key.get_secret_value().strip():
            raise Refused("Clé vide : collez la clé API fournie par la console du fournisseur.")
        key = SecretStr(key.get_secret_value().strip())
        effect = ApiKeySet(id=entry.id, host=entry.host, key=key)
        try:
            apply_setting(effect)
        except OSError as exc:
            raise Refused(
                f"La clé n'a pas pu être enregistrée ({config.api_keys_path()}) : "
                f"{exc.strerror or type(exc).__name__}."
            ) from None
        return {
            "key_set": True,
            "message_fr": f"Clé enregistrée pour {entry.provider}. Cliquez sur « Tester ».",
        }

    def test_cloud_model(self, model_id: str) -> dict[str, object]:
        """Intention `test_cloud_model` (AD-21): the fixed prompt and tool of `content/`, the
        model's real body, two calls at most, scope `diag`, `origin = model`. Emits the
        `model_call_*` events, then `diagnostic_check{check: cloud_test}`. Never trains the
        estimate ratio (the application session's own)."""
        entry = self.cfg.cloud_model(model_id)
        reason = self._cloud_refusal(entry, model_id)
        content = self._cloud_content()
        if entry is None or reason is not None:
            raise Refused(f"Test refusé : {reason}")
        if content is None:
            raise Refused("Test impossible : le fichier content/cloud.yaml est invalide.")
        key = config.cloud_key(entry)
        assert key is not None
        with self._lock:
            self._tests += 1
            n = self._tests
        test = content.test
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, test.prompt)]}
        ]
        tools = (
            [
                {
                    "type": "function",
                    "function": {
                        "name": test.tool.name,
                        "description": test.tool.description,
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]
            if entry.tools
            else None
        )
        engine = self._cloud_factory(entry, key)
        answer, tool_call, tps = "", None, None
        try:
            for k in (1, 2):
                step_id = f"diag.{n}.s{k}"
                scope = {
                    "turn_id": None,
                    "context_id": "diag",
                    "call_id": f"diag.{n}.c{k}",
                    "step_id": step_id,
                    "component": "core.model",
                    "origin": "model",
                }
                with scoped(**scope):
                    rendered = render_chat_body(
                        messages,
                        tools,
                        call_id=scope["call_id"],
                        fields=chat_fields(entry, entry.reserve),
                        markers=self.cfg.cloud_markers,
                        estimate=lambda t: config.estimate_tokens(t, self.cfg.chars_per_token),
                        provider_label_fr=content.provider_segment_fr,
                    )
                    out = run_call(
                        engine,
                        ChatBody(rendered.body.encode("utf-8")),
                        CancelToken(),
                        phase_label=f"Test de {entry.model} chez {entry.provider}",
                        estimated_prompt=rendered.raw_total,
                        chars_per_token=self.cfg.chars_per_token,
                        call_id=lambda i, s=step_id: tool_call_id(s, i),
                    )
                tps = out.output_tps if out.output_tps is not None else tps
                if k == 1 and out.calls and all("id" in c for c in out.calls):
                    call = out.calls[0]
                    tool_call = {"name": call["name"], "arguments": call["arguments"]}
                    assistant: dict[str, Any] = {"role": "assistant"}
                    if out.text:
                        assistant["content"] = [Part(SegmentKind.ASSISTANT_TURN, out.text)]
                    assistant["tool_calls"] = [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": call["name"], "arguments": call["arguments"]},
                        }
                    ]
                    reply = [Part(SegmentKind.TOOL_RESULT, test.tool_reply)]
                    messages += [
                        assistant,
                        {"role": "tool", "tool_call_id": call["id"], "content": reply},
                    ]
                    continue
                answer = out.text or out.reasoning
                break
        except ProviderError as error:
            self._emit_test(entry, "fail", f"Test en échec : {error.message_fr}", error.hints_fr)
            return {"ok": False, "message_fr": error.message_fr}
        finally:
            engine.close()
        rate = f", {tps} tokens/s" if tps is not None else ""
        if entry.tools and tool_call is None:
            message = (
                f"{entry.provider} répond{rate}, mais le modèle n'a pas appelé l'outil de test : "
                "l'appel d'outils risque d'échouer pendant la séance."
            )
            status = "warn"
        else:
            called = f" Appel d'outil reçu : {tool_call['name']}." if tool_call else ""
            message = f"Test réussi : {entry.provider} répond{rate}.{called}"
            status = "ok"
        self._emit_test(entry, status, message, [], answer=answer, tool_call=tool_call, tps=tps)
        return {"ok": status == "ok", "message_fr": message}

    def _emit_test(
        self,
        entry: CloudModel,
        status: str,
        message_fr: str,
        hints_fr: list[str],
        *,
        answer: str | None = None,
        tool_call: dict[str, object] | None = None,
        tps: int | None = None,
    ) -> None:
        get_journal().emit(
            "diagnostic_check",
            {
                "check": "cloud_test",
                "status": status,
                "message_fr": message_fr,
                "action_fr": " ".join(hints_fr) or None,
                "blocking": False,
                "model_id": entry.id,
                "answer": answer,
                "tool_call": tool_call,
                "output_tps": tps,
            },
        )

    def run(self) -> DiagnosticResult:
        """Run every diagnostic check once, in the order the story mandates."""
        try:
            self.check_memory()
            model_result = self.check_model()
            self.check_network()
            self.check_port()
            return model_result
        except Exception as exc:  # noqa: BLE001 - AD-16: never let the thread die silently
            return self._handle_unexpected(exc)


def _usable(
    candidates: list[discovery.ModelCandidate], path: str
) -> discovery.ModelCandidate | None:
    return next((c for c in candidates if c.path == path and c.status == "found"), None)


def _normalize(path: str) -> str:
    """A pasted path: surrounding quotes (Windows « Copier en tant que chemin d'accès »),
    `~`, relative. `absolute()`, not `resolve()`: a resolved symlink or junction (e.g. an
    OLLAMA_MODELS link) would no longer match the discovered candidate's path."""
    return str(Path(path.strip().strip('"').strip("'")).expanduser().absolute())
