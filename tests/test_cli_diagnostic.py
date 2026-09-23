from __future__ import annotations

import subprocess

from starlette.testclient import TestClient

from wavestack import config
from wavestack.models import discovery
from wavestack.session import diagnostic as diagnostic_module
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app


def _client(app):
    # TrustedHostMiddleware only allows the app's own host:port; point the
    # test client's Host header there instead of starlette's default "testserver".
    return TestClient(app, base_url="http://127.0.0.1:8420")


def _build(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    # Isolate discovery from whatever Ollama/LM Studio/HF cache happens to be
    # installed on the machine running the tests: this story's diagnostic
    # tests must be deterministic regardless of the dev's local setup.
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [tmp_path / "no-lmstudio"])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])

    cfg = config.load_config()
    session = DiagnosticSession(cfg, port=8420)
    # Keep these tests offline and process-free: story 1's network probe and
    # the subprocess GGUF probe are covered separately (test_net_guard.py,
    # test_probe.py); this file checks the diagnostic session/API wiring.
    monkeypatch.setattr(session, "check_network", lambda: None)
    monkeypatch.setattr(session, "_probe_candidate", lambda candidate: None)
    app = create_app(session, port=8420, version="test")
    return session, app


def test_health_endpoint(monkeypatch, tmp_path):
    _, app = _build(monkeypatch, tmp_path)
    response = _client(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_no_model_found_blocks_diagnostic(monkeypatch, tmp_path):
    session, app = _build(monkeypatch, tmp_path)

    result = session.check_model()
    assert result.ready is False
    assert result.blocking_checks == ["model"]

    body = _client(app).get("/api/diagnostic").json()
    assert body["ready"] is False
    assert body["blocking_checks"] == ["model"]

    events = get_journal().all_events()
    model_checks = [
        e for e in events if e.kind == "diagnostic_check" and e.payload["check"] == "model"
    ]
    assert model_checks[-1].payload["status"] == "fail"
    assert model_checks[-1].payload["blocking"] is True


def test_model_in_models_dir_passes_without_blocking(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "demo.gguf").write_bytes(b"placeholder")

    result = session.check_model()
    assert result.ready is True
    assert result.blocking_checks == []


def test_select_model_intention_rechecks_the_given_path(monkeypatch, tmp_path):
    session, app = _build(monkeypatch, tmp_path)
    model_file = tmp_path / "picked.gguf"
    model_file.write_bytes(b"placeholder")

    response = _client(app).post(
        "/api/intentions/select_model",
        json={"path": str(model_file)},
        headers={"Origin": "http://127.0.0.1:8420"},
    )
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert session.selected_model_path == str(model_file)


def test_select_model_wrong_origin_is_refused(monkeypatch, tmp_path):
    _, app = _build(monkeypatch, tmp_path)
    response = _client(app).post(
        "/api/intentions/select_model",
        json={"path": "irrelevant.gguf"},
        headers={"Origin": "http://evil.test"},
    )
    assert response.status_code == 403


def test_select_model_missing_origin_is_refused(monkeypatch, tmp_path):
    _, app = _build(monkeypatch, tmp_path)
    response = _client(app).post(
        "/api/intentions/select_model",
        json={"path": "irrelevant.gguf"},
    )
    assert response.status_code == 403


def test_select_model_wrong_content_type_is_rejected(monkeypatch, tmp_path):
    _, app = _build(monkeypatch, tmp_path)
    response = _client(app).post(
        "/api/intentions/select_model",
        content="not json",
        headers={
            "Origin": "http://127.0.0.1:8420",
            "Content-Type": "text/plain",
        },
    )
    assert response.status_code == 415


def test_probe_failure_marks_candidate_incompatible_and_stays_blocking(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    # _build() stubs _probe_candidate to a no-op; restore the real, bound method.
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "bad.gguf").write_bytes(b"not a real gguf")

    class _FakeCompletedProcess:
        stdout = '{"ok": false, "path": "bad.gguf", "reason": "Fichier corrompu."}'

    monkeypatch.setattr(
        diagnostic_module.subprocess, "run", lambda *a, **k: _FakeCompletedProcess()
    )

    before = get_journal().last_seq()
    result = session.check_model()

    assert result.ready is False
    assert result.blocking_checks == ["model"]
    errors = [e for e in get_journal().events_since(before) if e.kind == "harness_error"]
    assert errors and "Fichier corrompu." in errors[0].payload["cause"]


def test_probe_subprocess_crash_marks_candidate_incompatible(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    monkeypatch.setattr(
        session, "_probe_candidate", DiagnosticSession._probe_candidate.__get__(session)
    )
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "bad.gguf").write_bytes(b"not a real gguf")

    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="probe", timeout=1)

    monkeypatch.setattr(diagnostic_module.subprocess, "run", _raise)

    result = session.check_model()

    assert result.ready is False
    assert result.blocking_checks == ["model"]


def test_network_unreachable_warns_without_blocking(monkeypatch, tmp_path):
    # The session-wide guard fixture (conftest.py) allows only loopback hosts,
    # so this real check_network() call is refused by the guard exactly like
    # an unreachable host would be (AD-16: never an unhandled exception).
    session, _ = _build(monkeypatch, tmp_path)

    before = get_journal().last_seq()
    DiagnosticSession.check_network(session)  # _build() stubs the instance's check_network

    events = [
        e
        for e in get_journal().events_since(before)
        if e.kind == "diagnostic_check" and e.payload["check"] == "network"
    ]
    assert events[-1].payload["status"] == "warn"
    assert events[-1].payload["blocking"] is False


def test_full_run_emits_all_checks(monkeypatch, tmp_path):
    session, _ = _build(monkeypatch, tmp_path)
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "demo.gguf").write_bytes(b"placeholder")

    before = get_journal().last_seq()
    result = session.run()
    assert result.ready is True

    kinds_checked = {
        e.payload["check"]
        for e in get_journal().events_since(before)
        if e.kind == "diagnostic_check"
    }
    assert kinds_checked == {"memory", "model", "port"}
