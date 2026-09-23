from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

from wavestack import config
from wavestack.models import discovery
from wavestack.session.app_session import AppSession
from wavestack.session.diagnostic import DiagnosticResult, DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import _sse_stream, create_app


def _client(app):
    # TrustedHostMiddleware only allows the app's own host:port; point the
    # test client's Host header there instead of starlette's default "testserver".
    return TestClient(app, base_url="http://127.0.0.1:8421")


def _build(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-ollama"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "no-hf-cache"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [tmp_path / "no-lmstudio"])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])

    cfg = config.load_config()
    session = DiagnosticSession(cfg, port=8421)
    app = create_app(session, port=8421, version="test")
    return app


def test_index_page_served_at_root(monkeypatch, tmp_path):
    app = _build(monkeypatch, tmp_path)
    response = _client(app).get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_diagnostic_route_still_works(monkeypatch, tmp_path):
    """Boundary: `/diagnostic` from story 1 must stay untouched."""
    app = _build(monkeypatch, tmp_path)
    response = _client(app).get("/diagnostic")
    assert response.status_code == 200


def test_api_state_reflects_last_known_session_state_and_architecture(monkeypatch, tmp_path):
    app = _build(monkeypatch, tmp_path)
    AppSession().emit_initial()

    body = _client(app).get("/api/state").json()

    assert body["session_state"]["state"] == "idle"
    node_ids = {n["id"] for n in body["architecture_changed"]["nodes"]}
    assert node_ids == {"core.harness", "core.model"}
    assert body["architecture_changed"]["edges"] == []


def test_api_state_returns_the_most_recent_event_of_each_kind(monkeypatch, tmp_path):
    # The journal is a process-wide singleton (not reset between tests), so
    # this asserts "most recent wins", not "empty at start" — the latter
    # would be order-dependent across the test suite.
    app = _build(monkeypatch, tmp_path)
    journal = get_journal()
    journal.emit(
        "architecture_changed",
        {
            "nodes": [
                {
                    "id": "core.harness",
                    "kind": "harness",
                    "hosting": "local",
                    "label_fr": "Harnais",
                    "wanted": True,
                    "available": True,
                    "reason_fr": None,
                }
            ],
            "edges": [],
        },
    )
    journal.emit("session_state", {"state": "idle", "reason_fr": "le plus récent"})

    body = _client(app).get("/api/state").json()

    assert body["session_state"]["reason_fr"] == "le plus récent"
    assert body["seq"] == journal.last_seq()


def test_select_model_emits_initial_state_so_api_state_is_populated(monkeypatch, tmp_path):
    """A manually picked model (no auto-detected candidate) must still boot
    the front: `/api/state` cannot stay null forever after a ready select_model."""
    app = _build(monkeypatch, tmp_path)
    monkeypatch.setattr(DiagnosticSession, "check_model", lambda self: DiagnosticResult(ready=True))

    response = _client(app).post(
        "/api/intentions/select_model",
        json={"path": "/fake/model.gguf"},
        headers={"origin": "http://127.0.0.1:8421"},
    )
    assert response.json()["ready"] is True

    body = _client(app).get("/api/state").json()
    assert body["session_state"]["state"] == "idle"
    assert body["architecture_changed"] is not None


class _FakeRequest:
    """A request that reports "already disconnected": `_sse_stream` replays
    `events_since(seq)` then returns immediately, instead of blocking on the
    live queue. Exercises exactly the resume logic AD-1/`/api/stream` relies
    on, without needing a real, indefinitely-open HTTP connection."""

    def __init__(self, last_event_id: str | None) -> None:
        self.headers = {"last-event-id": last_event_id} if last_event_id else {}

    async def is_disconnected(self) -> bool:
        return True


def test_stream_resumes_from_last_event_id_without_duplicates():
    journal = get_journal()
    before = journal.emit("session_state", {"state": "idle", "reason_fr": None})
    after = journal.emit("session_state", {"state": "idle", "reason_fr": "après reprise"})

    async def _collect() -> str:
        response = _sse_stream(_FakeRequest(str(before.seq)))
        return "".join([chunk async for chunk in response.body_iterator])

    body = asyncio.run(_collect())

    assert f"id: {after.seq}" in body
    assert f"id: {before.seq}" not in body
