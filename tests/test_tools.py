"""Stories 5a-5b: native and network tools, the bounded turn loop, attribution."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from fake_engine import FakeEngine, booted_session
from test_bricks import HEADERS, _client
from test_turn import _run

from wavestack import config
from wavestack.models.capabilities import TOOL_CALL_TAGS, ChannelSplitter
from wavestack.net.factory import create_client
from wavestack.session.app_session import AppSession
from wavestack.tools import network
from wavestack.tools.native import calculator, read_file
from wavestack.tools.parser import ToolCall, parse_tool_calls
from wavestack.tools.registry import ToolError
from wavestack.trace.journal import get_journal

QWEN = (Path(__file__).parent / "fixtures" / "qwen3_5_chat_template.jinja").read_bytes()


def call(name: str, **arguments: str) -> str:
    """A tool call in the `qwen3_coder` format, as Qwen3.5 writes it."""
    params = "".join(f"<parameter={k}>\n{v}\n</parameter>\n" for k, v in arguments.items())
    return f"<tool_call>\n<function={name}>\n{params}</function>\n</tool_call>"


def tool_session(outputs: list[str], **kwargs):
    engine = FakeEngine(outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35")
    session = booted_session(engine, **kwargs)
    session.set_brick("tools", True)
    return engine, session


def _segments(ctx: dict, kind: str) -> list[dict]:
    return [s for s in ctx["segments"] if s["kind"] == kind]


def _prompt(ctx: dict) -> str:
    return "".join(s["text"] for s in ctx["segments"])


# ---------- I/O matrix ----------


def test_full_cycle_calculator():
    engine, session = tool_session([call("calculator", expression="12*37"), "Cela fait 444."])

    events = _run(session, "Combien font 12 × 37 ?")

    first, second = events["context_rendered"]
    catalog = _segments(first, "tool_catalog")
    assert [s["component"] for s in catalog] == [
        "tools.get_datetime",
        "tools.calculator",
        "tools.read_file",
    ]  # one segment per tool
    assert {s["brick"] for s in catalog} == {"tools"}
    assert "Calcule exactement" in catalog[1]["text"]
    group = next(g for g in first["breakdown"] if g["group"] == "tool_catalog")
    assert group["label_fr"] == "Descriptions d'outils" and group["tokens"] > 0
    for ctx in (first, second):  # the sum equals the total; the prompt sent is the one shown
        assert sum(s["tokens"] for s in ctx["segments"]) == ctx["used"]
    assert [list(_prompt(c).encode()) for c in (first, second)] == engine.calls

    assert events["model_call_ended"][0]["tool_calls"] == [
        {"name": "calculator", "arguments": {"expression": "12*37"}}
    ]
    assert events["tool_started"][0]["tool"] == "calculator"
    ended = events["tool_ended"][0]
    assert ended["status"] == "ok" and ended["result"] == "444"
    assert [s["text"] for s in _segments(second, "tool_result")] == ["444"]
    assert _segments(second, "tool_result")[0]["component"] == "tools.calculator"
    assert "calculator" in _segments(second, "assistant_turn")[0]["text"]  # the call, re-rendered
    assert "prefix_not_reused" not in events  # append only: the template re-renders the call as is
    assert events["model_call_ended"][1]["text"] == "Cela fait 444."
    assert events["turn_ended"][0]["status"] == "completed"


def test_two_tools_in_one_turn():
    engine, session = tool_session(
        [call("get_datetime"), call("calculator", expression="2+2"), "Voilà."]
    )

    events = _run(session, "Quelle heure est-il, et combien font 2 + 2 ?")

    assert len(engine.calls) == 3
    assert [e["tool"] for e in events["tool_started"]] == ["get_datetime", "calculator"]
    assert [e["status"] for e in events["tool_ended"]] == ["ok", "ok"]
    assert events["turn_ended"][0]["status"] == "completed"


def test_malformed_call_retries_then_stops_at_the_third_failure():
    engine, session = tool_session(["<tool_call>\n<function=calculator\n12*37\n</tool_call>"])

    events = _run(session, "Combien font 12 × 37 ?")

    malformed = events["tool_call_malformed"]
    assert [m["reaction"] for m in malformed] == ["retry", "retry", "stop"]
    assert malformed[0]["fragment"].startswith("<tool_call>") and malformed[0]["raw"]
    assert "<function=" in malformed[0]["detail_fr"]
    assert len(engine.calls) == 3
    second = events["context_rendered"][1]  # the error is reinjected as a tool response
    assert _segments(second, "tool_result")[0]["text"].startswith("Erreur :")
    assert events["limit_reached"] == [
        {"limit": "retries", "message_fr": events["limit_reached"][0]["message_fr"]}
    ]
    assert events["turn_ended"][0]["status"] == "limit"
    assert "tool_started" not in events
    assert session.state == "idle"


@pytest.mark.parametrize("disable", [False, True])
def test_unknown_or_disabled_tool_names_the_available_ones(disable):
    name = "calculator" if disable else "get_weather"
    engine, session = tool_session([call(name, expression="1+1"), "Je ne peux pas."])
    if disable:
        session.set_tool("calculator", False)

    events = _run(session, "Combien font 1 + 1 ?")

    detail = events["tool_call_malformed"][0]["detail_fr"]
    assert f"« {name} »" in detail and "get_datetime" in detail and "read_file" in detail
    assert ("calculator" in detail.split("disponibles")[1]) is not disable
    assert events["tool_call_malformed"][0]["reaction"] == "retry"
    assert "tool_started" not in events
    assert events["turn_ended"][0]["status"] == "completed"


def test_call_bound_stops_after_six_calls():
    engine, session = tool_session([call("get_datetime")])

    events = _run(session, "Quelle heure ?")

    assert len(engine.calls) == 6 and len(events["tool_ended"]) == 6
    assert events["limit_reached"][0]["limit"] == "calls"
    assert events["turn_ended"][0]["status"] == "limit"


WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="drive paths exist on Windows only")


@pytest.mark.parametrize(
    "path",
    ["../../pyproject.toml", pytest.param("C:/Windows/win.ini", marks=WINDOWS_ONLY), "/etc/passwd"],
)
def test_escape_is_refused_and_reinjected(path):
    _, session = tool_session([call("read_file", path=path), "Refusé."])

    events = _run(session, "Lis ce fichier")

    ended = events["tool_ended"][0]
    assert ended["status"] == "error" and ended["result"] is None
    assert "Accès refusé" in ended["error_fr"]
    tool_result = _segments(events["context_rendered"][1], "tool_result")[0]["text"]
    assert tool_result.startswith("Erreur : Accès refusé") and "[project]" not in tool_result
    assert events["turn_ended"][0]["status"] == "completed"


def test_execution_errors_are_reinjected_and_not_retries():
    outputs = [
        call("read_file", path="absent.txt"),
        call("calculator", expression="1/0"),
        call("calculator", expression="__import__('os')"),
        "Désolé.",
    ]
    engine, session = tool_session(outputs)

    events = _run(session, "Essaie")

    assert [e["status"] for e in events["tool_ended"]] == ["error"] * 3
    assert "Fichier absent" in events["tool_ended"][0]["error_fr"]
    assert "notes_reunion.txt" in events["tool_ended"][0]["error_fr"]
    assert "Division par zéro" in events["tool_ended"][1]["error_fr"]
    assert "limit_reached" not in events and "tool_call_malformed" not in events
    assert events["turn_ended"][0]["status"] == "completed" and len(engine.calls) == 4


@pytest.mark.parametrize("all_tools_off", [False, True])
def test_brick_off_or_every_tool_off_is_the_bare_llm_byte_for_byte(all_tools_off):
    template = QWEN.decode("utf-8")
    bare = FakeEngine(template=template, architecture="qwen35")
    _run(booted_session(bare), "Bonjour")
    engine, session = tool_session(["Bonjour !"])
    if all_tools_off:
        for name in ("get_datetime", "calculator", "read_file"):
            session.set_tool(name, False)
    else:
        session.set_brick("tools", False)

    events = _run(session, "Bonjour")

    assert engine.calls == bare.calls
    assert "tool_catalog" not in {s["kind"] for s in events["context_rendered"][0]["segments"]}


def test_model_without_parser_makes_the_brick_unavailable():
    session = booted_session(FakeEngine())  # ChatML, unknown family: no tool-call format
    session.set_brick("tools", True)

    available, reason = session._availability("tools")

    assert available is False and "l'appel d'outils" in reason
    assert session.build_turn_state().tools == ()


def test_output_cut_inside_a_tool_call_takes_the_malformed_path():
    cut = "<tool_call>\n<function=calculator>\n<parameter=expression>\n" + "1+" * 300
    _, session = tool_session([cut, "Pardon."])

    events = _run(session, "Calcule")

    assert events["output_truncated"][0]["channel"] == "tool_call"
    malformed = events["tool_call_malformed"][0]
    assert "coupée" in malformed["detail_fr"] and malformed["reaction"] == "retry"
    assert events["turn_ended"][0]["status"] == "completed"


def test_text_after_the_call_breaks_the_prefix_and_is_traced():
    _, session = tool_session([call("get_datetime") + "\nJ'attends.", "Il est midi."])

    events = _run(session, "Quelle heure ?")

    reused = events["prefix_not_reused"][0]
    assert 0 < reused["common_tokens"] < events["context_rendered"][1]["used"]
    assert "relit" in reused["message_fr"]


def test_completed_turn_enters_history_with_its_calls_and_results():
    _, session = tool_session([call("calculator", expression="12*37"), "444.", "Oui."])
    session.set_brick("short_memory", True)
    _run(session, "Combien font 12 × 37 ?")

    ctx = _run(session, "Tu es sûr ?")["context_rendered"][0]

    history = [s["text"] for s in _segments(ctx, "history")]
    assert history[0] == "Combien font 12 × 37 ?" and "444" in history
    assert any("calculator" in text and "12*37" in text for text in history)
    assert {s["brick"] for s in _segments(ctx, "history")} == {"short_memory"}
    assert sum(s["tokens"] for s in ctx["segments"]) == ctx["used"]


def test_tool_sub_options_are_cards_nodes_and_pending():
    _, session = tool_session(["ok"])
    session.join()
    card = next(b for b in _state(session)["bricks"] if b["id"] == "tools")
    assert [(o["id"], o["enabled"], o["network"]) for o in card["options"]] == [
        ("get_datetime", True, False),
        ("calculator", True, False),
        ("read_file", True, False),
        ("public_holidays", False, True),
        ("wikipedia_summary", False, True),
        ("fetch_page", False, True),
    ]
    assert "6 appels" in card["limits_fr"] and "2 nouveaux essais" in card["limits_fr"]
    nodes = {n["id"]: n for n in _architecture(session)["nodes"]}
    assert nodes["tools.read_file"]["kind"] == "tool" and nodes["file.demo_dir"]["kind"] == "file"
    assert {"from": "tools.read_file", "to": "file.demo_dir", "crosses_boundary": False} in (
        _architecture(session)["edges"]
    )

    _run(session, "Bonjour")
    session.set_tool("read_file", False)

    card = next(b for b in _state(session)["bricks"] if b["id"] == "tools")
    assert card["pending"]
    assert not {"tools.read_file", "file.demo_dir"} & {
        n["id"] for n in _architecture(session)["nodes"]
    }


def test_tool_intention_http():
    _, session = tool_session(["ok"])
    client = _client(session)

    ok = client.post(
        "/api/intentions/tool", json={"tool": "calculator", "enabled": False}, headers=HEADERS
    )
    unknown = client.post(
        "/api/intentions/tool", json={"tool": "nope", "enabled": True}, headers=HEADERS
    )

    assert ok.status_code == 200 and unknown.status_code == 404
    assert session.build_turn_state().tools == ("get_datetime", "read_file")


def _state(session) -> dict:
    return _client(session).get("/api/state").json()["bricks_changed"]


def _architecture(session) -> dict:
    return _client(session).get("/api/state").json()["architecture_changed"]


# ---------- parsers, splitter, confinement ----------


def test_parser_qwen3_coder_converts_per_schema():
    raw = "Je calcule.\n\n" + call("f", n="42", x="1.5", ok="true", s="12*37", o='{"a": 1}')
    schemas = {"f": {"n": "integer", "x": "number", "ok": "boolean", "s": "string", "o": "object"}}

    calls, malformed = parse_tool_calls(raw, "qwen3_coder", schemas)

    assert malformed is None
    assert calls == [ToolCall("f", {"n": 42, "x": 1.5, "ok": True, "s": "12*37", "o": {"a": 1}})]
    two, _ = parse_tool_calls(call("a") + "\n" + call("b"), "qwen3_coder", {})
    assert [c.name for c in two] == ["a", "b"]
    _, unclosed = parse_tool_calls(
        "<tool_call>\n<function=f>\n<parameter=n>\n1\n</function>\n</tool_call>", "qwen3_coder", {}
    )
    assert unclosed is not None and "</parameter>" in unclosed.detail_fr
    _, open_only = parse_tool_calls("<tool_call>\n<function=f>", "qwen3_coder", {})
    assert open_only is not None and "jamais fermée" in open_only.detail_fr
    assert parse_tool_calls("Pas d'appel.", "qwen3_coder", {}) == ([], None)


def test_parser_hermes():
    raw = '<tool_call>\n{"name": "calculator", "arguments": {"expression": "2*3"}}\n</tool_call>'
    assert parse_tool_calls(raw, "hermes", {}) == (
        [ToolCall("calculator", {"expression": "2*3"})],
        None,
    )
    as_string = '<tool_call>{"name": "f", "arguments": "{\\"a\\": 1}"}</tool_call>'
    assert parse_tool_calls(as_string, "hermes", {})[0] == [ToolCall("f", {"a": 1})]
    _, bad = parse_tool_calls("<tool_call>{name: f}</tool_call>", "hermes", {})
    assert bad is not None and "JSON" in bad.detail_fr and bad.fragment.startswith("<tool_call>")


def test_splitter_tool_call_channel():
    splitter = ChannelSplitter(("<think>", "</think>"), tool_tags=TOOL_CALL_TAGS)
    out = splitter.feed("Je calcule.<tool_c") + splitter.feed("all>\nx\n</tool_call>fin")
    out += splitter.flush()
    assert out == [("text", "Je calcule."), ("tool_call", "\nx\n"), ("text", "fin")]
    splitter = ChannelSplitter(("<think>", "</think>"), tool_tags=TOOL_CALL_TAGS)
    out = splitter.feed("a<think>r</think>b<tool_call>x</tool_call>") + splitter.flush()
    assert out == [("text", "a"), ("reasoning", "r"), ("text", "b"), ("tool_call", "x")]


def test_calculator_whitelist_and_bounds():
    assert calculator("12*37") == "444"
    assert calculator("12 × 37") == "444"
    assert calculator("(3+4)**2 - 7 // 2 % 5") == "46"
    for dangerous in (
        "1,000*3",  # a comma is refused, never read as a decimal point
        "__import__('os')",
        "9**9**9",
        "open('x')",
        "2**10000",
        "True + 1",
        "[1]",
    ):
        with pytest.raises(ToolError) as refused:
            calculator(dangerous)
        assert refused.value.message_fr[0].isupper()  # a French sentence, never a traceback
    with pytest.raises(ToolError, match="Division par zéro"):
        calculator("1/0")


def test_read_file_confined_to_demo_files(tmp_path):
    assert "WaveStack" in read_file("notes_reunion.txt")
    assert "confidentiel/budget_projet.txt" in read_file(".")
    escapes = ["../../pyproject.toml", str(tmp_path), "/etc/passwd"]
    if os.name == "nt":  # a backslash separator and UNC paths exist on Windows only
        escapes += ["..\\..\\pyproject.toml", "//srv/x"]
    for escape in escapes:
        with pytest.raises(ToolError, match="Accès refusé"):
            read_file(escape)
    with pytest.raises(ToolError, match="Fichier absent"):
        read_file("absent.txt")


# ---------- review follow-ups ----------


def test_stop_during_a_tool_turn_ends_cancelled_without_another_call():
    engine, session = tool_session([call("get_datetime"), "Il est midi."])
    session.set_brick("short_memory", True)

    def stop_after_tool(envelope) -> None:
        if envelope.kind == "tool_ended":
            session.stop()

    get_journal().subscribe(stop_after_tool)
    try:
        events = _run(session, "Quelle heure ?")
    finally:
        get_journal().unsubscribe(stop_after_tool)

    assert events["tool_ended"][0]["status"] == "ok"
    assert events["turn_ended"][0]["status"] == "cancelled"
    assert len(engine.calls) == 1
    assert session.build_turn_state().history == ()


def test_refused_call_on_the_last_allowed_call_stops_on_the_call_bound():
    _, session = tool_session([call("get_datetime")] * 5 + [call("nope")])

    events = _run(session, "Quelle heure ?")

    malformed = events["tool_call_malformed"]
    assert len(malformed) == 1 and malformed[0]["reaction"] == "stop"
    assert malformed[0]["fragment"] == call("nope")  # the source block, found in the raw output
    assert malformed[0]["fragment"] in malformed[0]["raw"]
    assert events["limit_reached"][0]["limit"] == "calls"
    assert events["turn_ended"][0]["status"] == "limit"


def test_configured_bounds_apply_and_show_on_the_card():
    engine = FakeEngine(
        outputs=[call("get_datetime")], template=QWEN.decode("utf-8"), architecture="qwen35"
    )
    values = {
        "context": {"window": 4096, "near_limit_ratio": 0.8},
        "tools": {"max_calls": 2, "max_retries": 0},
    }
    session = AppSession(config.Config(values=values), engine_factory=lambda path, n_ctx: engine)
    session.boot("fake.gguf").result()
    session.set_brick("tools", True)

    events = _run(session, "Quelle heure ?")

    assert len(engine.calls) == 2 and events["limit_reached"][0]["limit"] == "calls"
    card = next(b for b in events["bricks_changed"][-1]["bricks"] if b["id"] == "tools")
    assert "2 appels" in card["limits_fr"] and "0 nouveaux essais" in card["limits_fr"]


def test_bounds_below_the_minimum_are_clamped():
    cfg = config.Config(values={"tools": {"max_calls": 0, "max_retries": -3}})
    assert (cfg.tool_max_calls, cfg.tool_max_retries) == (1, 0)


# ---------- story 5b: network tools (AD-14, AD-15), never the real network ----------

HOLIDAYS_URL = "https://calendrier.api.gouv.fr/jours-feries/metropole/2026.json"


@pytest.fixture
def web(monkeypatch):
    """Network tools answer from `handler` through the real factory (`MockTransport`).

    Returns the requests that actually reached the transport.
    """
    sent: list[httpx.Request] = []

    def install(handler):
        def transport(request):
            sent.append(request)
            return handler(request)

        monkeypatch.setattr(
            network,
            "create_client",
            lambda **kw: create_client(transport=httpx.MockTransport(transport), **kw),
        )
        return sent

    return install


def network_session(tool: str, outputs: list[str]):
    engine, session = tool_session(outputs)
    session.set_tool(tool, True)
    return engine, session


def _node(session, node_id: str) -> dict:
    return next(n for n in _architecture(session)["nodes"] if n["id"] == node_id)


def test_network_tools_start_disabled_and_absent_from_the_catalog():
    _, session = tool_session(["ok"])

    events = _run(session, "Bonjour")

    assert session.build_turn_state().tools == ("get_datetime", "calculator", "read_file")
    catalog = _segments(events["context_rendered"][0], "tool_catalog")
    assert [s["component"] for s in catalog] == [
        "tools.get_datetime",
        "tools.calculator",
        "tools.read_file",
    ]
    assert not any(n["hosting"] == "network" for n in _architecture(session)["nodes"])


def test_public_holidays_traces_the_exact_request_then_the_node_is_available(web):
    days = {"2026-01-01": "1er janvier", "2026-05-01": "1er mai"}
    sent = web(lambda r: httpx.Response(200, json=days))
    outputs = [call("public_holidays", year="2026"), "Voilà."]
    _, session = network_session("public_holidays", outputs)
    node = _node(session, "tools.public_holidays")
    assert (node["hosting"], node["contact"], node["available"]) == (
        "network",
        "not_contacted",
        True,
    )
    assert {"from": "tools.public_holidays", "to": "core.harness", "crosses_boundary": True} in (
        _architecture(session)["edges"]
    )
    mark = get_journal().last_seq()

    events = _run(session, "Quels sont les jours fériés en 2026 ?")

    (outbound,) = events["outbound_request"]
    preview = session._registry.get("public_holidays").preview(year=2026)
    assert preview == {"method": "GET", "url": HOLIDAYS_URL, "body": ""}
    assert {k: outbound[k] for k in ("method", "url", "body")} == preview  # traced = previewed
    # Story 23: the headers sent, public ones in clear, the contact in the User-Agent.
    traced = {h["name"]: h["value"] for h in outbound["headers"]}
    assert config.DEFAULT_NET_CONTACT in traced["User-Agent"] and traced["Accept"] == "*/*"
    assert not any(h["masked"] for h in outbound["headers"])
    assert (sent[0].method, str(sent[0].url), sent[0].content) == ("GET", HOLIDAYS_URL, b"")
    kinds = [e.kind for e in get_journal().events_since(mark)]
    started = kinds.index("tool_started")
    assert started < kinds.index("outbound_request") < kinds.index("tool_ended")
    assert events["tool_ended"][0]["result"] == "2026-01-01 : 1er janvier\n2026-05-01 : 1er mai"
    assert _node(session, "tools.public_holidays")["contact"] == "available"


def test_wikipedia_summary_and_absent_page(web):
    def handler(request):
        if request.url.path.endswith("/Tour_Eiffel"):
            return httpx.Response(200, json={"title": "Tour Eiffel", "extract": "Tour de fer."})
        return httpx.Response(404, json={})

    sent = web(handler)
    outputs = [
        call("wikipedia_summary", title="Tour Eiffel"),
        call("wikipedia_summary", title="Nulle part"),
        "Voilà.",
    ]
    _, session = network_session("wikipedia_summary", outputs)

    events = _run(session, "Parle-moi de la tour Eiffel")

    assert str(sent[0].url) == "https://fr.wikipedia.org/api/rest_v1/page/summary/Tour_Eiffel"
    ok, absent = events["tool_ended"]
    assert ok["status"] == "ok" and ok["result"] == "Tour Eiffel\nTour de fer."
    assert absent["status"] == "error" and "Page absente" in absent["error_fr"]
    node = _node(session, "tools.wikipedia_summary")
    assert node["contact"] == "available" and node["available"]  # the service did answer


def test_fetch_page_converts_html_to_text_and_cuts_it(web):
    html = (
        "<html><head><style>p {color: red}</style><script>var x = 1;</script></head>"
        "<body><h1>Paris</h1>\n<p>Capitale de la <b>France</b>.</p>\n<p>" + "x" * 5000 + "</p>"
    )
    web(lambda r: httpx.Response(200, text=html, headers={"content-type": "text/html"}))
    outputs = [call("fetch_page", url="https://fr.wikipedia.org/wiki/Paris"), "Voilà."]
    # Lot B: the fake engine counts a token per byte; the bound in tokens is not tested here.
    _, session = tool_session(outputs, values={"tools": {"result_max_tokens": 8000}})
    session.set_tool("fetch_page", True)

    events = _run(session, "Lis la page Paris")

    result = events["tool_ended"][0]["result"]
    assert result.startswith("Paris\nCapitale de la France.\nxxx")
    assert "<" not in result and "color" not in result and "var x" not in result
    assert "[Texte coupé à 4000 caractères sur" in result
    assert len(result.split("\n[Texte coupé")[0]) == 4000


@pytest.mark.parametrize("url", ["https://example.com", "http://fr.wikipedia.org/wiki/Paris"])
def test_fetch_page_refuses_before_sending_and_leaves_the_state(web, url):
    sent = web(lambda r: httpx.Response(200))
    _, session = network_session("fetch_page", [call("fetch_page", url=url), "Refusé."])

    events = _run(session, "Lis cette page")

    ended = events["tool_ended"][0]
    assert ended["status"] == "error" and "Adresse refusée" in ended["error_fr"]
    assert sent == [] and "outbound_request" not in events
    assert _node(session, "tools.fetch_page")["contact"] == "not_contacted"
    assert events["turn_ended"][0]["status"] == "completed"


def test_redirect_outside_the_list_is_refused_and_the_node_unavailable(web):
    web(lambda r: httpx.Response(302, headers={"location": "https://example.com/"}))
    outputs = [call("wikipedia_summary", title="Paris"), "Pardon."]
    _, session = network_session("wikipedia_summary", outputs)

    events = _run(session, "Paris ?")

    assert [o["url"] for o in events["outbound_request"]] == [
        "https://fr.wikipedia.org/api/rest_v1/page/summary/Paris"
    ]
    ended = events["tool_ended"][0]
    assert ended["status"] == "error" and "example.com" in ended["error_fr"]
    node = _node(session, "tools.wikipedia_summary")
    assert node["contact"] == "unavailable" and not node["available"]
    assert node["reason_fr"] == ended["error_fr"]


def test_offline_error_is_reinjected_and_local_tools_still_work(web):
    def offline(request):
        raise httpx.ConnectError("no route", request=request)

    web(offline)
    outputs = [call("public_holidays", year="2026"), call("get_datetime"), "Voilà."]
    _, session = network_session("public_holidays", outputs)

    events = _run(session, "Prochain jour férié ?")

    network_end, local_end = events["tool_ended"]
    assert network_end["status"] == "error" and "injoignable" in network_end["error_fr"]
    tool_result = _segments(events["context_rendered"][1], "tool_result")[0]["text"]
    assert tool_result.startswith("Erreur : Service injoignable")
    assert local_end["status"] == "ok"
    node = _node(session, "tools.public_holidays")
    assert node["contact"] == "unavailable" and "injoignable" in node["reason_fr"]
    assert events["turn_ended"][0]["status"] == "completed"


def test_fetch_page_redirect_is_checked_again_on_every_hop(web):
    def handler(request):
        return httpx.Response(302, headers={"location": "http://fr.wikipedia.org/wiki/Paris"})

    sent = web(handler)
    outputs = [call("fetch_page", url="https://fr.wikipedia.org/wiki/Paris"), "Pardon."]
    _, session = network_session("fetch_page", outputs)

    events = _run(session, "Lis la page Paris")

    assert [str(r.url) for r in sent] == ["https://fr.wikipedia.org/wiki/Paris"]
    assert [o["url"] for o in events["outbound_request"]] == [str(sent[0].url)]
    ended = events["tool_ended"][0]
    assert ended["status"] == "error" and "Adresse refusée" in ended["error_fr"]
    assert "http://fr.wikipedia.org" in ended["error_fr"]


def test_html_to_text_breaks_blocks_and_skips_page_chrome():
    html = (
        "<header>Menu</header><nav><ul><li>Accueil</li></ul></nav><noscript>JS</noscript>"
        "<svg><text>logo</text></svg><h2>Titre</h2><ul><li>A</li><li>B</li></ul>"
        "<div>C<br>D</div><table><tr><td>E</td></tr></table><footer>Pied</footer>"
    )

    assert network.html_to_text(html) == "Titre\nA\nB\nC\nD\nE"


def test_contact_state_follows_the_last_sent_call(web):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("no route", request=request)
        return httpx.Response(200, json={"2026-01-01": "1er janvier"})

    web(handler)
    outputs = [
        call("public_holidays", year="2026"),
        call("public_holidays", year="2026"),
        call("fetch_page", url="https://example.com"),
        "Voilà.",
    ]
    _, session = network_session("public_holidays", outputs)
    session.set_tool("fetch_page", True)

    events = _run(session, "Jours fériés ?")

    states = [
        next(n for n in a["nodes"] if n["id"] == "tools.public_holidays")
        for a in events["architecture_changed"]
    ]
    assert [(n["contact"], n["available"]) for n in states] == [
        ("unavailable", False),
        ("available", True),
        ("available", True),
    ]
    assert states[1]["reason_fr"] is None and states[2]["reason_fr"] is None
    assert events["tool_ended"][2]["status"] == "error"  # the refused fetch_page
    assert _node(session, "tools.fetch_page")["contact"] == "not_contacted"


def test_configured_fetch_page_hosts_and_cut_apply(web):
    web(lambda r: httpx.Response(200, text="y" * 100, headers={"content-type": "text/plain"}))
    engine = FakeEngine(
        outputs=[
            call("fetch_page", url="https://calendrier.api.gouv.fr/page"),
            call("fetch_page", url="https://fr.wikipedia.org/wiki/Paris"),
            "Voilà.",
        ],
        template=QWEN.decode("utf-8"),
        architecture="qwen35",
    )
    values = {
        "context": {"window": 4096, "near_limit_ratio": 0.8},
        "tools": {"fetch_page_hosts": ["calendrier.api.gouv.fr"], "fetch_page_max_chars": 30},
    }
    session = AppSession(config.Config(values=values), engine_factory=lambda path, n_ctx: engine)
    session.boot("fake.gguf").result()
    session.set_brick("tools", True)
    session.set_tool("fetch_page", True)

    events = _run(session, "Lis ces pages")

    accepted, refused = events["tool_ended"]
    assert accepted["result"] == "y" * 30 + "\n[Texte coupé à 30 caractères sur 100.]"
    assert refused["status"] == "error" and "Adresse refusée" in refused["error_fr"]
    assert "calendrier.api.gouv.fr" in refused["error_fr"]


def test_fetch_page_max_chars_below_the_minimum_is_clamped():
    assert config.Config(values={"tools": {"fetch_page_max_chars": 0}}).fetch_page_max_chars == 1
