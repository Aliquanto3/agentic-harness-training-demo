"""Minimal diagnostic session (AD-3).

Before a model is confirmed usable, WaveStack has exactly one session state:
`diagnostic`. It only handles the `select_model` intention. Later stories add
the other states (`idle`, `turn`, ...); this module is not to be pre-built
for them.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass, field

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


class DiagnosticSession:
    """The only session that exists while WaveStack has no confirmed model."""

    def __init__(self, cfg: config.Config, port: int) -> None:
        self.cfg = cfg
        self.port = port
        self.selected_model_path: str | None = None
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
            probe.record_success(result)
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

    def _check_model_locked(self) -> DiagnosticResult:
        candidates = discovery.discover(self.selected_model_path)

        for candidate in candidates:
            if (
                candidate.status == "found"
                and candidate.path
                and not probe.already_probed(candidate.path)
            ):
                self._probe_candidate(candidate)

        usable = [c for c in candidates if c.status in ("found", "server")]
        if not usable:
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
                f"Aucun modèle utilisable trouvé. Emplacements recherchés : {SEARCHED_SOURCES_FR}.",
                f"{details}. Indiquez le chemin d'un fichier GGUF ou copiez-en un dans le "
                f"dossier de modèles.",
                blocking=True,
            )
            self.last_result = DiagnosticResult(
                ready=False, blocking_checks=["model"], candidates=candidates
            )
            return self.last_result

        found = usable[0].path or usable[0].server_url
        self._emit_check("model", "ok", f"Modèle trouvé : {found}.", blocking=False)
        self.last_result = DiagnosticResult(ready=True, candidates=candidates)
        return self.last_result

    def select_model(self, path: str) -> DiagnosticResult:
        """Intention `select_model` (AD-3, class a): re-runs the model check with this path."""
        try:
            self.selected_model_path = path
            return self.check_model()
        except Exception as exc:  # noqa: BLE001 - AD-16: never let the thread die silently
            return self._handle_unexpected(exc)

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
