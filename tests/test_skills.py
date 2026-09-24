"""Story 7: skills, the catalog in the system message and `load_skill` (AD-4, AD-19, AD-25)."""

from __future__ import annotations

import shutil

import pytest
from fake_engine import FakeEngine, booted_session
from test_bricks import HEADERS, _client
from test_mcp_lazy import exact
from test_tools import QWEN, _segments, call
from test_turn import _run

from wavestack import config
from wavestack.bricks.registry import SKILLS
from wavestack.trace.journal import get_journal

CAVEMAN = "Réponds en style télégraphique"  # the start of Caveman's body
WINDOW = 16384  # the fake engine counts one token per byte: every body loaded fits


def load(skill: str) -> str:
    return call("load_skill", skill=skill)


def skills_session(outputs=("Voilà.",), *, memory: bool = True):
    engine = FakeEngine(outputs=list(outputs), template=QWEN.decode("utf-8"), architecture="qwen35")
    session = booted_session(engine, window=WINDOW)
    if memory:
        session.set_brick("short_memory", True)
    session.set_brick("system_prompt", True)
    session.set_brick("skills", True)
    session.join()
    return engine, session


def since(mark: int, kind: str) -> list[dict]:
    return [e.payload for e in get_journal().events_since(mark) if e.kind == kind]


def preview(mark: int = 0) -> dict:
    return since(mark, "context_preview")[-1]


def nodes() -> dict[str, dict]:
    return {n["id"]: n for n in since(0, "architecture_changed")[-1]["nodes"]}


def card() -> dict:
    bricks = since(0, "bricks_changed")[-1]["bricks"]
    return next(b for b in bricks if b["id"] == "skills")


def catalog_lines(ctx: dict) -> list[dict]:
    return [s for s in _segments(ctx, "skill_catalog") if s["text"].startswith("- ")]


def check(ctx: dict, mark: int) -> None:
    """Every render: the sum equals the total, and no attribution error."""
    exact(ctx)
    assert since(mark, "harness_error") == []


def system_kinds(ctx: dict) -> list[str]:
    """The harness texts of the system message, in order (the template puts `tools` first)."""
    kinds = ("system_prompt", "skill_catalog", "skill_body")
    return [s["kind"] for s in ctx["segments"] if s["kind"] in kinds]


# ---------- I/O matrix ----------


def test_activation_puts_one_catalog_line_per_skill_and_load_skill():
    mark = get_journal().last_seq()
    _, session = skills_session()

    ctx = preview(mark)
    lines = catalog_lines(ctx)
    assert [s["component"] for s in lines] == [f"skills.{s}" for s in SKILLS]
    assert {s["brick"] for s in _segments(ctx, "skill_catalog")} == {"skills"}
    assert lines[0]["text"].startswith("- caveman : Répondre en style télégraphique")
    (intro,) = [s for s in _segments(ctx, "skill_catalog") if s not in lines]
    assert intro["component"] == "core.harness" and "load_skill" in intro["text"]
    assert "load_skill" in session.build_turn_state().tools
    meta = [s for s in _segments(ctx, "tool_catalog") if s["text"].startswith("load_skill")]
    assert [(s["brick"], s["component"]) for s in meta] == [("skills", "core.harness")]
    assert system_kinds(ctx) == ["system_prompt"] + ["skill_catalog"] * (len(SKILLS) + 1)
    check(ctx, mark)
    options = card()["options"]
    assert [(o["id"], o["enabled"]) for o in options] == [(s, True) for s in SKILLS]
    assert card()["category"] == "context" and card()["available"]
    skill_nodes = [n for n in nodes().values() if n["kind"] == "skill"]
    assert [n["id"] for n in skill_nodes] == [f"skills.{s}" for s in SKILLS]
    caveman = nodes()["skills.caveman"]
    assert caveman["label_fr"] == "Caveman" and caveman["loaded"] is False
    assert caveman["detail_fr"].startswith("Répondre en style")
    assert caveman["hosting"] == "local"
    session.close()


def test_without_system_prompt_the_system_message_is_the_skills_alone():
    _, session = skills_session()
    mark = get_journal().last_seq()
    session.set_brick("system_prompt", False)
    session.join()

    ctx = preview(mark)
    assert system_kinds(ctx) == ["skill_catalog"] * (len(SKILLS) + 1)
    assert _segments(ctx, "skill_catalog")[0]["text"].startswith("Skills disponibles.")
    check(ctx, mark)
    session.close()


def test_load_answers_in_the_turn_then_joins_the_system_message():
    outputs = [load("caveman"), "Paris. Capitale.", "Lyon."]
    _, session = skills_session(outputs)
    mark = get_journal().last_seq()

    events = _run(session, "Réponds en mode caveman : capitale de la France ?")

    (started,) = events["tool_started"]
    assert started["phase_label"] == "Chargement du skill" and started["source"] == "harness"
    (envelope,) = [e for e in get_journal().events_since(mark) if e.kind == "tool_started"]
    assert (envelope.brick, envelope.component) == ("skills", "core.harness")
    assert events["tool_ended"][0]["result"].startswith(CAVEMAN)
    first, second = events["context_rendered"]
    (body,) = _segments(second, "skill_body")
    assert body["component"] == "skills.caveman" and body["text"].startswith(CAVEMAN)
    texts = [[s["text"] for s in catalog_lines(c)] for c in (first, second)]
    assert texts[0] == texts[1]  # the system message does not change in the turn
    assert "prefix_not_reused" not in events
    assert [e["output_tokens"] for e in events["model_call_ended"]] == [
        len(load("caveman").encode()),
        len("Paris. Capitale."),  # ASCII: one byte per character
    ]  # each call shows its output tokens (FR-25)
    for ctx in events["context_rendered"]:
        check(ctx, mark)
    assert nodes()["skills.caveman"]["loaded"] is True

    after = _run(session, "Et la deuxième ville ?")

    ctx = after["context_rendered"][0]
    (body,) = _segments(ctx, "skill_body")
    assert body["component"] == "skills.caveman" and body["brick"] == "skills"
    assert body["text"].startswith(f"Skill « Caveman » (caveman) :\n{CAVEMAN}")
    assert system_kinds(ctx) == ["system_prompt"] + ["skill_catalog"] * len(SKILLS) + ["skill_body"]
    assert [s["component"] for s in catalog_lines(ctx)] == [f"skills.{s}" for s in SKILLS[1:]]
    history = [s["text"] for s in _segments(ctx, "history")]
    assert "Skill « Caveman » chargé." in history
    assert not any(t.startswith(CAVEMAN) for t in history)
    assert len(_segments(ctx, "skill_catalog")) < len(_segments(first, "skill_catalog"))
    check(ctx, mark)
    session.close()


def test_loading_twice_or_an_unknown_or_disabled_name():
    outputs = [load("pirate"), load("pirate"), load("nope"), load("caveman"), "Voilà."]
    _, session = skills_session(outputs)
    session.set_skill("caveman", False)
    mark = get_journal().last_seq()

    events = _run(session, "Parle comme un pirate")

    _, again, unknown, disabled = events["tool_ended"]
    assert again["result"] == "Le skill « pirate » est déjà chargé."
    last = events["context_rendered"][-1]
    assert again["result"] in [s["text"] for s in _segments(last, "tool_result")]
    assert len(_segments(last, "skill_body")) == 1
    for error, name in ((unknown, "nope"), (disabled, "caveman")):
        assert error["status"] == "error" and f"« {name} »" in error["error_fr"]
        assert "meeting_minutes, explain_like_ten" in error["error_fr"]
        assert "caveman," not in error["error_fr"] and "pirate" not in error["error_fr"]
    for ctx in events["context_rendered"]:
        check(ctx, mark)
    session.close()


def test_everything_loaded_leaves_no_catalog_nor_meta_tool():
    # Three calls per output: the fake engine's 512-byte output reserve holds them.
    outputs = [*("\n".join(load(s) for s in part) for part in (SKILLS[:3], SKILLS[3:]))]
    outputs += ["Voilà.", "Encore."]
    _, session = skills_session(outputs)
    assert _run(session, "Charge tout")["turn_ended"][0]["status"] == "completed"
    mark = get_journal().last_seq()

    state = session.build_turn_state()
    assert state.skill_catalog == () and "load_skill" not in state.tools
    assert state.skills == SKILLS
    ctx = _run(session, "Et maintenant ?")["context_rendered"][0]
    assert _segments(ctx, "skill_catalog") == []
    assert '"load_skill"' not in "".join(s["text"] for s in ctx["segments"])
    bodies = _segments(ctx, "skill_body")
    assert [s["component"] for s in bodies] == [f"skills.{s}" for s in SKILLS]
    assert all(b["text"].startswith("Skill « ") for b in bodies)  # each body is named
    check(ctx, mark)
    session.close()


def test_a_disabled_skill_leaves_the_context_and_comes_back():
    _, session = skills_session([load("caveman"), "Voilà.", "Encore.", "Toujours."])
    _run(session, "Mode caveman")
    assert card()["pending"] is False

    session.set_skill("caveman", False)
    assert card()["pending"] is True
    events = _run(session, "Et sans ?")
    ctx = events["context_rendered"][0]
    assert _segments(ctx, "skill_body") == []
    assert "skills.caveman" not in {s["component"] for s in catalog_lines(ctx)}
    assert "skills.caveman" not in nodes()

    session.set_skill("caveman", True)
    ctx = _run(session, "Et avec ?")["context_rendered"][0]
    assert [s["component"] for s in _segments(ctx, "skill_body")] == ["skills.caveman"]
    assert nodes()["skills.caveman"]["loaded"] is True
    session.close()


def test_clearing_the_conversation_unloads_every_skill():
    _, session = skills_session([load("caveman"), "Voilà."])
    _run(session, "Mode caveman")
    mark = get_journal().last_seq()

    session.clear_conversation()
    session.join()

    assert session.build_turn_state().skills == ()
    ctx = preview(mark)
    assert [s["component"] for s in catalog_lines(ctx)] == [f"skills.{s}" for s in SKILLS]
    assert _segments(ctx, "skill_body") == []
    assert since(mark, "architecture_changed")  # the schema is emitted again
    assert nodes()["skills.caveman"]["loaded"] is False
    session.close()


@pytest.mark.parametrize(
    ("broken", "cause"),
    [
        (lambda t: t.replace("description:", "summary:"), "description"),  # no description
        (lambda t: t.replace("---\n", "", 2), "en-tête YAML"),  # no front matter
        (lambda t: t.replace("name: pirate", "name: corsaire"), "'corsaire'"),  # name != id
    ],
)
def test_an_invalid_skill_makes_the_brick_unavailable(tmp_path, monkeypatch, broken, cause):
    content = tmp_path / "content"
    shutil.copytree(config.content_dir(), content)
    skill = content / "skills" / "pirate" / "SKILL.md"
    skill.write_text(broken(skill.read_text(encoding="utf-8")), "utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    mark = get_journal().last_seq()

    engine, session = skills_session(["Bonjour !"])

    (error,) = since(mark, "harness_error")
    assert "pirate" in error["cause"] and cause in error["cause"]
    assert card()["wanted"] and not card()["available"]
    assert "content/skills" in card()["reason_fr"]
    events = _run(session, "Bonjour")
    assert events["turn_ended"][0]["status"] == "completed"
    kinds = {s["kind"] for s in events["context_rendered"][0]["segments"]}
    assert "system_prompt" in kinds and not {"skill_catalog", "tool_catalog"} & kinds
    session.close()


def test_brick_on_then_off_is_the_bare_llm_byte_for_byte():
    template = QWEN.decode("utf-8")
    bare = FakeEngine(template=template, architecture="qwen35")
    _run(booted_session(bare), "Bonjour")
    engine = FakeEngine(template=template, architecture="qwen35")
    session = booted_session(engine)
    session.set_brick("skills", True)
    session.join()
    session.set_brick("skills", False)

    _run(session, "Bonjour")

    assert engine.calls == bare.calls
    session.close()


# ---------- intentions ----------


def test_skill_intention_http():
    _, session = skills_session()
    client = _client(session)

    ok = client.post(
        "/api/intentions/skill", json={"skill": "pirate", "enabled": False}, headers=HEADERS
    )
    unknown = client.post(
        "/api/intentions/skill", json={"skill": "nope", "enabled": True}, headers=HEADERS
    )

    assert ok.status_code == 200 and unknown.status_code == 404
    assert "pirate" not in session.build_turn_state().skill_catalog
    pirate = next(o for o in card()["options"] if o["id"] == "pirate")
    assert pirate["enabled"] is False and card()["pending"]
    session.close()


# ---------- attribution of refused calls (AD-4) ----------


def test_refused_calls_with_the_skills_brick_alone_belong_to_skills():
    outputs = ["<tool_call>\n<function=load_skill\n</tool_call>", call("load_skill"), "Voilà."]
    engine = FakeEngine(outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35")
    session = booted_session(engine, window=WINDOW)
    session.set_brick("skills", True)
    mark = get_journal().last_seq()

    events = _run(session, "Mode caveman")

    malformed = [e for e in get_journal().events_since(mark) if e.kind == "tool_call_malformed"]
    assert [e.brick for e in malformed] == ["skills", "skills"]
    assert "manquant" in malformed[1].payload["detail_fr"]
    results = _segments(events["context_rendered"][2], "tool_result")
    assert [s["brick"] for s in results] == ["skills", "skills"]
    session.close()


def test_load_skill_without_argument_stays_skills_with_the_tools_brick_on():
    _, session = skills_session([call("load_skill"), "Voilà."])
    session.set_brick("tools", True)
    mark = get_journal().last_seq()

    events = _run(session, "Mode caveman")

    (malformed,) = [e for e in get_journal().events_since(mark) if e.kind == "tool_call_malformed"]
    assert malformed.brick == "skills" and "manquant" in malformed.payload["detail_fr"]
    (result,) = _segments(events["context_rendered"][1], "tool_result")
    assert result["brick"] == "skills"
    session.close()
