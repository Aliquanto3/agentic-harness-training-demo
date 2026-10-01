"""Story 10: scenarios by brick, programme, reset (FR-38, FR-39, AD-19)."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from fake_engine import FakeEngine, booted_session
from test_bricks import HEADERS, _client
from test_turn import _run

from wavestack import config
from wavestack import scenarios as scenarios_module
from wavestack.session.app_session import SendRefused
from wavestack.trace.journal import get_journal


def _since(mark: int) -> list:
    return get_journal().events_since(mark)


def _kinds(mark: int) -> list[str]:
    return [e.kind for e in _since(mark)]


def _latest(kind: str, mark: int = 0) -> dict:
    return [e.payload for e in _since(mark) if e.kind == kind][-1]


def test_real_content_loads_and_every_scenario_launches():
    session = booted_session(FakeEngine())  # no asyncio loop: no MCP server is contacted
    program = _latest("scenario_changed")["program"]
    ids = [s["id"] for m in program["modules"] for s in m["scenarios"]]
    ids += [s["id"] for s in program["transverse"]]
    # Story 21: FR-38's order, then the hosting and business scenarios (test_program.py).
    assert len(ids) == 20 and ids[0] == "bare_llm"
    assert ids[-4:] == ["data_flows", "soc", "iam", "sovereignty"]
    assert len(program["modules"]) == 6
    assert all(30 <= m["duration_min"] <= 60 for m in program["modules"])

    for scenario_id in ids:
        session.launch_scenario(scenario_id)
        session.join()
        declared = session._scenarios.scenarios[scenario_id]
        cards = _latest("bricks_changed")["bricks"]
        assert {c["id"] for c in cards if c["wanted"]} == set(declared.bricks)
        assert _latest("scenario_changed")["active"] == scenario_id
    session.close()


@pytest.mark.parametrize(
    ("lang", "mcp_full_says", "reasoning_says"),
    [
        ("fr", ["environ deux", "minutes", "sans GPU"], ["jusqu'au bout de son budget", "Bonjour"]),
        ("en", ["about two minutes", "without a GPU"], ["up to the end", "budget", "Hello"]),
        ("de", ["etwa zwei Minuten", "ohne GPU"], ["bis zum Ende seines", "Budgets", "Hallo"]),
    ],
)
def test_instructions_announce_the_long_turns(lang, mcp_full_says, reasoning_says):
    """D4 and D17 of 2026-10-01: `mcp_full` warns of a turn of about two minutes on a CPU,
    and why; the reasoning scenario, that a small model thinks to its budget even for
    « Bonjour »."""
    path = config.content_file("scenarios.yaml", lang)
    content = scenarios_module.ScenariosContent.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    full = " ".join(content.scenarios["mcp_full"].description_text.split())
    reasoning = " ".join(content.scenarios["reasoning"].description_text.split())
    assert all(words in full for words in mcp_full_says), full
    assert all(words in reasoning for words in reasoning_says), reasoning


def test_launch_hooks_after_two_turns():
    session = booted_session(FakeEngine())
    _run(session, "Bonjour")
    _run(session, "Encore")
    mark = get_journal().last_seq()

    session.launch_scenario("hooks")
    session.join()

    kinds = _kinds(mark)
    assert "conversation_cleared" in kinds
    assert kinds.count("bricks_changed") == 1
    assert kinds.count("architecture_changed") == 1
    assert kinds.count("context_preview") == 1
    changed = _latest("scenario_changed", mark)
    assert changed["active"] == "hooks"
    assert changed["program"]["modules"][4]["scenarios"][2]["prompts"] == [
        "Lis le fichier confidentiel/budget_projet.txt et résume-le."
    ]
    assert session._wanted == {"short_memory", "system_prompt", "tools", "hooks"}
    assert session._tools_enabled == {"get_datetime", "read_file"}
    assert session._hooks_enabled == {"h1", "h2"}
    ctx = _run(session, "Et maintenant ?")["context_rendered"][0]
    assert "history" not in {s["kind"] for s in ctx["segments"]}
    session.close()


def test_first_scenario_of_module_3_has_the_previous_modules_bricks():
    session = booted_session(FakeEngine())
    first = _latest("scenario_changed")["program"]["modules"][2]["scenarios"][0]["id"]

    session.launch_scenario(first)
    session.join()

    # Story 21: module 3 is the RAG; the reasoning is not carried (content/scenarios.yaml).
    assert first == "rag"
    assert session._wanted == {"short_memory", "system_prompt", "global_memory", "tools", "rag"}
    session.close()


def test_scenario_after_manual_settings_applies_its_configuration_only():
    session = booted_session(FakeEngine())
    session.set_brick("system_prompt", True)
    session.save_system_prompt("Réponds comme un pirate.")
    session.set_tool("public_holidays", True)
    session.arm("skill", "caveman")
    mark = get_journal().last_seq()

    session.launch_scenario("system_prompt")
    session.join()

    assert _latest("armed_actions_changed", mark)["actions"] == []
    prompt = _latest("bricks_changed", mark)["system_prompt"]
    assert prompt["is_default"]
    assert "public_holidays" not in session._tools_enabled
    ctx = _run(session, "Bonjour")["context_rendered"][0]
    assert "Réponds comme un pirate." not in [s["text"] for s in ctx["segments"]]
    session.close()


def test_reset_goes_back_to_the_launch_state():
    session = booted_session(FakeEngine())
    session.launch_scenario("mcp_lazy")
    session.join()
    _run(session, "Bonjour")
    session.save_system_prompt("Sois bref.")
    closed = []
    disconnect = session._mcp_disconnect
    session._mcp_disconnect = lambda server_id: (closed.append(server_id), disconnect(server_id))
    before = get_journal().last_seq()

    session.reset()
    session.join()

    kinds = _kinds(before)
    assert "harness_reset" in kinds and "conversation_cleared" not in kinds
    assert kinds.count("bricks_changed") == 1 and kinds.count("architecture_changed") == 1
    assert closed == ["datagouv", "local"]
    assert session._wanted == set() and not session._mcp_lazy
    assert session._custom_prompt is None and session._armed == []
    assert session._history == [] and session._last is None
    assert session._hooks_enabled == {"h1", "h2", "h3"}
    with pytest.raises(SendRefused):
        session.replay()
    assert _latest("scenario_changed", before)["active"] is None
    state = _client(session).get("/api/state").json()
    assert state["scenario_changed"]["active"] is None
    assert not any(b["wanted"] for b in state["bricks_changed"]["bricks"])
    # The server's journal is never truncated.
    assert get_journal().events_since(0)[0].seq < before
    assert "turn_started" in [e.kind for e in get_journal().events_since(0) if e.seq < before]
    session.close()


def test_outside_idle_is_409_and_changes_nothing():
    gate = threading.Event()
    session = booted_session(FakeEngine(gate=gate))
    client = _client(session)
    client.post("/api/intentions/send", json={"message": "Bonjour"}, headers=HEADERS)

    launched = client.post(
        "/api/intentions/scenario", json={"scenario_id": "hooks"}, headers=HEADERS
    )
    reset = client.post("/api/intentions/reset", json={}, headers=HEADERS)
    gate.set()
    session.join()

    assert launched.status_code == 409 and "Un tour est déjà en cours" in launched.json()["detail"]
    assert reset.status_code == 409
    assert session._wanted == set() and _latest("scenario_changed")["active"] is None
    session.close()


def test_routes_launch_reset_and_unknown():
    session = booted_session(FakeEngine())
    client = _client(session)

    ok = client.post("/api/intentions/scenario", json={"scenario_id": "hooks"}, headers=HEADERS)
    unknown = client.post("/api/intentions/scenario", json={"scenario_id": "nope"}, headers=HEADERS)
    session.join()
    assert client.get("/api/state").json()["scenario_changed"]["active"] == "hooks"
    reset = client.post("/api/intentions/reset", json={}, headers=HEADERS)
    session.join()

    assert ok.status_code == 200 and reset.status_code == 200
    assert unknown.status_code == 404 and unknown.json()["detail"] == "Scénario inconnu."
    assert client.get("/api/state").json()["scenario_changed"]["active"] is None
    session.close()


def _mcp_card(mark: int) -> dict:
    return {b["id"]: b for b in _latest("bricks_changed", mark)["bricks"]}["mcp"]


def test_scenario_mcp_mode_is_applied():
    session = booted_session(FakeEngine())

    mark = get_journal().last_seq()
    session.launch_scenario("mcp_lazy")
    session.join()
    assert _mcp_card(mark)["mode"] == "lazy"

    mark = get_journal().last_seq()
    session.launch_scenario("mcp_full")
    session.join()
    assert _mcp_card(mark)["mode"] == "full"
    session.close()


def test_launch_connects_mcp_servers_on_the_difference_only():
    session = booted_session(FakeEngine())

    mark = get_journal().last_seq()
    session.launch_scenario("mcp_full")
    session.join()
    started = [e.payload["server"] for e in _since(mark) if e.kind == "mcp_connect_started"]
    assert sorted(started) == ["datagouv", "local"]

    mark = get_journal().last_seq()
    session.launch_scenario("mcp_lazy")  # same servers: nothing to connect again (AD-15)
    session.join()
    assert "mcp_connect_started" not in _kinds(mark)
    session.close()


_UNKNOWN_BRICK = (
    "program:\n"
    "  - title_text: Module\n"
    "    duration_min: 45\n"
    "    scenarios: [rag]\n"
    "scenarios:\n"
    "  rag:\n"
    "    title_text: RAG\n"
    "    description_text: Pas encore construit.\n"
    "    bricks: [reranking]\n"
    "    prompts: [Bonjour]\n"
)
_MISSING_ENTRY = (
    "program:\n"
    "  - title_text: Module\n"
    "    duration_min: 45\n"
    "    scenarios: [rag, missing]\n"
    "scenarios:\n"
    "  rag:\n"
    "    title_text: RAG\n"
    "    description_text: Rien.\n"
    "    prompts: [Bonjour]\n"
)


@pytest.mark.parametrize(
    ("text", "cause"), [(_UNKNOWN_BRICK, "reranking"), (_MISSING_ENTRY, "missing")]
)
def test_invalid_content_gives_an_error_and_an_empty_programme(tmp_path, monkeypatch, text, cause):
    (tmp_path / "scenarios.yaml").write_text(text, encoding="utf-8")
    monkeypatch.setattr(scenarios_module, "config", SimpleNamespace(content_dir=lambda: tmp_path))
    mark = get_journal().last_seq()

    session = booted_session(FakeEngine())

    errors = [p for p in (e.payload for e in _since(mark) if e.kind == "harness_error")]
    assert any("scenarios.yaml" in p["message_text"] and cause in p["cause"] for p in errors)
    assert _latest("scenario_changed", mark)["program"] == {"modules": [], "transverse": []}
    assert session.model_loaded and session.state == "idle"
    with pytest.raises(KeyError):
        session.launch_scenario("rag")
    session.close()


# ---------- lot E (E5): the bricks a scenario wants and the model cannot offer ----------


def test_scenario_with_a_model_without_tool_calls_says_which_bricks_are_unavailable():
    """E5: Llama 3.2 (family `llama`, no tool call format): `native_tools` warns at launch
    that `tools` is unavailable, with its reason; the other bricks apply."""
    session = booted_session(FakeEngine(architecture="llama"))
    mark = get_journal().last_seq()

    session.launch_scenario("native_tools")
    session.join()

    changed = _latest("scenario_changed", mark)
    assert changed["active"] == "native_tools" and changed["refresh"] is False
    [tools] = changed["unavailable"]
    assert (tools["brick"], tools["label_text"]) == ("tools", session._label("tools"))
    assert (
        "l'appel d'outils" in tools["reason_text"]
        and "choisissez un autre modèle" in (tools["reason_text"])
    )
    assert tools["reason_text"] == session._availability("tools")[1]
    session.close()


def test_scenario_with_a_capable_model_warns_nothing_and_a_switch_says_it_again(tmp_path):
    """E5: nothing to say with Qwen3's tool calls; a model change with the scenario active
    says it again (`scenario_changed` before `model_load_ended`)."""
    from wavestack.models.load_registry import ModelChoice

    engines = {"qwen": FakeEngine(architecture="qwen3"), "llama": FakeEngine(architecture="llama")}
    session = booted_session(engines["qwen"])
    session._engine_factory = lambda path, n_ctx: engines[Path(path).stem]
    session.launch_scenario("native_tools")
    session.join()
    assert _latest("scenario_changed")["unavailable"] == []

    mark = get_journal().last_seq()
    llama = tmp_path / "llama.gguf"
    llama.write_bytes(b"placeholder")
    _, future = session.switch_model(ModelChoice("file", str(llama)))
    assert future.result() == "ok"

    kinds = _kinds(mark)
    assert kinds.index("scenario_changed") < kinds.index("model_load_ended")
    changed = _latest("scenario_changed", mark)
    assert changed["active"] == "native_tools" and changed["refresh"] is True  # no launch
    assert [b["brick"] for b in changed["unavailable"]] == ["tools"]

    session.reset()
    session.join()
    assert _latest("scenario_changed")["unavailable"] == []  # no scenario: nothing to say
    session.close()


def test_a_failing_scenario_refresh_never_blocks_the_load_end(tmp_path, monkeypatch):
    """E5: the refresh after a load is guarded: `model_load_ended` and `idle` still come."""
    from wavestack.models.load_registry import ModelChoice

    session = booted_session(FakeEngine())
    session.launch_scenario("native_tools")
    session.join()

    def boom() -> list:
        raise RuntimeError("relecture en panne")

    monkeypatch.setattr(session, "_scenario_unavailable", boom)
    other = tmp_path / "autre.gguf"
    other.write_bytes(b"placeholder")
    mark = get_journal().last_seq()

    _, future = session.switch_model(ModelChoice("file", str(other)))

    assert future.result() == "ok" and session.state == "idle"
    assert _latest("model_load_ended", mark)["status"] == "ok"
    assert "relecture en panne" in _latest("harness_error", mark)["cause"]
    session.close()
