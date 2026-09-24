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

import httpx
import psutil

from wavestack import config
from wavestack.models import discovery, probe
from wavestack.net.factory import create_client
from wavestack.net.guard import NetworkBlocked
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


class DiagnosticSession:
    """The only session that exists while WaveStack has no confirmed model."""

    def __init__(self, cfg: config.Config, port: int) -> None:
        self.cfg = cfg
        self.port = port
        self.selected_model_path: str | None = cfg.selected_model
        self.booted_path: str | None = None  # set once a file is handed out for loading
        self.state = "diagnostic"
        self.last_result: DiagnosticResult | None = None
        self._lock = threading.Lock()
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
        saved = self.selected_model_path
        candidates = self._discover(saved)
        notice_fr = ""
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
        loaded = self.booted_path is not None
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

        self.selected_model_path = chosen.path
        saved = self._persist(lambda: config.save_setting("selected_model", chosen.path))
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

    def boot_finished(self, loaded: bool) -> None:
        """A load that failed frees the choice: the next `select_model` loads again."""
        if not loaded:
            with self._lock:
                self.booted_path = None

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
