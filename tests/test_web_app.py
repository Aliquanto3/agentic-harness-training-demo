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


def test_models_page_and_tabs_shared_with_the_diagnostic(monkeypatch, tmp_path):
    """Story 25: `/models` answers, and both pages carry the same tabs, each marking itself."""
    client = _client(_build(monkeypatch, tmp_path))
    models = client.get("/models")
    assert models.status_code == 200 and "text/html" in models.headers["content-type"]
    assert '<a href="/models" aria-current="page">Modèles</a>' in models.text
    diagnostic = client.get("/diagnostic").text
    assert '<a href="/diagnostic" aria-current="page">Diagnostic</a>' in diagnostic
    assert '<a href="/models">Modèles</a>' in diagnostic
    for page in (models.text, diagnostic):  # one stylesheet; « Ouvrir » gated by `ready`
        assert '<link rel="stylesheet" href="/static/pages.css" />' in page
        assert '<a href="/" id="open-link" hidden>Ouvrir WaveStack</a>' in page


def test_api_diagnostic_contains_a_model_table_failure(monkeypatch, tmp_path):
    """Story 25 (AD-16): the table failing leaves `/api/diagnostic` whole, without `models`
    (the picker then lists the candidates as before)."""
    from wavestack.models import catalog

    def broken(*args, **kwargs):
        raise RuntimeError("table cassée")

    monkeypatch.setattr(catalog, "models_payload", broken)
    response = _client(_build(monkeypatch, tmp_path)).get("/api/diagnostic")
    assert response.status_code == 200
    body = response.json()
    assert "models" not in body
    assert body["candidates"] == [] and body["cloud"]["models"]


def test_pages_and_static_files_are_revalidated_but_api_is_not(monkeypatch, tmp_path):
    client = _client(_build(monkeypatch, tmp_path))
    for path in ("/", "/diagnostic", "/models", "/static/app.js", "/static/theme.js"):
        response = client.get(path)
        assert response.status_code == 200, path  # story 31: theme.js, without a new route
        assert response.headers["cache-control"] == "no-cache", path
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


class _OpenRequest:
    """A client still connected until the test says it left."""

    def __init__(self, last_event_id: str) -> None:
        self.headers = {"last-event-id": last_event_id}
        self.gone = False

    async def is_disconnected(self) -> bool:
        return self.gone


def _seqs(chunks: list[str]) -> list[int]:
    return [
        int(line[4:]) for chunk in chunks for line in chunk.split("\n") if line.startswith("id: ")
    ]


async def _read_until(
    iterator, request: _OpenRequest, seq: int, chunks: list[str]
) -> tuple[list[str], int]:
    """Reads on up to the chunk carrying `seq`, then up to a sentinel emitted after it: a
    duplicate still waiting in the queue would come before the sentinel. Gives the sentinel's
    `seq` too."""

    async def _up_to(target: int) -> None:
        while target not in _seqs(chunks):
            chunks.append(await asyncio.wait_for(anext(iterator), timeout=2))

    await _up_to(seq)
    sentinel = get_journal().emit("session_state", {"state": "idle", "reason_fr": "fin"}).seq
    await _up_to(sentinel)
    request.gone = True
    chunks.extend([chunk async for chunk in iterator])
    return chunks, sentinel


def test_stream_keeps_an_event_emitted_during_the_replay():
    """An event emitted while the snapshot is being sent reaches this stream, once, after
    the replayed ones and in `seq` order (it used to be lost: subscribed after the replay)."""
    journal = get_journal()
    start = journal.last_seq()
    replayed = [
        journal.emit("session_state", {"state": "idle", "reason_fr": str(i)}) for i in range(3)
    ]

    async def _collect() -> tuple[int, list[str], int]:
        request = _OpenRequest(str(start))
        iterator = _sse_stream(request).body_iterator
        chunks = [await anext(iterator), await anext(iterator)]  # instance, first replayed
        late = journal.emit("session_state", {"state": "idle", "reason_fr": "pendant le rejeu"})
        return late.seq, *await _read_until(iterator, request, late.seq, chunks)

    late_seq, chunks, sentinel = asyncio.run(_collect())

    assert _seqs(chunks) == [e.seq for e in replayed] + [late_seq, sentinel]


def test_stream_drops_the_overlap_between_subscription_and_snapshot(monkeypatch):
    """An event emitted after the subscription but before the snapshot is in both: it is
    sent once, from the snapshot."""
    journal = get_journal()
    start = journal.last_seq()
    replayed = journal.emit("session_state", {"state": "idle", "reason_fr": "avant"})
    snapshot = journal.events_since

    def racing_events_since(seq: int):
        journal.emit("session_state", {"state": "idle", "reason_fr": "course"})
        return snapshot(seq)

    monkeypatch.setattr(journal, "events_since", racing_events_since)
    racing_seq = replayed.seq + 1

    async def _collect() -> tuple[list[str], int]:
        request = _OpenRequest(str(start))
        iterator = _sse_stream(request).body_iterator
        return await _read_until(iterator, request, racing_seq, [])

    chunks, sentinel = asyncio.run(_collect())

    # The racing event was queued too (subscribed first): sent once, from the snapshot.
    assert _seqs(chunks) == [replayed.seq, racing_seq, sentinel]


def test_stream_with_an_id_of_another_instance_still_sends_live_events():
    """A `Last-Event-ID` beyond this journal's tip (a relaunch, tab left open) replays
    nothing, but the live events still reach the stream."""
    journal = get_journal()

    async def _collect() -> tuple[int, list[str], int]:
        request = _OpenRequest(str(journal.last_seq() + 1000))
        iterator = _sse_stream(request).body_iterator
        chunks = [await anext(iterator)]  # the instance
        live = journal.emit("session_state", {"state": "idle", "reason_fr": "en direct"})
        return live.seq, *await _read_until(iterator, request, live.seq, chunks)

    live_seq, chunks, sentinel = asyncio.run(_collect())

    assert _seqs(chunks) == [live_seq, sentinel]


def test_stream_unsubscribes_when_the_client_leaves_during_the_replay():
    journal = get_journal()
    start = journal.last_seq()
    for i in range(3):
        journal.emit("session_state", {"state": "idle", "reason_fr": str(i)})
    before = len(journal._subscribers)

    async def _leave() -> None:
        iterator = _sse_stream(_OpenRequest(str(start))).body_iterator
        await anext(iterator)
        await anext(iterator)
        assert len(journal._subscribers) == before + 1
        await iterator.aclose()

    asyncio.run(_leave())

    assert len(journal._subscribers) == before


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
