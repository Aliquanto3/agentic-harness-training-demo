"""Story 13 (CAP-5): the brick's « Installer » (the `guardrails` extra, a real `uv sync`) and
Prompt Guard 2's own install (a Hugging Face token, then its ONNX download). No real
subprocess, no real download, no real file written under the user's data dir: `subprocess.run`
and the manager's classifier are faked; `config.write_hf_token` is monkeypatched."""

from __future__ import annotations

import subprocess
import time

import pytest
from fake_engine import FakeEngine, booted_session

from wavestack.guardrails.manager import GuardrailsManager
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.trace.journal import get_journal


def wait_idle(session: AppSession) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if session.state == "idle" and session._download_cancel is None:
            break
        time.sleep(0.01)
    time.sleep(0.05)  # the thread's last emission
    session.join()


def _session() -> AppSession:
    return booted_session(FakeEngine(output="ok"))


def test_install_guardrails_extra_refused_when_already_installed() -> None:
    session = _session()
    session._guardrails_missing = None
    with pytest.raises(SendRefused):
        session.install_guardrails_extra()


def test_install_guardrails_extra_activates_the_brick_live_on_success(monkeypatch) -> None:
    session = _session()
    session._guardrails_missing = "non installés"
    monkeypatch.setattr(
        "wavestack.session.app_session.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0, "", ""),
    )
    monkeypatch.setattr(
        "wavestack.session.app_session.guardrails_availability.missing_fr", lambda: None
    )
    mark = get_journal().last_seq()

    reason = session.install_guardrails_extra()
    assert "install" in reason.lower() or "Install" in reason
    wait_idle(session)

    assert session._guardrails_missing is None
    kinds = [e.kind for e in get_journal().events_since(mark)]
    assert "harness_error" not in kinds
    effects = [e.payload for e in get_journal().events_since(mark) if e.kind == "effect_applied"]
    assert any(e["effect"] == "guardrails_extra_installed" for e in effects)


def test_install_guardrails_extra_failure_keeps_not_installed(monkeypatch) -> None:
    session = _session()
    session._guardrails_missing = "non installés"
    monkeypatch.setattr(
        "wavestack.session.app_session.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 1, "", "proxy refused"),
    )
    mark = get_journal().last_seq()

    session.install_guardrails_extra()
    wait_idle(session)

    assert session._guardrails_missing is not None  # unchanged: still "non installés"
    kinds = [e.kind for e in get_journal().events_since(mark)]
    assert "harness_error" in kinds


def test_install_prompt_guard_refused_without_token() -> None:
    session = _session()
    session._guardrails_missing = None
    with pytest.raises(SendRefused):
        session.install_prompt_guard("   ")


def test_install_prompt_guard_refused_when_extra_missing() -> None:
    session = _session()
    session._guardrails_missing = "non installés"
    with pytest.raises(SendRefused):
        session.install_prompt_guard("a-token")


def test_install_prompt_guard_saves_token_then_loads_the_classifier(monkeypatch) -> None:
    session = _session()
    session._guardrails_missing = None

    class FakePromptGuard:
        loaded = False

        def ensure_loaded(self, on_progress=None) -> None:
            if on_progress is not None:
                on_progress(1, 1)
            self.loaded = True

        def classify(self, text):  # pragma: no cover - not exercised here
            raise AssertionError

        def mask(self, text, entities):  # pragma: no cover
            return text

        def unload(self) -> None:
            self.loaded = False

    fake = FakePromptGuard()
    session._guardrails = GuardrailsManager({"injection": lambda: fake})
    saved: list[str] = []
    monkeypatch.setattr(
        "wavestack.config.write_hf_token", lambda key: saved.append(key.get_secret_value())
    )
    mark = get_journal().last_seq()

    reason = session.install_prompt_guard("hf_my_token")
    assert "Prompt Guard" in reason
    wait_idle(session)

    assert saved == ["hf_my_token"]
    assert session._guardrails.injection_ready() is True
    effects = [e.payload for e in get_journal().events_since(mark) if e.kind == "effect_applied"]
    assert any(e["effect"] == "model_download" for e in effects)


def test_install_prompt_guard_reports_a_download_failure(monkeypatch) -> None:
    session = _session()
    session._guardrails_missing = None

    class Failing:
        def ensure_loaded(self, on_progress=None) -> None:
            raise RuntimeError("401 unauthorized")

    session._guardrails = GuardrailsManager({"injection": lambda: Failing()})
    monkeypatch.setattr("wavestack.config.write_hf_token", lambda key: None)
    mark = get_journal().last_seq()

    session.install_prompt_guard("bad-token")
    wait_idle(session)

    assert session._guardrails.injection_ready() is False
    kinds = [e.kind for e in get_journal().events_since(mark)]
    assert "harness_error" in kinds
