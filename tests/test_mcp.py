"""Story 6: MCP servers, local (real child process) and public (`httpx2.MockTransport`).

Nothing leaves the machine: public servers answer from a JSON-RPC handler behind
the real async client factory.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time

import httpx2
import psutil
import pytest
from fake_engine import FakeEngine
from test_tools import QWEN, _segments, call
from test_turn import _run

from wavestack import config
from wavestack.mcp import connection
from wavestack.mcp.servers import load_mcp_content, mcp_servers
from wavestack.net.factory import create_async_client
from wavestack.session.app_session import AppSession
from wavestack.tools.parser import parse_tool_calls
from wavestack.trace.journal import get_journal

MSLEARN_TOOLS = [
    {
        "name": "microsoft_docs_search",
        "description": "Search official Microsoft/Azure documentation.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The question."}},
            "required": ["query"],
        },
    },
    {
        "name": "microsoft_code_sample_search",
        "description": "Search code snippets in Microsoft Learn.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."},
                "language": {"type": ["string", "null"], "description": "Optional language."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "microsoft_docs_fetch",
        "description": "Fetch a Microsoft Learn page as markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Page address."}},
            "required": ["url"],
        },
    },
]


@pytest.fixture
def loop():
    """FastAPI's loop stand-in: a loop running in its own thread (AD-24)."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(5)


class McpWeb:
    """A Streamable HTTP MCP server, answered in process; records what reached it."""

    def __init__(self, tools: list[dict], answer=None) -> None:
        self.tools = tools
        self.answer = answer or (lambda params: {"content": [{"type": "text", "text": "ok"}]})
        self.offline = False
        self.delay = 0.0  # before answering `tools/call`
        self.list_delay = 0.0  # before answering `tools/list`
        self.error: dict | None = None  # a JSON-RPC error answering `tools/call`
        self.sent: list[httpx2.Request] = []

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.sent.append(request)
        if self.offline:
            raise httpx2.ConnectError("no route", request=request)
        if request.method != "POST":
            return httpx2.Response(405)
        message = json.loads(request.content)
        if "id" not in message:
            return httpx2.Response(202)
        method = message["method"]
        if method == "initialize":
            result = {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test", "version": "1"},
            }
        elif method == "tools/list":
            await asyncio.sleep(self.list_delay)
            result = {"tools": self.tools}
        else:
            await asyncio.sleep(self.delay)
            if self.error is not None:
                body = {"jsonrpc": "2.0", "id": message["id"], "error": self.error}
                return httpx2.Response(200, json=body, headers={"mcp-session-id": "s1"})
            result = self.answer(message["params"])
        body = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        return httpx2.Response(200, json=body, headers={"mcp-session-id": "s1"})


@pytest.fixture
def web(monkeypatch):
    def install(server: McpWeb) -> McpWeb:
        monkeypatch.setattr(
            connection,
            "create_async_client",
            lambda **kw: create_async_client(transport=httpx2.MockTransport(server), **kw),
        )
        return server

    return install


def mcp_session(loop, outputs=("Voilà.",), *, window=4096, **mcp) -> AppSession:
    engine = FakeEngine(outputs=list(outputs), template=QWEN.decode("utf-8"), architecture="qwen35")
    values = {
        "context": {"window": window, "near_limit_ratio": 0.8},
        "mcp": {"connect_timeout_s": 10, "call_timeout_s": 10, **mcp},
    }
    session = AppSession(config.Config(values=values), engine_factory=lambda path, n_ctx: engine)
    session.boot("fake.gguf").result()
    session.attach_loop(loop)
    return session


def wait_for(session: AppSession, kind: str, mark: int, n: int = 1) -> list[dict]:
    """The payloads of `kind` since `mark`, once `n` arrived and the worker applied them."""
    deadline = time.monotonic() + 30
    while True:
        found = [e.payload for e in get_journal().events_since(mark) if e.kind == kind]
        if len(found) >= n or time.monotonic() > deadline:
            break
        time.sleep(0.02)
    session.join()
    return found


def since(mark: int, kind: str) -> list:
    return [e for e in get_journal().events_since(mark) if e.kind == kind]


def node(session: AppSession, node_id: str) -> dict | None:
    architecture = since(0, "architecture_changed")[-1].payload
    return next((n for n in architecture["nodes"] if n["id"] == node_id), None)


def enable(session: AppSession, server: str | None = None) -> dict:
    """Enable the brick (and `server`); returns that server's `mcp_connect_ended`."""
    mark = get_journal().last_seq()
    session.set_brick("mcp", True)
    if server is not None:
        session.set_mcp_server(server, True)
    wanted = server or "local"
    deadline = time.monotonic() + 30
    while (
        not (
            ended := [
                p for p in wait_for(session, "mcp_connect_ended", mark) if p["server"] == wanted
            ]
        )
        and time.monotonic() < deadline
    ):
        time.sleep(0.02)
    return ended[-1]


def card(brick_id: str) -> dict:
    bricks = since(0, "bricks_changed")[-1].payload["bricks"]
    return next(b for b in bricks if b["id"] == brick_id)


def no_local_server_left() -> bool:
    deadline = time.monotonic() + 10
    while local_servers() and time.monotonic() < deadline:
        time.sleep(0.05)
    return local_servers() == []


def local_servers() -> list[psutil.Process]:
    children = psutil.Process().children(recursive=True)
    found = []
    for child in children:
        try:
            if "wavestack.mcp.local_server" in " ".join(child.cmdline()):
                found.append(child)
        except psutil.Error:
            pass
    return found


# ---------- local server: a real child process, offline ----------


def test_local_server_lifecycle_call_and_shutdown(loop):
    session = mcp_session(
        loop,
        [call("local__define_term", term="MCP"), call("local__define_term", term="zzz"), "Voilà."],
    )
    session.set_mcp_server("datagouv", False)  # public servers start disabled anyway
    mark = get_journal().last_seq()

    ended = enable(session)

    (started,) = [e.payload for e in since(mark, "mcp_connect_started")]
    assert started["server"] == "local" and "Glossaire" in started["phase_label"]
    assert ended["status"] == "ok" and ended["error_fr"] is None
    assert ended["tools"] == ["local__list_terms", "local__define_term"]
    assert since(mark, "outbound_request") == []
    assert local_servers()  # the venv launcher may add a second process
    local = node(session, "mcp.local")
    assert (local["kind"], local["hosting"], local["contact"], local["available"]) == (
        "mcp_server",
        "local",
        "available",
        True,
    )
    assert local["tools"] == ended["tools"]
    assert local.get("sends_fr") is None  # story 34: nothing leaves the workstation
    assert node(session, "mcp.datagouv") is None  # drawn only once its sub-option is on
    preview = since(mark, "context_preview")[-1].payload
    catalog = _segments(preview, "tool_catalog")
    assert [(s["brick"], s["component"]) for s in catalog] == [("mcp", "mcp.local")] * 2
    assert session.build_turn_state().tools == ("local__list_terms", "local__define_term")

    events = _run(session, "Que veut dire MCP ?")

    assert [e["source"] for e in events["tool_started"]] == ["mcp_local"] * 2
    ok, unknown = events["tool_ended"]
    assert ok["status"] == "ok" and "Model Context Protocol" in ok["result"]
    assert unknown["status"] == "error" and "Terme inconnu" in unknown["error_fr"]
    assert "outbound_request" not in events
    results = _segments(events["context_rendered"][-1], "tool_result")
    assert results[0]["component"] == "mcp.local" and results[0]["brick"] == "mcp"
    assert results[1]["text"].startswith("Erreur : Terme inconnu")
    assert node(session, "mcp.local")["available"]  # a tool error is not a lost server

    session.set_brick("mcp", False)  # the process stops, the tools leave the next turn
    session.join()
    deadline = time.monotonic() + 10
    while local_servers() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert local_servers() == []
    assert session.build_turn_state().tools == ()

    enable(session)  # re-enabled: a new process
    assert local_servers()  # the venv launcher may add a second process
    session.close()  # AD-21: nothing survives WaveStack
    assert local_servers() == []


# ---------- public servers: in-process HTTP ----------


def test_public_server_discovery_is_traced_and_weighs_in_the_gauge(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop)
    session.set_mcp_server("local", False)
    session.set_brick("mcp", True)
    session.join()
    before = since(0, "context_preview")[-1].payload
    assert since(get_journal().last_seq(), "outbound_request") == []
    mark = get_journal().last_seq()
    session.set_mcp_server("mslearn", True)
    assert node(session, "mcp.mslearn")["contact"] == "not_contacted"  # drawn, being contacted

    ended = wait_for(session, "mcp_connect_ended", mark)[-1]

    assert ended["status"] == "ok" and len(ended["tools"]) == 3
    outbound = since(mark, "outbound_request")
    methods = [json.loads(e.payload["body"]).get("method") for e in outbound if e.payload["body"]]
    assert methods[:3] == ["initialize", "notifications/initialized", "tools/list"]
    assert {e.turn_id for e in outbound} == {None}  # out of any turn
    assert {(e.payload["origin"], e.component) for e in outbound} == {("brick", "mcp.mslearn")}
    assert outbound[0].payload["url"] == "https://learn.microsoft.com/api/mcp"
    assert len(server.sent) == len(outbound)  # everything sent was traced first
    mslearn = node(session, "mcp.mslearn")
    assert (mslearn["hosting"], mslearn["contact"], mslearn["available"]) == (
        "network",
        "available",
        True,
    )
    after = since(mark, "context_preview")[-1].payload
    catalog = _segments(after, "tool_catalog")
    assert {s["component"] for s in catalog} == {"mcp.mslearn"} and len(catalog) == 3
    assert after["used"] - before["used"] >= sum(s["tokens"] for s in catalog)
    card = next(b for b in since(mark, "bricks_changed")[-1].payload["bricks"] if b["id"] == "mcp")
    assert [(o["id"], o["enabled"], o["hosting_fr"]) for o in card["options"]] == [
        ("local", False, "Local"),
        ("datagouv", False, "RÉSEAU"),
        ("mslearn", True, "RÉSEAU"),
    ]
    assert card["pending"]
    session.close()


def test_public_call_sends_the_exact_body_then_a_delay_makes_it_unavailable(loop, web):
    def answer(params):
        return {"content": [{"type": "text", "text": f"Résultat pour {params['arguments']}"}]}

    server = web(McpWeb(MSLEARN_TOOLS, answer))
    outputs = [
        call("mslearn__microsoft_docs_search", query="accès conditionnel"),
        call("mslearn__microsoft_docs_search", query="lent"),
        "Voilà.",
    ]
    session = mcp_session(loop, outputs, call_timeout_s=0.5)
    session.set_mcp_server("local", False)
    enable(session, "mslearn")
    mark = get_journal().last_seq()

    def slow_after_first(envelope) -> None:
        if envelope.kind == "tool_ended":
            server.delay = 2

    get_journal().subscribe(slow_after_first)
    try:
        events = _run(session, "Comment déployer une stratégie d'accès conditionnel ?")
    finally:
        get_journal().unsubscribe(slow_after_first)

    first = [e for e in get_journal().events_since(mark) if e.step_id == "t1.main.s2"]
    kinds = [e.kind for e in first]
    assert kinds[0] == "tool_started" and kinds[-1] == "tool_ended"
    (outbound,) = [e.payload for e in first if e.kind == "outbound_request"]
    body = json.loads(outbound["body"])
    assert body["method"] == "tools/call"
    assert body["params"]["name"] == "microsoft_docs_search"  # the server's own name
    assert body["params"]["arguments"] == {"query": "accès conditionnel"}
    assert first[0].payload["source"] == "mcp_public"
    assert {e.component for e in first} == {"mcp.mslearn"}
    ok, late = events["tool_ended"]
    assert ok["status"] == "ok" and "accès conditionnel" in ok["result"]
    assert _segments(events["context_rendered"][1], "tool_result")[0]["text"].startswith(
        "Résultat pour"
    )
    assert late["status"] == "error" and "délai" in late["error_fr"]
    mslearn = node(session, "mcp.mslearn")
    assert mslearn["contact"] == "unavailable" and not mslearn["available"]
    assert "délai" in mslearn["reason_fr"]
    assert events["turn_ended"][0]["status"] == "completed"
    assert session.build_turn_state().tools == ()  # an unavailable server lends no tool
    session.close()


def test_offline_server_is_unavailable_others_work_and_rechecking_retries(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    server.offline = True
    session = mcp_session(loop, [call("get_datetime"), "Il est midi."])
    session.set_mcp_server("local", False)
    session.set_brick("tools", True)

    ended = enable(session, "mslearn")

    assert ended["status"] == "error" and "injoignable" in ended["error_fr"]
    mslearn = node(session, "mcp.mslearn")
    assert (mslearn["contact"], mslearn["available"]) == ("unavailable", False)
    assert mslearn["reason_fr"] == ended["error_fr"]
    events = _run(session, "Quelle heure est-il ?")  # native tools still work
    assert events["tool_ended"][0]["status"] == "ok"

    server.offline = False
    mark = get_journal().last_seq()
    session.set_mcp_server("mslearn", False)
    session.set_mcp_server("mslearn", True)
    retried = wait_for(session, "mcp_connect_ended", mark)[-1]

    assert retried["status"] == "ok"
    assert node(session, "mcp.mslearn")["contact"] == "available"
    session.close()


def test_host_outside_the_list_is_refused_before_anything_is_sent(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop, urls={"mslearn": "https://mcp.example.test/mcp"})
    session.set_mcp_server("local", False)
    mark = get_journal().last_seq()

    ended = enable(session, "mslearn")

    assert ended["status"] == "error" and "refusée par le harnais" in ended["error_fr"]
    assert "mcp.example.test" in ended["error_fr"]
    assert server.sent == [] and since(mark, "outbound_request") == []
    assert node(session, "mcp.mslearn")["contact"] == "unavailable"
    session.close()


def test_disabling_a_server_closes_it_and_removes_its_tools(loop, web):
    web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop)
    session.set_mcp_server("local", False)
    enable(session, "mslearn")
    conn = session._mcp_conns["mslearn"]
    assert len(session.build_turn_state().tools) == 3

    session.set_mcp_server("mslearn", False)
    session.join()

    assert session.build_turn_state().tools == ()
    assert node(session, "mcp.mslearn") is None
    assert not session._registry.names or all(
        not n.startswith("mslearn__") for n in session._registry.names
    )
    deadline = time.monotonic() + 10
    while not conn._task.done() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert conn._task.done()
    session.close()


def test_datagouv_overflows_the_default_window_and_names_the_descriptions(loop, web):
    long = "Recherche dans les jeux de données publics de data.gouv.fr. " * 30
    tools = [
        {
            "name": f"tool_{i}",
            "description": long,
            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
        }
        for i in range(10)
    ]
    web(McpWeb(tools))
    session = mcp_session(loop)
    session.set_mcp_server("local", False)
    enable(session, "datagouv")
    # Story 34: a public server's node says what leaves the workstation (AD-19).
    assert node(session, "mcp.datagouv")["sends_fr"] == "la recherche et ses arguments"

    events = _run(session, "Bonjour")

    (overflow,) = events["context_overflow"]
    assert "descriptions d'outils" in overflow["message_fr"]
    assert "serveur MCP" in overflow["message_fr"]
    assert "model_call_started" not in events  # the call is not sent
    session.close()


def test_colliding_tool_names_leave_the_second_unavailable(loop, web):
    web(McpWeb([MSLEARN_TOOLS[0], {**MSLEARN_TOOLS[0], "description": "Doublon."}]))
    session = mcp_session(loop)
    session.set_mcp_server("local", False)
    mark = get_journal().last_seq()

    ended = enable(session, "mslearn")

    assert ended["tools"] == ["mslearn__microsoft_docs_search"]
    (error,) = [e.payload for e in since(mark, "harness_error")]
    assert "mslearn__microsoft_docs_search" in error["message_fr"]
    definition = session._registry.definition("mslearn__microsoft_docs_search")
    assert definition["function"]["description"] == MSLEARN_TOOLS[0]["description"]
    session.close()


def test_mcp_intention_http(loop):
    from test_bricks import HEADERS, _client

    session = mcp_session(loop)
    client = _client(session)

    ok = client.post(
        "/api/intentions/mcp_server", json={"server": "datagouv", "enabled": True}, headers=HEADERS
    )
    unknown = client.post(
        "/api/intentions/mcp_server", json={"server": "nope", "enabled": True}, headers=HEADERS
    )

    assert ok.status_code == 200 and unknown.status_code == 404
    assert "datagouv" in session._mcp_enabled
    assert session._mcp_conns == {}  # brick not wanted: nothing contacted
    session.close()


def test_optional_arguments_and_untyped_values_are_accepted(loop, web):
    web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop)
    session.set_mcp_server("local", False)
    enable(session, "mslearn")
    spec = session._registry.get("mslearn__microsoft_code_sample_search")
    assert spec.params == {"query": "string", "language": ""} and spec.required == ("query",)
    executor = session._tool_executor
    from wavestack.tools.parser import ToolCall

    enabled = session.build_turn_state().tools
    name = "mslearn__microsoft_code_sample_search"
    assert executor.check(ToolCall(name, {"query": "x"}), enabled) is None
    assert executor.check(ToolCall(name, {"query": "x", "language": 3}), enabled) is None
    assert "manquant" in executor.check(ToolCall(name, {"language": "py"}), enabled)
    raw = call(name, query="12", language="python")
    calls, _ = parse_tool_calls(raw, "qwen3_coder", {name: spec.params})
    assert calls[0].arguments == {"query": "12", "language": "python"}  # unknown type: text kept
    session.close()


def test_local_server_that_cannot_start_is_unavailable_with_its_reason(loop, monkeypatch):
    monkeypatch.setattr(connection.sys, "executable", "Z:/absent/python.exe")
    session = mcp_session(loop)

    ended = enable(session)

    assert ended["status"] == "error" and "processus du serveur" in ended["error_fr"], ended
    local = node(session, "mcp.local")
    assert (local["contact"], local["available"]) == ("unavailable", False)
    assert local["reason_fr"] == ended["error_fr"]
    assert session.build_turn_state().tools == ()
    session.close()


# ---------- review follow-ups ----------


def test_app_lifespan_attaches_the_loop_and_stops_the_local_server():
    from fastapi.testclient import TestClient
    from test_bricks import HEADERS

    from wavestack.session.diagnostic import DiagnosticSession
    from wavestack.web.app import create_app

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
    mark = get_journal().last_seq()

    with TestClient(app, base_url="http://127.0.0.1:8421") as client:  # enters the lifespan
        brick = {"brick": "mcp", "wanted": True}
        assert client.post("/api/intentions/brick", json=brick, headers=HEADERS).is_success
        local = {"server": "local", "enabled": True}
        assert client.post("/api/intentions/mcp_server", json=local, headers=HEADERS).is_success
        ended = wait_for(session, "mcp_connect_ended", mark)
        assert ended and ended[-1]["status"] == "ok"
        assert local_servers()

    assert no_local_server_left()


def test_mcp_card_is_pending_until_the_next_send(loop):
    session = mcp_session(loop, ["Bonjour."])
    enable(session)
    _run(session, "Bonjour")
    assert not card("mcp")["pending"]

    session.set_mcp_server("local", False)
    session.join()
    assert card("mcp")["pending"]

    _run(session, "Bonjour")
    assert not card("mcp")["pending"]
    session.close()


def test_invalid_call_with_the_mcp_brick_alone_belongs_to_mcp(loop):
    session = mcp_session(loop, [call("local__define_term"), "Voilà."])  # `term` missing
    enable(session)
    mark = get_journal().last_seq()

    events = _run(session, "Que veut dire MCP ?")

    (malformed,) = since(mark, "tool_call_malformed")
    assert malformed.brick == "mcp" and "manquant" in malformed.payload["detail_fr"]
    (result,) = _segments(events["context_rendered"][1], "tool_result")
    assert result["brick"] == "mcp"
    session.close()


def test_connect_timeout_makes_the_server_unavailable(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    server.list_delay = 5
    session = mcp_session(loop, connect_timeout_s=0.5)
    session.set_mcp_server("local", False)
    mark = get_journal().last_seq()
    session.set_brick("mcp", True)
    session.set_mcp_server("mslearn", True)
    conn = session._mcp_conns["mslearn"]

    ended = wait_for(session, "mcp_connect_ended", mark)[-1]

    assert ended["status"] == "error" and "délai" in ended["error_fr"]
    assert node(session, "mcp.mslearn")["contact"] == "unavailable"
    assert conn._task.done()
    session.close()


def test_mcp_tools_stay_out_of_the_tools_brick(loop):
    session = mcp_session(loop)
    session.set_brick("tools", True)
    enable(session)

    assert not any(o["id"].startswith("local__") for o in card("tools")["options"])
    with pytest.raises(KeyError):
        session.set_tool("local__define_term", True)
    session.close()


def test_json_rpc_error_answer_is_a_tool_error_and_the_server_stays(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    server.error = {"code": -32602, "message": "Invalid params: query"}
    outputs = [call("mslearn__microsoft_docs_search", query="x"), "Voilà."]
    session = mcp_session(loop, outputs)
    session.set_mcp_server("local", False)
    enable(session, "mslearn")

    events = _run(session, "Cherche")

    (ended,) = events["tool_ended"]
    assert ended["status"] == "error" and "Invalid params: query" in ended["error_fr"]
    mslearn = node(session, "mcp.mslearn")
    assert mslearn["contact"] == "available" and mslearn["available"]
    assert len(session.build_turn_state().tools) == 3
    session.close()


def test_disabling_a_server_during_a_call_ends_the_call_at_once(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    server.delay = 8
    outputs = [call("mslearn__microsoft_docs_search", query="x"), "Voilà."]
    session = mcp_session(loop, outputs, call_timeout_s=10)
    session.set_mcp_server("local", False)
    enable(session, "mslearn")

    def disable_once_sent(envelope) -> None:
        if envelope.kind == "outbound_request" and "tools/call" in envelope.payload["body"]:
            threading.Timer(0.2, session.set_mcp_server, ("mslearn", False)).start()

    get_journal().subscribe(disable_once_sent)
    try:
        events = _run(session, "Cherche")
    finally:
        get_journal().unsubscribe(disable_once_sent)

    (ended,) = events["tool_ended"]
    assert ended["status"] == "error" and ended["duration_ms"] < 3000
    assert events["turn_ended"][0]["status"] == "completed"
    session.close()


# ---------- story 34: what each public server receives, in content (AD-19) ----------


@pytest.mark.parametrize("server", list(mcp_servers(config.Config()).values()), ids=lambda s: s.id)
def test_public_servers_say_what_they_receive_and_local_ones_do_not(server):
    text = load_mcp_content().servers[server.id]
    if server.network:
        assert text.sends_fr and text.sends_fr.strip()
    else:
        assert text.sends_fr is None
