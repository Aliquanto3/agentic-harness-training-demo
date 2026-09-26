"""Story 10: scenarios by brick, programme, reset (FR-38, FR-39, AD-19)."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from fake_engine import FakeEngine, booted_session
from test_bricks import HEADERS, _client
from test_turn import _run

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
    assert len(ids) == 15 and ids[0] == "bare_llm" and ids[-1] == "data_flows"
    assert program["modules"][-4]["scenarios"][0]["id"] == "reasoning"  # story 13
    assert program["modules"][-3]["scenarios"][0]["id"] == "global_memory"  # story 14
    assert program["modules"][-2]["scenarios"][0]["id"] == "subagent"  # story 19
    assert program["modules"][-1]["scenarios"][0]["id"] == "rag"  # story 15
    assert all(30 <= m["duration_min"] <= 60 for m in program["modules"])

    for scenario_id in ids:
        session.launch_scenario(scenario_id)
        session.join()
        declared = session._scenarios.scenarios[scenario_id]
        cards = _latest("bricks_changed")["bricks"]
        assert {c["id"] for c in cards if c["wanted"]} == set(declared.bricks)
        assert _latest("scenario_changed")["active"] == scenario_id
    session.close()


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
    assert changed["program"]["modules"][3]["scenarios"][2]["prompts"] == [
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

    assert session._wanted == {"short_memory", "system_prompt", "tools", "mcp"}
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
    "  - title_fr: Module\n"
    "    duration_min: 45\n"
    "    scenarios: [rag]\n"
    "scenarios:\n"
    "  rag:\n"
    "    title_fr: RAG\n"
    "    description_fr: Pas encore construit.\n"
    "    bricks: [compression]\n"
    "    prompts: [Bonjour]\n"
)
_MISSING_ENTRY = (
    "program:\n"
    "  - title_fr: Module\n"
    "    duration_min: 45\n"
    "    scenarios: [rag, missing]\n"
    "scenarios:\n"
    "  rag:\n"
    "    title_fr: RAG\n"
    "    description_fr: Rien.\n"
    "    prompts: [Bonjour]\n"
)


@pytest.mark.parametrize(
    ("text", "cause"), [(_UNKNOWN_BRICK, "compression"), (_MISSING_ENTRY, "missing")]
)
def test_invalid_content_gives_an_error_and_an_empty_programme(tmp_path, monkeypatch, text, cause):
    (tmp_path / "scenarios.yaml").write_text(text, encoding="utf-8")
    monkeypatch.setattr(scenarios_module, "config", SimpleNamespace(content_dir=lambda: tmp_path))
    mark = get_journal().last_seq()

    session = booted_session(FakeEngine())

    errors = [p for p in (e.payload for e in _since(mark) if e.kind == "harness_error")]
    assert any("scenarios.yaml" in p["message_fr"] and cause in p["cause"] for p in errors)
    assert _latest("scenario_changed", mark)["program"] == {"modules": [], "transverse": []}
    assert session.model_loaded and session.state == "idle"
    with pytest.raises(KeyError):
        session.launch_scenario("rag")
    session.close()
