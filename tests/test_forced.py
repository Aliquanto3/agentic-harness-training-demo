"""Story 9: forced actions, armed from the bricks panel, consumed by the next turn before its
first model call, through the single executor with `trigger = user` (AD-3, AD-14, AD-25)."""

from __future__ import annotations

import threading
import time

import httpx
import pytest
from fake_engine import FakeEngine
from pydantic import ValidationError
from test_bricks import HEADERS, _client
from test_hooks import HOLIDAYS, SECRET, h5_session, hooks_session, wait_asked
from test_mcp import card, loop  # noqa: F401 - fixture
from test_mcp_lazy import DEFINE, LOCAL, exact, lazy_session
from test_skills import CAVEMAN, skills_session
from test_tools import QWEN, _segments, call, tool_session, web  # noqa: F401 - fixture

from wavestack.tools.registry import ToolText
from wavestack.trace.journal import get_journal


def run(session, message: str) -> list:
    """Send `message`, wait for the turn; returns this turn's envelopes, in order."""
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    return get_journal().events_since(mark)


def of(events: list, kind: str) -> list:
    return [e for e in events if e.kind == kind]


def armed() -> list[dict]:
    """The armed actions, as the front projects them: the last `armed_actions_changed`."""
    changes = [e for e in get_journal().all_events() if e.kind == "armed_actions_changed"]
    return changes[-1].payload["actions"] if changes else []


def before_first_call(events: list, envelope) -> bool:
    return envelope.seq < of(events, "model_call_started")[0].seq


# ---------- I/O matrix ----------


def test_forced_read_of_the_sensitive_file_is_blocked_by_h1_then_the_model_answers():
    engine, session = hooks_session(["Je ne peux pas lire ce fichier."])
    session.arm("tool", "read_file", {"path": SECRET})

    events = run(session, "Bonjour")

    (blocked,) = [e for e in of(events, "hook_decided") if e.payload["point"] == "before_tool"]
    assert (blocked.payload["hook"], blocked.payload["decision"]) == ("h1", "block")
    assert blocked.trigger == "user"  # the Orchestration line reads « Forcé par l'utilisateur »
    assert before_first_call(events, blocked)
    assert of(events, "tool_started") == []  # blocked: the tool never runs
    assert len(engine.calls) == 1  # the model answers after, the forced action costs no call
    ctx = of(events, "context_rendered")[0].payload
    refusal = [s for s in _segments(ctx, "tool_result") if s["brick"] == "hooks"]
    assert refusal and "garde-fou" in refusal[0]["text"]
    assert of(events, "turn_ended")[0].payload["status"] == "completed"
    session.close()


def test_forced_skill_is_loaded_and_the_model_answers_with_it_in_the_same_turn():
    engine, session = skills_session(["Moi répondre court."])
    session.arm("skill", "caveman")

    events = run(session, "Explique le MCP.")

    (started,) = of(events, "tool_started")
    assert started.payload["tool"] == "load_skill" and started.trigger == "user"
    assert (started.brick, before_first_call(events, started)) == ("skills", True)
    ctx = of(events, "context_rendered")[0].payload
    body = [s for s in _segments(ctx, "skill_body") if CAVEMAN in s["text"]]
    assert [(s["brick"], s["component"]) for s in body] == [("skills", "skills.caveman")]
    assert len(engine.calls) == 1
    assert "caveman" in session._loaded_skills  # `SkillLoaded` applied
    exact(ctx)
    session.close()


def test_forced_mcp_documentation_makes_the_tool_callable_in_the_same_turn(loop):  # noqa: F811
    session = lazy_session(loop, [call(DEFINE, term="MCP"), "Voilà."])
    session.arm("tool_doc", DEFINE)

    events = run(session, "Que veut dire MCP ?")

    loading, calling = of(events, "tool_started")
    assert (loading.payload["tool"], loading.trigger, loading.brick) == (
        "load_tool_doc",
        "user",
        "mcp",
    )
    assert before_first_call(events, loading)
    assert (calling.payload["tool"], calling.trigger) == (DEFINE, "model")
    assert [e.payload["status"] for e in of(events, "tool_ended")] == ["ok", "ok"]
    ctx = of(events, "context_rendered")[0].payload
    doc = [s for s in _segments(ctx, "tool_catalog") if s["text"].startswith('{"type"')]
    assert [(s["brick"], s["component"]) for s in doc] == [("mcp", "mcp.local")]
    for rendered in of(events, "context_rendered"):
        exact(rendered.payload)
    session.close()


def test_two_armed_actions_run_in_order_before_c1_and_keep_the_call_budget():
    time_asked = [call("get_datetime")]
    engine = FakeEngine(outputs=time_asked, template=QWEN.decode(), architecture="qwen35")
    _, session = skills_session()
    session._engine = engine  # the same session, a model that always asks for the time
    session.set_brick("tools", True)
    session.arm("tool", "get_datetime")
    session.arm("skill", "caveman")

    events = run(session, "Quelle heure ?")

    started = of(events, "tool_started")
    assert [(e.payload["tool"], e.trigger) for e in started[:2]] == [
        ("get_datetime", "user"),
        ("load_skill", "user"),
    ]
    assert all(before_first_call(events, e) for e in started[:2])
    assert {e.trigger for e in started[2:]} == {"model"}
    assert len(engine.calls) == session.cfg.tool_max_calls  # the call budget stays whole
    assert of(events, "limit_reached")[0].payload["limit"] == "calls"
    session.close()


def test_a_target_no_longer_available_is_dropped_and_the_turn_goes_on():
    engine, session = skills_session(["Voilà."])
    armed_id = session.arm("skill", "caveman")
    session.set_skill("caveman", False)

    events = run(session, "Bonjour")

    (dropped,) = of(events, "action_dropped")
    assert dropped.payload["armed_id"] == armed_id
    assert "décoché" in dropped.payload["reason_fr"] and "Caveman" in dropped.payload["reason_fr"]
    assert of(events, "tool_started") == []
    assert of(events, "turn_ended")[0].payload["status"] == "completed"
    assert armed() == []  # taken by the turn: removed at its end
    session.close()


def test_an_action_armed_during_a_turn_waits_for_the_next_one():
    gate = threading.Event()
    engine = FakeEngine(gate=gate, template=QWEN.decode(), architecture="qwen35")
    _, session = tool_session(["Voilà."])
    session._engine = engine
    mark = get_journal().last_seq()
    session.send("Bonjour")

    armed_id = session.arm("tool", "get_datetime")  # class (a): accepted in `turn`
    gate.set()
    session.join()

    events = get_journal().events_since(mark)
    assert of(events, "tool_started") == []
    assert [a["armed_id"] for a in armed()] == [armed_id]  # still armed after `turn_ended`
    after = run(session, "Encore")
    assert [e.payload["tool"] for e in of(after, "tool_started")] == ["get_datetime"]
    assert armed() == []
    session.close()


def test_stopped_or_limited_turns_remove_the_actions_they_took():
    engine, session = tool_session([call("get_datetime")])
    session.arm("tool", "calculator", {"expression": "2+2"})

    events = run(session, "Quelle heure ?")

    assert of(events, "turn_ended")[0].payload["status"] == "limit"
    (removed,) = of(events, "armed_actions_changed")
    assert removed.payload["actions"] == [] and removed.seq < of(events, "turn_ended")[0].seq

    engine.outputs, engine.delay = ["z" * 400], 0.005
    session.arm("tool", "get_datetime")
    mark = get_journal().last_seq()
    session.send("Parle longtemps")
    deadline = time.monotonic() + 5
    while not of(get_journal().events_since(mark), "model_first_token"):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    session.stop()
    session.join()
    assert of(get_journal().events_since(mark), "turn_ended")[0].payload["status"] == "cancelled"
    assert armed() == []
    session.close()


def test_arming_an_unknown_target_is_404_and_arms_nothing():
    _, session = tool_session(["Voilà."])
    client = _client(session)
    mark = get_journal().last_seq()

    for body in (
        {"kind": "tool", "target": "get_weather"},
        {"kind": "skill", "target": "inconnu"},
        {"kind": "tool_doc", "target": "local__define_term"},  # no server connected
    ):
        response = client.post("/api/intentions/arm", json=body, headers=HEADERS)
        assert response.status_code == 404
        assert "Rien n'est armé" in response.json()["detail"]
    invalid = {"kind": "tool", "target": "public_holidays", "args": {"year": "demain"}}
    response = client.post("/api/intentions/arm", json=invalid, headers=HEADERS)
    assert response.status_code == 422 and "entier" in response.json()["detail"]
    assert of(get_journal().events_since(mark), "armed_actions_changed") == []
    session.close()


# ---------- context rendering, trigger, API ----------


def test_the_forced_call_follows_the_user_message_attributed_to_its_brick():
    engine, session = tool_session(["Cela fait 444."])
    session.arm("tool", "calculator", {"expression": "12*37"})

    events = run(session, "Combien ?")

    ctx = of(events, "context_rendered")[0].payload
    kinds = [s["kind"] for s in ctx["segments"] if s["kind"] != "template"]
    user = kinds.index("user_message")
    assert kinds[user + 1 :] == ["assistant_turn"] * kinds.count("assistant_turn") + ["tool_result"]
    calls = _segments(ctx, "assistant_turn")
    assert {(s["brick"], s["component"]) for s in calls} == {("tools", "tools.calculator")}
    assert [(s["text"], s["brick"]) for s in _segments(ctx, "tool_result")] == [("444", "tools")]
    assert engine.calls == [list("".join(s["text"] for s in ctx["segments"]).encode())]
    exact(ctx)
    # The next turn keeps it in the history, as any step of a completed turn.
    session.set_brick("short_memory", True)
    ctx = of(run(session, "Et 2+2 ?"), "context_rendered")[0].payload
    assert "444" in "".join(s["text"] for s in _segments(ctx, "history"))
    session.close()


def test_a_call_the_model_decided_carries_trigger_model():
    _, session = tool_session([call("calculator", expression="12*37"), "Cela fait 444."])

    events = run(session, "Combien font 12 × 37 ?")

    (started,) = of(events, "tool_started")
    assert started.trigger == "model"
    assert {e.trigger for e in of(events, "tool_ended")} == {"model"}
    session.close()


def test_arm_disarm_and_the_state_after_a_reload():
    _, session = tool_session(["Voilà."])
    client = _client(session)

    response = client.post(
        "/api/intentions/arm",
        json={"kind": "tool", "target": "read_file", "args": {"path": SECRET}},
        headers=HEADERS,
    )
    assert response.status_code == 200
    armed_id = response.json()["armed_id"]
    state = client.get("/api/state").json()["armed_actions_changed"]
    assert state["actions"] == [
        {
            "armed_id": armed_id,
            "kind": "tool",
            "brick": "tools",
            "target": "read_file",
            "args": {"path": SECRET},
            "label_fr": f"Lecture de fichier ({SECRET})",
        }
    ]
    body = {"armed_id": armed_id}
    assert client.post("/api/intentions/disarm", json=body, headers=HEADERS).status_code == 200
    assert client.get("/api/state").json()["armed_actions_changed"]["actions"] == []
    assert client.post("/api/intentions/disarm", json=body, headers=HEADERS).status_code == 404
    session.close()


def test_tool_options_carry_parameters_and_presets():
    _, session = tool_session(["Voilà."])
    bricks = [e for e in get_journal().all_events() if e.kind == "bricks_changed"][-1]
    (card,) = [b for b in bricks.payload["bricks"] if b["id"] == "tools"]
    tools = {o["id"]: o for o in card["options"]}

    assert list(tools["read_file"]["parameters"]) == ["path"]
    assert "Chemin relatif" in tools["read_file"]["parameters"]["path"]
    sensitive = {"label_fr": "Fichier sensible", "args": {"path": SECRET}}
    assert sensitive in tools["read_file"]["presets"]
    assert tools["get_datetime"]["parameters"] == {} and tools["get_datetime"]["presets"] == []
    session.close()


# ---------- review follow-up: conversion, every drop reason, refusals, options, H5 ----------


def test_form_text_is_converted_to_the_tool_schema():
    _, session = tool_session(["Voilà."])
    session.set_tool("public_holidays", True)
    client = _client(session)

    body = {"kind": "tool", "target": "public_holidays", "args": {"year": "2026"}}
    response = client.post("/api/intentions/arm", json=body, headers=HEADERS)

    assert response.status_code == 200
    (action,) = armed()
    assert action["args"] == {"year": 2026} and isinstance(action["args"]["year"], int)
    session.close()


def assert_dropped(events: list, armed_id: str, reason: str) -> None:
    (dropped,) = of(events, "action_dropped")
    assert dropped.payload["armed_id"] == armed_id
    assert reason in dropped.payload["reason_fr"]
    assert of(events, "turn_ended")[0].payload["status"] == "completed"


@pytest.mark.parametrize(
    ("switch_off", "reason"),
    [
        (lambda s: s.set_tool("calculator", False), "est décoché"),
        (lambda s: s.set_brick("tools", False), "« Outils » n'est pas active"),
    ],
)
def test_a_tool_no_longer_available_is_dropped(switch_off, reason):
    _, session = tool_session(["Voilà."])
    armed_id = session.arm("tool", "calculator", {"expression": "2+2"})
    switch_off(session)

    events = run(session, "Bonjour")

    assert_dropped(events, armed_id, reason)
    assert of(events, "tool_started") == []
    session.close()


def test_a_skill_already_loaded_is_dropped():
    _, session = skills_session(["Voilà."])
    session.arm("skill", "caveman")
    second = session.arm("skill", "caveman")

    events = run(session, "Bonjour")

    assert_dropped(events, second, "est déjà chargé")
    assert [e.payload["tool"] for e in of(events, "tool_started")] == ["load_skill"]  # once
    session.close()


@pytest.mark.parametrize("case", ["loaded", "full", "disabled"])
def test_a_documentation_no_longer_loadable_is_dropped(loop, case):  # noqa: F811
    session = lazy_session(loop, ["Voilà."])
    if case == "loaded":
        session.arm("tool_doc", DEFINE)
        run(session, "Premier tour")
    armed_id = session.arm("tool_doc", DEFINE)
    reasons = {
        "loaded": "est déjà chargée",
        "full": "en documentation complète",
        "disabled": "n'est pas connecté ou est désactivé",
    }
    if case == "full":
        session.set_mcp_mode(False)
    elif case == "disabled":
        session.set_mcp_server("local", False)
    session.join()

    events = run(session, "Bonjour")

    assert_dropped(events, armed_id, reasons[case])
    assert of(events, "tool_started") == []
    session.close()


def test_kind_tool_refuses_an_mcp_tool_and_a_meta_tool(loop):  # noqa: F811
    session = lazy_session(loop)
    session.set_brick("skills", True)
    session.join()
    client = _client(session)
    mark = get_journal().last_seq()

    for target in (DEFINE, "load_skill", "load_tool_doc"):
        body = {"kind": "tool", "target": target}
        response = client.post("/api/intentions/arm", json=body, headers=HEADERS)
        assert response.status_code == 404, target
    assert of(get_journal().events_since(mark), "armed_actions_changed") == []
    session.close()


def test_mcp_option_lists_its_tools_once_connected_in_lazy_loading(loop):  # noqa: F811
    session = lazy_session(loop)

    (local,) = [o for o in card("mcp")["options"] if o["id"] == "local"]

    assert local["tools"] == list(LOCAL)
    session.close()


def test_a_preset_with_an_undeclared_argument_is_invalid():
    with pytest.raises(ValidationError):
        ToolText.model_validate(
            {
                "label_fr": "Lecture",
                "description": "Lit un fichier.",
                "parameters": {"path": "Chemin."},
                "presets": [{"label_fr": "Faux", "args": {"chemin": "a.txt"}}],
            }
        )


def test_a_forced_network_call_stopped_while_h5_waits_cancels_the_turn(web):  # noqa: F811
    sent = web(lambda r: httpx.Response(200, json=HOLIDAYS))
    session = h5_session(["Jamais lu."])
    session.arm("tool", "public_holidays", {"year": 2026})
    mark = get_journal().last_seq()

    session.send("Bonjour")
    asked = wait_asked(mark)
    assert asked.trigger == "user"
    session.stop()
    session.join()

    events = get_journal().events_since(mark)
    assert sent == [] and of(events, "model_call_started") == []
    assert of(events, "turn_ended")[0].payload["status"] == "cancelled"
    assert armed() == []
    session.close()
