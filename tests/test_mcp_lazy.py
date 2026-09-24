"""Story 6b: MCP lazy loading, `load_tool_doc` and documentation on demand (AD-25, AD-4).

The local server is the real child process; data.gouv.fr answers in process (`McpWeb`).
"""

from __future__ import annotations

import json

from fake_engine import FakeEngine
from test_mcp import McpWeb, card, enable, loop, mcp_session, since, wait_for, web  # noqa: F401
from test_tools import QWEN, _segments, call
from test_turn import _run

from wavestack.context.render import render_context
from wavestack.context.segments import Joined, Part, SegmentKind
from wavestack.trace.journal import get_journal

LOCAL = ("local__list_terms", "local__define_term")
DEFINE = "local__define_term"


def load(tool: str) -> str:
    return call("load_tool_doc", tool=tool)


def lazy_session(loop, outputs=("Voilà.",), **kwargs):  # noqa: F811
    session = mcp_session(loop, outputs, **kwargs)
    session.set_brick("short_memory", True)
    enable(session)
    session.set_mcp_mode(True)
    session.join()
    return session


def preview() -> dict:
    return since(0, "context_preview")[-1].payload


def exact(ctx: dict) -> None:
    """AD-4: every token belongs to one segment."""
    assert sum(s["tokens"] for s in ctx["segments"]) == ctx["used"]


def definition_names(ctx: dict) -> list[str]:
    """The names of the tools described in `tools`, in order."""
    prompt = "".join(s["text"] for s in ctx["segments"])
    tools = prompt.split("<tools>")[1].split("</tools>")[0] if "<tools>" in prompt else ""
    return [json.loads(line)["function"]["name"] for line in tools.strip().splitlines()]


# ---------- I/O matrix ----------


def test_toggle_swaps_the_documentation_for_one_line_per_tool(loop):  # noqa: F811
    session = mcp_session(loop)
    enable(session)
    full = preview()
    mark = get_journal().last_seq()

    session.set_mcp_mode(True)
    session.join()

    lazy = preview()
    assert definition_names(lazy) == ["load_tool_doc"]
    assert session.build_turn_state().tools == ("load_tool_doc",)
    assert session.build_turn_state().loadable == LOCAL
    lines = [s for s in _segments(lazy, "tool_catalog") if s["text"].startswith("- local__")]
    assert [(s["brick"], s["component"]) for s in lines] == [("mcp", "mcp.local")] * 2
    assert lines[0]["text"].startswith("- local__list_terms : Liste les termes")
    assert {s["brick"] for s in _segments(lazy, "tool_catalog")} == {"mcp"}  # AC: MCP brick
    assert lazy["used"] < full["used"]
    exact(lazy)
    assert since(mark, "harness_error") == []
    assert since(mark, "mcp_connect_started") == []  # the switch contacts no server
    mcp = card("mcp")
    assert mcp["mode"] == "lazy" and mcp["pending"] and mcp["lazy_label_fr"] == "Lazy loading"
    session.close()


def test_load_then_call_in_the_same_turn_then_the_next_turn(loop):  # noqa: F811
    outputs = [load(DEFINE), call(DEFINE, term="MCP"), "Voilà.", "Encore."]
    session = lazy_session(loop, outputs)
    mark = get_journal().last_seq()

    events = _run(session, "Que veut dire MCP ?")

    loading, calling = events["tool_started"]
    assert loading["phase_label"] == "Chargement de la documentation"
    assert loading["source"] == "harness"
    (started,) = [e for e in since(mark, "tool_started") if e.payload["tool"] == "load_tool_doc"]
    assert (started.brick, started.component) == ("mcp", "core.harness")
    first_answer, second_answer = events["tool_ended"]
    assert json.loads(first_answer["result"])["function"]["name"] == DEFINE
    assert calling["tool"] == DEFINE and second_answer["status"] == "ok"
    assert "Model Context Protocol" in second_answer["result"]
    assert events["model_call_ended"][1]["tool_calls"] == [
        {"name": DEFINE, "arguments": {"term": "MCP"}}
    ]
    second = events["context_rendered"][1]
    doc = [s for s in _segments(second, "tool_catalog") if s["text"].startswith('{"type"')]
    assert [(s["brick"], s["component"]) for s in doc] == [("mcp", "mcp.local")]
    assert definition_names(second) == ["load_tool_doc"]  # nothing enters `tools` in the turn
    assert "prefix_not_reused" not in events and "harness_error" not in events
    for ctx in events["context_rendered"]:
        exact(ctx)

    after = _run(session, "Et encore ?")

    ctx = after["context_rendered"][0]
    assert definition_names(ctx) == [DEFINE, "load_tool_doc"]
    lines = [s["text"] for s in _segments(ctx, "tool_catalog") if s["text"].startswith("- ")]
    assert lines == [lines[0]] and lines[0].startswith("- local__list_terms")
    history = [s["text"] for s in _segments(ctx, "history")]
    assert "Documentation de « local__define_term » chargée." in history
    assert not any(t.startswith('{"type"') for t in history)
    exact(ctx)
    session.close()


def test_same_turn_call_is_typed_by_the_loaded_schema(loop, web):  # noqa: F811
    tool = {
        "name": "get_page",
        "description": "Donne une page de résultats.",
        "inputSchema": {
            "type": "object",
            "properties": {"page": {"type": "integer"}},
            "required": ["page"],
        },
    }
    server = web(McpWeb([tool], lambda p: {"content": [{"type": "text", "text": str(p)}]}))
    outputs = [load("datagouv__get_page"), call("datagouv__get_page", page="3"), "Voilà."]
    session = mcp_session(loop, outputs)
    session.set_mcp_server("local", False)
    enable(session, "datagouv")
    session.set_mcp_mode(True)
    session.join()

    events = _run(session, "Page 3")

    assert events["model_call_ended"][1]["tool_calls"] == [
        {"name": "datagouv__get_page", "arguments": {"page": 3}}
    ]
    assert [e["status"] for e in events["tool_ended"]] == ["ok", "ok"]
    sent = [json.loads(r.content) for r in server.sent if r.method == "POST"]
    calls = [m["params"]["arguments"] for m in sent if m.get("method") == "tools/call"]
    assert calls == [{"page": 3}]
    session.close()


def test_mode_switch_is_pending_until_the_next_send(loop):  # noqa: F811
    session = mcp_session(loop, ["Bonjour."])
    enable(session)
    _run(session, "Bonjour")
    assert not card("mcp")["pending"]

    session.set_mcp_mode(True)
    session.join()
    assert card("mcp")["pending"]

    _run(session, "Bonjour")
    assert not card("mcp")["pending"]
    session.close()


def test_undocumented_call_is_refused_before_sending_and_counts_as_a_retry(loop):  # noqa: F811
    session = lazy_session(loop, [call("local__list_terms")])

    events = _run(session, "Liste les termes")

    assert "tool_started" not in events  # nothing reached the server
    malformed = events["tool_call_malformed"]
    assert [m["reaction"] for m in malformed] == ["retry", "retry", "stop"]
    assert (
        "La documentation de « local__list_terms » n'est pas chargée : appelle d'abord "
        'load_tool_doc avec tool="local__list_terms".'
    ) in malformed[0]["detail_fr"]
    assert events["limit_reached"][0]["limit"] == "retries"
    result = _segments(events["context_rendered"][1], "tool_result")[0]
    assert "n'est pas chargée" in result["text"]
    session.close()


def test_loading_twice_or_an_unknown_name(loop):  # noqa: F811
    session = lazy_session(loop, [load(DEFINE), load(DEFINE), load("nope"), "Voilà."])

    events = _run(session, "Que veut dire MCP ?")

    _, again, unknown = events["tool_ended"]
    assert again["result"] == "La documentation de « local__define_term » est déjà chargée."
    last = events["context_rendered"][-1]
    results = [s["text"] for s in _segments(last, "tool_result")]
    assert again["result"] in results  # a short tool_result, not the documentation again
    docs = [s for s in _segments(last, "tool_catalog") if s["text"].startswith('{"type"')]
    assert len(docs) == 1
    assert unknown["status"] == "error"
    assert "« nope »" in unknown["error_fr"] and "local__list_terms" in unknown["error_fr"]
    session.close()


def test_everything_loaded_removes_the_meta_tool_then_clearing_unloads(loop):  # noqa: F811
    session = lazy_session(loop, [load(LOCAL[0]), load(LOCAL[1]), "Voilà."])
    _run(session, "Charge tout")

    assert session.build_turn_state().tools == LOCAL
    assert session.build_turn_state().loadable == ()
    mark = get_journal().last_seq()

    session.clear_conversation()
    session.join()

    assert session.build_turn_state().tools == ("load_tool_doc",)
    after = since(mark, "context_preview")[-1].payload
    assert definition_names(after) == ["load_tool_doc"]
    session.close()


def test_a_loaded_documentation_waits_while_its_server_is_off(loop):  # noqa: F811
    session = lazy_session(loop, [load(DEFINE), "Voilà."])
    _run(session, "Que veut dire MCP ?")
    assert session.build_turn_state().tools == (DEFINE, "load_tool_doc")

    session.set_mcp_server("local", False)
    session.join()
    assert session.build_turn_state().tools == ()

    mark = get_journal().last_seq()
    session.set_mcp_server("local", True)
    wait_for(session, "mcp_connect_ended", mark)
    assert session.build_turn_state().tools == (DEFINE, "load_tool_doc")
    session.close()


DATAGOUV_TOOLS = [
    {
        "name": f"tool_{i}",
        "description": "Recherche dans les jeux de données publics de data.gouv.fr. " * 30,
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
    }
    for i in range(10)
]


def test_datagouv_overflow_names_lazy_loading_which_avoids_it(loop, web):  # noqa: F811
    web(McpWeb(DATAGOUV_TOOLS))
    session = mcp_session(loop, ["Bonjour."])
    session.set_mcp_server("local", False)
    enable(session, "datagouv")

    events = _run(session, "Bonjour")

    (overflow,) = events["context_overflow"]
    assert "lazy loading" in overflow["message_fr"] and "serveur MCP" in overflow["message_fr"]
    assert "model_call_started" not in events

    session.set_mcp_mode(True)
    events = _run(session, "Bonjour")

    assert "context_overflow" not in events
    assert events["turn_ended"][0]["status"] == "completed"
    ctx = events["context_rendered"][0]
    lines = [s for s in _segments(ctx, "tool_catalog") if s["text"].startswith("- datagouv__")]
    assert len(lines) == 10 and {s["component"] for s in lines} == {"mcp.datagouv"}
    assert all(s["text"].endswith("…") and len(s["text"]) <= 150 for s in lines)
    exact(ctx)
    session.close()


def test_lazy_overflow_suggests_unloading_not_lazy_loading(loop, web):  # noqa: F811
    web(McpWeb(DATAGOUV_TOOLS))
    session = mcp_session(loop, ["Bonjour."], window=1536)
    session.set_mcp_server("local", False)
    enable(session, "datagouv")
    session.set_mcp_mode(True)

    events = _run(session, "Bonjour")

    (overflow,) = events["context_overflow"]
    assert "passez la carte MCP en lazy loading" not in overflow["message_fr"]
    assert "décharger les documentations" in overflow["message_fr"]
    session.close()


def test_mcp_mode_intention_http(loop):  # noqa: F811
    from test_bricks import HEADERS, _client

    session = mcp_session(loop)
    client = _client(session)

    response = client.post("/api/intentions/mcp_mode", json={"lazy": True}, headers=HEADERS)

    assert response.status_code == 200
    session.join()
    assert card("mcp")["mode"] == "lazy"
    assert "load_tool_doc" not in [o["id"] for o in card("tools")["options"]]
    harness = {"tool": "load_tool_doc", "enabled": True}
    refused = client.post("/api/intentions/tool", json=harness, headers=HEADERS)
    assert refused.status_code == 404
    session.close()


# ---------- attribution (AD-4) ----------


def test_joined_description_with_two_servers_attributes_each_line():
    """`load_tool_doc` with two servers on the Qwen template: no attribution error."""
    engine = FakeEngine(template=QWEN.decode("utf-8"), architecture="qwen35")
    lines = [
        Part(SegmentKind.TOOL_CATALOG, "- local__define_term : Donne la définition.", "mcp",
             "mcp.local", "local__define_term"),
        Part(SegmentKind.TOOL_CATALOG, "- datagouv__search : Cherche un jeu « public ».", "mcp",
             "mcp.datagouv", "datagouv__search"),
    ]  # fmt: skip
    name = Part(SegmentKind.TOOL_CATALOG, "load_tool_doc", "mcp", "core.harness", "load_tool_doc")
    intro = Part(
        SegmentKind.TOOL_CATALOG, "Charge une documentation :", "mcp", "core.harness", name.group
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": name,
                "parameters": {"type": "object", "properties": {"tool": {"type": "string"}}},
                "description": Joined((intro, *lines), sep="\n"),
            },
        }
    ]
    mark = get_journal().last_seq()

    rendered = render_context(
        engine,
        QWEN.decode("utf-8"),
        [{"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Bonjour")]}],
        call_id=None,
        special_tokens=("<|im_start|>", "<|im_end|>"),
        tools=tools,
        enable_thinking=False,
    )

    assert [e for e in get_journal().events_since(mark) if e.kind == "harness_error"] == []
    assert sum(s.tokens for s in rendered.segments) == len(rendered.ids)
    catalog = [(s.component, s.text) for s in rendered.segments if s.kind == "tool_catalog"]
    assert catalog[1:] == [(p.component, p.text) for p in lines]
    assert catalog[0][0] == "core.harness" and catalog[0][1].endswith(intro.text)
    assert '"description": "Charge une documentation :\\n- local__define_term' in rendered.prompt
