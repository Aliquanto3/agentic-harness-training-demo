"""Corrections of 2026-09-30, story 6: the MCP workshop (`/mcp`), the protocol laid bare.

The local server is the real glossary, a child process over stdio; the public ones answer
from `McpWeb`, in process, behind the real async client factory: nothing leaves the
machine. The workshop's connections are its own: the brick's never change.
"""

from __future__ import annotations

import json
import time

import test_mcp
from starlette.testclient import TestClient
from test_mcp import (
    MSLEARN_TOOLS,
    McpWeb,
    enable,
    local_servers,
    mcp_session,
    no_local_server_left,
    since,
)
from test_tools import call
from test_turn import _run

from wavestack.mcp import lab as mcp_lab
from wavestack.mcp.servers import load_local_tools
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import TraceScope
from wavestack.web.app import create_app

# The fixtures of test_mcp.py: its loop (AD-24) and its in-process public servers.
loop = test_mcp.loop
web = test_mcp.web

HEADERS = {"origin": "http://127.0.0.1:8421"}
KINDS = ("mcp_lab_message", "mcp_lab_connect_ended", "mcp_lab_call_ended")


def wait_idle(session: AppSession, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and session.state != "idle":
        time.sleep(0.02)
    session.join()
    assert session.state == "idle", session.state


def lab_events(mark: int) -> list:
    return [e for e in get_journal().events_since(mark) if e.kind in KINDS]


def connect(session: AppSession, server: str = "local") -> tuple[str, list, dict]:
    """One connection of the workshop, the worker joined: its id, its messages and its end."""
    mark = get_journal().last_seq()
    step_id = session.mcp_lab_connect(server)
    wait_idle(session)
    events = lab_events(mark)
    messages = [e for e in events if e.kind == "mcp_lab_message"]
    (ended,) = [e.payload for e in events if e.kind == "mcp_lab_connect_ended"]
    return step_id, messages, ended


def lab_call(session: AppSession, server: str, tool: str, **args) -> tuple[list, dict]:
    mark = get_journal().last_seq()
    session.mcp_lab_call(server, tool, args)
    wait_idle(session)
    events = lab_events(mark)
    messages = [e.payload for e in events if e.kind == "mcp_lab_message"]
    (ended,) = [e.payload for e in events if e.kind == "mcp_lab_call_ended"]
    return messages, ended


def brick_state(session: AppSession) -> tuple:
    return (
        set(session._mcp_enabled),
        session._mcp_lazy,
        dict(session._mcp_conns),
        sorted(session._registry.names),
    )


def _client(session: AppSession) -> TestClient:
    """No lifespan: the session keeps the test's loop (`attach_loop`)."""
    app = create_app(
        DiagnosticSession(session.cfg, port=8421), port=8421, version="t", app_session=session
    )
    return TestClient(app, base_url="http://127.0.0.1:8421")


# ---------- the capture and the helpers, alone ----------


def test_the_capture_times_a_response_from_its_request():
    from mcp_types import JSONRPCRequest, JSONRPCResponse

    seen = []
    capture = mcp_lab.Capture(lambda payload, step: seen.append((step, payload)))
    capture.begin("mcp3")
    capture.record("to_server", JSONRPCRequest(jsonrpc="2.0", id=1, method="tools/list"))
    capture.record("from_server", JSONRPCResponse(jsonrpc="2.0", id=1, result={"tools": []}))
    (step_a, request), (step_b, response) = seen
    assert step_a == step_b == "mcp3"
    assert (request["direction"], request["method"]) == ("to_server", "tools/list")
    assert (response["direction"], response["method"]) == ("from_server", "tools/list")
    assert json.loads(response["jsonrpc"]) == {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
    assert not request["reconstructed"] and not response["reconstructed"]
    assert capture.received("tools/list") == response["jsonrpc"]
    capture.record("to_server", object())  # never raises: the exchange goes on uncaptured
    assert len(seen) == 2


def test_catalog_line_and_step_number():
    assert mcp_lab.catalog_line("local__x", "Première ligne\nseconde", 120) == (
        "- local__x : Première ligne"
    )
    assert mcp_lab.catalog_line("local__x", "", 120) == "- local__x"
    assert mcp_lab.catalog_line("a", "x" * 10, 4) == "- a : xxxx…"
    assert mcp_lab.step_number("mcp12") == 12 and mcp_lab.step_number("lab1") is None


class _Envelope:
    """What `last_session` reads of an envelope."""

    def __init__(self, kind: str, step_id: str | None, context_id: str = "mcp_lab") -> None:
        self.kind, self.step_id, self.context_id = kind, step_id, context_id

    def model_dump(self, mode: str) -> dict:
        return {"kind": self.kind, "step_id": self.step_id}


def test_last_session_is_the_last_connection_and_its_calls():
    journal = [
        _Envelope("mcp_lab_message", "mcp3"),  # a first connection, then a call on it
        _Envelope("mcp_lab_connect_ended", "mcp3"),
        _Envelope("mcp_lab_message", "mcp4"),
        _Envelope("outbound_request", "mcp4"),
        _Envelope("mcp_lab_call_ended", "mcp4"),
        _Envelope("tool_ended", "mcp4"),  # not a kind of the workshop
        _Envelope("mcp_lab_message", "mcp4", context_id="main"),  # another context
        _Envelope("session_state", None),
        _Envelope("mcp_lab_message", "mcp5"),  # the connection after it
        _Envelope("mcp_lab_connect_ended", "mcp5"),
        _Envelope("mcp_lab_message", "mcp6"),
        _Envelope("mcp_lab_call_ended", "mcp6"),
    ]

    def steps(first: int) -> list[tuple]:
        return [(e["kind"], e["step_id"]) for e in mcp_lab.last_session(journal, first)]

    assert steps(5) == [
        ("mcp_lab_message", "mcp5"),
        ("mcp_lab_connect_ended", "mcp5"),
        ("mcp_lab_message", "mcp6"),
        ("mcp_lab_call_ended", "mcp6"),
    ]
    assert steps(3)[:5] == [
        ("mcp_lab_message", "mcp3"),
        ("mcp_lab_connect_ended", "mcp3"),
        ("mcp_lab_message", "mcp4"),
        ("outbound_request", "mcp4"),
        ("mcp_lab_call_ended", "mcp4"),
    ]
    assert steps(0) == []  # no connection yet


def test_invalid_content_is_said_and_refuses_the_connection(monkeypatch):
    from fake_engine import FakeEngine, booted_session

    session = booted_session(FakeEngine())

    def broken(*_, **__):  # noqa: ANN202
        raise ValueError("fichier cassé")

    broken.cache_clear = lambda: None  # type: ignore[attr-defined]
    monkeypatch.setattr(mcp_lab, "load_lab_content", broken)
    mark = get_journal().last_seq()
    state = session.mcp_lab_state()
    assert state["content"] is None and "content/mcp_lab.yaml" in state["content_error_text"]
    assert session.mcp_lab_state()["content"] is None  # read twice, traced once
    try:
        session.mcp_lab_connect("local")
    except SendRefused as refused:
        assert "content/mcp_lab.yaml" in str(refused.reason_text)
    else:
        raise AssertionError("connection refused without the page's texts")
    events = get_journal().events_since(mark)
    assert [e for e in events if e.kind in KINDS] == []
    errors = [e for e in events if e.kind == "harness_error" and e.context_id == "mcp_lab"]
    assert len(errors) == 1
    assert session.state == "idle"


# ---------- the local server: a real child process ----------


def test_local_handshake_messages_weights_and_brick_untouched(loop):
    session = mcp_session(loop)
    before = brick_state(session)

    step_id, messages, ended = connect(session)

    assert step_id.startswith("mcp")
    shape = [(e.payload["direction"], e.payload["method"]) for e in messages]
    assert shape == [
        ("to_server", "initialize"),
        ("from_server", "initialize"),
        ("to_server", "notifications/initialized"),
        ("to_server", "tools/list"),
        ("from_server", "tools/list"),
    ]
    for envelope in messages:
        assert (envelope.context_id, envelope.turn_id, envelope.step_id) == (
            "mcp_lab",
            None,
            step_id,
        )
        assert (envelope.brick, envelope.component) == ("mcp", "mcp_lab.local")
        assert envelope.payload["reconstructed"] is False
        assert envelope.payload["elapsed_ms"] >= 0
        assert json.loads(envelope.payload["jsonrpc"])["jsonrpc"] == "2.0"
    answer = json.loads(messages[1].payload["jsonrpc"])
    assert answer["result"]["serverInfo"]["name"] == "wavestack-glossaire"

    assert ended["status"] == "ok" and ended["error_text"] is None
    names = [t["name"] for t in ended["tools"]]
    assert names == ["local__list_terms", "local__define_term"]
    assert [t["tool"] for t in ended["tools"]] == ["list_terms", "define_term"]
    for tool in ended["tools"]:  # fake engine: one token per byte, counted, not estimated
        assert tool["doc_tokens"] == len(tool["definition_text"].encode())
        assert tool["line_tokens"] == len(tool["line_text"].encode())
        assert tool["line_text"] in ended["lazy_definition_text"]
        assert json.loads(tool["definition_text"])["function"]["name"] == tool["name"]
    assert ended["full_tokens"] == sum(t["doc_tokens"] for t in ended["tools"])
    assert ended["lazy_tokens"] == len(ended["lazy_definition_text"].encode())
    assert ended["estimated"] is False
    lazy = json.loads(ended["lazy_definition_text"])
    assert lazy["function"]["name"] == "load_tool_doc"

    # The sandbox: the brick's state, connections and registry are untouched.
    assert brick_state(session) == before
    state = session.mcp_lab_state()
    assert state["open_server"] == "local"
    assert [e["kind"] for e in state["last_session"]][-1] == "mcp_lab_connect_ended"
    assert {s["id"]: s["transport"] for s in state["servers"]} == {
        "local": "stdio",
        "datagouv": "streamable_http",
        "mslearn": "streamable_http",
    }
    assert state["servers"][0]["command"] == "python -m wavestack.mcp.local_server fr"
    assert local_servers()

    # The definitions are the brick's own, as `_tool_definitions` renders them.
    enable(session)
    for tool in ended["tools"]:
        brick = json.dumps(session._registry.definition(tool["name"]), ensure_ascii=False)
        assert brick == tool["definition_text"]
    assert session._mcp_conns["local"] is not session._mcp_lab_conn

    session.close()
    assert no_local_server_left()


def test_valid_call_and_unknown_term(loop):
    session = mcp_session(loop)
    connect(session)

    messages, ended = lab_call(session, "local", "define_term", term="harnais")

    assert [(m["direction"], m["method"]) for m in messages] == [
        ("to_server", "tools/call"),
        ("from_server", "tools/call"),
    ]
    assert json.loads(messages[0]["jsonrpc"])["params"]["arguments"] == {"term": "harnais"}
    assert ended["status"] == "ok" and ended["error_text"] is None
    assert ended["raw"] == messages[1]["jsonrpc"]
    assert ended["text"].lower().startswith("harnais")
    assert ended["truncated"] is None and ended["duration_ms"] >= 0

    _, unknown = lab_call(session, "local", "define_term", term="zzz")

    assert unknown["status"] == "error"
    assert json.loads(unknown["raw"])["result"]["isError"] is True
    assert "Terme inconnu" in unknown["text"]
    assert unknown["text"].startswith("Erreur : ")  # reinjected as the brick does
    assert "is_error" in unknown["error_text"]
    assert session.mcp_lab_state()["open_server"] == "local"  # the server is still there
    session.close()
    assert no_local_server_left()


def test_a_call_needs_the_workshops_connection_and_a_listed_tool(loop):
    session = mcp_session(loop)
    mark = get_journal().last_seq()
    try:
        session.mcp_lab_call("local", "define_term", {"term": "MCP"})
    except SendRefused as refused:
        assert "Connectez-vous d'abord" in str(refused.reason_text)
    else:
        raise AssertionError("refused without a connection")
    connect(session)
    try:
        session.mcp_lab_call("local", "nope", {})
    except SendRefused as refused:
        assert "nope" in str(refused.reason_text)
    else:
        raise AssertionError("refused for a tool not listed")
    assert [e for e in lab_events(mark) if e.kind == "mcp_lab_call_ended"] == []
    session.close()


def test_next_connection_language_change_and_close_leave_no_process(loop, web):
    web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop)
    connect(session)
    assert local_servers()

    _, _, ended = connect(session, "mslearn")  # the next connection closes the former

    assert ended["status"] == "ok"
    assert no_local_server_left()
    connect(session)
    assert local_servers()
    session.set_language("en")  # the local server would describe its tools in English
    try:
        assert no_local_server_left()
        assert session.mcp_lab_state()["open_server"] is None
    finally:
        session.set_language("fr")
    connect(session)
    session.close()
    assert no_local_server_left()


def test_german_page_texts_and_the_local_tools_in_german(loop):
    session = mcp_session(loop)
    session.set_language("de")
    try:
        state = session.mcp_lab_state()
        assert state["content"]["title_text"].startswith("MCP-Werkstatt")
        assert state["servers"][0]["label_text"] == "WaveStack-Glossar"
        _, messages, ended = connect(session)
        assert ended["status"] == "ok"
        german = load_local_tools("de")
        assert [t["description"] for t in ended["tools"]] == [
            german.list_terms,
            german.define_term,
        ]
        assert [m.payload["method"] for m in messages][0] == "initialize"
    finally:
        session.set_language("fr")  # `settings.json` back in French for the next tests
        session.close()
    assert no_local_server_left()


# ---------- the public servers: in process ----------


def test_public_server_handshake_is_traced_under_the_workshop(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop)
    before = brick_state(session)
    mark = get_journal().last_seq()

    step_id, messages, ended = connect(session, "mslearn")

    assert ended["status"] == "ok" and len(ended["tools"]) == 3
    outbound = since(mark, "outbound_request")
    assert outbound and len(server.sent) == len(outbound)
    assert {(e.context_id, e.component, e.step_id) for e in outbound} == {
        ("mcp_lab", "mcp_lab.mslearn", step_id)
    }
    assert [m.payload["method"] for m in messages][:2] == ["initialize", "initialize"]
    assert brick_state(session) == before
    last = session.mcp_lab_state()["last_session"]
    assert {e["kind"] for e in last} == {*KINDS[:2], "outbound_request"}
    session.close()


def test_public_server_offline_is_said_without_breaking_the_page(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    server.offline = True
    session = mcp_session(loop)

    _, _, ended = connect(session, "datagouv")

    assert ended["status"] == "error" and ended["error_text"]
    assert ended["tools"] == []
    client = _client(session)
    page = client.get("/api/mcp_lab")
    assert page.status_code == 200 and page.json()["open_server"] is None
    session.close()


def test_json_rpc_error_and_delay_exceeded(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop, call_timeout_s=1)
    connect(session, "mslearn")

    server.error = {"code": -32602, "message": "Invalid params"}
    _, refused = lab_call(session, "mslearn", "microsoft_docs_search", query=1)

    assert refused["status"] == "error" and "refusé l'appel" in refused["error_text"]
    assert "Invalid params" in refused["raw"]

    server.error = None
    server.delay = 3
    _, late = lab_call(session, "mslearn", "microsoft_docs_search", query="MFA")

    assert late["status"] == "error" and "délai" in late["error_text"]
    session.close()


def test_stop_during_a_call_closes_the_connection(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop)
    connect(session, "mslearn")
    server.delay = 20
    mark = get_journal().last_seq()

    session.mcp_lab_call("mslearn", "microsoft_docs_search", {"query": "MFA"})
    deadline = time.monotonic() + 10
    while not [e for e in lab_events(mark) if e.kind == "mcp_lab_message"]:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert session.state == "mcp_lab"
    assert session.stop() is True
    wait_idle(session, timeout=15)

    (ended,) = [e.payload for e in lab_events(mark) if e.kind == "mcp_lab_call_ended"]
    assert ended["status"] == "error" and "arrêté" in ended["error_text"]
    assert session._mcp_lab_conn is None
    assert session.mcp_lab_state()["open_server"] is None
    assert session.stop() is False  # back in idle: nothing to stop
    session.close()


def test_stop_during_the_handshake(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    server.list_delay = 20
    session = mcp_session(loop)
    mark = get_journal().last_seq()

    session.mcp_lab_connect("mslearn")
    deadline = time.monotonic() + 10
    while not [e for e in lab_events(mark) if e.payload.get("method") == "tools/list"]:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    session.stop()
    wait_idle(session, timeout=15)

    (ended,) = [e.payload for e in lab_events(mark) if e.kind == "mcp_lab_connect_ended"]
    assert ended["status"] == "error" and "arrêté" in ended["error_text"]
    assert session._mcp_lab_conn is None
    session.close()


def test_a_server_gone_during_a_call_closes_the_workshops_connection(loop):
    session = mcp_session(loop)
    connect(session)
    (child,) = local_servers()
    child.kill()
    child.wait(5)

    try:
        _, ended = lab_call(session, "local", "define_term", term="MCP")
    except SendRefused:  # the connection's task saw the end first: refused before the call
        ended = None
    if ended is not None:
        assert ended["status"] == "error"
        assert "reconnectez-vous" in ended["error_text"]
    assert session.mcp_lab_state()["open_server"] is None
    try:
        session.mcp_lab_call("local", "define_term", {"term": "MCP"})
    except SendRefused as refused:
        assert "Connectez-vous d'abord" in str(refused.reason_text)
    else:
        raise AssertionError("refused once the connection is gone")
    session.close()
    assert no_local_server_left()


def test_lifespan_closes_the_workshops_connection():
    from fake_engine import FakeEngine
    from test_tools import QWEN

    from wavestack import config

    engine = FakeEngine(template=QWEN.decode("utf-8"), architecture="qwen35")
    session = AppSession(
        config.Config(values={"context": {"window": 4096, "near_limit_ratio": 0.8}}),
        engine_factory=lambda path, n_ctx: engine,
    )
    session.boot("fake.gguf").result()
    app = create_app(
        DiagnosticSession(config.load_config(), port=8421),
        port=8421,
        version="test",
        app_session=session,
    )
    with TestClient(app, base_url="http://127.0.0.1:8421") as client:  # enters the lifespan
        answer = client.post(
            "/api/intentions/mcp_lab_connect", json={"server": "local"}, headers=HEADERS
        )
        assert answer.status_code == 200
        wait_idle(session)
        assert session.mcp_lab_state()["open_server"] == "local"
        assert local_servers()

    assert no_local_server_left()


# ---------- the brick keeps its own connections ----------


def test_a_turn_uses_the_bricks_connection_while_the_workshops_is_open(loop):
    session = mcp_session(loop, [call("local__define_term", term="MCP"), "Voilà."])
    enable(session)
    brick_conn = session._mcp_conns["local"]
    connect(session)
    lab_conn = session._mcp_lab_conn
    assert lab_conn is not None and lab_conn is not brick_conn

    events = _run(session, "Que veut dire MCP ?")

    (ended,) = events["tool_ended"]
    assert ended["status"] == "ok" and "Model Context Protocol" in ended["result"]
    assert session._mcp_conns["local"] is brick_conn
    assert session._mcp_lab_conn is lab_conn and lab_conn.alive
    assert "mcp_lab_message" not in events  # the turn's call is the brick's
    session.close()
    assert no_local_server_left()


# ---------- the web layer ----------


def test_routes_page_snapshot_refusals(loop):
    session = mcp_session(loop)
    client = _client(session)
    assert client.get("/mcp").status_code == 200
    body = client.get("/api/mcp_lab").json()
    assert set(body) >= {
        "servers",
        "content",
        "content_error_text",
        "last_session",
        "session_state",
        "seq",
    }
    assert body["content"]["title_text"] and body["content_error_text"] is None
    assert body["last_session"] == [] and body["open_server"] is None
    assert body["call_presets"]["local__define_term"][0]["args"] == {"term": "MCP"}

    unknown = client.post("/api/intentions/mcp_lab_connect", json={"server": "x"}, headers=HEADERS)
    assert unknown.status_code == 404
    not_connected = client.post(
        "/api/intentions/mcp_lab_call",
        json={"server": "local", "tool": "define_term", "args": {"term": "MCP"}},
        headers=HEADERS,
    )
    assert not_connected.status_code == 409

    mark = get_journal().last_seq()
    session._set_state("turn", "Un tour est en cours.")
    busy = client.post("/api/intentions/mcp_lab_connect", json={"server": "local"}, headers=HEADERS)
    assert busy.status_code == 409 and "Un tour est en cours" in busy.json()["detail"]
    assert lab_events(mark) == []  # nothing started
    session._set_state("idle")

    ok = client.post("/api/intentions/mcp_lab_connect", json={"server": "local"}, headers=HEADERS)
    assert ok.status_code == 200 and ok.json()["step_id"].startswith("mcp")
    wait_idle(session)
    called = client.post(
        "/api/intentions/mcp_lab_call",
        json={"server": "local", "tool": "define_term", "args": {"term": "MCP"}},
        headers=HEADERS,
    )
    assert called.status_code == 200
    wait_idle(session)
    kinds = [e["kind"] for e in client.get("/api/mcp_lab").json()["last_session"]]
    assert kinds[-1] == "mcp_lab_call_ended"
    session.close()
    assert no_local_server_left()


def test_the_lab_scope_carries_the_context_to_the_http_hook():
    scope = TraceScope(**AppSession._mcp_lab_scope("mcp4", "mslearn"), origin="brick")
    assert (scope.context_id, scope.step_id, scope.component) == (
        "mcp_lab",
        "mcp4",
        "mcp_lab.mslearn",
    )
