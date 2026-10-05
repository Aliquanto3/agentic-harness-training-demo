"""The MCP workshop (`/mcp`), the protocol laid bare in sequence (story 6 of 2026-09-30, lot 4
of 2026-10-04, AD-27).

The local server is the real glossary, a child process over stdio; the public ones answer
from `McpWeb`, in process, behind the real async client factory: nothing leaves the
machine. The workshop's connections are its own: the brick's never change.
"""

from __future__ import annotations

import asyncio
import json
import time

import httpx2
import psutil
import pytest
import test_mcp
from fake_engine import FakeEngine
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
from test_tools import QWEN, call
from test_turn import _run

from wavestack import config
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
KINDS = mcp_lab.KINDS
ENDS = (
    "mcp_lab_connect_ended",
    "mcp_lab_call_ended",
    "mcp_lab_read_ended",
    "mcp_lab_prompt_ended",
    "mcp_lab_ask_ended",
)


def wait_idle(session: AppSession, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and session.state != "idle":
        time.sleep(0.02)
    session.join()
    assert session.state == "idle", session.state


def lab_events(mark: int) -> list:
    return [
        e for e in get_journal().events_since(mark) if e.kind in KINDS and e.context_id == "mcp_lab"
    ]


def one(events: list, kind: str) -> dict:
    (found,) = [e.payload for e in events if e.kind == kind]
    return found


def connect(session: AppSession, server: str = "local") -> tuple[str, list, dict]:
    """One connection of the workshop, the worker joined: its id, its messages and its end."""
    mark = get_journal().last_seq()
    step_id = session.mcp_lab_connect(server)
    wait_idle(session)
    events = lab_events(mark)
    messages = [e for e in events if e.kind == "mcp_lab_message"]
    return step_id, messages, one(events, "mcp_lab_connect_ended")


def exchange(session: AppSession, start) -> tuple[str, list]:  # noqa: ANN001
    """An exchange started by `start()`, the worker joined: its id and its events."""
    mark = get_journal().last_seq()
    step_id = start()
    wait_idle(session)
    return step_id, lab_events(mark)


def lab_call(session: AppSession, server: str, tool: str, **args) -> tuple[list, dict]:
    _, events = exchange(session, lambda: session.mcp_lab_call(server, tool, args))
    messages = [e.payload for e in events if e.kind == "mcp_lab_message"]
    return messages, one(events, "mcp_lab_call_ended")


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


def lab_session(loop, engine: FakeEngine, *, window: int = 4096, **values) -> AppSession:  # noqa: ANN001
    """`mcp_session` with an engine of the test's and more configuration."""
    merged = {
        "context": {"window": window, "near_limit_ratio": 0.8},
        "mcp": {"connect_timeout_s": 10, "call_timeout_s": 10},
    } | values
    session = AppSession(config.Config(values=merged), engine_factory=lambda path, n_ctx: engine)
    session.boot("fake.gguf").result()
    session.attach_loop(loop)
    return session


def qwen(*outputs: str, delay: float = 0.0) -> FakeEngine:
    return FakeEngine(
        outputs=list(outputs), template=QWEN.decode("utf-8"), architecture="qwen35", delay=delay
    )


def last_connection(session: AppSession) -> str | None:
    """AD-27: the `connection` of the journal's last end or closing, as the page reads it."""
    state = session.mcp_lab_state()
    for envelope in reversed(state["last_session"]):
        if envelope["kind"] in ENDS and "." not in envelope["step_id"]:
            payload = envelope["payload"]
            return payload["server"] if payload["connection"] == "open" else None
        if envelope["kind"] == "mcp_lab_closed":
            return None
    return None


def one_pair_per_step(events: list) -> None:
    """AD-27: every step carries exactly one `mcp_lab_*` pair."""
    starts: dict[str, list[str]] = {}
    for e in events:
        if e.kind in ("mcp_lab_exchange_started", "mcp_lab_model_started", *ENDS) or (
            e.kind == "mcp_lab_model_ended"
        ):
            starts.setdefault(e.step_id, []).append(e.kind)
    for step, kinds in starts.items():
        assert len(kinds) == 2, (step, kinds)
        assert kinds[0] in ("mcp_lab_exchange_started", "mcp_lab_model_started"), (step, kinds)


# ---------- the capture and the helpers, alone ----------


def test_the_capture_pairs_a_response_with_its_request():
    from mcp_types import (
        JSONRPCError,
        JSONRPCNotification,
        JSONRPCRequest,
        JSONRPCResponse,
    )

    seen: list[tuple[str, dict]] = []

    def emit(payload: dict, step: str) -> int:
        seen.append((step, payload))
        return 100 + len(seen)

    capture = mcp_lab.Capture(emit, "mcp3", lambda: "fr")
    capture.begin("mcp3")
    capture.record("to_server", JSONRPCRequest(jsonrpc="2.0", id=1, method="tools/list"))
    # A request of the server with the same id: never paired with the client's.
    capture.record("from_server", JSONRPCRequest(jsonrpc="2.0", id=1, method="ping"))
    capture.record(
        "from_server",
        JSONRPCResponse(jsonrpc="2.0", id=1, result={"tools": [{"name": "a"}, {"name": "b"}]}),
    )
    capture.record("to_server", JSONRPCResponse(jsonrpc="2.0", id=1, result={}))
    capture.record("to_server", JSONRPCNotification(jsonrpc="2.0", method="notifications/x"))
    request, ping, response, pong, note = (p for _, p in seen)
    assert (request["message_type"], request["rpc_id"], request["elapsed_kind"]) == (
        "request",
        1,
        "since_start",
    )
    assert (response["method"], response["reply_to_seq"]) == ("tools/list", 101)
    assert response["elapsed_kind"] == "round_trip" and response["summary_text"] == "2 outils"
    assert (pong["method"], pong["reply_to_seq"]) == ("ping", 102)
    assert note["message_type"] == "notification" and note["summary_text"] is None
    assert not any(p["unsolicited"] for _, p in seen)
    assert json.loads(response["jsonrpc"])["result"]["tools"][1] == {"name": "b"}
    assert capture.received("tools/list") == response["jsonrpc"]
    assert capture.seq_of(request["jsonrpc"]) == 101
    assert capture.failed_seq("mcp3") is None

    # An error answer: its request is the failed one; a request left alone too.
    capture.begin("mcp4")
    capture.record("to_server", JSONRPCRequest(jsonrpc="2.0", id=2, method="tools/call"))
    error = {"code": -32602, "message": "Invalid params"}
    capture.record("from_server", JSONRPCError(jsonrpc="2.0", id=2, error=error))
    (_, failed) = seen[-1]
    assert failed["message_type"] == "error" and failed["error"] == error
    assert failed["summary_text"] == "erreur -32602 : Invalid params"
    assert capture.failed_seq("mcp4") == 106
    capture.record("to_server", JSONRPCRequest(jsonrpc="2.0", id=3, method="tools/call"))
    assert capture.failed_seq("mcp4") == 108

    # Outside any exchange: on the connection's first step, unsolicited.
    capture.end()
    capture.record("from_server", JSONRPCNotification(jsonrpc="2.0", method="notifications/y"))
    step, stray = seen[-1]
    assert step == "mcp3" and stray["unsolicited"] is True
    capture.record("to_server", object())  # never raises: the exchange goes on uncaptured
    assert len(seen) == 9


def test_summaries_say_what_a_message_carries():
    def said(method: str, result: dict, lang: str = "fr") -> str | None:
        return mcp_lab.summary(method, "response", {"result": result}, lang)

    caps = {"capabilities": {"prompts": {}, "tools": {}, "resources": {}}}
    assert said("initialize", caps) == "capacités : tools · resources · prompts"
    assert said("resources/list", {"resources": [{}]}) == "1 ressource"
    assert said("prompts/list", {"prompts": []}) == "0 prompt"
    assert said("tools/call", {"content": [{"type": "text", "text": "x"}]}) == "1 bloc texte"
    error = {"content": [{"type": "text", "text": "x"}], "isError": True}
    assert said("tools/call", error) == "isError · 1 bloc texte"
    content = {"contents": [{"uri": "a", "mimeType": "text/plain", "text": "a\nb"}]}
    assert said("resources/read", content) == "text/plain · 2 lignes"
    assert said("prompts/get", {"messages": [{}]}, "en") == "1 message"
    assert mcp_lab.summary("tools/list", "request", {}, "fr") is None


def test_catalog_line_and_step_number():
    assert mcp_lab.catalog_line("local__x", "Première ligne\nseconde", 120) == (
        "- local__x : Première ligne"
    )
    assert mcp_lab.catalog_line("local__x", "", 120) == "- local__x"
    assert mcp_lab.catalog_line("a", "x" * 10, 4) == "- a : xxxx…"
    assert mcp_lab.step_number("mcp12") == 12
    assert mcp_lab.step_number("mcp7.c2") == mcp_lab.step_number("mcp7.t1") == 7
    for other in ("lab1", "mcp_lab", "mcp7.x1", "mcp7.c", None):
        assert mcp_lab.step_number(other) is None


class _Envelope:
    """What `last_session` reads of an envelope."""

    def __init__(self, kind: str, step_id: str | None, context_id: str = "mcp_lab") -> None:
        self.kind, self.step_id, self.context_id = kind, step_id, context_id

    def model_dump(self, mode: str) -> dict:
        return {"kind": self.kind, "step_id": self.step_id}


def test_last_session_is_the_last_connection_and_its_exchanges():
    journal = [
        _Envelope("mcp_lab_message", "mcp3"),  # a first connection, then a call on it
        _Envelope("mcp_lab_connect_ended", "mcp3"),
        _Envelope("mcp_lab_exchange_started", "mcp4"),
        _Envelope("outbound_request", "mcp4"),
        _Envelope("mcp_lab_call_ended", "mcp4"),
        _Envelope("tool_ended", "mcp4"),  # not a kind of the workshop
        _Envelope("mcp_lab_message", "mcp4", context_id="main"),  # another context
        _Envelope("session_state", None),
        _Envelope("mcp_lab_exchange_started", "mcp5"),  # the connection after it
        _Envelope("mcp_lab_connect_ended", "mcp5"),
        _Envelope("mcp_lab_exchange_started", "mcp6"),  # an ask on it
        _Envelope("mcp_lab_model_started", "mcp6.c1"),
        _Envelope("model_call_started", "mcp6.c1"),
        _Envelope("model_delta", "mcp6.c1"),  # never: `model_call_ended` is what counts
        _Envelope("harness_error", "mcp6.c1"),
        _Envelope("model_call_ended", "mcp6.c1"),
        _Envelope("mcp_lab_model_ended", "mcp6.c1"),
        _Envelope("mcp_lab_exchange_started", "mcp6.t1"),
        _Envelope("mcp_lab_call_ended", "mcp6.t1"),
        _Envelope("mcp_lab_ask_ended", "mcp6"),
        _Envelope("mcp_lab_closed", "mcp5"),
    ]

    def steps(first: int) -> list[tuple]:
        return [(e["kind"], e["step_id"]) for e in mcp_lab.last_session(journal, first)]

    assert steps(5) == [
        ("mcp_lab_exchange_started", "mcp5"),
        ("mcp_lab_connect_ended", "mcp5"),
        ("mcp_lab_exchange_started", "mcp6"),
        ("mcp_lab_model_started", "mcp6.c1"),
        ("model_call_started", "mcp6.c1"),
        ("model_call_ended", "mcp6.c1"),
        ("mcp_lab_model_ended", "mcp6.c1"),
        ("mcp_lab_exchange_started", "mcp6.t1"),
        ("mcp_lab_call_ended", "mcp6.t1"),
        ("mcp_lab_ask_ended", "mcp6"),
        ("mcp_lab_closed", "mcp5"),
    ]
    assert steps(3)[:5] == [
        ("mcp_lab_message", "mcp3"),
        ("mcp_lab_connect_ended", "mcp3"),
        ("mcp_lab_exchange_started", "mcp4"),
        ("outbound_request", "mcp4"),
        ("mcp_lab_call_ended", "mcp4"),
    ]
    assert steps(0) == []  # no connection yet


def test_invalid_content_is_said_and_refuses_the_connection(monkeypatch):
    from fake_engine import booted_session

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


def test_the_content_needs_every_method_and_the_resource_template():
    from pydantic import ValidationError

    data = mcp_lab.load_lab_content("fr").model_dump()
    assert len(data["methods"]) == 8
    del data["methods"]["prompts/get"]
    try:
        mcp_lab.McpLabContent.model_validate(data)
    except ValidationError as exc:
        assert "methods" in str(exc)
    else:
        raise AssertionError("a method without its text")
    data = mcp_lab.load_lab_content("fr").model_dump()
    data["ask_resource_text"] = "{uri} {content}"
    try:
        mcp_lab.McpLabContent.model_validate(data)
    except ValidationError as exc:
        assert "{question}" in str(exc)
    else:
        raise AssertionError("a resource template without the question")


# ---------- the local server: a real child process ----------


def test_local_handshake_lists_the_three_primitives_and_leaves_the_brick(loop):
    session = mcp_session(loop)
    before = brick_state(session)
    mark = get_journal().last_seq()

    step_id, messages, ended = connect(session)

    events = lab_events(mark)
    started = one(events, "mcp_lab_exchange_started")
    assert (started["exchange"], started["by"], started["transport"]) == ("connect", None, "stdio")
    assert started["launch_text"] == "lance le serveur : python -m wavestack.mcp.local_server fr"
    assert events[0].kind == "mcp_lab_exchange_started" and events[-1].kind.endswith("_ended")
    shape = [(e.payload["direction"], e.payload["method"]) for e in messages]
    assert shape == [
        ("to_server", "initialize"),
        ("from_server", "initialize"),
        ("to_server", "notifications/initialized"),
        ("to_server", "tools/list"),
        ("from_server", "tools/list"),
        ("to_server", "resources/list"),
        ("from_server", "resources/list"),
        ("to_server", "prompts/list"),
        ("from_server", "prompts/list"),
    ]
    by_seq = {e.seq: e.payload for e in messages}
    for envelope in messages:
        payload = envelope.payload
        assert (envelope.context_id, envelope.turn_id, envelope.step_id) == (
            "mcp_lab",
            None,
            step_id,
        )
        assert (envelope.brick, envelope.component) == ("mcp", "mcp_lab.local")
        assert payload["reconstructed"] is False and payload["unsolicited"] is False
        assert payload["elapsed_ms"] >= 0
        assert json.loads(payload["jsonrpc"])["jsonrpc"] == "2.0"
        if payload["message_type"] == "response":
            request = by_seq[payload["reply_to_seq"]]
            assert request["method"] == payload["method"] and request["direction"] == "to_server"
            assert payload["elapsed_kind"] == "round_trip"
    summaries = [m.payload["summary_text"] for m in messages if m.payload["summary_text"]]
    assert summaries == [
        "capacités : tools · resources · prompts",
        "2 outils",
        "1 ressource",
        "1 prompt",
    ]
    assert messages[2].payload["message_type"] == "notification"

    assert ended["status"] == "ok" and ended["error_kind"] is None
    assert ended["connection"] == "open" and ended["failed_seq"] is None
    assert ended["primitives"] == {"tools": True, "resources": True, "prompts": True}
    assert ended["server_info"]["name"] == "wavestack-glossaire" and ended["list_errors"] == []
    (resource,) = ended["resources"]
    assert (resource["uri"], resource["mime_type"]) == ("glossary://terms", "text/plain")
    (prompt,) = ended["prompts"]
    assert prompt["name"] == "explain_term"
    assert [(a["name"], a["required"]) for a in prompt["arguments"]] == [("term", True)]
    names = [t["name"] for t in ended["tools"]]
    assert names == ["local__list_terms", "local__define_term"]
    for tool in ended["tools"]:  # fake engine: one token per byte, counted, not estimated
        assert tool["doc_tokens"] == len(tool["definition_text"].encode())
        assert tool["line_text"] in ended["lazy_definition_text"]
    assert ended["full_tokens"] == sum(t["doc_tokens"] for t in ended["tools"])
    assert ended["estimated"] is False

    # The sandbox: the brick's state, connections and registry are untouched.
    assert brick_state(session) == before
    state = session.mcp_lab_state()
    assert state["open_server"] == "local" == last_connection(session)
    assert [e["kind"] for e in state["last_session"]][-1] == "mcp_lab_connect_ended"
    local = state["servers"][0]
    assert (local["source_label_text"], local["source_action_text"]) == (
        "glossary.yaml",
        "lit glossary.yaml",
    )
    assert state["ask"]["model_ready"] is True and state["ask"]["tools"] is True
    assert local_servers()

    # The definitions are the brick's own, as `_tool_definitions` renders them.
    enable(session)
    for tool in ended["tools"]:
        brick = json.dumps(session._registry.definition(tool["name"]), ensure_ascii=False)
        assert brick == tool["definition_text"]
    assert session._mcp_conns["local"] is not session._mcp_lab_conn

    session.close()
    assert no_local_server_left()


def test_valid_call_and_is_error_are_results(loop):
    session = mcp_session(loop)
    connect(session)

    messages, ended = lab_call(session, "local", "define_term", term="harnais")

    assert [(m["direction"], m["method"]) for m in messages] == [
        ("to_server", "tools/call"),
        ("from_server", "tools/call"),
    ]
    assert json.loads(messages[0]["jsonrpc"])["params"]["arguments"] == {"term": "harnais"}
    assert ended["status"] == "ok" and ended["error_text"] is None and not ended["is_error"]
    assert (ended["by"], ended["arguments"]) == ("hand", {"term": "harnais"})
    assert ended["raw"] == messages[1]["jsonrpc"] and messages[1]["summary_text"] == "1 bloc texte"
    assert ended["text"].lower().startswith("harnais")
    assert ended["tokens"] == len(ended["text"].encode()) and ended["truncated"] is None

    _, unknown = lab_call(session, "local", "define_term", term="xyz")

    assert unknown["status"] == "ok" and unknown["is_error"] is True
    assert unknown["connection"] == "open" and unknown["failed_seq"] is None
    assert json.loads(unknown["raw"])["result"]["isError"] is True
    assert "Terme inconnu" in unknown["text"] and unknown["text"].startswith("Erreur : ")
    assert "isError" in unknown["error_text"]
    assert session.mcp_lab_state()["open_server"] == "local"  # the server is still there
    session.close()
    assert no_local_server_left()


def test_resource_and_prompt_then_sent_to_the_model(loop):
    session = mcp_session(loop, ("Voilà, des termes.", "Un hook est un point d'accroche."))
    start = get_journal().last_seq()
    connect(session)
    for refused in (
        lambda: session.mcp_lab_read("local", "glossary://nope"),
        lambda: session.mcp_lab_prompt("local", "explain_term", {}),  # `term` is required
        lambda: session.mcp_lab_prompt("local", "nope", {}),
        lambda: session.mcp_lab_ask("local", "Une question ?", of="mcp1"),  # nothing read
    ):
        try:
            refused()
        except SendRefused:
            pass
        else:
            raise AssertionError("refused")

    read_id, events = exchange(session, lambda: session.mcp_lab_read("local", "glossary://terms"))

    started = one(events, "mcp_lab_exchange_started")
    assert (started["exchange"], started["by"], started["uri"]) == (
        "read",
        "app",
        "glossary://terms",
    )
    read = one(events, "mcp_lab_read_ended")
    assert read["status"] == "ok" and read["connection"] == "open"
    (content,) = read["contents"]
    assert content["mime_type"] == "text/plain" and "harnais" in content["text"]
    assert read["text"] == content["text"] and read["tokens"] == len(read["text"].encode())
    assert [m.payload["method"] for m in events if m.kind == "mcp_lab_message"] == [
        "resources/read",
        "resources/read",
    ]

    try:  # a question goes with a resource
        session.mcp_lab_ask("local", None, of=read_id)
    except SendRefused:
        pass
    else:
        raise AssertionError("refused without a question")
    ask_id, events = exchange(
        session, lambda: session.mcp_lab_ask("local", "Quels termes ?", of=read_id)
    )

    started = one(events, "mcp_lab_exchange_started")
    assert (started["by"], started["of"], started["uri"]) == ("app", read_id, "glossary://terms")
    model = one(events, "mcp_lab_model_started")
    assert [s["part"] for s in model["sends"]] == ["resource", "question", "tools"]
    assert model["doc_mode"] == "full" and model["prompt_tokens"] > model["sends_total_tokens"]
    ended = one(events, "mcp_lab_model_ended")
    assert (ended["outcome"], ended["final"], ended["direct"]) == ("answer", True, False)
    asked = one(events, "mcp_lab_ask_ended")
    assert (asked["status"], asked["outcome"], asked["calls"]) == ("ok", "answer", 1)
    assert asked["final_step"] == f"{ask_id}.c1" and asked["connection"] == "open"
    # The content sent is the one the session kept, never the page's.
    sent = [e for e in events if e.kind == "model_call_started"]
    assert sent and all(e.step_id == f"{ask_id}.c1" for e in sent)
    assert session._engine.calls  # the fake engine read the rendered context

    prompt_id, events = exchange(
        session, lambda: session.mcp_lab_prompt("local", "explain_term", {"term": "hook"})
    )
    got = one(events, "mcp_lab_prompt_ended")
    assert got["status"] == "ok" and got["arguments"] == {"term": "hook"}
    (message,) = got["messages"]
    assert message["role"] == "user" and "hook" in message["text"]
    assert got["tokens"] == len(got["text"].encode())
    assert one(events, "mcp_lab_exchange_started")["by"] == "user"

    try:  # a prompt leaves without a question
        session.mcp_lab_ask("local", "Une question", of=prompt_id)
    except SendRefused:
        pass
    else:
        raise AssertionError("refused with a question")
    _, events = exchange(session, lambda: session.mcp_lab_ask("local", None, of=prompt_id))
    model = one(events, "mcp_lab_model_started")
    assert [s["part"] for s in model["sends"]] == ["prompt", "tools"]
    assert one(events, "mcp_lab_exchange_started")["prompt"] == "explain_term"
    assert one(events, "mcp_lab_ask_ended")["outcome"] == "answer"
    one_pair_per_step(lab_events(start))
    session.close()
    assert no_local_server_left()


def test_by_the_model_one_tool_through_the_host(loop):
    session = mcp_session(loop, (call("local__define_term", term="MCP"), "MCP est un protocole."))
    connect(session)
    gauge_before = _client(session).get("/api/state").json()

    ask_id, events = exchange(session, lambda: session.mcp_lab_ask("local", "Que veut dire MCP ?"))

    kinds = [(e.kind, e.step_id) for e in events if e.kind.startswith("mcp_lab_")]
    calls = [(k, s) for k, s in kinds if k != "mcp_lab_message"]
    assert calls == [
        ("mcp_lab_exchange_started", ask_id),
        ("mcp_lab_model_started", f"{ask_id}.c1"),
        ("mcp_lab_model_ended", f"{ask_id}.c1"),
        ("mcp_lab_exchange_started", f"{ask_id}.t1"),
        ("mcp_lab_call_ended", f"{ask_id}.t1"),
        ("mcp_lab_model_started", f"{ask_id}.c2"),
        ("mcp_lab_model_ended", f"{ask_id}.c2"),
        ("mcp_lab_ask_ended", ask_id),
    ]
    for e in events:
        if "." in (e.step_id or ""):
            assert e.parent_step == ask_id
        if e.step_id == f"{ask_id}.c1":
            assert e.call_id == f"{ask_id}.c1"
    first = one([e for e in events if e.step_id == f"{ask_id}.c1"], "mcp_lab_model_ended")
    assert first["outcome"] == "tool_call" and first["final"] is False
    assert first["tool_call"]["name"] == "local__define_term"
    assert first["tool_call"]["tool"] == "define_term"
    assert first["tool_call"]["arguments"] == {"term": "MCP"}
    t1 = [e.payload for e in events if e.step_id == f"{ask_id}.t1"]
    assert t1[0]["by"] == "model" and t1[0]["exchange"] == "call"
    assert [p["method"] for p in t1 if "method" in p] == ["tools/call", "tools/call"]
    called = one([e for e in events if e.step_id == f"{ask_id}.t1"], "mcp_lab_call_ended")
    assert called["status"] == "ok" and called["by"] == "model"
    second = [e.payload for e in events if e.step_id == f"{ask_id}.c2"]
    assert [s["part"] for s in second[0]["sends"]] == [
        "question",
        "tools",
        "tool_call",
        "tool_result",
    ]
    assert second[-1]["outcome"] == "answer" and second[-1]["final"] is True
    asked = one(events, "mcp_lab_ask_ended")
    assert (asked["status"], asked["outcome"], asked["calls"]) == ("ok", "answer", 2)
    assert asked["model_ms"] >= 0 and "génération" in asked["share_text"]
    one_pair_per_step(events)

    # The main workshop's gauge does not move; no context event in the workshop.
    assert not [e for e in events if e.kind.startswith("context_")]
    assert not [
        e
        for e in get_journal().all_events()
        if e.context_id == "mcp_lab" and e.kind.startswith("context_")
    ]
    gauge_after = _client(session).get("/api/state").json()
    for key in ("context_rendered", "context_reconciled", "context_preview"):
        assert gauge_after.get(key) == gauge_before.get(key), key
    assert not session._call_ids  # the turn's ids are untouched
    # The replay rebuilds the same arrows.
    replay = [e["kind"] for e in session.mcp_lab_state()["last_session"]]
    assert replay.count("mcp_lab_model_ended") == 2 and replay[-1] == "mcp_lab_ask_ended"
    assert "model_delta" not in replay and "model_call_ended" in replay
    session.close()
    assert no_local_server_left()


def test_without_a_tool_a_refused_call_and_a_window_too_small(loop):
    session = mcp_session(
        loop, ("Je sais déjà.", call("local__nope", term="MCP"), call("local__define_term"))
    )
    connect(session)

    _, events = exchange(session, lambda: session.mcp_lab_ask("local", "Que veut dire MCP ?"))
    ended = one(events, "mcp_lab_model_ended")
    assert (ended["outcome"], ended["direct"], ended["answer_text"]) == (
        "answer",
        True,
        "Je sais déjà.",
    )
    assert one(events, "mcp_lab_ask_ended")["outcome"] == "no_tool"

    for _ in range(2):  # an unknown tool, then a missing argument: refused, nothing sent
        _, events = exchange(session, lambda: session.mcp_lab_ask("local", "Et MCP ?"))
        ended = one(events, "mcp_lab_model_ended")
        assert ended["outcome"] == "refused" and ended["refusal_text"]
        asked = one(events, "mcp_lab_ask_ended")
        assert (asked["status"], asked["outcome"], asked["calls"]) == ("ok", "refused", 1)
        assert not [e for e in events if e.kind == "mcp_lab_message"]
    session.close()

    small = mcp_session(loop, window=600)
    connect(small)
    _, events = exchange(small, lambda: small.mcp_lab_ask("local", "Que veut dire MCP ?"))
    assert [e.kind for e in events if e.step_id.endswith(".c1")] == [
        "mcp_lab_model_started",
        "mcp_lab_model_ended",
    ]
    ended = one(events, "mcp_lab_model_ended")
    assert (ended["status"], ended["outcome"]) == ("error", "overflow")
    asked = one(events, "mcp_lab_ask_ended")
    assert (asked["status"], asked["outcome"], asked["calls"]) == ("error", "overflow", 0)
    small.close()
    assert no_local_server_left()


def test_lazy_loading_reaches_the_bound_of_calls(loop):
    """Two documentations loaded, two calls to the model: `tools.max_calls` (2) reached
    before a third, without `limit_reached`; no MCP message at all."""
    session = lab_session(
        loop,
        qwen(
            call("load_tool_doc", tool="local__list_terms"),
            call("load_tool_doc", tool="local__define_term"),
        ),
        tools={"max_calls": 2},
    )
    connect(session)

    _, events = exchange(
        session, lambda: session.mcp_lab_ask("local", "Que veut dire MCP ?", doc_mode="lazy")
    )
    models = [e.payload for e in events if e.kind == "mcp_lab_model_ended"]
    assert [m["outcome"] for m in models] == ["meta_call", "meta_call"]
    assert models[0]["tool_call"]["tool"] is None and not models[0]["final"]
    started = [e.payload for e in events if e.kind == "mcp_lab_model_started"]
    assert started[0]["doc_mode"] == "lazy"
    assert "tool_doc" in [s["part"] for s in started[1]["sends"]]
    asked = one(events, "mcp_lab_ask_ended")
    assert (asked["status"], asked["outcome"], asked["calls"]) == ("limit", "max_calls", 2)
    assert asked["connection"] == "open" and asked["final_step"].endswith(".c2")
    assert not [e for e in events if e.kind == "mcp_lab_message"]  # no MCP message at all
    assert not [
        e
        for e in get_journal().all_events()
        if e.kind == "limit_reached" and e.context_id == "mcp_lab"
    ]
    session.close()


def test_a_second_tool_ends_the_workshop(loop):
    session = mcp_session(loop, (call("local__define_term", term="MCP"), call("local__list_terms")))
    connect(session)

    ask_id, events = exchange(session, lambda: session.mcp_lab_ask("local", "Que veut dire MCP ?"))

    models = [e.payload for e in events if e.kind == "mcp_lab_model_ended"]
    assert [(m["outcome"], m["final"]) for m in models] == [
        ("tool_call", False),
        ("tool_call", True),
    ]
    assert models[1]["tool_call"]["tool"] == "list_terms"
    asked = one(events, "mcp_lab_ask_ended")
    assert (asked["status"], asked["outcome"], asked["calls"]) == ("limit", "second_tool", 2)
    # Only the first tool went to the server.
    assert [e.step_id for e in events if e.kind == "mcp_lab_call_ended"] == [f"{ask_id}.t1"]
    session.close()
    assert no_local_server_left()


def test_an_output_cut_at_the_reserve_ends_the_workshop(loop):
    session = mcp_session(loop, ("x" * 700,))
    connect(session)

    _, events = exchange(session, lambda: session.mcp_lab_ask("local", "Que veut dire MCP ?"))

    ended = one(events, "mcp_lab_model_ended")
    assert (ended["status"], ended["outcome"], ended["final"]) == ("ok", "cut", True)
    asked = one(events, "mcp_lab_ask_ended")
    assert (asked["status"], asked["outcome"], asked["calls"]) == ("limit", "cut", 1)
    assert not [e for e in events if e.kind == "mcp_lab_message"]
    session.close()
    assert no_local_server_left()


def test_the_turn_after_an_ask_keeps_its_prefix(loop):
    session = mcp_session(loop, ("Bonjour !", "Voilà.", "Et voilà."))
    engine = session._engine
    session.send("Bonjour")
    session.join()
    connect(session)
    exchange(session, lambda: session.mcp_lab_ask("local", "Que veut dire MCP ?"))
    mark = get_journal().last_seq()

    session.send("Et ensuite ?")
    session.join()

    assert engine.restores == 1  # the main context's state came back
    events = get_journal().events_since(mark)
    causes = [e.payload["cause"] for e in events if e.kind == "prefix_not_reused"]
    assert "mcp_lab" not in causes
    session.close()
    assert no_local_server_left()


def test_a_stateless_engine_says_the_workshop_took_its_cache(loop):
    engine = FakeEngine(
        outputs=["Bonjour !", "Voilà.", "Et voilà."],
        template=QWEN.decode("utf-8"),
        architecture="qwen35",
        stateful=False,
    )
    session = lab_session(loop, engine)
    session.send("Bonjour")
    session.join()
    connect(session)
    exchange(session, lambda: session.mcp_lab_ask("local", "Que veut dire MCP ?"))
    mark = get_journal().last_seq()

    session.send("Et ensuite ?")
    session.join()

    causes = [e.payload for e in get_journal().events_since(mark) if e.kind == "prefix_not_reused"]
    assert [c["cause"] for c in causes] == ["mcp_lab"]
    assert causes[0]["message_text"].startswith("L'Atelier MCP a occupé le cache du moteur")
    session.close()
    assert no_local_server_left()


@pytest.mark.parametrize("which", ["connect", "call", "read", "prompt"])
def test_an_end_always_comes(loop, monkeypatch, which):
    """AD-27: an end that does not validate gives one `harness_error` and the minimal end
    (`error`, `interrupted`), with the state of the connection."""
    kind = {
        "connect": "mcp_lab_connect_ended",
        "call": "mcp_lab_call_ended",
        "read": "mcp_lab_read_ended",
        "prompt": "mcp_lab_prompt_ended",
    }[which]
    session = mcp_session(loop)
    if which != "connect":
        connect(session)
    original = AppSession._mcp_lab_emit

    def emit(self, k, payload, step_id, server_id):  # noqa: ANN001, ANN202
        if k == kind and payload.get("error_kind") != "interrupted":
            raise ValueError("une fin invalide")
        return original(self, k, payload, step_id, server_id)

    monkeypatch.setattr(AppSession, "_mcp_lab_emit", emit)
    start = {
        "connect": lambda: session.mcp_lab_connect("local"),
        "call": lambda: session.mcp_lab_call("local", "define_term", {"term": "MCP"}),
        "read": lambda: session.mcp_lab_read("local", "glossary://terms"),
        "prompt": lambda: session.mcp_lab_prompt("local", "explain_term", {"term": "hook"}),
    }[which]
    mark = get_journal().last_seq()

    step_id, events = exchange(session, start)

    errors = [
        e
        for e in get_journal().events_since(mark)
        if e.kind == "harness_error" and e.context_id == "mcp_lab"
    ]
    assert len(errors) == 1 and errors[0].step_id == step_id
    ended = one(events, kind)
    assert (ended["status"], ended["error_kind"], ended["connection"]) == (
        "error",
        "interrupted",
        "open",
    )
    assert session.state == "idle"
    monkeypatch.undo()
    session.close()
    assert no_local_server_left()


def test_ask_needs_a_model_that_calls_tools(loop):
    import dataclasses

    session = mcp_session(loop)
    connect(session)
    session._caps = dataclasses.replace(session._caps, tool_call_parser=None)
    state = session.mcp_lab_state()["ask"]
    assert state["model_ready"] is True and state["tools"] is False
    assert "n'appelle pas d'outils" in str(state["tools_reason_text"])
    try:
        session.mcp_lab_ask("local", "Que veut dire MCP ?")
    except SendRefused as refused:
        assert "n'appelle pas d'outils" in str(refused.reason_text)
    else:
        raise AssertionError("refused without tool calling")
    # A resource still leaves, without the tools block.
    read_id, _ = exchange(session, lambda: session.mcp_lab_read("local", "glossary://terms"))
    _, events = exchange(session, lambda: session.mcp_lab_ask("local", "Quoi ?", of=read_id))
    model = one(events, "mcp_lab_model_started")
    assert model["doc_mode"] == "none" and [s["part"] for s in model["sends"]] == [
        "resource",
        "question",
    ]
    session.close()


def test_stop_during_a_generation_keeps_the_connection(loop):
    session = lab_session(loop, qwen("Une longue réponse, lettre par lettre.", delay=0.2))
    try:
        connect(session)
        mark = get_journal().last_seq()
        session.mcp_lab_ask("local", "Que veut dire MCP ?")
        deadline = time.monotonic() + 10
        while not [e for e in get_journal().events_since(mark) if e.kind == "model_first_token"]:
            assert time.monotonic() < deadline
            time.sleep(0.02)
        assert session.stop() is True
        wait_idle(session)
        events = lab_events(mark)
        asked = one(events, "mcp_lab_ask_ended")
        assert (asked["status"], asked["error_kind"], asked["connection"]) == (
            "cancelled",
            "stopped",
            "open",
        )
        assert one(events, "mcp_lab_model_ended")["status"] == "cancelled"
        assert session.mcp_lab_state()["open_server"] == "local" == last_connection(session)
    finally:
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


def test_next_connection_language_change_reset_and_close(loop, web):
    web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop)
    connect(session)
    assert local_servers()

    _, _, ended = connect(session, "mslearn")  # the next connection closes the former

    assert ended["status"] == "ok"
    assert no_local_server_left()
    first, _, _ = connect(session)
    assert local_servers()
    mark = get_journal().last_seq()
    session.set_language("en")  # the local server would describe its tools in English
    try:
        assert no_local_server_left()
        closed = one(lab_events(mark), "mcp_lab_closed")
        assert closed == {"server": "local", "cause": "language"}
        assert session.mcp_lab_state()["open_server"] is None is last_connection(session)
    finally:
        session.set_language("fr")
    connect(session)
    mark = get_journal().last_seq()
    session.reset()
    assert one(lab_events(mark), "mcp_lab_closed")["cause"] == "reset"
    state = session.mcp_lab_state()
    assert state["last_session"] == [] and state["open_server"] is None
    assert no_local_server_left()
    connect(session)
    mark = get_journal().last_seq()
    session.close()
    assert one(lab_events(mark), "mcp_lab_closed")["cause"] == "session_close"
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
        assert ended["resources"][0]["title"] == "Begriffe des Glossars"
        assert [m.payload["method"] for m in messages][0] == "initialize"
        assert messages[1].payload["summary_text"].startswith("Fähigkeiten")
    finally:
        session.set_language("fr")  # `settings.json` back in French for the next tests
        session.close()
    assert no_local_server_left()


# ---------- the public servers: in process ----------


class McpWebAll(McpWeb):
    """`McpWeb` announcing resources and prompts too; `prompts/list` may hang."""

    def __init__(self, tools: list[dict]) -> None:
        super().__init__(tools)
        self.prompts_delay = 0.0

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            message = json.loads(request.content)
            method = message.get("method")
            if method == "initialize":
                self.sent.append(request)
                caps = {"tools": {}, "resources": {}, "prompts": {}}
                result = {
                    "protocolVersion": message["params"]["protocolVersion"],
                    "capabilities": caps,
                    "serverInfo": {"name": "test", "version": "1"},
                }
                body = {"jsonrpc": "2.0", "id": message["id"], "result": result}
                return httpx2.Response(200, json=body, headers={"mcp-session-id": "s1"})
            if method in ("resources/list", "prompts/list"):
                self.sent.append(request)
                if method == "prompts/list":
                    await asyncio.sleep(self.prompts_delay)
                key = method.split("/")[0]
                body = {"jsonrpc": "2.0", "id": message["id"], "result": {key: []}}
                return httpx2.Response(200, json=body, headers={"mcp-session-id": "s1"})
        return await super().__call__(request)


def test_public_server_announces_tools_only_and_names_its_posts(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop)
    before = brick_state(session)
    mark = get_journal().last_seq()

    step_id, messages, ended = connect(session, "mslearn")

    assert ended["status"] == "ok" and len(ended["tools"]) == 3
    assert ended["primitives"] == {"tools": True, "resources": False, "prompts": False}
    assert ended["resources"] is None and ended["prompts"] is None
    methods = [m.payload["method"] for m in messages]
    assert "resources/list" not in methods and "prompts/list" not in methods
    outbound = since(mark, "outbound_request")
    assert outbound and len(server.sent) == len(outbound)
    assert {(e.context_id, e.component, e.step_id) for e in outbound} == {
        ("mcp_lab", "mcp_lab.mslearn", step_id)
    }
    sent = {m.seq: m.payload for m in messages if m.payload["direction"] == "to_server"}
    for request in outbound:
        if request.payload["method"] == "POST":
            message = sent[request.payload["message_seq"]]
            assert json.loads(message["jsonrpc"]) == json.loads(request.payload["body"])
        else:
            assert request.payload["message_seq"] is None
    assert brick_state(session) == before
    last = session.mcp_lab_state()["last_session"]
    assert {
        "mcp_lab_exchange_started",
        "mcp_lab_message",
        "mcp_lab_connect_ended",
        "outbound_request",
        "outbound_response",  # the GET of the event stream, refused by the fake server
    } >= {e["kind"] for e in last}
    try:
        session.mcp_lab_read("mslearn", "x://y")
    except SendRefused as refused:
        assert "n'annonce pas de ressources" in str(refused.reason_text)
    else:
        raise AssertionError("refused without resources")
    session.close()


def test_a_list_in_error_leaves_the_connection_open(loop, web):
    server = web(McpWebAll(MSLEARN_TOOLS))
    server.prompts_delay = 3
    session = mcp_session(loop, call_timeout_s=1)

    _, messages, ended = connect(session, "mslearn")

    assert ended["status"] == "ok" and ended["connection"] == "open"
    assert ended["resources"] == [] and ended["prompts"] is None
    (failed,) = ended["list_errors"]
    assert (failed["method"], failed["error_kind"]) == ("prompts/list", "timeout")
    assert "délai" in failed["error_text"]
    assert session.mcp_lab_state()["open_server"] == "mslearn"
    session.close()


def test_public_server_offline_is_unreachable(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    server.offline = True
    session = mcp_session(loop)

    _, _, ended = connect(session, "datagouv")

    assert (ended["status"], ended["error_kind"], ended["connection"]) == (
        "error",
        "unreachable",
        "closed",
    )
    assert ended["error_text"] and ended["tools"] is None and ended["failed_seq"] is not None
    client = _client(session)
    page = client.get("/api/mcp_lab")
    assert page.status_code == 200 and page.json()["open_server"] is None
    assert last_connection(session) is None
    session.close()


def test_json_rpc_error_and_delay_exceeded(loop, web):
    server = web(McpWeb(MSLEARN_TOOLS))
    session = mcp_session(loop, call_timeout_s=1)
    connect(session, "mslearn")

    server.error = {"code": -32602, "message": "Invalid params"}
    messages, refused = lab_call(session, "mslearn", "microsoft_docs_search", query=1)

    assert (refused["status"], refused["error_kind"], refused["connection"]) == (
        "error",
        "jsonrpc_error",
        "open",
    )
    assert "refusé l'appel" in refused["error_text"] and "Invalid params" in refused["raw"]
    assert refused["failed_seq"] is not None
    assert messages[-1]["error"] == {"code": -32602, "message": "Invalid params"}

    server.error = None
    server.delay = 3
    _, late = lab_call(session, "mslearn", "microsoft_docs_search", query="MFA")

    assert (late["status"], late["error_kind"], late["connection"]) == (
        "error",
        "timeout",
        "closed",
    )
    assert "délai" in late["error_text"]
    assert session.mcp_lab_state()["open_server"] is None
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

    ended = one(lab_events(mark), "mcp_lab_call_ended")
    assert (ended["status"], ended["error_kind"], ended["connection"]) == (
        "cancelled",
        "stopped",
        "closed",
    )
    assert "arrêté" in ended["error_text"] and ended["failed_seq"] is not None
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

    ended = one(lab_events(mark), "mcp_lab_connect_ended")
    assert (ended["status"], ended["error_kind"]) == ("cancelled", "stopped")
    assert "arrêté" in ended["error_text"]
    # `initialize` had answered: its fields stay.
    assert ended["primitives"]["tools"] is True and ended["server_info"]["name"] == "test"
    assert session._mcp_lab_conn is None
    session.close()


def _call_sent(mark: int) -> bool:
    return any(
        e.kind == "mcp_lab_message"
        and e.payload["direction"] == "to_server"
        and e.payload["method"] == "tools/call"
        for e in lab_events(mark)
    )


def _hang_the_local_server(session: AppSession, children: list[psutil.Process]) -> int:
    """The workshop connected to the glossary, its process suspended (it reads no request
    any more), then a call sent: the session waits for an answer that never comes.
    `children`: filled with the suspended processes before anything can fail, so that the
    caller's `finally` resumes them. The journal's mark before the call."""
    connect(session)
    children += local_servers()  # the workshop's only: the brick is off
    assert children
    for child in children:
        child.suspend()
    mark = get_journal().last_seq()
    session.mcp_lab_call("local", "define_term", {"term": "MCP"})
    deadline = time.monotonic() + 10
    while not _call_sent(mark):
        assert time.monotonic() < deadline, "tools/call never left"
        time.sleep(0.02)
    assert session.state == "mcp_lab"
    return mark


def _resume(children: list[psutil.Process]) -> None:
    for child in children:
        try:
            child.resume()
        except psutil.Error:  # already closed by the session: what is expected
            pass


def test_stop_during_a_call_to_the_local_glossary_closes_its_process(loop):
    """Restes du 2026-10-01 (story 6, IA3 and BH16): « Arrêter » while the stdio server
    does not answer: the call ends « arrêté », the connection is closed and no child process
    is left."""
    session = mcp_session(loop)
    children: list[psutil.Process] = []
    try:
        mark = _hang_the_local_server(session, children)
        assert session.stop() is True
        wait_idle(session, timeout=30)
        ended = one(lab_events(mark), "mcp_lab_call_ended")
        assert ended["status"] == "cancelled" and "arrêté" in ended["error_text"], ended
        assert session._mcp_lab_conn is None
        assert session.mcp_lab_state()["open_server"] is None
        assert no_local_server_left()  # closed by « Arrêter », not by the session's end
    finally:
        _resume(children)
        session.close()
    assert no_local_server_left()


def test_the_main_screens_intentions_are_refused_during_a_workshop_exchange(loop):
    """Restes du 2026-10-01 (story 6, BH16): while the workshop waits for the glossary, the
    class (b) intentions of the main screen and of the other workshops answer 409 with the
    reason, and start nothing."""
    session = mcp_session(loop)
    client = _client(session)
    children: list[psutil.Process] = []
    sampling = {"temperature": 0.2, "top_k": 5, "top_p": 0.9, "min_p": 0.05}
    intentions = {
        "send": {"message": "Bonjour"},
        "replay": {},
        "scenario": {"scenario_id": "bare_llm"},
        "clear_conversation": {},
        "language": {"language": "en"},
        "memory": {"op": "clear"},
        "context_window": {"window": 8192},
        "select_model": {"kind": "file", "path": "fake.gguf"},
        "llm_tokenize": {"text": "Bonjour"},
        "llm_generate": {"prompt": "Bonjour", "sampling": sampling},
        "llm_compare": {"prompt": "Bonjour", "sampling_a": sampling, "sampling_b": sampling},
        "rag_lab_run": {"question": "Combien de jours de télétravail ?"},
        "mcp_lab_connect": {"server": "local"},
        "mcp_lab_call": {"server": "local", "tool": "list_terms", "arguments": {}},
        "mcp_lab_read": {"server": "local", "uri": "glossary://terms"},
        "mcp_lab_prompt": {"server": "local", "prompt": "explain_term", "arguments": {"term": "x"}},
        "mcp_lab_ask": {"server": "local", "question": "Bonjour"},
        "set_api_key": {"id": "groq", "key": "gsk-e2e-not-a-key"},
        "test_cloud_model": {"id": "groq"},
        "reset": {},
    }
    # `download_model` and `build_rag_index` answer 404 first here: the RAG brick is off.
    try:
        _hang_the_local_server(session, children)
        mark = get_journal().last_seq()
        refused = {}
        for name, body in intentions.items():
            answer = client.post(f"/api/intentions/{name}", json=body, headers=HEADERS)
            refused[name] = (answer.status_code, answer.json().get("detail", ""))
        assert {n: code for n, (code, _) in refused.items()} == dict.fromkeys(intentions, 409)
        for name, (_, detail) in refused.items():
            assert "Atelier MCP" in detail, (name, detail)
        # Nothing at all is emitted by the refusals: no event since the mark.
        started = [(e.kind, e.payload) for e in get_journal().events_since(mark)]
        assert started == [], started
        assert session.state == "mcp_lab" and session.language == "fr"
        assert session.stop() is True
        wait_idle(session, timeout=30)
    finally:
        _resume(children)
        session.close()
    assert no_local_server_left()


def test_a_server_gone_closes_the_workshops_connection(loop):
    """The server killed outside any exchange: either the connection's task saw it end
    (`mcp_lab_closed{lost}`, then a call is refused), or the next call finds it gone
    (`call_ended{error, lost, closed}`). Either way the journal says it closed once."""
    session = mcp_session(loop)
    try:
        connect(session)
        mark = get_journal().last_seq()
        for child in local_servers():
            try:
                child.kill()
                child.wait(5)
            except psutil.Error:
                pass
        try:
            _, ended = lab_call(session, "local", "define_term", term="MCP")
        except SendRefused:  # the connection's task saw the end first
            ended = None
        session.join()
        events = lab_events(mark)
        if ended is None:
            assert one(events, "mcp_lab_closed") == {"server": "local", "cause": "lost"}
        else:
            assert (ended["status"], ended["error_kind"], ended["connection"]) == (
                "error",
                "lost",
                "closed",
            )
            assert "reconnectez-vous" in ended["error_text"]
            assert not [e for e in events if e.kind == "mcp_lab_closed"]
        assert session.mcp_lab_state()["open_server"] is None is last_connection(session)
        try:
            session.mcp_lab_call("local", "define_term", {"term": "MCP"})
        except SendRefused as refused:
            assert "Connectez-vous d'abord" in str(refused.reason_text)
        else:
            raise AssertionError("refused once the connection is gone")
    finally:
        session.close()
    assert no_local_server_left()


def test_lifespan_closes_the_workshops_connection():
    from test_tools import QWEN as TEMPLATE

    engine = FakeEngine(template=TEMPLATE.decode("utf-8"), architecture="qwen35")
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
        "ask",
    }
    assert body["content"]["title_text"] and body["content_error_text"] is None
    assert body["last_session"] == [] and body["open_server"] is None
    assert body["call_presets"]["local__define_term"][0]["args"] == {"term": "MCP"}
    assert set(body["ask"]) == {
        "model_ready",
        "model_reason_text",
        "tools",
        "tools_reason_text",
        "model",
    }

    unknown = client.post("/api/intentions/mcp_lab_connect", json={"server": "x"}, headers=HEADERS)
    assert unknown.status_code == 404
    for name, payload in (
        ("mcp_lab_call", {"server": "local", "tool": "define_term", "arguments": {"term": "MCP"}}),
        ("mcp_lab_read", {"server": "local", "uri": "glossary://terms"}),
        ("mcp_lab_prompt", {"server": "local", "prompt": "explain_term"}),
        ("mcp_lab_ask", {"server": "local", "question": "MCP ?"}),
    ):
        answer = client.post(f"/api/intentions/{name}", json=payload, headers=HEADERS)
        assert answer.status_code == 409, name
    unknown_read = client.post(
        "/api/intentions/mcp_lab_read", json={"server": "x", "uri": "a"}, headers=HEADERS
    )
    assert unknown_read.status_code == 404

    mark = get_journal().last_seq()
    session._set_state("turn", "Un tour est en cours.")
    busy = client.post("/api/intentions/mcp_lab_connect", json={"server": "local"}, headers=HEADERS)
    assert busy.status_code == 409 and "Un tour est déjà en cours" in busy.json()["detail"]
    assert lab_events(mark) == []  # nothing started
    session._set_state("idle")

    ok = client.post("/api/intentions/mcp_lab_connect", json={"server": "local"}, headers=HEADERS)
    assert ok.status_code == 200 and ok.json()["step_id"].startswith("mcp")
    wait_idle(session)
    called = client.post(  # `args`, the former name, still accepted
        "/api/intentions/mcp_lab_call",
        json={"server": "local", "tool": "define_term", "args": {"term": "MCP"}},
        headers=HEADERS,
    )
    assert called.status_code == 200
    wait_idle(session)
    read = client.post(
        "/api/intentions/mcp_lab_read",
        json={"server": "local", "uri": "glossary://terms"},
        headers=HEADERS,
    )
    assert read.status_code == 200
    wait_idle(session)
    kinds = [e["kind"] for e in client.get("/api/mcp_lab").json()["last_session"]]
    assert kinds[-1] == "mcp_lab_read_ended" and "mcp_lab_call_ended" in kinds
    mark = get_journal().last_seq()
    asked = client.post(  # `doc_mode` forwarded to the session
        "/api/intentions/mcp_lab_ask",
        json={"server": "local", "question": "Que veut dire MCP ?", "doc_mode": "lazy"},
        headers=HEADERS,
    )
    assert asked.status_code == 200
    wait_idle(session)
    events = lab_events(mark)
    assert one(events, "mcp_lab_exchange_started")["doc_mode_requested"] == "lazy"
    assert one(events, "mcp_lab_model_started")["doc_mode"] == "lazy"
    assert client.get("/api/mcp_lab").json()["open_server"] == "local" == last_connection(session)
    session.close()
    assert no_local_server_left()


def test_the_lab_scope_carries_the_context_to_the_http_hook():
    scope = TraceScope(**AppSession._mcp_lab_scope("mcp4", "mslearn"), origin="brick")
    assert (scope.context_id, scope.step_id, scope.component, scope.parent_step) == (
        "mcp_lab",
        "mcp4",
        "mcp_lab.mslearn",
        None,
    )
    sub = AppSession._mcp_lab_scope("mcp4.c2", "local")
    assert (sub["parent_step"], sub["call_id"]) == ("mcp4", "mcp4.c2")
    tool = AppSession._mcp_lab_scope("mcp4.t1", "local")
    assert (tool["parent_step"], tool["call_id"]) == ("mcp4", None)
