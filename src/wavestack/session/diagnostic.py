"""Minimal diagnostic session (AD-3).

Before a model is confirmed usable, WaveStack has exactly one session state:
`diagnostic`. It only handles the `select_model` intention. Later stories add
the other states (`idle`, `turn`, ...); this module is not to be pre-built
for them.

Startup rule (story 1b): the saved `selected_model` if still usable; else the
only usable file; with several, block until the user picks one. A model served by
an already-running local server (story 18) is taken back when it was the saved
choice and is still served, but never chosen by default: served models only block
until the user picks one. Once a model is handed out for loading, a new choice is a
hot switch (story 17, CAP-34): the application session loads it, and saves it after
a success.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr

from wavestack import config
from wavestack.cloud import (
    CloudContent,
    chat_fields,
    disclosure,
    fill,
    load_cloud_content,
    price_line_fr,
    warning_fr,
)
from wavestack.config import CloudModel
from wavestack.config import mo_fr as _mo
from wavestack.context.render import render_chat_body
from wavestack.context.segments import Part, SegmentKind
from wavestack.messages import KeyedError, Lazy, Message, Said, msg, render
from wavestack.models import discovery, probe
from wavestack.models.engine import CancelToken
from wavestack.models.load_registry import ModelChoice
from wavestack.models.openai_chat import ChatBody, OpenAIChatEngine, ProviderError, run_call
from wavestack.net.factory import create_client
from wavestack.net.guard import NetworkBlocked
from wavestack.session.effects import ApiKeySet, SettingWrite, apply_setting
from wavestack.tools.parser import tool_call_id
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import scoped

# Story 24: below this RAM available at launch, the memory check warns whatever the budget.
MEMORY_WARN_MB = 1024
NETWORK_CHECK_TIMEOUT = 3.0
PROBE_TIMEOUT_S = 300  # lot E: the probe also reads a first batch of 512 tokens
PROBE_POLL_S = 0.2  # story 24: how often a hot switch's probe looks at « Arrêter »


def _m(key: str, /, **kw: Any) -> Message:
    """`diagnostic.{key}`, kept as a `Message`: a piece of a text, rendered with it."""
    return Message(f"diagnostic.{key}", **kw)


def _cat(*parts: Any) -> Lazy:
    """Pieces written one after the other, each in the language of the text they end in."""
    return Lazy(lambda lang: "".join(render(p, lang) for p in parts))


def _probe_argv(path: str, window: int) -> list[str]:
    """AD-7: the probe's child process, at the window the engine loads it with (lot E, E2),
    the path last. Story 24: the seam the tests and the E2E launcher replace."""
    return [sys.executable, "-m", "wavestack.models.probe", "--window", str(window), path]


def _run_probe(
    argv: list[str], cancel: CancelToken | None, timeout: float
) -> subprocess.CompletedProcess[str] | None:
    """Story 24: run the probe's child, waiting by slices of `PROBE_POLL_S` so that
    « Arrêter » (`cancel`) kills it at once: `None` then, nothing read. Past `timeout`, the
    child is killed and `subprocess.TimeoutExpired` raised (lot E: time, not the file). The
    output is read as UTF-8 (the child writes ASCII JSON), invalid bytes replaced."""
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    deadline = time.monotonic() + timeout
    while True:
        try:
            out, err = proc.communicate(timeout=PROBE_POLL_S)
        except subprocess.TimeoutExpired:
            pass  # retrying `communicate` loses no output
        else:
            if cancel is not None and cancel.cancelled:
                return None  # ended in the slice « Arrêter » was pressed: stopped all the same
            return subprocess.CompletedProcess(argv, proc.returncode, out, err)
        if cancel is not None and cancel.cancelled:
            proc.kill()  # TerminateProcess on Windows: immediate; the probe writes nothing
            proc.communicate()  # reap the child
            return None
        if time.monotonic() >= deadline:
            proc.kill()
            out, err = proc.communicate()
            raise subprocess.TimeoutExpired(argv, timeout, output=out, stderr=err)


@dataclass
class DiagnosticResult:
    ready: bool
    blocking_checks: list[str] = field(default_factory=list)
    candidates: list[discovery.ModelCandidate] = field(default_factory=list)
    model_path: str | None = None  # the file the caller must load now, if any
    saved: bool = False  # `select_model`: the choice was recorded in settings.json
    message_text: str | None = None  # `select_model`: the outcome, in the session's language
    cloud_model: CloudModel | None = None  # the cloud model the caller must boot now, if any
    # Story 18: the served model (`discovery.ModelCandidate`, `source = server`) the caller
    # must boot now, if any.
    server: discovery.ModelCandidate | None = None
    # Story 17: `model_path` or `cloud_model` is a hot switch for the application session,
    # which saves the choice after a success (nothing written yet).
    hot: bool = False


class Refused(Exception):
    """A diagnostic intention refused with its reason (session language); nothing was written."""

    def __init__(self, reason_text: str) -> None:
        super().__init__(reason_text)
        self.reason_text = reason_text


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
        self.selected_server: str | None = (  # story 18: `ollama/{name}`, `llama_server/{file}`
            selected["ref"] if selected.get("kind") == "server" else None
        )
        # Set once a model is handed out for loading: from then on a choice is a hot switch
        # (story 17). What is loaded is the application session's to say.
        self.handed_out = False
        # Languages (3/5): the application session's language, for the cloud texts; `create_app`
        # binds it to `AppSession.language` (the launch's language until then).
        self.language: Callable[[], str] = lambda: cfg.language
        self.state = "diagnostic"
        self.last_result: DiagnosticResult | None = None
        self._lock = threading.Lock()
        self._tests = 0  # « Tester » runs, for their `diag.{n}` ids (AD-21)
        # model id -> its last « Tester » outcome, for the page opened after it
        self._last_tests: dict[str, dict[str, object]] = {}
        self._cloud_factory = cloud_factory or (
            lambda entry, key: OpenAIChatEngine(
                entry,
                key,
                connect_timeout_s=cfg.cloud_connect_timeout_s,
                read_timeout_s=cfg.cloud_read_timeout_s,
            )
        )
        self._emit_state(self._t("starting"))

    def _t(self, key: str | Message, /, **kw: Any) -> str:
        """`diagnostic.{key}` (or a `Message`) in the session's language, keeping its
        `Message` for the terminal (`Said`)."""
        message = key if isinstance(key, Message) else _m(key, **kw)
        return Said(message, self.language())

    def _rendered(self, value: Any) -> str:
        """A text written elsewhere: a `Message` (or our own keyed error) in the session's
        language, kept for the terminal; a plain text (a third party's) as it is."""
        if isinstance(value, KeyedError):
            value = value.message
        return Said(value, self.language()) if isinstance(value, Message) else str(value)

    def _cause(self, exc: BaseException) -> str:
        """A `harness_error`'s cause: our own keyed error in the session's language, a
        third party's text as it is."""
        return self._rendered(exc)

    def _error(self, message_text: str, cause: str | None, effect_text: str) -> None:
        get_journal().emit(
            "harness_error",
            {"message_text": message_text, "cause": cause, "effect_text": effect_text},
        )

    def _emit_state(self, reason_text: str) -> None:
        get_journal().emit("session_state", {"state": self.state, "reason_text": reason_text})

    def _emit_check(
        self,
        check: str,
        status: str,
        message_text: str,
        action_text: str | None = None,
        *,
        blocking: bool,
    ) -> None:
        get_journal().emit(
            "diagnostic_check",
            {
                "check": check,
                "status": status,
                "message_text": message_text,
                "action_text": action_text,
                "blocking": blocking,
            },
        )

    def check_memory(self) -> None:
        """AD-8, story 24: the RAM read at launch and the budget the session refuses with
        (the same `Config.memory_budget`, computed once), with how it was reached. `warn`,
        never blocking, when the RAM could not be read, when it limits the dynamic budget
        below its cap, when it is low, or when a fixed budget exceeds it."""
        budget = self.cfg.memory_budget

        def mo(n: int) -> Lazy:  # « 4 096 » in French, « 4,096 » in English
            return Lazy(lambda lang: _mo(n, lang))

        figures = _m("memory.figures", size=mo(budget.bytes), calc=Lazy(budget.calc_fr))
        if not budget.measured or budget.available_bytes is None:
            action = self._t(
                "memory.fixed_action" if budget.mode == "fixed" else "memory.cap_action"
            )
            self._emit_check(
                "memory",
                "warn",
                self._t("memory.not_measured", figures=figures),
                action,
                blocking=False,
            )
            return
        available = budget.available_bytes
        ram = (
            _m("memory.ram_total", total=mo(budget.total_bytes), available=mo(available))
            if budget.total_bytes
            else _m("memory.ram_available", available=mo(available))
        )
        if budget.mode == "fixed" and budget.bytes > available:
            where = _m(
                "memory.where_total"
                if budget.total_bytes and budget.bytes > budget.total_bytes
                else "memory.where_available"
            )
            why = self._t("memory.fixed_over", where=where)
        elif budget.ram_limited:
            why = self._t("memory.ram_limited")
        elif available < MEMORY_WARN_MB * 1024 * 1024:
            why = self._t("memory.low")
        else:
            self._emit_check(
                "memory", "ok", self._t("memory.measured", ram=ram, figures=figures), blocking=False
            )
            return
        self._emit_check(
            "memory",
            "warn",
            self._t("memory.measured", ram=ram, figures=figures),
            why,
            blocking=False,
        )

    def check_port(self) -> None:
        self._emit_check("port", "ok", self._t("port", port=self.port), blocking=False)

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
                    self._t("network.unavailable"),
                    self._t("network.offline_action"),
                    blocking=False,
                )
            else:
                self._emit_check("network", "ok", self._t("network.available"), blocking=False)
            finally:
                client.close()

    def _probe_candidate(
        self, candidate: discovery.ModelCandidate, cancel: CancelToken | None = None
    ) -> None:
        """AD-7: probe `candidate` in a child process. Story 24: `cancel` (a hot switch's
        load token; never the launch's diagnostic, which has no « Arrêter ») kills the child
        at once; then nothing is touched: neither the candidate, nor `failed_probes`, nor
        the journal."""
        assert candidate.path is not None
        proc = None

        def stopped() -> bool:  # « Arrêter », even in the slice where the child ended
            return cancel is not None and cancel.cancelled

        try:
            # Lot E (E2): at the window the engine loads it with (the path stays last).
            argv = _probe_argv(candidate.path, self.cfg.context_window)
            proc = _run_probe(argv, cancel=cancel, timeout=PROBE_TIMEOUT_S)
            if proc is None or stopped():  # the load is stopped: nothing said about the file
                return
            last_line = proc.stdout.strip().splitlines()[-1]
            result = probe.ProbeResult.model_validate_json(last_line)
        except Exception as exc:  # noqa: BLE001 - any probe failure marks the file incompatible
            if stopped():
                return
            if isinstance(exc, subprocess.TimeoutExpired):  # lot E: time, not the file
                self._probe_transient(candidate, probe.transient_fr(), str(exc))
                return
            # Only a native crash of the load says something about the file. Exit code 1 is
            # a Python error (config, guard...); no process, the environment.
            if proc is not None and proc.returncode not in (0, 1):
                self._persist(lambda: probe.record_failure(candidate.path, _m("probe.unconfirmed")))
            self._error(
                self._t("probe.failed", path=candidate.path),
                self._cause(exc),
                self._t("probe.marked_incompatible"),
            )
            candidate.status = "incompatible"
            # A `Message` (French as a text): `/api/diagnostic` renders it in its language.
            candidate.reason = _m("probe.unconfirmed")
            return

        if stopped():
            return
        if result.ok:
            candidate.architecture = result.architecture
            candidate.size_label = result.size_label
            self._persist(lambda: probe.record_success(result))
            return
        if result.transient:  # lot E: memory or time, not the file: never remembered
            self._probe_transient(candidate, result.reason or probe.transient_fr(), result.detail)
            return

        self._error(
            self._t("probe.incompatible", reason=result.reason),
            # Lot E (E6): the loader's own message, as the technical detail.
            result.detail or result.reason,
            self._t("probe.marked_incompatible"),
        )
        candidate.status = "incompatible"
        candidate.reason = result.reason
        self._persist(
            lambda: probe.record_failure(candidate.path, result.reason or _m("probe.unconfirmed"))
        )

    def _probe_transient(
        self, candidate: discovery.ModelCandidate, reason_text: str, detail: str | None
    ) -> None:
        """Lot E: the probe lacked memory or time. Unusable for now, never remembered: the
        file is probed again when chosen."""
        cause = detail or self._rendered(reason_text)
        self._error(
            self._t("probe.unmeasured", path=candidate.path),
            cause,
            self._t("probe.unmeasured_effect"),
        )
        candidate.status, candidate.reason = "incompatible", reason_text

    def _persist(self, write: Callable[[], None]) -> bool:
        """AD-16: a settings.json write failure is traced, never fatal. True if written."""
        try:
            write()
            return True
        except OSError as exc:
            self._error(
                self._t("settings_write.message"),
                self._cause(exc),
                self._t("settings_write.effect"),
            )
            return False

    def _handle_unexpected(self, exc: Exception) -> DiagnosticResult:
        """AD-16: no exception crosses the session boundary, not even an unforeseen one."""
        self._error(self._t("unexpected.message"), self._cause(exc), self._t("unexpected.effect"))
        self._emit_check(
            "model",
            "fail",
            self._t("unexpected.check"),
            self._t("unexpected.action"),
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
        self,
        explicit_path: str | None,
        probe_only: set[str] | None = None,
        reprobe: frozenset[str] | set[str] = frozenset(),
        report_progress: bool = False,
    ) -> list[discovery.ModelCandidate]:
        """Every candidate, architecture from the probe cache. Unprobed files are probed in a
        child process, all of them or only those in `probe_only`. Lot E (E2): a file whose
        entry is an older probe's or incomplete (`probe.measured`) is probed again only when
        in `reprobe` (the model about to boot, nothing loaded yet); the others are measured
        again when chosen (`AppSession._load`, after the release). A remembered failure of
        the current probe wins over an older success: no endless reprobe.

        Story 3 (corrections): with `report_progress` (the launch search only), one
        `diagnostic_progress{done: 0, total}` once the cache has been read (`total` = the
        probes actually needed), then one after each probe. Several Ollama tags sharing one
        blob are probed once; the others take its outcome."""
        candidates = discovery.discover(explicit_path)
        to_probe: list[discovery.ModelCandidate] = []
        siblings: dict[str, list[discovery.ModelCandidate]] = {}
        for candidate in candidates:
            if candidate.status != "found" or not candidate.path:
                continue
            path = candidate.path
            probing = probe_only is None or path in probe_only
            entry = probe.probed_entry(path)
            if entry is not None and probe.measured(path):
                candidate.architecture = entry.get("architecture")
                candidate.size_label = entry.get("size_label")
            elif (failed := probe.failed_entry(path)) is not None:
                # Remembered failure: no reprobe, same reason.
                candidate.status, candidate.reason = "incompatible", failed.get("reason")
            elif probing and (entry is None or path in reprobe):
                if path in siblings:
                    siblings[path].append(candidate)
                else:
                    siblings[path] = []
                    to_probe.append(candidate)
            elif entry is not None:
                candidate.architecture = entry.get("architecture")
                candidate.size_label = entry.get("size_label")
        total = len(to_probe)
        self._emit_progress(0, total, report_progress)
        for done, candidate in enumerate(to_probe, start=1):
            self._probe_candidate(candidate)
            for sibling in siblings[candidate.path]:
                sibling.architecture, sibling.size_label = (
                    candidate.architecture,
                    candidate.size_label,
                )
                sibling.status, sibling.reason = candidate.status, candidate.reason
            self._emit_progress(done, total, report_progress)
        return candidates

    def _emit_progress(self, done: int, total: int, report: bool) -> None:
        if report:
            get_journal().emit("diagnostic_progress", {"done": done, "total": total})

    def _hand_out(
        self,
        chosen: discovery.ModelCandidate,
        candidates: list[discovery.ModelCandidate],
        notice_text: str | Message = "",
    ) -> DiagnosticResult:
        """`chosen` is the file to load now; from here on, a choice is a hot switch."""
        self.handed_out = True
        self._emit_check(
            "model",
            "warn" if notice_text else "ok",
            self._t("model.retained_file", notice=notice_text, name=chosen.name, path=chosen.path),
            blocking=False,
        )
        self.last_result = DiagnosticResult(
            ready=True, candidates=candidates, model_path=chosen.path
        )
        return self.last_result

    def _check_model_locked(self) -> DiagnosticResult:
        for error_text in self.cfg.cloud_models[1]:  # AD-20: left out, never blocking
            self._emit_check("cloud", "warn", self._rendered(error_text), blocking=False)
        saved = self.selected_model_path
        # Lot E (E2): the saved file, about to boot, is measured again if its entry is old.
        candidates = self._discover(
            saved, reprobe={saved} if saved else set(), report_progress=True
        )
        notice_text: str | Message = ""
        if self.selected_cloud:
            entry = self.cfg.cloud_model(self.selected_cloud)
            reason = self._cloud_refusal(entry, self.selected_cloud)
            if entry is not None and reason is None:  # AD-21: no request, no new warning
                self.handed_out = True
                self._emit_check(
                    "model",
                    "ok",
                    self._t(
                        "model.retained_saved_cloud", model=entry.model, provider=entry.provider
                    ),
                    blocking=False,
                )
                self.last_result = DiagnosticResult(
                    ready=True, candidates=candidates, cloud_model=entry
                )
                return self.last_result
            notice_text = _m("model.notice_cloud", reason=reason)
        if self.selected_server:
            served = _served(candidates, self.selected_server)
            if served is not None:  # still served: taken back, never launched (story 18)
                return self._hand_out_server(served, candidates, _m("model.previous_launch"))
            listed = next((c for c in candidates if c.ref == self.selected_server), None)
            why = listed.reason if listed is not None and listed.reason else _m("model.server_gone")
            notice_text = _m(
                "model.notice_server",
                ref=self.selected_server,
                why=Lazy(lambda lang: render(why, lang).rstrip(".")),
            )
        if saved:
            chosen = _usable(candidates, saved)
            if chosen:
                return self._hand_out(chosen, candidates)
            notice_text = _m("model.notice_file", path=saved)

        files = [c for c in candidates if c.status == "found" and c.path]
        distinct = {c.path for c in files}  # several Ollama tags may share one blob
        if len(distinct) == 1:
            return self._hand_out(files[0], candidates, notice_text)
        if len(distinct) > 1:
            self._emit_check(
                "model",
                "warn",
                self._t("model.several", notice=notice_text),
                self._t("model.several_action"),
                blocking=True,
            )
            self.last_result = DiagnosticResult(
                ready=False, blocking_checks=["model"], candidates=candidates
            )
            return self.last_result

        servers = [c for c in candidates if c.status == "server"]
        if servers:  # story 18: never chosen by default, since Ollama would load it
            self._emit_check(
                "model",
                "warn",
                self._t("model.served_only", notice=notice_text, count=len(servers)),
                self._t("model.served_only_action"),
                blocking=True,
            )
            self.last_result = DiagnosticResult(
                ready=False, blocking_checks=["model"], candidates=candidates
            )
            return self.last_result

        if candidates:
            listed = [
                (c.source, c.path or c.server_url or "?", c.reason or c.status) for c in candidates
            ]
            details: str | Lazy | Message = Lazy(
                lambda lang: "; ".join(
                    msg("diagnostic.model.detail", lang, source=s, where=w, reason=render(r, lang))
                    for s, w, r in listed
                )
            )
        else:
            details = _m("model.no_candidate")
        self._emit_check(
            "model",
            "fail",
            self._t("model.none", notice=notice_text, sources=_m("model.searched_sources")),
            self._t("model.none_action", details=details),
            blocking=True,
        )
        self.last_result = DiagnosticResult(
            ready=False, blocking_checks=["model"], candidates=candidates
        )
        return self.last_result

    def select_model(self, path: str, *, hot: bool = False) -> DiagnosticResult:
        """Intention `select_model` (AD-3): exactly this file, or its reason. `hot`: a model
        was handed out already, so the file is neither probed here nor saved: the result is a
        hot switch for the application session (story 17)."""
        with self._lock:
            try:
                return self._select_model_locked(_normalize(path), hot)
            except Exception as exc:  # noqa: BLE001 - AD-16: never let the thread die silently
                return self._handle_unexpected(exc)

    def _select_model_locked(self, path: str, hot: bool) -> DiagnosticResult:
        # Probe only the chosen file, and not here for a hot switch: a probe loads full
        # weights, so the application session probes it once the active model is released.
        candidates = self._discover(
            path, probe_only=set() if hot else {path}, reprobe=set() if hot else {path}
        )
        previous = self.last_result or DiagnosticResult(ready=False, blocking_checks=["model"])
        known = {  # files only: a served model has no path (story 18)
            c.path: c for c in previous.candidates if c.status == "incompatible" and c.path
        }
        for candidate in candidates:  # keep earlier probe failures of the unprobed others
            if candidate.path != path and candidate.path in known:
                candidate.status, candidate.reason = "incompatible", known[candidate.path].reason
        chosen = _usable(candidates, path)
        if chosen is None:
            listed = next((c for c in candidates if c.path == path), None)
            reason = (listed.reason if listed else None) or _m("model.file_missing")
            # Nothing saved, nothing loaded: the diagnostic stays as it was.
            self.last_result = DiagnosticResult(
                ready=previous.ready,
                blocking_checks=previous.blocking_checks,
                candidates=candidates,
                message_text=self._t("model.not_retained", ref=path, reason=reason),
            )
            return self.last_result
        if hot:
            self.last_result = DiagnosticResult(
                ready=previous.ready,
                blocking_checks=previous.blocking_checks,
                candidates=candidates,
                model_path=chosen.path,
                hot=True,
            )
            return self.last_result

        self.selected_model_path, self.selected_cloud, self.selected_server = (
            chosen.path,
            None,
            None,
        )
        saved = self._save_choice("file", chosen.path)
        result = self._hand_out(chosen, candidates)
        result.saved = saved
        result.message_text = self._t(
            "model.chosen_file",
            name=chosen.name,
            not_saved="" if saved else _m("model.not_saved_launches"),
        )
        return result

    def _hand_out_server(
        self,
        chosen: discovery.ModelCandidate,
        candidates: list[discovery.ModelCandidate],
        why_text: str | Message = "",
    ) -> DiagnosticResult:
        """`chosen`, a served model, is the model to prepare now (story 18). Lot E (E1): a
        llama-server launched with a context much larger than the window is a warning."""
        self.handed_out = True
        warning = _cat(" ", chosen.warning_text) if chosen.warning_text else ""
        self._emit_check(
            "model",
            "warn" if warning else "ok",
            self._t(
                "model.retained_server",
                name=chosen.name,
                provider=chosen.provider,
                url=chosen.server_url,
                why=why_text,
                warning=warning,
            ),
            blocking=False,
        )
        self.last_result = DiagnosticResult(ready=True, candidates=candidates, server=chosen)
        return self.last_result

    def select_server(self, ref: str, *, hot: bool = False) -> DiagnosticResult:
        """Intention `select_model{kind: server}` (story 18): the model `ref` as the servers
        list it now, or its reason. Same path as a file: before any model is handed out, saved
        and prepared now; after (`hot`), a hot switch for the application session."""
        with self._lock:
            try:
                return self._select_server_locked(ref.strip(), hot)
            except Exception as exc:  # noqa: BLE001 - AD-16: never let the thread die silently
                return self._handle_unexpected(exc)

    def _select_server_locked(self, ref: str, hot: bool) -> DiagnosticResult:
        candidates = self._discover(None, probe_only=set())  # read again: is it still served?
        previous = self.last_result or DiagnosticResult(ready=False, blocking_checks=["model"])
        known = {  # files only: a served model has no path (story 18)
            c.path: c for c in previous.candidates if c.status == "incompatible" and c.path
        }
        for candidate in candidates:  # keep earlier probe failures of the unprobed files
            if candidate.path in known and candidate.status == "found":
                candidate.status, candidate.reason = "incompatible", known[candidate.path].reason
        chosen = _served(candidates, ref)
        if chosen is None:
            listed = next((c for c in candidates if c.ref == ref), None)
            reason = (listed.reason if listed else None) or _m("model.not_served")
            self.last_result = DiagnosticResult(
                ready=previous.ready,
                blocking_checks=previous.blocking_checks,
                candidates=candidates,
                message_text=self._t("model.not_retained", ref=ref, reason=reason),
            )
            return self.last_result
        if hot:
            self.last_result = DiagnosticResult(
                ready=previous.ready,
                blocking_checks=previous.blocking_checks,
                candidates=candidates,
                server=chosen,
                hot=True,
            )
            return self.last_result
        self.selected_server, self.selected_model_path, self.selected_cloud = ref, None, None
        saved = self._save_choice("server", ref)
        result = self._hand_out_server(chosen, candidates)
        result.saved = saved
        result.message_text = self._t(
            "model.chosen_server",
            name=chosen.name,
            provider=chosen.provider,
            not_saved="" if saved else _m("model.not_saved_launches"),
        )
        return result

    def _save_choice(self, kind: str, ref: str) -> bool:
        """AD-20: `selected_model = {kind, ref}`, by the single applier (AD-23)."""
        value = {"kind": kind, "ref": ref}
        return self._persist(lambda: apply_setting(SettingWrite(key="selected_model", value=value)))

    def hand_to(self, app_session: Any, result: DiagnosticResult, *, launch: bool = False) -> None:
        """Boot the model `result` hands out on `app_session`: the cloud model, else the file.
        At launch (`launch`), a ready result without file still boots (a server only), so the
        session leaves `diagnostic` with its reason. The same path for the cli and the web."""
        future = None
        if result.cloud_model is not None:
            future = app_session.boot_cloud(result.cloud_model)
        elif result.server is not None:
            future = app_session.boot_server(result.server)
        elif result.model_path:
            future = app_session.boot(result.model_path, _name(result, result.model_path))
        elif launch and result.ready:
            app_session.boot(None)  # a server only: no model, the session says why
        if hasattr(future, "add_done_callback"):  # lot E: a boot left without any model
            future.add_done_callback(lambda f: self._booted(f, _loaded(app_session)))

    def _booted(self, future: Any, loaded: Callable[[], bool]) -> None:
        """Lot E (E4): the launch's load ended `cancelled` (« Arrêter ») or `error` with no
        model loaded: the diagnostic blocks again, as after a hot switch."""
        try:
            status = future.result()
        except Exception:  # noqa: BLE001 - the session traced it (AD-16)
            status = "error"
        if status not in ("cancelled", "error") or loaded():
            return
        self._block(
            self._t("model.none_loaded_stopped" if status == "cancelled" else "model.none_loaded"),
            self._t("model.choose_below"),
        )

    def _block(self, message_text: str, action_text: str) -> None:
        """No model is active any more: the diagnostic is no longer `ready`."""
        with self._lock:
            if self.last_result is not None:
                self.last_result.ready, self.last_result.blocking_checks = False, ["model"]
        self._emit_check("model", "fail", message_text, action_text, blocking=True)

    def switch(self, app_session: Any, result: DiagnosticResult) -> tuple[str, bool]:
        """Story 17: the hot switch `result` asks for, on `app_session` (class b, AD-3). Raises
        its `SendRefused` (state, budget). Returns the French answer and whether a load
        started. The probe is this session's single probe code (AD-7)."""
        entry = result.cloud_model
        path = result.model_path or ""
        if entry is not None:
            choice = ModelChoice("cloud", entry.id, entry)
        elif result.server is not None:
            choice = ModelChoice.served(result.server)
        else:
            choice = ModelChoice("file", path, name=_name(result, path))
        message_text, future = app_session.switch_model(choice, probe=self.probe_path)
        if future is not None:
            loaded = _loaded(app_session)
            future.add_done_callback(lambda f: self._switched(choice, f, loaded))
        return message_text, future is not None

    def _switched(
        self, choice: ModelChoice, future: Any, loaded: Callable[[], bool] = lambda: True
    ) -> None:
        """A hot switch ended. `ok`: nothing blocks any more, and the choice is the saved one
        only if settings.json holds it. `error` (no model active any more): the diagnostic
        blocks again (no longer `ready`). `restored`: unchanged.
        `cancelled` (lot E, E4): unchanged, unless no model is active any more (`loaded`)."""
        try:
            status = future.result()
        except Exception:  # noqa: BLE001 - the session traced it (AD-16)
            status = "error"
        if status == "cancelled":
            if not loaded():
                self._block(self._t("model.none_loaded_stopped"), self._t("model.choose_below"))
            return
        label: str | Message
        if choice.entry is not None:
            label = _m(
                "model.cloud_label", model=choice.entry.model, provider=choice.entry.provider
            )
        elif choice.kind == "server":
            label = _m("model.server_label", name=choice.label, provider=choice.provider)
        else:
            label = choice.file_name
        if status == "error":
            self._block(
                self._t("model.none_loaded_switch", label=label),
                self._t("model.choose_other"),
            )
            return
        if status != "ok":
            return
        saved = config.read_settings().get("selected_model") == {
            "kind": choice.kind,
            "ref": choice.ref,
        }
        with self._lock:
            if saved:
                self.selected_model_path = choice.ref if choice.kind == "file" else None
                self.selected_cloud = choice.ref if choice.kind == "cloud" else None
                self.selected_server = choice.ref if choice.kind == "server" else None
            if self.last_result is not None:
                self.last_result.ready, self.last_result.blocking_checks = True, []
        # Lot E (E1): llama-server launched with a context much larger than the window.
        warning = getattr(choice.server, "warning_text", None) if choice.kind == "server" else None
        self._emit_check(
            "model",
            "ok" if saved and not warning else "warn",
            self._t(
                "model.active",
                label=label,
                not_saved="" if saved else _m("model.switch_not_saved"),
                warning=_cat(" ", warning) if warning else "",
            ),
            blocking=False,
        )

    def probe_path(self, path: str, cancel: CancelToken | None = None) -> str | None:
        """AD-7's probe of `path` in a child process, for the application session's hot
        switch: `None` when the file loads, else why. A failure marks the listed candidate
        incompatible. Runs on the session's worker, without this session's lock. Story 24:
        « Arrêter » (`cancel`) kills the child and answers `None`, nothing recorded: the
        load's next checkpoint sees the stop."""
        candidate = discovery.ModelCandidate(
            source="explicit", status="found", path=path, name=Path(path).name
        )
        self._probe_candidate(candidate, cancel)
        if cancel is not None and cancel.cancelled:
            return None
        listed = self.last_result.candidates if self.last_result else []
        for known in listed:
            if known.path == path:
                known.status, known.reason = candidate.status, candidate.reason
                known.architecture = candidate.architecture or known.architecture
                known.size_label = candidate.size_label or known.size_label
        if candidate.status == "found":
            return None
        return candidate.reason or _m("probe.unconfirmed")

    def first_launch(self) -> bool:
        """AD-21: no `diagnostic_shown` in settings.json yet. Writes it, by the single
        applier; a failed write is ignored (the next launch counts as first again)."""
        if "diagnostic_shown" in config.read_settings():
            return False
        path = config.settings_path()
        if path.exists():  # a hand-edited file that does not parse is never rewritten
            try:
                valid = isinstance(json.loads(path.read_text(encoding="utf-8")), dict)
            except (OSError, ValueError):
                valid = False
            if not valid:
                return True
        try:
            apply_setting(SettingWrite(key="diagnostic_shown", value=True))
        except OSError:
            pass
        return True

    # ---------- cloud models (story 11, AD-20, AD-21) ----------

    def _cloud_refusal(self, entry: CloudModel | None, model_id: str) -> str | None:
        """Why `entry` can be neither tested nor chosen; `None` when it can. A `Message`
        (French as a text) or a text of `content/cloud.yaml` in the session's language: a
        variable of the text it ends in, or `render`ed."""
        if entry is None:
            return _m("cloud.undeclared", id=model_id)
        if config.cloud_key(entry) is None:
            content = self._cloud_content()
            if config.api_key_host_changed(entry):
                return content.host_changed_text if content else _m("cloud.key_again")
            return fill(content.no_key_text, entry, content) if content else _m("cloud.no_key")
        return config.cloud_unavailable_fr(entry)

    def _cloud_content(self) -> CloudContent | None:
        """`content/cloud.yaml` in the session's language; an invalid translation is traced,
        then the French file answers (AD-19, as `AppSession._localized`)."""
        lang = self.language()
        if lang != config.DEFAULT_LANGUAGE:
            try:
                return load_cloud_content(lang)
            except Exception as exc:  # noqa: BLE001 - AD-19: traced, then French
                self._error(
                    self._t(Message("session.translation_invalid.message", lang=lang)),
                    str(exc),  # a validation message of the file: never translated
                    self._t(Message("session.translation_invalid.effect")),
                )
        try:
            return load_cloud_content(config.DEFAULT_LANGUAGE)
        except Exception as exc:  # noqa: BLE001 - AD-19: traced, never fatal
            self._error(
                self._t("cloud.content_invalid"), str(exc), self._t("cloud.content_invalid_effect")
            )
            return None

    def cloud_rows(self, active: str | None = None) -> dict[str, object]:
        """`/api/diagnostic`: each declared cloud model, its key state (never the key), why
        its buttons are disabled, its mentions and the warning's text; and the common texts.
        `active`: the cloud model the application session has loaded, if any (story 17)."""
        content = self._cloud_content()
        rows = []
        for entry in self.cfg.cloud_models[0]:
            reason = self._cloud_refusal(entry, entry.id)
            price = price_line_fr(entry, self.language())
            rows.append(
                {
                    "id": entry.id,
                    "provider": entry.provider,
                    "model": entry.model,
                    "host": entry.host,
                    "disclosure": disclosure(entry),
                    "training_text": (
                        content.training_text.get(entry.training, entry.training)
                        if content
                        else entry.training
                    ),
                    "key_set": config.cloud_key(entry) is not None,
                    # AD-20: where the key comes from, and the variable's name, never its value.
                    "key_source": config.cloud_key_source(entry),
                    "key_env": entry.key_env,
                    "disabled_text": None if reason is None else self._rendered(reason),
                    "selected": entry.id == self.selected_cloud,
                    "loaded": entry.id == active,
                    "test_hint_text": fill(content.test_hint_text, entry, content)
                    if content
                    else "",
                    "warning": warning_fr(entry, content) if content else None,
                    "last_test": self._last_tests.get(entry.id),
                    # FinOps: the declared prices, `None` without them.
                    "price_text": None if price is None else self._rendered(price),
                }
            )
        return {"models": rows, "key_hint_text": content.key_hint_text if content else ""}

    def select_cloud(
        self, model_id: str, acknowledged: bool, *, hot: bool = False
    ) -> DiagnosticResult:
        """Intention `select_model{kind: cloud}` (AD-21): refused without the warning's
        confirmation or a usable key, nothing written then (`Refused`). Before any model is
        handed out, the caller boots it; after (`hot`), it is a hot switch (story 17)."""
        with self._lock:
            entry = self.cfg.cloud_model(model_id)
            if entry is not None and not acknowledged:
                raise Refused(self._t("cloud.unacknowledged"))
            reason = self._cloud_refusal(entry, model_id)
            if entry is None or reason is not None:
                raise Refused(self._t("cloud.choice_refused", reason=reason))
            previous = self.last_result or DiagnosticResult(ready=False)
            if hot:
                self.last_result = DiagnosticResult(
                    ready=previous.ready,
                    blocking_checks=previous.blocking_checks,
                    candidates=previous.candidates,
                    cloud_model=entry,
                    hot=True,
                )
                return self.last_result
            self.selected_cloud, self.selected_model_path, self.selected_server = (
                entry.id,
                None,
                None,
            )
            saved = self._save_choice("cloud", entry.id)
            label = _m("model.cloud_label", model=entry.model, provider=entry.provider)
            self.handed_out = True
            self._emit_check("model", "ok", self._t("cloud.retained", label=label), blocking=False)
            self.last_result = DiagnosticResult(
                ready=True,
                candidates=previous.candidates,
                saved=saved,
                cloud_model=entry,
                message_text=self._t(
                    "cloud.chosen",
                    label=label,
                    not_saved="" if saved else _m("cloud.not_saved"),
                ),
            )
            return self.last_result

    def set_api_key(self, model_id: str, key: SecretStr) -> dict[str, object]:
        """Intention `set_api_key` (AD-20): saved with the host declared now, by the single
        applier. The answer never carries what it received (AD-15)."""
        entry = self.cfg.cloud_model(model_id)
        if entry is None:
            raise Refused(self._t("cloud.key_undeclared", id=model_id))
        if not key.get_secret_value().strip():
            raise Refused(self._t("cloud.key_empty"))
        key = SecretStr(key.get_secret_value().strip())
        effect = ApiKeySet(id=entry.id, host=entry.host, key=key)
        try:
            apply_setting(effect)
        except OSError as exc:
            raise Refused(
                self._t(
                    "cloud.key_not_saved",
                    path=config.api_keys_path(),
                    cause=exc.strerror or type(exc).__name__,
                )
            ) from None
        return {
            "key_set": True,
            "message_text": self._t("cloud.key_saved", provider=entry.provider),
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
            raise Refused(self._t("cloud.test_refused", reason=reason))
        if content is None:
            raise Refused(self._t("cloud.test_impossible"))
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
                        provider_label_text=content.provider_segment_text,
                        lang=self.language(),
                    )
                    out = run_call(
                        engine,
                        ChatBody(rendered.body.encode("utf-8")),
                        CancelToken(),
                        phase_label=self._t(
                            "cloud.test_phase", model=entry.model, provider=entry.provider
                        ),
                        estimated_prompt=rendered.raw_total,
                        chars_per_token=self.cfg.chars_per_token,
                        call_id=lambda i, s=step_id: tool_call_id(s, i),
                        eur_per_usd=self.cfg.eur_per_usd,
                    )
                tps = out.output_tps if out.output_tps is not None else tps
                if k == 1 and out.calls and all("id" in c for c in out.calls):
                    call = out.calls[0]
                    tool_call = {"name": call["name"], "arguments": call["arguments"]}
                    assistant: dict[str, Any] = {"role": "assistant"}
                    if out.text:
                        assistant["content"] = [Part(SegmentKind.ASSISTANT_TURN, out.text)]
                    replayed: dict[str, Any] = {
                        "id": call["id"],
                        "type": "function",
                        "function": {"name": call["name"], "arguments": call["arguments"]},
                    }
                    if call.get("extra_content"):  # Gemini 3.x: its thought signature
                        replayed["extra_content"] = call["extra_content"]
                    assistant["tool_calls"] = [replayed]
                    reply = [Part(SegmentKind.TOOL_RESULT, test.tool_reply)]
                    messages += [
                        assistant,
                        {"role": "tool", "tool_call_id": call["id"], "content": reply},
                    ]
                    continue
                answer = out.text or out.reasoning
                break
        except ProviderError as error:
            # The provider's texts: `Message`s (or a third party's text), in the language.
            self._emit_test(
                entry,
                "fail",
                self._t("cloud.test_failed", message=error.message_text),
                list(error.hints_text),
            )
            return {"ok": False, "message_text": self._rendered(error.message_text)}
        finally:
            engine.close()
        rate = _m("cloud.test_rate", tps=tps) if tps is not None else ""
        if entry.tools and tool_call is None:
            message = self._t("cloud.test_no_tool", provider=entry.provider, rate=rate)
            status = "warn"
        else:
            called = _m("cloud.test_tool_called", name=tool_call["name"]) if tool_call else ""
            message = self._t("cloud.test_ok", provider=entry.provider, rate=rate, called=called)
            status = "ok"
        self._emit_test(entry, status, message, [], answer=answer, tool_call=tool_call, tps=tps)
        return {"ok": status == "ok", "message_text": message}

    def _emit_test(
        self,
        entry: CloudModel,
        status: str,
        message_text: str,
        hints_text: list[str],
        *,
        answer: str | None = None,
        tool_call: dict[str, object] | None = None,
        tps: int | None = None,
    ) -> None:
        # The provider's hints (`Message`s or plain texts), one after the other.
        hints = Lazy(lambda lang: " ".join(render(h, lang) for h in hints_text))
        payload: dict[str, object] = {
            "check": "cloud_test",
            "status": status,
            "message_text": message_text,
            "action_text": self._t(Message("common.verbatim", text=hints)) if hints_text else None,
            "blocking": False,
            "model_id": entry.id,
            "answer": answer,
            "tool_call": tool_call,
            "output_tps": tps,
        }
        self._last_tests[entry.id] = payload
        get_journal().emit("diagnostic_check", payload)

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


def launch_page(result: DiagnosticResult) -> str:
    """AD-21, step 2: the main page when the launch is ready and nothing blocks, else the
    diagnostic."""
    return "/" if result.ready and not result.blocking_checks else "/diagnostic"


def _loaded(app_session: Any) -> Callable[[], bool]:
    """Whether `app_session` has a model loaded now (a double without the property: yes)."""
    return lambda: bool(getattr(app_session, "model_loaded", True))


def _name(result: DiagnosticResult, path: str | None) -> str | None:
    """The readable name discovery gave `path` (an Ollama `model:tag`), if listed."""
    return next((c.name for c in result.candidates if path and c.path == path), None)


def _served(
    candidates: list[discovery.ModelCandidate], ref: str
) -> discovery.ModelCandidate | None:
    """The served model `ref`, if a server serves it now and WaveStack can use it."""
    return next((c for c in candidates if c.ref == ref and c.status == "server"), None)


def _usable(
    candidates: list[discovery.ModelCandidate], path: str
) -> discovery.ModelCandidate | None:
    return next((c for c in candidates if c.path == path and c.status == "found"), None)


def _normalize(path: str) -> str:
    """A pasted path: surrounding quotes (Windows « Copier en tant que chemin d'accès »),
    `~`, relative. `absolute()`, not `resolve()`: a resolved symlink or junction (e.g. an
    OLLAMA_MODELS link) would no longer match the discovered candidate's path."""
    return str(Path(path.strip().strip('"').strip("'")).expanduser().absolute())
