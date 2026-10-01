from __future__ import annotations

import asyncio
import re

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


# Story 2 (2026-09-30): the bar shared by the five pages, in a fixed order.
SITE_PAGES = ("/", "/llm", "/rag", "/mcp", "/diagnostic", "/models")  # story 6: /mcp


def _site_nav(page: str) -> str:
    start = page.index('<nav class="site-nav"')
    return page[start : page.index("</nav>", start) + len("</nav>")]


def _projection_row(nav: str) -> str:
    """The lines of « Mode projection », the main screen's only (app.js applies it)."""
    start = nav.rfind('<div class="display-menu-row">', 0, nav.index('id="projection-toggle"'))
    start = nav.rfind("\n", 0, start) + 1
    return nav[start : nav.index("\n", nav.index("</div>", start)) + 1]


def test_every_page_opens_on_the_same_shared_bar(monkeypatch, tmp_path):
    """Story 2 (2026-09-30): the same `nav.site-nav` at the head of the five pages, but for
    `aria-current` (one, on the page's own link) and the projection mode (the main screen's):
    the brand, then the five pages in a fixed order, then « Affichage ▾ » with the theme and
    the language. No `.page-tabs`, « ← Atelier » nor « Ouvrir WaveStack » left."""
    client = _client(_build(monkeypatch, tmp_path))
    navs = {}
    for path in SITE_PAGES:
        response = client.get(path)
        assert response.status_code == 200 and "text/html" in response.headers["content-type"]
        page = response.text
        assert page.count('<nav class="site-nav"') == 1, path
        body = page[page.index("<body") :]
        # At the head of the page: the first element of `<body>` (comments aside).
        first = re.sub(r"<!--.*?-->", "", body[body.index(">") + 1 :], flags=re.S).lstrip()
        assert first.startswith('<nav class="site-nav"'), path
        for gone in ('class="page-tabs"', 'id="back-link"', 'id="open-link"', 'id="llm-link"'):
            assert gone not in page, (path, gone)
        assert 'id="rag-link"' not in page and 'class="top-bar-title"' not in page, path
        nav = _site_nav(page)
        assert nav.count('aria-current="page"') == 1, path
        current = nav[: nav.index('aria-current="page"')]
        assert current[current.rindex("<a ") :].startswith(f'<a href="{path}"'), path
        assert "site-nav-brand" not in current[current.rindex("<a ") :], path
        hrefs = re.findall(r'<a href="([^"]*)"', nav)
        assert hrefs == ["/", *SITE_PAGES], (path, hrefs)
        assert '<a href="/" class="site-nav-brand">WaveStack</a>' in nav
        assert 'data-i18n-aria-label="common.links.pages" data-i18n-links>' in nav
        for control in ('id="display-menu"', 'id="theme-picker"', 'id="language-picker"'):
            assert control in nav, (path, control)
        assert nav.index("/models") < nav.index('id="display-menu"'), path
        assert ('id="projection-toggle"' in page) == (path == "/"), path
        if path == "/":
            nav = nav.replace(_projection_row(nav), "")
        navs[path] = nav.replace(' aria-current="page"', "")
    assert len(set(navs.values())) == 1, "the five copies of the bar differ"


def test_the_main_screen_bar_is_under_the_panes(monkeypatch, tmp_path):
    """Story 2 (2026-09-30): `header.top-bar` after the panes, without the title, the screen
    links nor « Affichage ▾ », « Réinitialiser » still in it; pages.css shared."""
    client = _client(_build(monkeypatch, tmp_path))
    index = client.get("/").text
    bar = index[
        index.index('<header class="top-bar">') : index.index(
            "</header>", index.index('<header class="top-bar">')
        )
    ]
    assert index.index("</main>") < index.index('<header class="top-bar">')
    assert 'id="reset-button"' in bar and 'id="scenario-picker"' in bar
    assert 'id="display-menu"' not in bar and "screen-link" not in bar
    for path in SITE_PAGES:
        page = client.get(path).text
        assert '<link rel="stylesheet" href="/static/pages.css" />' in page, path
        assert page.index('src="/static/i18n.js"') < page.index('src="/static/site-nav.js"'), path


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
    pages = ("/", "/diagnostic", "/models", "/llm", "/static/app.js", "/static/theme.js")
    story_pages = ("/static/llm.js", "/static/llm.css", "/rag", "/static/rag.js")
    for path in (*pages, *story_pages, "/static/rag.css"):  # stories 29 and 30
        response = client.get(path)
        assert response.status_code == 200, path  # story 31: theme.js, without a new route
        assert response.headers["cache-control"] == "no-cache", path
    assert "cache-control" not in client.get("/api/health").headers


def test_favicon_is_served_and_declared_on_every_page(monkeypatch, tmp_path):
    """Lot K, suite (K7): `/favicon.ico` (asked by Edge) and the SVG icon answer 200, and the
    five pages declare the icon."""
    client = _client(_build(monkeypatch, tmp_path))
    for path in ("/favicon.ico", "/static/favicon.svg"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("image/svg+xml"), path
        assert response.text.lstrip().startswith("<svg"), path
    link = '<link rel="icon" href="/static/favicon.svg" type="image/svg+xml" />'
    for page in ("/", "/diagnostic", "/models", "/llm", "/rag"):
        text = client.get(page).text
        assert link in text[: text.index("</head>")], page


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
                    "label_text": "Harnais",
                    "wanted": True,
                    "available": True,
                    "reason_text": None,
                }
            ],
            "edges": [],
        },
    )
    journal.emit("session_state", {"state": "idle", "reason_text": "le plus récent"})

    body = _client(app).get("/api/state").json()

    assert body["session_state"]["reason_text"] == "le plus récent"
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
    assert "Envoi indisponible" in body["session_state"]["reason_text"]
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
    before = journal.emit("session_state", {"state": "idle", "reason_text": None})
    after = journal.emit("session_state", {"state": "idle", "reason_text": "après reprise"})

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
    sentinel = get_journal().emit("session_state", {"state": "idle", "reason_text": "fin"}).seq
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
        journal.emit("session_state", {"state": "idle", "reason_text": str(i)}) for i in range(3)
    ]

    async def _collect() -> tuple[int, list[str], int]:
        request = _OpenRequest(str(start))
        iterator = _sse_stream(request).body_iterator
        chunks = [await anext(iterator), await anext(iterator)]  # instance, first replayed
        late = journal.emit("session_state", {"state": "idle", "reason_text": "pendant le rejeu"})
        return late.seq, *await _read_until(iterator, request, late.seq, chunks)

    late_seq, chunks, sentinel = asyncio.run(_collect())

    assert _seqs(chunks) == [e.seq for e in replayed] + [late_seq, sentinel]


def test_stream_drops_the_overlap_between_subscription_and_snapshot(monkeypatch):
    """An event emitted after the subscription but before the snapshot is in both: it is
    sent once, from the snapshot."""
    journal = get_journal()
    start = journal.last_seq()
    replayed = journal.emit("session_state", {"state": "idle", "reason_text": "avant"})
    snapshot = journal.events_since

    def racing_events_since(seq: int):
        journal.emit("session_state", {"state": "idle", "reason_text": "course"})
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
        live = journal.emit("session_state", {"state": "idle", "reason_text": "en direct"})
        return live.seq, *await _read_until(iterator, request, live.seq, chunks)

    live_seq, chunks, sentinel = asyncio.run(_collect())

    assert _seqs(chunks) == [live_seq, sentinel]


def test_stream_unsubscribes_when_the_client_leaves_during_the_replay():
    journal = get_journal()
    start = journal.last_seq()
    for i in range(3):
        journal.emit("session_state", {"state": "idle", "reason_text": str(i)})
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
    journal.emit("session_state", {"state": "idle", "reason_text": None})

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


def test_the_session_spend_is_in_the_state_and_has_its_place_in_the_top_bar(monkeypatch, tmp_path):
    """FinOps: `/api/state` gives the session's spend (`None` before a paid call), for a
    reloaded page; `#consumption` follows the gauge's figures; `/models` has « Prix »."""
    from wavestack.models import openai_chat

    client = _client(_build(monkeypatch, tmp_path))
    assert client.get("/api/state").json()["consumption_updated"] is None

    openai_chat.record_spend(openai_chat.CallCost(0.001, 0.002, "api"), 0.86)

    spend = client.get("/api/state").json()["consumption_updated"]
    assert spend["total_in_usd"] == 0.001 and spend["total_out_usd"] == 0.002
    assert spend["calls"] == 1 and spend["approx"] is False
    assert spend["total_eur"] == (0.001 + 0.002) * 0.86
    index = client.get("/").text
    assert index.index('id="gauge-figures"') < index.index('id="consumption"')
    assert '<th scope="col">Prix</th>' in client.get("/models").text


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
    assert app_session.state == "idle" and app_session.reason_text is None
