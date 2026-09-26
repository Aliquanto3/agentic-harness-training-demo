from __future__ import annotations

import asyncio

from fake_engine import FakeEngine, booted_session
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


def test_pages_and_static_files_are_revalidated_but_api_is_not(monkeypatch, tmp_path):
    client = _client(_build(monkeypatch, tmp_path))
    for path in ("/", "/diagnostic", "/static/app.js"):
        assert client.get(path).headers["cache-control"] == "no-cache", path
    assert "cache-control" not in client.get("/api/health").headers


def test_api_state_reflects_last_known_session_state_and_architecture(monkeypatch, tmp_path):
    app = _build(monkeypatch, tmp_path)
    booted_session(FakeEngine())

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
    monkeypatch.setattr(
        DiagnosticSession,
        "select_model",
        lambda self, path, hot=False: DiagnosticResult(ready=True, model_path="/fake/model.gguf"),
    )

    response = _client(app).post(
        "/api/intentions/select_model",
        json={"path": "/fake/model.gguf"},
        headers={"origin": "http://127.0.0.1:8421"},
    )
    assert response.json()["ready"] is True
    app.state.app_session.join()

    body = _client(app).get("/api/state").json()
    # The fake path cannot load: idle, but sending is unavailable with the reason.
    assert body["session_state"]["state"] == "idle"
    assert "Envoi indisponible" in body["session_state"]["reason_fr"]
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


class _OpenOnceRequest:
    """Connected for one wait on the live queue, then disconnected."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.checks = 0

    async def is_disconnected(self) -> bool:
        self.checks += 1
        return self.checks > 1


def test_an_event_emitted_during_the_replay_is_never_lost_nor_repeated():
    """A long journal streams slowly: an event emitted while the history is being sent (a
    model switch clicked on a page that just opened) still reaches the page, once."""
    journal = get_journal()
    journal.emit("session_state", {"state": "idle", "reason_fr": "un"})
    journal.emit("session_state", {"state": "idle", "reason_fr": "deux"})

    async def _collect() -> list[str]:
        response = _sse_stream(_OpenOnceRequest())
        chunks = response.body_iterator
        received = [await anext(chunks), await anext(chunks)]  # the instance, then history
        live = journal.emit("session_state", {"state": "idle", "reason_fr": "pendant"})
        received += [chunk async for chunk in chunks]
        received.append(f"live={live.seq}")
        return received

    received = asyncio.run(_collect())
    live = int(received.pop().removeprefix("live="))
    ids = [c.split("\n")[0] for c in received if c.startswith("id: ")]
    assert f"id: {live}" in ids
    assert len(ids) == len(set(ids))  # the replay and the queue never give one twice


def test_stream_starts_with_the_server_instance_outside_the_envelope():
    """A1: a tab left open across a relaunch learns, on reconnecting, that the journal
    behind the stream is another one, whatever `Last-Event-ID` it sends."""
    journal = get_journal()
    journal.emit("session_state", {"state": "idle", "reason_fr": None})

    async def _collect(last_event_id: str | None) -> str:
        response = _sse_stream(_FakeRequest(last_event_id))
        return "".join([chunk async for chunk in response.body_iterator])

    for last_event_id in (None, str(journal.last_seq() + 1000)):
        body = asyncio.run(_collect(last_event_id))
        first, _, rest = body.partition("\n\n")
        assert first == (
            f'event: server_instance\ndata: {{"instance_id": "{journal.instance_id}"}}'
        )
        assert "id:" not in first  # never moves the client's `Last-Event-ID`
        assert "server_instance" not in rest


def test_state_gives_the_journal_instance(monkeypatch, tmp_path):
    app = _build(monkeypatch, tmp_path)

    body = _client(app).get("/api/state").json()

    assert body["instance_id"] == get_journal().instance_id
    assert len(body["instance_id"]) == 32


def test_select_model_boots_the_found_candidate_path(monkeypatch, tmp_path):
    _build(monkeypatch, tmp_path)
    received = []

    def recording_factory(path, n_ctx):
        received.append(path)
        return FakeEngine()

    monkeypatch.setattr(
        DiagnosticSession,
        "select_model",
        lambda self, path, hot=False: DiagnosticResult(ready=True, model_path=path),
    )
    app_session = AppSession(config.load_config(), engine_factory=recording_factory)
    app = create_app(
        DiagnosticSession(config.load_config(), port=8421),
        port=8421,
        version="test",
        app_session=app_session,
    )

    _client(app).post(
        "/api/intentions/select_model",
        json={"path": "/fake/model.gguf"},
        headers={"origin": "http://127.0.0.1:8421"},
    )
    app_session.join()

    assert received == ["/fake/model.gguf"]
    assert app_session.state == "idle" and app_session.reason_fr is None
