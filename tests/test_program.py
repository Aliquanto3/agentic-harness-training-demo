"""Story 21: the programme in FR-38's order, cumulative modules (CAP-40), every scenario
within the default window (AD-9), and the business scenarios (FR-40, CAP-42)."""

from __future__ import annotations

import time

from fake_engine import FakeEngine, booted_session
from pydantic import SecretStr
from test_cloud import GROQ_TEXT, SENTINEL, Provider
from test_hooks import audit_lines, decisions, hooks_session
from test_mcp import McpWeb, loop, mcp_session, node, web  # noqa: F401 - fixtures
from test_rag import Embedders, index, place_model, rag_values  # noqa: F401 - fixture
from test_tools import call
from test_turn import _run

from wavestack import config
from wavestack.session.app_session import AppSession
from wavestack.tools.native import read_file
from wavestack.trace.journal import get_journal

# FR-38: the order in which the bricks come into the programme.
FR38 = [
    "reasoning",
    "short_memory",
    "system_prompt",
    "global_memory",
    "tools",
    "rag",
    "mcp",
    "skills",
    "hooks",
    "subagent",
    "compression",
]
PROGRAMME = [
    ["bare_llm", "reasoning", "short_memory", "system_prompt", "global_memory"],
    ["native_tools", "network_tools"],
    ["rag", "rag_rerank"],
    ["mcp_full", "mcp_lazy"],
    ["skills", "caveman", "hooks"],
    ["subagent", "compression"],
]
TRANSVERSE = ["data_flows", "soc", "iam", "sovereignty"]
# The exceptions written at the top of content/scenarios.yaml (AD-9).
NEVER_CARRIED = {"reasoning"}
LEFT_OFF = {"mcp_full": {"rag"}}
CHARS_PER_TOKEN = 4  # the cloud estimate (wavestack.toml `[cloud] chars_per_token`)


def _content():
    session = booted_session(FakeEngine())  # no asyncio loop: no MCP server is contacted
    content = session._scenarios
    session.close()
    return content


def test_programme_follows_fr38_then_the_hosting_and_business_scenarios():
    content = _content()

    assert [m.scenarios for m in content.program] == PROGRAMME
    assert content.transverse == TRANSVERSE
    assert all(30 <= m.duration_min <= 60 for m in content.program)
    introduced: list[str] = []
    for module in content.program:
        for scenario_id in module.scenarios:
            for brick in content.scenarios[scenario_id].bricks:
                if brick not in introduced:
                    introduced.append(brick)
    assert introduced == FR38
    assert not content.scenarios["rag"].rag_rerank and content.scenarios["rag_rerank"].rag_rerank
    assert not content.scenarios["mcp_full"].mcp_lazy and content.scenarios["mcp_lazy"].mcp_lazy


def test_first_scenario_of_each_module_has_the_previous_modules_bricks():
    content = _content()
    before: set[str] = set()
    for i, module in enumerate(content.program):
        first_id = module.scenarios[0]
        first = content.scenarios[first_id]
        expected = before - NEVER_CARRIED - LEFT_OFF.get(first_id, set())
        assert expected <= set(first.bricks), (first_id, expected - set(first.bricks))
        if i > 0:  # the scenario's instructions say which brick stays off, and why
            assert "raisonnement" in first.description_fr, first_id
        if "rag" in LEFT_OFF.get(first_id, set()):
            assert "RAG" in first.description_fr, first_id
        for scenario_id in module.scenarios:
            before |= set(content.scenarios[scenario_id].bricks)


def test_business_scenarios_fix_their_bricks_and_hooks():
    content = _content()
    soc, iam, sovereignty = (content.scenarios[i] for i in ("soc", "iam", "sovereignty"))

    assert soc.bricks == ["short_memory", "system_prompt", "tools", "hooks"]
    assert soc.tools == ["read_file"] and soc.hooks == ["h1", "h2"]
    assert iam.bricks == ["short_memory", "system_prompt", "mcp"]
    assert iam.mcp_servers == ["mslearn"] and not iam.mcp_lazy  # AD-9: full documentation
    assert sovereignty.mcp_servers == ["datagouv"] and sovereignty.mcp_lazy  # AD-9: lazy
    for scenario in (soc, iam, sovereignty):
        assert scenario.title_fr.startswith("Métier ") and len(scenario.prompts) == 2
    # The SOC's files: one readable, one behind H1 (NFR-11: both fictitious).
    alerts = read_file("alertes_siem.log")
    assert "FICTIF" in alerts and "CRITIQUE" in alerts and "adm.leroy" in alerts
    assert "confidentiel/comptes_privilegies.txt" in read_file(".")
    assert (
        "adm.leroy" in soc.prompts[1] and "confidentiel/comptes_privilegies.txt" in soc.prompts[1]
    )


def test_soc_scenario_logs_the_read_and_blocks_the_confidential_file():
    outputs = [
        call("read_file", path="alertes_siem.log"),
        "Alerte critique : adm.leroy ajouté aux admins du domaine.",
        call("read_file", path="confidentiel/comptes_privilegies.txt"),
        "La lecture a été bloquée par le harnais.",
    ]
    _, session = hooks_session(outputs)
    session.launch_scenario("soc")
    session.join()
    first, second = session._scenarios.scenarios["soc"].prompts

    allowed = _run(session, first)
    blocked = _run(session, second)

    assert allowed["tool_ended"][0]["status"] == "ok"
    assert ("h1", "before_tool", "allow") in decisions(allowed)
    assert ("h1", "before_tool", "block") in decisions(blocked)
    assert "tool_started" not in blocked  # the harness said no before any execution
    audit = "\n".join(audit_lines())
    assert "alertes_siem.log" in audit and "bloqué par H1" in audit
    assert "adm.nguyen" not in str(blocked)  # the file's content never reaches the context
    session.close()


# ---------- AD-9: every scenario within the default window ----------


def _wait_mcp(mark: int, timeout: float = 30) -> None:
    """Until every server contacted since `mark` answered (the public ones fail at once)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = get_journal().events_since(mark)
        started = [e.payload["server"] for e in events if e.kind == "mcp_connect_started"]
        ended = [e.payload["server"] for e in events if e.kind == "mcp_connect_ended"]
        if all(s in ended for s in started):
            return
        time.sleep(0.05)
    raise AssertionError(f"serveurs MCP sans réponse : {started} / {ended}")


def test_every_scenario_fits_the_default_window_with_its_first_prompt(index, loop, web):  # noqa: F811
    """Counted as the cloud estimate does (4 characters per token), with the reasoning
    reserve, the RAG excerpts at their declared maximum, the real local MCP server; the
    public servers are unreachable here (their tools: to measure on the target PC)."""
    server = web(McpWeb([]))
    server.offline = True
    place_model()
    values = config._deep_merge(
        config.load_config().values, {"rag": rag_values(index), "memory": {"load_margin_mb": 1}}
    )
    cfg = config.Config(values=values)
    entry = cfg.cloud_model("mistral")  # reasoning on demand, 4 096-token window
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    session = AppSession(
        cfg, cloud_factory=Provider(GROQ_TEXT).factory, embedder_factory=Embedders()
    )
    session.boot_cloud(entry).result()
    session.attach_loop(loop)
    content = session._scenarios
    measured = {}

    for scenario_id in [i for m in content.program for i in m.scenarios] + content.transverse:
        scenario = content.scenarios[scenario_id]
        mark = get_journal().last_seq()
        session.launch_scenario(scenario_id)
        session.join()
        _wait_mcp(mark)
        session.join()
        session._emit_preview()
        preview = [
            e.payload for e in get_journal().events_since(mark) if e.kind == "context_preview"
        ]
        ctx = preview[-1]
        prompt = -(-len(scenario.prompts[0]) // CHARS_PER_TOKEN)
        measured[scenario_id] = (ctx["used"], prompt, ctx["usable"])
        assert ctx["window"] == 4096, scenario_id
        assert ctx["reserve"] == (1536 if "reasoning" in scenario.bricks else 512), scenario_id
        assert not ctx["overflow"] and ctx["used"] + prompt <= ctx["usable"], (scenario_id, ctx)
        if "rag" in scenario.bricks:  # counted: the brick is available here
            assert any(s["kind"] == "rag_excerpt" for s in ctx["segments"]), scenario_id
        if "mcp" in scenario.bricks and "local" in (scenario.mcp_servers or ["local"]):
            assert any("local__" in s["text"] for s in ctx["segments"]), scenario_id
    print("\nAD-9, aperçu + premier prompt / utilisables :")
    for scenario_id, (used, prompt, usable) in measured.items():
        print(f"  {scenario_id:<14} {used + prompt:>5} / {usable}")
    session.close()


def test_business_mcp_servers_are_drawn_unavailable_with_their_reason_offline(loop, web):  # noqa: F811
    server = web(McpWeb([]))
    server.offline = True
    session = mcp_session(loop, ["Voilà."])  # a model that calls tools

    for scenario_id, server_id in (("iam", "mslearn"), ("sovereignty", "datagouv")):
        mark = get_journal().last_seq()
        session.launch_scenario(scenario_id)
        session.join()
        _wait_mcp(mark)
        session.join()
        drawn = node(session, f"mcp.{server_id}")
        assert drawn is not None and drawn["hosting"] == "network", scenario_id
        assert (drawn["contact"], drawn["available"]) == ("unavailable", False)
        assert "injoignable" in drawn["reason_fr"]
        assert _run(session, "Bonjour")["turn_ended"][0]["status"] == "completed"
    session.close()
