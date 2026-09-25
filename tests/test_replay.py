"""Story 9b: replay of the last prompt, from the conversational state before its turn (AD-17)."""

from __future__ import annotations

import threading

import pytest
from fake_engine import FakeEngine, booted_session
from test_bricks import HEADERS, _client
from test_mcp import loop  # noqa: F401 - fixture
from test_mcp_lazy import LOCAL, definition_names, lazy_session
from test_mcp_lazy import load as load_doc
from test_skills import CAVEMAN, nodes, skills_session
from test_skills import load as load_skill
from test_tools import _segments
from test_turn import _run

from wavestack.session.app_session import SendRefused
from wavestack.trace.journal import get_journal

NOTHING = "Aucun prompt à rejouer : envoyez d'abord un message."


def replay(session) -> dict[str, list[dict]]:
    """Replay the last prompt, wait for the turn, return this turn's payloads by kind."""
    mark = get_journal().last_seq()
    session.replay()
    session.join()
    by_kind: dict[str, list[dict]] = {}
    for envelope in get_journal().events_since(mark):
        by_kind.setdefault(envelope.kind, []).append(envelope.payload)
    return by_kind


def branch(session) -> list[str]:
    return [e.turn_id for e in session.build_turn_state().history]


def memory_session(outputs: list[str]):
    engine = FakeEngine(outputs=outputs)
    session = booted_session(engine)
    session.set_brick("short_memory", True)
    session.join()
    return engine, session


# ---------- I/O matrix ----------


def test_simple_replay_starts_from_the_turns_before_the_last_one():
    engine, session = memory_session(["Réponse un", "Réponse deux", "Réponse trois", "Autre"])
    for question in ("Question un", "Question deux", "Question trois"):
        _run(session, question)

    events = replay(session)

    assert events["turn_started"][0] == {"replay_of": "t3", "message": "Question trois"}
    prompt = bytes(engine.calls[-1]).decode()
    assert "Question un" in prompt and "Réponse deux" in prompt
    assert prompt.count("Question trois") == 1 and "Réponse trois" not in prompt
    assert branch(session) == ["t1", "t2", "t4"]


def test_a_brick_enabled_before_the_replay_is_in_the_replayed_context():
    _, session = memory_session(["Bonjour.", "Bonjour encore."])
    first = _run(session, "Bonjour")["context_rendered"][0]
    assert "system_prompt" not in {s["kind"] for s in first["segments"]}
    session.set_brick("system_prompt", True)
    session.join()

    ctx = replay(session)["context_rendered"][0]

    assert "system_prompt" in {s["kind"] for s in ctx["segments"]}


def test_a_skill_loaded_in_the_origin_turn_is_back_in_the_catalog():
    engine, session = skills_session(["Salut.", load_skill("caveman"), "Moi court.", "Réponse."])
    _run(session, "Bonjour")
    _run(session, "Explique le MCP.")
    assert session.build_turn_state().skills == ("caveman",)

    events = replay(session)

    ctx = events["context_rendered"][0]
    assert not [s for s in _segments(ctx, "skill_body") if CAVEMAN in s["text"]]
    assert "load_skill" in bytes(engine.calls[-1]).decode()  # the model may load it again
    assert nodes()["skills.caveman"]["loaded"] is False  # the schema follows the branch
    session.close()


def test_a_documentation_loaded_in_the_origin_turn_is_unloaded_an_earlier_one_stays(loop):  # noqa: F811
    outputs = [load_doc(LOCAL[0]), "Ok.", load_doc(LOCAL[1]), "Ok.", "Voilà."]
    session = lazy_session(loop, outputs)
    _run(session, "Liste les termes.")
    _run(session, "Définis MCP.")

    ctx = replay(session)["context_rendered"][0]

    assert definition_names(ctx) == [LOCAL[0], "load_tool_doc"]
    session.close()


def test_a_replay_of_a_replay_starts_from_the_same_history():
    engine, session = memory_session(["Un.", "Deux.", "Trois."])
    _run(session, "Premier")
    _run(session, "Second")

    assert replay(session)["turn_started"][0]["replay_of"] == "t2"
    events = replay(session)

    assert events["turn_started"][0]["replay_of"] == "t3"
    assert engine.calls[-1] == engine.calls[-2]  # t3 and t4 read the same prompt
    assert branch(session) == ["t1", "t4"]


def test_an_armed_action_is_consumed_by_the_replayed_turn():
    _, session = skills_session(["Salut.", "Moi court."])
    _run(session, "Bonjour")
    session.arm("skill", "caveman")
    mark = get_journal().last_seq()

    session.replay()
    session.join()

    events = get_journal().events_since(mark)
    (turn,) = [e for e in events if e.kind == "turn_started"]
    assert turn.payload["replay_of"] == "t1"
    started = [e for e in events if e.kind == "tool_started"]
    assert [(e.payload["tool"], e.trigger) for e in started] == [("load_skill", "user")]
    changes = [e for e in events if e.kind == "armed_actions_changed"]
    assert changes and changes[-1].payload["actions"] == []  # consumed by the replayed turn
    session.close()


def test_a_stopped_origin_turn_is_replayed_from_the_turn_before():
    engine, session = memory_session(["Un.", "Deux.", "Deux bis."])
    _run(session, "Premier")
    engine.gate = threading.Event()
    session.send("Second")
    assert session.stop() is True
    engine.gate.set()
    session.join()
    engine.gate = None

    events = replay(session)

    assert events["turn_started"][0]["replay_of"] == "t2"
    prompt = bytes(engine.calls[-1]).decode()
    assert "Premier" in prompt and prompt.count("Second") == 1
    assert branch(session) == ["t1", "t3"]


def test_replay_outside_idle_is_refused_and_changes_nothing():
    engine, session = memory_session(["Un.", "Deux."])
    _run(session, "Premier")
    engine.gate = threading.Event()
    session.send("Second")

    with pytest.raises(SendRefused) as refused:
        session.replay()
    engine.gate.set()
    session.join()

    assert "Un tour est déjà en cours" in refused.value.reason_fr
    assert branch(session) == ["t1", "t2"]


def test_nothing_to_replay_before_a_turn_or_after_clearing():
    _, session = memory_session(["Un."])
    with pytest.raises(SendRefused, match=NOTHING):
        session.replay()
    _run(session, "Premier")
    session.clear_conversation()

    with pytest.raises(SendRefused, match=NOTHING):
        session.replay()


# ---------- route ----------


def test_route_replay_is_200_with_the_turn_id_then_409_after_clearing():
    _, session = memory_session(["Un.", "Deux."])
    client = _client(session)

    nothing = client.post("/api/intentions/replay", json={}, headers=HEADERS)
    assert (nothing.status_code, nothing.json()["detail"]) == (409, NOTHING)
    client.post("/api/intentions/send", json={"message": "Premier"}, headers=HEADERS)
    session.join()

    replayed = client.post("/api/intentions/replay", json={}, headers=HEADERS)
    session.join()
    assert (replayed.status_code, replayed.json()) == (200, {"turn_id": "t2"})
    client.post("/api/intentions/clear_conversation", json={}, headers=HEADERS)
    assert client.post("/api/intentions/replay", json={}, headers=HEADERS).status_code == 409
