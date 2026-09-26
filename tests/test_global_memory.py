"""Story 14: the global memory, injected in the system message, written by `remember` or by
force, edited in the drawer, restored by the reset (AD-4, AD-17, AD-20, AD-23, AD-25)."""

from __future__ import annotations

import json

import pytest
from fake_engine import FakeEngine, booted_session
from test_bricks import HEADERS, _client
from test_cloud import GROQ_TEXT, Provider, _cloud_session
from test_mcp_lazy import exact
from test_skills import since
from test_tools import QWEN, _segments, call

from wavestack import config
from wavestack import memory as memory_file
from wavestack.trace.journal import get_journal

DEMO = [
    "L'utilisateur s'appelle Camille.",
    "Camille est consultante en cybersécurité.",
    "Camille prépare une formation sur les agents IA.",
]
PREFERENCE = "Camille préfère des réponses en trois points au plus."


def remember(text: str) -> str:
    return call("remember", text=text)


def memory_session(outputs=("Voilà.",), *, qwen: bool = True, skills: bool = True):
    kwargs = {"template": QWEN.decode("utf-8"), "architecture": "qwen35"} if qwen else {}
    engine = FakeEngine(outputs=list(outputs), **kwargs)
    session = booted_session(engine, window=16384)
    for brick in ("short_memory", "system_prompt", "global_memory"):
        session.set_brick(brick, True)
    if skills:
        session.set_brick("skills", True)
    session.join()
    return engine, session


def run(session, message: str) -> list:
    """Send `message`, wait for the turn; returns this turn's envelopes."""
    mark = get_journal().last_seq()
    session.send(message)
    session.join()
    return get_journal().events_since(mark)


def of(events: list, kind: str) -> list:
    return [e for e in events if e.kind == kind]


def memory_texts(ctx: dict) -> list[str]:
    return [s["text"] for s in _segments(ctx, "global_memory")]


def system_kinds(ctx: dict) -> list[str]:
    kinds = ("system_prompt", "global_memory", "skill_catalog")
    return [s["kind"] for s in ctx["segments"] if s["kind"] in kinds]


def last(kind: str, mark: int = 0) -> dict:
    return since(mark, kind)[-1]


def card() -> dict:
    return next(b for b in last("bricks_changed")["bricks"] if b["id"] == "global_memory")


def saved() -> list[dict]:
    return json.loads(config.memory_path().read_text(encoding="utf-8"))


def check(ctx: dict, mark: int) -> None:
    exact(ctx)
    assert since(mark, "harness_error") == []


# ---------- I/O matrix ----------


def test_injection_puts_the_demo_between_system_prompt_and_skills_catalog():
    mark = get_journal().last_seq()
    _, session = memory_session()

    ctx = last("context_preview", mark)
    lines = [f"- {text}" for text in DEMO]
    assert memory_texts(ctx)[1:] == lines
    assert memory_texts(ctx)[0].startswith("Mémoire globale :")
    segments = _segments(ctx, "global_memory")
    assert {(s["brick"], s["component"]) for s in segments} == {("global_memory", "file.memory")}
    kinds = system_kinds(ctx)
    assert kinds.index("global_memory") > kinds.index("system_prompt")
    assert max(i for i, k in enumerate(kinds) if k == "global_memory") < kinds.index(
        "skill_catalog"
    )
    check(ctx, mark)
    assert not config.memory_path().exists()  # H5: the demonstration is not written

    events = run(session, "Bonjour")
    (first,) = [e.payload for e in of(events, "context_rendered")]
    assert memory_texts(first)[1:] == lines
    check(first, mark)
    assert "remember" in session.build_turn_state().tools
    session.close()


def test_the_model_writes_then_the_next_turn_reads_it():
    _, session = memory_session([remember(PREFERENCE), "C'est noté.", "Voici trois points."])
    mark = get_journal().last_seq()

    events = run(session, "Retiens que je préfère des réponses en trois points au plus.")

    (started,) = of(events, "tool_started")
    assert started.payload["tool"] == "remember" and started.trigger == "model"
    assert (started.brick, started.component) == ("global_memory", "core.harness")
    (ended,) = of(events, "tool_ended")
    assert ended.payload["status"] == "ok" and PREFERENCE in ended.payload["result"]
    (applied,) = of(events, "effect_applied")
    assert applied.payload["effect"] == "memory_write" and applied.payload["op"] == "add"
    assert applied.payload["text"] == PREFERENCE
    assert (applied.brick, applied.component) == ("global_memory", "file.memory")
    (changed,) = of(events, "memory_changed")
    assert applied.seq < changed.seq
    assert [e["text"] for e in changed.payload["entries"]] == [*DEMO, PREFERENCE]
    # The file holds the demonstration and the new entry, written by the session.
    entries = saved()
    assert [e["source"] for e in entries] == ["demo", "demo", "demo", "model"]
    assert entries[-1]["id"].startswith("m") and len(entries[-1]["id"]) == 9
    # AD-17: the system message of this turn does not change; the reply shows the write.
    first, second = [e.payload for e in of(events, "context_rendered")]
    for ctx in (first, second):
        assert f"- {PREFERENCE}" not in memory_texts(ctx)
        check(ctx, mark)
    reply = [s for s in _segments(second, "tool_result") if PREFERENCE in s["text"]]
    assert [(s["brick"], s["component"]) for s in reply] == [("global_memory", "core.harness")]

    after = run(session, "Quelles bonnes pratiques pour un mot de passe ?")
    ctx = of(after, "context_rendered")[0].payload
    assert f"- {PREFERENCE}" in memory_texts(ctx)
    # No stub: the reply stays in the history as it was (AD-25).
    history = [s["text"] for s in _segments(ctx, "history")]
    assert any("Retenu en mémoire globale" in text for text in history)
    session.close()


def test_forced_write_runs_before_the_first_call_by_the_user():
    engine, session = memory_session(["Noté."])
    session.arm("memory", "remember", {"text": f"  {PREFERENCE}  "})
    assert last("armed_actions_changed")["actions"][0]["label_fr"].startswith("Écrire en mémoire (")

    events = run(session, "Bonjour")

    (started,) = of(events, "tool_started")
    assert started.trigger == "user" and started.brick == "global_memory"
    assert started.seq < of(events, "model_call_started")[0].seq
    assert len(engine.calls) == 1
    (applied,) = of(events, "effect_applied")
    assert applied.trigger == "user" and applied.payload["text"] == PREFERENCE
    assert saved()[-1]["source"] == "user"
    assert last("armed_actions_changed")["actions"] == []
    session.close()


@pytest.mark.parametrize(
    ("text", "error"),
    [("   ", "vide"), ("x" * 301, "301 caractères"), ("pleine", "pleine (20 entrées)")],
)
def test_refusals_are_reinjected_without_effect(text, error):
    _, session = memory_session([remember(text), "D'accord."])
    if text == "pleine":
        session._memory = memory_file.demo_entries([f"Fait {i}" for i in range(20)], "x")

    events = run(session, "Retiens ceci.")

    (ended,) = of(events, "tool_ended")
    assert ended.payload["status"] == "error" and error in ended.payload["error_fr"]
    second = of(events, "context_rendered")[1].payload
    assert any(error in s["text"] for s in _segments(second, "tool_result"))
    assert of(events, "effect_applied") == [] and of(events, "memory_changed") == []
    assert not config.memory_path().exists()
    session.close()


def test_duplicate_adds_nothing():
    _, session = memory_session([remember("  l'utilisateur S'APPELLE camille.  "), "Déjà su."])

    events = run(session, "Retiens mon prénom.")

    (ended,) = of(events, "tool_ended")
    assert ended.payload["result"].startswith("Déjà en mémoire")
    assert of(events, "effect_applied") == [] and not config.memory_path().exists()
    session.close()


def test_forced_write_is_dropped_when_the_brick_is_off():
    _, session = memory_session(["Bonjour."])
    session.arm("memory", "remember", {"text": PREFERENCE})
    session.set_brick("global_memory", False)

    events = run(session, "Bonjour")

    (dropped,) = of(events, "action_dropped")
    assert "« Mémoire globale » n'est pas active" in dropped.payload["reason_fr"]
    assert of(events, "tool_started") == [] and not config.memory_path().exists()
    assert memory_texts(of(events, "context_rendered")[0].payload) == []
    session.close()


def test_without_parser_injection_and_drawer_stay_forced_write_is_dropped():
    engine, session = memory_session(["Bonjour."], qwen=False, skills=False)
    mark = get_journal().last_seq()

    assert card()["available"] and "ne sait pas appeler d'outil" in card()["note_fr"]
    assert "remember" not in session.build_turn_state().tools
    session.arm("memory", "remember", {"text": PREFERENCE})
    events = run(session, "Bonjour")

    (dropped,) = of(events, "action_dropped")
    assert "remember" in dropped.payload["reason_fr"]
    assert of(events, "tool_started") == []
    ctx = of(events, "context_rendered")[0].payload
    assert memory_texts(ctx)[1:] == [f"- {text}" for text in DEMO]
    check(ctx, mark)
    session.edit_memory("delete", "demo1")
    assert [e["id"] for e in saved()] == ["demo2", "demo3"]
    session.close()


def test_drawer_replace_delete_clear_and_refusals():
    _, session = memory_session()
    client = _client(session)
    route = "/api/intentions/memory"
    mark = get_journal().last_seq()

    body = {"op": "replace", "entry_id": "demo2", "text": " Consultante. "}
    ok = client.post(route, json=body, headers=HEADERS)
    assert ok.status_code == 200
    session.join()
    replaced = saved()[1]
    assert replaced["id"] == "demo2" and replaced["text"] == "Consultante."
    assert replaced["source"] == "user"
    (applied,) = [e for e in get_journal().events_since(mark) if e.kind == "effect_applied"]
    assert applied.payload == {
        "effect": "memory_write",
        "op": "replace",
        "entry_id": "demo2",
        "text": "Consultante.",
    }
    assert (applied.brick, applied.component) == ("global_memory", "file.memory")
    assert "- Consultante." in memory_texts(last("context_preview", mark))

    unknown = client.post(route, json={"op": "delete", "entry_id": "nope"}, headers=HEADERS)
    empty = client.post(
        route, json={"op": "replace", "entry_id": "demo1", "text": "  "}, headers=HEADERS
    )
    long = client.post(
        route, json={"op": "replace", "entry_id": "demo1", "text": "x" * 301}, headers=HEADERS
    )
    assert (unknown.status_code, empty.status_code, long.status_code) == (404, 422, 422)

    deleted = client.post(route, json={"op": "delete", "entry_id": "demo1"}, headers=HEADERS)
    assert deleted.is_success
    assert [e["id"] for e in saved()] == ["demo2", "demo3"]
    mark = get_journal().last_seq()
    assert client.post(route, json={"op": "clear"}, headers=HEADERS).is_success
    session.join()
    assert saved() == []
    ops = [(p["op"], p["entry_id"]) for p in since(mark, "effect_applied")]
    assert ops == [("delete", "demo2"), ("delete", "demo3")]
    assert len(since(mark, "memory_changed")) == 1  # one write for « Tout effacer »
    assert memory_texts(last("context_preview", mark)) == []  # empty: nothing injected
    assert client.get("/api/state").json()["memory_changed"]["entries"] == []

    session._set_state("turn", "Un tour est en cours.")
    busy = client.post(route, json={"op": "clear"}, headers=HEADERS)
    assert busy.status_code == 409 and "tour" in busy.json()["detail"]
    session._set_state("idle")
    session.close()


def test_write_failure_is_an_error_and_the_memory_is_unchanged(tmp_path, monkeypatch):
    _, session = memory_session([remember(PREFERENCE), "D'accord."])
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setattr(config, "memory_path", lambda: blocker / "memory.json")
    mark = get_journal().last_seq()

    events = run(session, "Retiens ceci.")

    (error,) = of(events, "harness_error")
    assert error.payload["message_fr"] == "La mémoire globale n'a pas pu être écrite."
    assert of(events, "effect_applied") == [] and of(events, "memory_changed") == []
    second = of(events, "context_rendered")[1].payload
    replies = [s["text"] for s in _segments(second, "tool_result")]
    assert any("n'a pas pu être écrite" in text for text in replies)
    assert not any("Retenu" in text for text in replies)
    assert [e.text for e in session._memory] == DEMO
    response = _client(session).post(
        "/api/intentions/memory", json={"op": "delete", "entry_id": "demo1"}, headers=HEADERS
    )
    assert response.status_code == 500 and [e.text for e in session._memory] == DEMO
    assert len(since(mark, "harness_error")) == 2
    session.close()


def test_invalid_file_makes_the_brick_unavailable_then_the_reset_restores_it():
    path = config.memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{pas du json", encoding="utf-8")
    mark = get_journal().last_seq()

    _, session = memory_session()

    assert "La mémoire globale est illisible." in [
        p["message_fr"] for p in since(mark, "harness_error")
    ]
    assert not card()["available"] and "Réinitialiser" in card()["reason_fr"]
    assert last("memory_changed")["error_fr"] and last("memory_changed")["entries"] == []
    assert "global_memory" not in session.build_turn_state().effective
    busy = _client(session).post("/api/intentions/memory", json={"op": "clear"}, headers=HEADERS)
    assert busy.status_code == 409
    assert path.read_text(encoding="utf-8") == "{pas du json"  # never rewritten

    session.reset()
    session.join()

    assert [e["text"] for e in saved()] == DEMO
    assert {e["source"] for e in saved()} == {"demo"}
    assert [e["id"] for e in saved()] == ["demo1", "demo2", "demo3"]
    assert card()["available"] and last("memory_changed")["error_fr"] is None
    session.close()


def test_reset_restores_the_demonstration_but_scenarios_and_clearing_do_not():
    _, session = memory_session([remember(PREFERENCE), "Noté."])
    run(session, "Retiens ceci.")
    session.edit_memory("delete", "demo1")
    session.clear_conversation()
    session.launch_scenario("system_prompt")
    session.join()
    assert [e["text"] for e in saved()] == [DEMO[1], DEMO[2], PREFERENCE]
    mark = get_journal().last_seq()

    session.reset()
    session.join()

    kinds = [e.kind for e in get_journal().events_since(mark)]
    assert kinds.index("harness_reset") < kinds.index("effect_applied")
    ops = [p["op"] for p in since(mark, "effect_applied")]
    assert ops == ["delete"] * 3 + ["add"] * 3
    assert [e["text"] for e in saved()] == DEMO
    assert kinds.count("bricks_changed") == 1 and kinds.count("architecture_changed") == 1
    session.close()


def test_replay_reads_the_current_memory():
    _, session = memory_session([remember(PREFERENCE), "Noté.", "Rejoué."])
    events = run(session, "Retiens ceci.")
    assert f"- {PREFERENCE}" not in memory_texts(of(events, "context_rendered")[0].payload)
    mark = get_journal().last_seq()

    session.replay()  # t1 again, from before t1: the memory it wrote is read now
    session.join()

    replayed = since(mark, "context_rendered")[0]
    assert f"- {PREFERENCE}" in memory_texts(replayed)
    assert since(mark, "turn_started")[0]["replay_of"] == "t1"
    session.close()


# ---------- acceptance and surroundings ----------


def test_a_new_session_on_the_same_folder_reads_the_entry_written():
    _, first = memory_session([remember(PREFERENCE), "Noté."])
    run(first, "Retiens ceci.")
    first.close()
    mark = get_journal().last_seq()

    _, second = memory_session(["Bonjour."])

    assert PREFERENCE in [e["text"] for e in last("memory_changed", mark)["entries"]]
    events = run(second, "Bonjour")
    assert f"- {PREFERENCE}" in memory_texts(of(events, "context_rendered")[0].payload)
    second.close()


def test_schema_draws_the_memory_file_linked_to_the_harness():
    _, session = memory_session()

    architecture = last("architecture_changed")
    nodes = {n["id"]: n for n in architecture["nodes"]}
    memory = nodes["file.memory"]
    assert (memory["kind"], memory["hosting"], memory["label_fr"]) == (
        "file",
        "local",
        "Mémoire globale",
    )
    assert memory["detail_fr"] == str(config.memory_path())
    edges = {(e["from"], e["to"]) for e in architecture["edges"]}
    assert ("global_memory.memory", "core.harness") in edges
    assert ("global_memory.memory", "file.memory") in edges
    assert nodes["global_memory.memory"]["kind"] == "brick"
    assert card()["category"] == "context" and card()["note_fr"] is None
    session.close()


def test_chat_mode_puts_the_memory_in_the_system_message():
    provider = Provider(GROQ_TEXT)
    session = _cloud_session("groq", provider, bricks=("system_prompt", "global_memory"))

    events = run(session, "Bonjour")

    body = json.loads(provider.requests[0].content)
    system = body["messages"][0]
    assert system["role"] == "system" and f"- {DEMO[0]}" in system["content"]
    assert [t["function"]["name"] for t in body.get("tools", [])] == ["remember"]
    ctx = of(events, "context_rendered")[0].payload
    assert memory_texts(ctx)[1:] == [f"- {text}" for text in DEMO]
    session.close()


def test_arming_a_memory_write_checks_its_text():
    _, session = memory_session()
    client = _client(session)

    empty = client.post(
        "/api/intentions/arm",
        json={"kind": "memory", "target": "remember", "args": {"text": " "}},
        headers=HEADERS,
    )
    other = client.post(
        "/api/intentions/arm",
        json={"kind": "memory", "target": "forget", "args": {"text": "x"}},
        headers=HEADERS,
    )
    assert (empty.status_code, other.status_code) == (422, 404)
    assert session._armed == []
    session.close()


def test_memory_scenario_keeps_the_previous_modules_bricks():
    session = booted_session(FakeEngine())

    session.launch_scenario("global_memory")
    session.join()

    assert session._wanted == {
        "short_memory",
        "system_prompt",
        "tools",
        "mcp",
        "skills",
        "hooks",
        "reasoning",
        "global_memory",
    }
    assert session._mcp_lazy
    session.close()
