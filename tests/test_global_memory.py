"""Story 14: the global memory, injected in the system message, written by `remember` or by
force, edited in the drawer, restored by the reset (AD-4, AD-17, AD-20, AD-23, AD-25)."""

from __future__ import annotations

import json
import shutil
import threading
import time

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
    "L'utilisateur s'appelle Pascal.",
    "Pascal est consultant en cybersécurité.",
    "Pascal prépare une formation sur les agents IA.",
]
PREFERENCE = "Pascal préfère des réponses en trois points au plus."


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


def test_the_model_writes_then_the_next_conversation_reads_it():
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

    # N1 (lot A): the next turn keeps the conversation's system message, the entry waits in
    # the drawer; the engine reuses its cache.
    after = run(session, "Quelles bonnes pratiques pour un mot de passe ?")
    ctx = of(after, "context_rendered")[0].payload
    assert f"- {PREFERENCE}" not in memory_texts(ctx)
    assert memory_texts(ctx) == memory_texts(first)
    assert of(after, "prefix_not_reused") == []
    assert PREFERENCE in [e["text"] for e in last("memory_changed")["entries"]]
    # No stub: the reply stays in the history as it was (AD-25).
    history = [s["text"] for s in _segments(ctx, "history")]
    assert any("Retenu en mémoire globale" in text for text in history)

    session.clear_conversation()  # the next conversation reads the memory again
    session.join()
    assert f"- {PREFERENCE}" in memory_texts(last("context_preview"))
    ctx = of(run(session, "Et pour une clé d'API ?"), "context_rendered")[0].payload
    assert f"- {PREFERENCE}" in memory_texts(ctx)
    session.close()


def test_forced_write_runs_before_the_first_call_by_the_user():
    engine, session = memory_session(["Noté."])
    session.arm("memory", "remember", {"text": f"  {PREFERENCE}  "})
    assert last("armed_actions_changed")["actions"][0]["label_text"].startswith(
        "Écrire en mémoire ("
    )

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
    assert ended.payload["status"] == "error" and error in ended.payload["error_text"]
    second = of(events, "context_rendered")[1].payload
    assert any(error in s["text"] for s in _segments(second, "tool_result"))
    assert of(events, "effect_applied") == [] and of(events, "memory_changed") == []
    assert not config.memory_path().exists()
    session.close()


def test_duplicate_adds_nothing():
    _, session = memory_session([remember("  l'utilisateur S'APPELLE pascal.  "), "Déjà su."])

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
    assert "« Mémoire globale » n'est pas active" in dropped.payload["reason_text"]
    assert of(events, "tool_started") == [] and not config.memory_path().exists()
    assert memory_texts(of(events, "context_rendered")[0].payload) == []
    session.close()


def test_without_parser_injection_and_drawer_stay_forced_write_is_dropped():
    engine, session = memory_session(["Bonjour."], qwen=False, skills=False)
    mark = get_journal().last_seq()

    assert card()["available"] and "ne sait pas appeler d'outil" in card()["note_text"]
    assert "remember" not in session.build_turn_state().tools
    session.arm("memory", "remember", {"text": PREFERENCE})
    events = run(session, "Bonjour")

    (dropped,) = of(events, "action_dropped")
    assert "remember" in dropped.payload["reason_text"]
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

    body = {"op": "replace", "entry_id": "demo2", "text": " Consultant. "}
    ok = client.post(route, json=body, headers=HEADERS)
    assert ok.status_code == 200
    session.join()
    replaced = saved()[1]
    assert replaced["id"] == "demo2" and replaced["text"] == "Consultant."
    assert replaced["source"] == "user"
    (applied,) = [e for e in get_journal().events_since(mark) if e.kind == "effect_applied"]
    assert applied.payload == {
        "effect": "memory_write",
        "op": "replace",
        "entry_id": "demo2",
        "text": "Consultant.",
    }
    assert (applied.brick, applied.component) == ("global_memory", "file.memory")
    assert applied.trigger == "user"  # the drawer is the user's (independent review)
    assert "- Consultant." in memory_texts(last("context_preview", mark))

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
    assert error.payload["message_text"] == "La mémoire globale n'a pas pu être écrite."
    assert of(events, "effect_applied") == [] and of(events, "memory_changed") == []
    (ended,) = of(events, "tool_ended")  # the trace never shows a write that did not happen
    assert ended.payload["status"] == "error" and ended.seq > error.seq
    assert "n'a pas pu être écrite" in ended.payload["error_text"]
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
        p["message_text"] for p in since(mark, "harness_error")
    ]
    assert not card()["available"] and "Réinitialiser" in card()["reason_text"]
    assert last("memory_changed")["error_text"] and last("memory_changed")["entries"] == []
    assert "global_memory" not in session.build_turn_state().effective
    busy = _client(session).post("/api/intentions/memory", json={"op": "clear"}, headers=HEADERS)
    assert busy.status_code == 409
    assert path.read_text(encoding="utf-8") == "{pas du json"  # never rewritten

    session.reset()
    session.join()

    assert [e["text"] for e in saved()] == DEMO
    assert {e["source"] for e in saved()} == {"demo"}
    assert [e["id"] for e in saved()] == ["demo1", "demo2", "demo3"]
    assert card()["available"] and last("memory_changed")["error_text"] is None
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


def test_replay_reads_the_memory_of_its_conversation():
    _, session = memory_session([remember(PREFERENCE), "Noté.", "Rejoué."])
    events = run(session, "Retiens ceci.")
    assert f"- {PREFERENCE}" not in memory_texts(of(events, "context_rendered")[0].payload)
    mark = get_journal().last_seq()

    session.replay()  # t1 again, from before t1, with the memory its conversation read (N1)
    session.join()

    replayed = since(mark, "context_rendered")[0]
    assert f"- {PREFERENCE}" not in memory_texts(replayed)
    assert since(mark, "turn_started")[0]["replay_of"] == "t1"
    assert PREFERENCE in [e["text"] for e in saved()]  # written all the same
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
    assert (memory["kind"], memory["hosting"], memory["label_text"]) == (
        "file",
        "local",
        "Mémoire globale",
    )
    assert memory["detail_text"] == str(config.memory_path())
    edges = {(e["from"], e["to"]) for e in architecture["edges"]}
    assert ("global_memory.memory", "core.harness") in edges
    assert ("global_memory.memory", "file.memory") in edges
    assert nodes["global_memory.memory"]["kind"] == "brick"
    assert card()["category"] == "context" and card()["note_text"] is None
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


def test_memory_scenario_closes_module_1():
    """Story 21: last scenario of module 1 (FR-38); the modules after it keep the brick."""
    session = booted_session(FakeEngine())

    session.launch_scenario("global_memory")
    session.join()

    assert session._wanted == {"short_memory", "system_prompt", "global_memory"}
    assert not session._mcp_lazy
    session.launch_scenario("native_tools")
    session.join()
    assert "global_memory" in session._wanted
    session.close()


# ---------- independent review ----------

NO_TEXT = "<tool_call>\n<function=remember>\n</function>\n</tool_call>"


def test_invalid_call_with_the_memory_brick_alone_belongs_to_it():
    _, session = memory_session([NO_TEXT, "Voilà."], skills=False)
    mark = get_journal().last_seq()

    events = run(session, "Retiens ceci.")

    (malformed,) = [e for e in get_journal().events_since(mark) if e.kind == "tool_call_malformed"]
    assert malformed.brick == "global_memory" and "manquant" in malformed.payload["detail_text"]
    (result,) = _segments(of(events, "context_rendered")[1].payload, "tool_result")
    assert result["brick"] == "global_memory"
    session.close()


def test_invalid_memory_content_makes_the_brick_and_the_drawer_unavailable(tmp_path, monkeypatch):
    content = tmp_path / "content"
    shutil.copytree(config.content_dir(), content)
    (content / "memory" / "memory.yaml").write_text("intro: seule\n", encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    mark = get_journal().last_seq()

    _, session = memory_session(["Bonjour."], skills=False)

    assert "Les textes de la mémoire globale sont invalides." in [
        p["message_text"] for p in since(mark, "harness_error")
    ]
    assert card()["wanted"] and not card()["available"]
    assert "content/memory/memory.yaml" in card()["reason_text"]
    changed = last("memory_changed")
    assert changed["entries"] == [] and "content/memory/memory.yaml" in changed["error_text"]
    busy = _client(session).post("/api/intentions/memory", json={"op": "clear"}, headers=HEADERS)
    assert busy.status_code == 409 and "memory.yaml" in busy.json()["detail"]
    events = run(session, "Bonjour")
    assert of(events, "turn_ended")[0].payload["status"] == "completed"
    ctx = of(events, "context_rendered")[0].payload
    assert _segments(ctx, "global_memory") == [] and "remember" not in json.dumps(ctx)
    session.close()


def _entry(i: int, text: str) -> dict:
    return {"id": f"m{i}", "text": text, "created_at": "x", "source": "user"}


@pytest.mark.parametrize(
    "entries",
    [
        [_entry(i, f"Fait {i}") for i in range(21)],
        [_entry(1, "x" * (memory_file.MAX_CHARS + 1))],
        [_entry(1, "Un\ndeux")],
        [_entry(1, "Un"), _entry(1, "Deux")],
    ],
    ids=["21 entrées", "301 caractères", "retour à la ligne", "id en double"],
)
def test_a_file_beyond_the_limits_is_unreadable(entries):
    path = config.memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")

    _, session = memory_session(skills=False)

    assert not card()["available"] and last("memory_changed")["error_text"]
    assert json.loads(path.read_text(encoding="utf-8")) == entries  # never rewritten
    session.close()


def test_the_applier_and_the_demonstration_keep_the_limits():
    full = memory_file.demo_entries([f"Fait {i}" for i in range(20)], "x")
    one_more = memory_file.MemoryWrite(op="add", entry_id="m1", text="Un de plus")
    with pytest.raises(ValueError):
        memory_file.apply_writes(full, [one_more], "model", "x")
    content = memory_file.load_memory_content().model_dump()
    with pytest.raises(ValueError):
        memory_file.MemoryContent.model_validate({**content, "demo": ["Un", "un"]})


def test_a_full_memory_fits_the_smallest_window_with_the_scenario_bricks():
    """H3: 20 entries of `MAX_CHARS` characters, the reasoning reserve, the default window."""
    bricks = ("short_memory", "system_prompt", "tools", "skills", "hooks", "reasoning")
    session = _cloud_session("mistral", Provider(GROQ_TEXT), bricks=(*bricks, "global_memory"))
    longest = "é" * (memory_file.MAX_CHARS - 3)
    session._memory = memory_file.demo_entries([f"{longest}{i:03d}" for i in range(20)], "x")
    mark = get_journal().last_seq()

    session._emit_preview()

    ctx = last("context_preview", mark)
    assert ctx["window"] == 4096 and ctx["reserve"] == 1536
    memory = sum(s["tokens"] for s in _segments(ctx, "global_memory"))
    assert not ctx["overflow"] and ctx["used"] < ctx["usable"]
    assert memory <= 0.65 * ctx["usable"]  # the rest of the context keeps its room
    session.close()


def test_reset_on_the_demonstration_writes_nothing():
    _, session = memory_session()
    mark = get_journal().last_seq()

    session.reset()
    session.join()

    assert since(mark, "effect_applied") == [] and since(mark, "memory_changed") == []
    assert not config.memory_path().exists()  # H5: still the demonstration in memory only
    session.edit_memory("delete", "demo1")
    mark = get_journal().last_seq()
    session.reset()
    session.join()
    applied = [e for e in get_journal().events_since(mark) if e.kind == "effect_applied"]
    assert applied and {e.trigger for e in applied} == {"user"}
    assert [e["source"] for e in saved()] == ["demo"] * 3
    session.close()


def test_drawer_replace_refuses_a_duplicate_and_ignores_no_change():
    _, session = memory_session()
    client = _client(session)
    route = "/api/intentions/memory"
    mark = get_journal().last_seq()

    same = {"op": "replace", "entry_id": "demo1", "text": DEMO[0]}
    twice = {"op": "replace", "entry_id": "demo1", "text": DEMO[1].upper()}
    same = client.post(route, json=same, headers=HEADERS)
    duplicate = client.post(route, json=twice, headers=HEADERS)
    no_id = client.post(route, json={"op": "delete"}, headers=HEADERS)
    no_text = client.post(route, json={"op": "replace", "entry_id": "demo1"}, headers=HEADERS)

    assert same.status_code == 200 and not config.memory_path().exists()
    assert duplicate.status_code == 422 and "déjà en mémoire" in duplicate.json()["detail"]
    assert (no_id.status_code, no_text.status_code) == (422, 422)
    assert since(mark, "effect_applied") == []
    session.close()


def test_texts_are_one_line_and_arming_refuses_a_non_text():
    _, session = memory_session([remember("Préfère\n\nle   café."), "Noté."])
    arm = _client(session).post(
        "/api/intentions/arm",
        json={"kind": "memory", "target": "remember", "args": {"text": 42}},
        headers=HEADERS,
    )
    assert arm.status_code == 422

    run(session, "Retiens ceci.")

    assert saved()[-1]["text"] == "Préfère le café."
    session.close()


def test_no_drawer_write_during_a_turn(monkeypatch):
    engine, session = memory_session(["Bonjour."])
    entered, gate = threading.Event(), threading.Event()
    write = memory_file.write_memory

    def slow(path, entries):
        entered.set()
        gate.wait(5)
        write(path, entries)

    monkeypatch.setattr(memory_file, "write_memory", slow)
    mark = get_journal().last_seq()
    editor = threading.Thread(target=session.edit_memory, args=("delete", "demo1"))
    editor.start()
    assert entered.wait(5)
    sender = threading.Thread(target=session.send, args=("Bonjour",))
    sender.start()
    time.sleep(0.2)
    assert sender.is_alive() and engine.calls == []  # the turn waits for the write

    gate.set()
    editor.join(5)
    sender.join(5)
    session.join()

    kinds = [e.kind for e in get_journal().events_since(mark)]
    assert kinds.index("effect_applied") < kinds.index("turn_started")
    assert DEMO[0] not in json.dumps(since(mark, "context_rendered")[0])
    session.close()


def test_the_card_says_what_the_drawer_and_the_force_need():
    _, session = memory_session()
    assert card()["empty_text"].startswith("Aucune information en mémoire globale. Le modèle peut")
    assert f"{memory_file.MAX_CHARS} caractères au plus" in card()["text_help_text"]
    changed = last("memory_changed")
    assert (changed["max_entries"], changed["max_chars"]) == (20, memory_file.MAX_CHARS)
    session.close()
    _, session = memory_session(qwen=False, skills=False)
    assert "même par une écriture forcée" in card()["empty_text"]
    session.close()
