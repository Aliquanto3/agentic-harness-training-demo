"""Story 4: brick contract, short memory, system prompt, clearing the conversation."""

from __future__ import annotations

import threading

import pytest
from fake_engine import FakeEngine, booted_session
from starlette.testclient import TestClient
from test_turn import _run

from wavestack import config
from wavestack.bricks.contract import BrickContent, BrickDeclaration, Component
from wavestack.bricks.registry import BRICKS, check_unique_ids
from wavestack.session import app_session as app_session_module
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.journal import get_journal
from wavestack.web.app import create_app

HEADERS = {"origin": "http://127.0.0.1:8421"}


def _kinds(ctx: dict) -> set[str]:
    return {s["kind"] for s in ctx["segments"]}


def _texts(ctx: dict, kind: str) -> list[str]:
    return [s["text"] for s in ctx["segments"] if s["kind"] == kind]


def _latest(kind: str, mark: int) -> dict:
    return [e.payload for e in get_journal().events_since(mark) if e.kind == kind][-1]


def _client(app_session: AppSession) -> TestClient:
    app = create_app(
        DiagnosticSession(config.load_config(), port=8421),
        port=8421,
        version="test",
        app_session=app_session,
    )
    return TestClient(app, base_url="http://127.0.0.1:8421")


# ---------- I/O matrix ----------


def test_bare_llm_second_turn_is_byte_identical_to_story_3():
    engine = FakeEngine(output="Bonjour !")
    session = booted_session(engine)

    _run(session, "Bonjour")
    ctx = _run(session, "Encore")["context_rendered"][0]

    assert _kinds(ctx) == {"user_message", "template"}
    assert engine.calls[1] == list(b"<|im_start|>user\nEncore<|im_end|>\n<|im_start|>assistant\n")


def test_short_memory_reinjects_turns_made_while_off_and_grows():
    engine = FakeEngine(output="Bonjour !")
    session = booted_session(engine)
    first = _run(session, "Bonjour")["context_rendered"][0]  # brick off: still recorded

    session.set_brick("short_memory", True)
    second = _run(session, "Encore")
    third = _run(session, "Et après ?")

    ctx = second["context_rendered"][0]
    assert _texts(ctx, "history") == ["Bonjour", "Bonjour !"]
    assert {s["brick"] for s in ctx["segments"] if s["kind"] == "history"} == {"short_memory"}
    assert sum(s["tokens"] for s in ctx["segments"]) == ctx["used"]
    prompt_tokens = [
        first["used"],
        second["model_call_ended"][0]["prompt_tokens"],
        third["model_call_ended"][0]["prompt_tokens"],
    ]
    assert prompt_tokens == sorted(set(prompt_tokens))  # strictly increasing
    assert _texts(third["context_rendered"][0], "history")[-2:] == ["Encore", "Bonjour !"]


@pytest.mark.parametrize(
    ("engine_kwargs", "window", "message", "status"),
    [
        ({"fail": True}, 4096, "Bonjour", "error"),
        ({"output": "a" * 600}, 4096, "Bonjour", "limit"),
        ({}, 600, "x" * 200, "overflow"),
    ],
)
def test_unfinished_turn_stays_out_of_history(engine_kwargs, window, message, status):
    engine = FakeEngine(**engine_kwargs)
    session = booted_session(engine, window=window)
    session.set_brick("short_memory", True)

    assert _run(session, message)["turn_ended"][0]["status"] == status
    engine.fail, engine.output = False, "ok"
    ctx = _run(session, "Encore")["context_rendered"][0]

    assert "history" not in _kinds(ctx)


def test_cancelled_turn_stays_out_of_history():
    gate = threading.Event()
    session = booted_session(FakeEngine(gate=gate))
    session.set_brick("short_memory", True)
    mark = get_journal().last_seq()
    session.send("Bonjour")
    assert session.stop() is True
    gate.set()
    session.join()
    assert _latest("turn_ended", mark)["status"] == "cancelled"

    assert "history" not in _kinds(_run(session, "Encore")["context_rendered"][0])


def test_saved_system_prompt_reaches_next_turn_and_preview():
    session = booted_session(FakeEngine())
    session.set_brick("system_prompt", True)
    mark = get_journal().last_seq()

    saved = session.save_system_prompt("Réponds en alexandrins.")
    session.join()

    assert saved == {"text": "Réponds en alexandrins.", "is_default": False}
    assert _texts(_latest("context_preview", mark), "system_prompt") == ["Réponds en alexandrins."]
    ctx = _run(session, "Bonjour")["context_rendered"][0]
    assert _texts(ctx, "system_prompt") == ["Réponds en alexandrins."]
    assert ctx["segments"][1]["kind"] == "system_prompt"  # system message first

    default = session.save_system_prompt(None)
    assert default["is_default"] and default["text"].startswith("Tu es l'assistant")


def test_toggle_during_turn_is_accepted_and_waits_for_next_turn():
    gate = threading.Event()
    session = booted_session(FakeEngine(gate=gate))
    mark = get_journal().last_seq()
    session.send("Bonjour")

    session.set_brick("system_prompt", True)  # class (a): no refusal while in `turn`
    gate.set()
    session.join()

    assert "system_prompt" not in _kinds(_latest("context_rendered", mark))
    assert "system_prompt" in _kinds(_run(session, "Encore")["context_rendered"][0])


def test_pending_until_next_turn_started():
    session = booted_session(FakeEngine())
    mark = get_journal().last_seq()
    session.set_brick("short_memory", True)
    card = {b["id"]: b for b in _latest("bricks_changed", mark)["bricks"]}["short_memory"]
    assert card["wanted"] and card["available"] and card["pending"]

    events = _run(session, "Bonjour")

    assert not any(b["pending"] for b in events["bricks_changed"][-1]["bricks"])


def test_clear_conversation_empties_history_only():
    session = booted_session(FakeEngine())
    session.set_brick("short_memory", True)
    session.set_brick("system_prompt", True)
    session.save_system_prompt("Sois bref.")
    _run(session, "Bonjour")
    mark = get_journal().last_seq()

    session.clear_conversation()
    session.join()

    kinds = [e.kind for e in get_journal().events_since(mark)]
    assert "conversation_cleared" in kinds and "context_preview" in kinds
    ctx = _run(session, "Encore")["context_rendered"][0]
    assert "history" not in _kinds(ctx)
    assert _texts(ctx, "system_prompt") == ["Sois bref."]


def test_clear_conversation_outside_idle_is_409():
    gate = threading.Event()
    session = booted_session(FakeEngine(gate=gate))
    client = _client(session)

    client.post("/api/intentions/send", json={"message": "Bonjour"}, headers=HEADERS)
    refused = client.post("/api/intentions/clear_conversation", json={}, headers=HEADERS)
    toggled = client.post(
        "/api/intentions/brick", json={"brick": "short_memory", "wanted": True}, headers=HEADERS
    )
    gate.set()
    session.join()

    assert refused.status_code == 409 and "Un tour est déjà en cours" in refused.json()["detail"]
    assert toggled.status_code == 200
    with pytest.raises(SendRefused):
        AppSession(config.Config(values={})).clear_conversation()  # still in `diagnostic`


def test_invalid_brick_content_makes_it_unavailable(monkeypatch):
    real = app_session_module.load_brick_content

    def load(brick_id: str) -> BrickContent:
        if brick_id == "short_memory":
            raise ValueError("YAML illisible")
        return real(brick_id)

    monkeypatch.setattr(app_session_module, "load_brick_content", load)
    mark = get_journal().last_seq()
    session = booted_session(FakeEngine())
    session.set_brick("short_memory", True)

    assert any("short_memory" in e.payload["message_fr"] for e in _harness_errors(mark))
    card = {b["id"]: b for b in _latest("bricks_changed", mark)["bricks"]}["short_memory"]
    assert card["wanted"] and not card["available"] and "short_memory.yaml" in card["reason_fr"]
    _run(session, "Bonjour")
    events = _run(session, "Encore")
    assert "history" not in _kinds(events["context_rendered"][0])
    assert events["turn_ended"][0]["status"] == "completed"


def test_invalid_default_prompt_makes_system_prompt_unavailable(monkeypatch):
    def fail() -> str:
        raise OSError("system.md introuvable")

    monkeypatch.setattr(app_session_module, "load_default_system_prompt", fail)
    mark = get_journal().last_seq()
    session = booted_session(FakeEngine())
    session.set_brick("system_prompt", True)

    card = {b["id"]: b for b in _latest("bricks_changed", mark)["bricks"]}["system_prompt"]
    assert not card["available"] and "system.md" in card["reason_fr"]
    assert _harness_errors(mark)
    assert "system_prompt" not in _kinds(_run(session, "Bonjour")["context_rendered"][0])


def _harness_errors(mark: int) -> list:
    return [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]


# ---------- contract and availability ----------


def _fake(brick_id: str, requires: list[str] | None = None) -> BrickDeclaration:
    component = Component(id=f"{brick_id}.part", kind="fake", hosting="local_process")
    return BrickDeclaration(
        id=brick_id, category="harness", requires=requires or [], components=[component]
    )


def test_missing_dependency_is_unavailable_with_reason(monkeypatch):
    content = BrickContent(
        label_fr="Parent", category_fr="x", hosting_fr="Local", explanation_fr=["x"]
    )
    monkeypatch.setattr(app_session_module, "load_brick_content", lambda _: content)
    session = AppSession(
        config.Config(values={}), bricks=[_fake("parent"), _fake("child", requires=["parent"])]
    )
    session.set_brick("child", True)

    child = session._availability("child")
    assert child[0] is False and "Parent" in child[1]
    assert session.build_turn_state().effective == frozenset()

    session.set_brick("parent", True)
    assert session._availability("child") == (True, None)
    assert session.build_turn_state().effective == {"parent", "child"}


def test_duplicate_or_reserved_ids_are_refused():
    with pytest.raises(ValueError, match="duplicate"):
        check_unique_ids([*BRICKS, _fake("short_memory")])
    clash = BrickDeclaration(
        id="core",
        category="harness",
        components=[Component(id="core.harness", kind="fake", hosting="local_process")],
    )
    with pytest.raises(ValueError, match="duplicate"):
        check_unique_ids([clash])
    with pytest.raises(ValueError, match="must start with"):
        BrickDeclaration(
            id="a",
            category="harness",
            components=[Component(id="b.x", kind="f", hosting="local_file")],
        )


def test_wanted_brick_is_drawn_linked_to_the_harness():
    session = booted_session(FakeEngine())
    mark = get_journal().last_seq()

    session.set_brick("short_memory", True)

    arch = _latest("architecture_changed", mark)
    node = next(n for n in arch["nodes"] if n["id"] == "short_memory.history")
    assert node["kind"] == "brick" and node["label_fr"] == "Mémoire courte"
    model = next(n for n in arch["nodes"] if n["id"] == "core.model")
    assert model["model"] == "fake"
    assert arch["edges"] == [
        {"from": "short_memory.history", "to": "core.harness", "crosses_boundary": False}
    ]
    session.set_brick("short_memory", False)
    assert [n["id"] for n in _latest("architecture_changed", mark)["nodes"]] == [
        "core.harness",
        "core.model",
    ]


def test_http_intentions_and_state():
    session = booted_session(FakeEngine())
    client = _client(session)

    ok = client.post(
        "/api/intentions/brick", json={"brick": "system_prompt", "wanted": True}, headers=HEADERS
    )
    unknown = client.post(
        "/api/intentions/brick", json={"brick": "nope", "wanted": True}, headers=HEADERS
    )
    saved = client.post(
        "/api/intentions/system_prompt", json={"text": "Sois bref."}, headers=HEADERS
    )
    cleared = client.post("/api/intentions/clear_conversation", json={}, headers=HEADERS)
    session.join()

    assert ok.status_code == 200 and unknown.status_code == 404
    assert saved.json() == {"text": "Sois bref.", "is_default": False}
    assert cleared.status_code == 200
    state = client.get("/api/state").json()["bricks_changed"]
    assert state["system_prompt"] == {"text": "Sois bref.", "is_default": False}
    cards = {b["id"]: b for b in state["bricks"]}
    assert cards["system_prompt"]["wanted"] and cards["system_prompt"]["category_fr"]
    assert cards["short_memory"]["explanation_fr"] and cards["short_memory"]["hosting_fr"]


# ---------- review follow-ups ----------


def test_boot_emits_bare_llm_cards_without_any_toggle():
    for boot in (
        lambda: booted_session(FakeEngine()),
        lambda: AppSession(config.Config(values={})).boot(None).result(),
    ):
        mark = get_journal().last_seq()
        boot()
        cards = _latest("bricks_changed", mark)
        assert {b["id"]: b["wanted"] for b in cards["bricks"]} == {
            "short_memory": False,
            "system_prompt": False,
            "global_memory": False,
            "reasoning": False,
            "tools": False,
            "mcp": False,
            "skills": False,
            "hooks": False,
            "subagent": False,
            "rag": False,
            "compression": False,
        }
        assert cards["system_prompt"]["is_default"] is True


def test_toggle_without_engine_raises_no_harness_error():
    session = AppSession(config.Config(values={}))
    session.boot(None).result()
    mark = get_journal().last_seq()

    session.set_brick("short_memory", True)
    session.join()

    assert _harness_errors(mark) == []
    model = next(
        n for n in _latest("architecture_changed", mark)["nodes"] if n["id"] == "core.model"
    )
    assert model["model"] is None  # no model loaded: the robot shows no file name


def test_missing_capability_is_unavailable_with_reason(monkeypatch):
    content = BrickContent(label_fr="X", category_fr="x", hosting_fr="Local", explanation_fr=["x"])
    monkeypatch.setattr(app_session_module, "load_brick_content", lambda _: content)
    brick = _fake("tools").model_copy(update={"capabilities": ["tool_call_parser"]})
    session = AppSession(
        config.Config(values={}), engine_factory=lambda path, n_ctx: FakeEngine(), bricks=[brick]
    )
    session.boot("fake.gguf").result()  # the fake model has no tool-call parser

    available, reason = session._availability("tools")
    assert available is False and "l'appel d'outils" in reason


def test_edge_to_an_undrawn_node_is_dropped(monkeypatch):
    content = BrickContent(
        label_fr="Audit", category_fr="x", hosting_fr="Local", explanation_fr=["x"]
    )
    monkeypatch.setattr(app_session_module, "load_brick_content", lambda _: content)
    component = Component(
        id="audit.log",
        kind="fake",
        hosting="local_process",
        edges_to=["core.harness", "file.rag_index"],
    )
    brick = BrickDeclaration(id="audit", category="harness", components=[component])
    session = AppSession(config.Config(values={}), bricks=[brick])
    mark = get_journal().last_seq()

    session.set_brick("audit", True)

    edges = _latest("architecture_changed", mark)["edges"]
    assert edges == [{"from": "audit.log", "to": "core.harness", "crosses_boundary": False}]


def test_pending_only_when_the_next_turn_changes():
    session = booted_session(FakeEngine())
    mark = get_journal().last_seq()

    session.set_brick("short_memory", True)
    session.set_brick("short_memory", False)  # back to what the last send froze
    session.save_system_prompt("Sois bref.")  # brick off: no effect on the next turn

    assert not any(b["pending"] for b in _latest("bricks_changed", mark)["bricks"])
    session.set_brick("system_prompt", True)
    _run(session, "Bonjour")
    session.save_system_prompt("Sois bref.")  # unchanged text
    assert not any(b["pending"] for b in _latest("bricks_changed", mark)["bricks"])


def _overflow(session, message: str) -> str:
    events = _run(session, message)
    assert events["turn_ended"][0]["status"] == "overflow"
    return events["context_overflow"][0]["message_fr"]


def test_overflow_cause_is_the_heaviest_segment():
    session = booted_session(FakeEngine(output="r" * 60), window=700)  # usable: 188 byte-tokens
    session.set_brick("short_memory", True)
    _run(session, "q" * 40)
    assert "videz la conversation" in _overflow(session, "Et ensuite ?")

    session.clear_conversation()
    session.set_brick("short_memory", False)
    session.set_brick("system_prompt", True)
    session.save_system_prompt("p" * 200)
    assert "prompt système" in _overflow(session, "Bonjour")
    session.save_system_prompt(None)
    assert "le message à lui seul" in _overflow(session, "m" * 300)


# ---------- story 22: display order, turn ids across clearing and reset ----------


def test_reasoning_card_comes_first_and_the_ids_are_unchanged():
    mark = get_journal().last_seq()
    booted_session(FakeEngine())

    cards = _latest("bricks_changed", mark)["bricks"]

    assert cards[0]["id"] == "reasoning"
    assert {b["id"] for b in cards} == {
        "short_memory",
        "system_prompt",
        "global_memory",
        "reasoning",
        "tools",
        "mcp",
        "skills",
        "hooks",
        "subagent",
        "rag",
        "compression",
    }
    assert [b.id for b in BRICKS] == [b["id"] for b in cards]


def test_turn_ids_keep_growing_after_clearing_and_reset():
    session = booted_session(FakeEngine(output="Bonjour !"))
    mark = get_journal().last_seq()

    _run(session, "Un")
    _run(session, "Deux")
    session.clear_conversation()
    session.join()
    _run(session, "Trois")
    session.reset()
    session.join()
    _run(session, "Quatre")

    started = [e.turn_id for e in get_journal().events_since(mark) if e.kind == "turn_started"]
    assert started == ["t1", "t2", "t3", "t4"]
