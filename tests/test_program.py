"""Story 21: the programme in FR-38's order, cumulative modules (CAP-40), every scenario
within the default window (AD-9), and the business scenarios (FR-40, CAP-42).

The checks follow structural rules, not a list of scenario ids: a scenario added to
`content/scenarios.yaml` by the rules of its header needs no change here (FR-40).
"""

from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

import pytest
from fake_engine import FakeEngine, booted_session
from pydantic import SecretStr
from test_cloud import GROQ_TEXT, SENTINEL, Provider
from test_hooks import audit_lines, decisions, hooks_session
from test_mcp import McpWeb, loop, mcp_session, node, web  # noqa: F401 - fixtures
from test_rag import Embedders, index, place_model, rag_values  # noqa: F401 - fixture
from test_tools import call
from test_turn import _run

from wavestack import config, scenarios
from wavestack.net import guard
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
# The exceptions written at the top of content/scenarios.yaml (AD-9).
NEVER_CARRIED = {"reasoning"}
LEFT_OFF = {"mcp_full": {"rag"}}
# Variants of a module's first scenario (a sub-option): the same bricks, but for
# `mcp_lazy`, which lights the RAG again (the room the lazy loading frees).
VARIANTS = {"network_tools": "native_tools", "rag_rerank": "rag", "mcp_lazy": "mcp_full"}
LAUNCH_HOOKS = {"h1", "h2", "h3"}  # `hooks` absent: the launch values (story 8)
# Lot B (B3): without `WAVESTACK_TEST_GGUF`, the test session estimates 2 characters per
# token, calibrated on the target PC (`mcp_full`: 3 204 tokens by Qwen3.5's tokenizer, 1 530
# at 4 characters per token); with it, the GGUF's tokenizer counts the preview's segments.
CHARS_PER_TOKEN = 2
SAFETY = 1.1  # AD-9: room for the template and what the estimate still misses
# Lot B (N3): the scenarios whose first prompt calls a public MCP server or a network tool,
# which must leave room for its first result, bounded to `[tools] result_max_tokens`.
# `data_flows` as its description says: the MCP brick, local and data.gouv.fr.
FIRST_RESULT_ROOM = {"network_tools", "data_flows", "iam", "sovereignty"}
# `mcp_full` and `mcp_lazy`: their first prompt (« Que veut dire MCP ? ») calls the local
# server's `define_term`, whose real answer is measured in the test (227 characters, 114
# tokens at 2 characters per token) and must fit too.
LOCAL_FIRST = {"mcp_full", "mcp_lazy"}
LOCAL_FIRST_CALL = ("local__define_term", {"term": "MCP"})
LOCAL_ANSWER_MAX = 200  # the measure above, with margin: a longer answer revisits the room
BY_HAND = {"data_flows": {"bricks": ["mcp"], "mcp_servers": ["local", "datagouv"]}}
FIXTURES = Path(__file__).parent / "fixtures" / "mcp_tools"


def _content() -> scenarios.ScenariosContent:
    session = booted_session(FakeEngine())  # no asyncio loop: no MCP server is contacted
    content = session._scenarios
    session.close()
    return content


def _business(content: scenarios.ScenariosContent) -> list[str]:
    return [i for i in content.transverse if content.scenarios[i].title_fr.startswith("Métier ")]


def test_programme_follows_fr38_then_the_hosting_and_business_scenarios():
    content = _content()
    module_ids = [i for m in content.program for i in m.scenarios]

    assert all(30 <= m.duration_min <= 60 for m in content.program)
    introduced: list[str] = []
    for scenario_id in module_ids:
        for brick in content.scenarios[scenario_id].bricks:
            if brick not in introduced:
                introduced.append(brick)
    assert introduced == FR38
    # RAG simple then reranking, MCP full documentation then lazy loading, in one module.
    for module in content.program:
        ids = module.scenarios
        reranked = [i for i in ids if content.scenarios[i].rag_rerank]
        lazy = [
            i for i in ids if "mcp" in content.scenarios[i].bricks and content.scenarios[i].mcp_lazy
        ]
        if reranked and "rag" in introduced_in(content, module):
            assert ids.index(reranked[0]) > 0 and not content.scenarios[ids[0]].rag_rerank
        if lazy and "mcp" in introduced_in(content, module):
            assert not content.scenarios[ids[0]].mcp_lazy and ids.index(lazy[0]) > 0
    # The hosting scenario first, then at least three business ones (FR-40).
    business = _business(content)
    assert content.transverse[0] == "data_flows" and len(business) >= 3
    assert content.transverse[1:] == business
    assert not set(module_ids) & set(content.transverse)


def introduced_in(content: scenarios.ScenariosContent, module: scenarios.Module) -> set[str]:
    before = set()
    for m in content.program[: content.program.index(module)]:
        for i in m.scenarios:
            before |= set(content.scenarios[i].bricks)
    now = set().union(*(set(content.scenarios[i].bricks) for i in module.scenarios))
    return now - before


def test_first_scenario_of_each_module_has_the_previous_modules_bricks():
    content = _content()
    before: set[str] = set()
    hooks_before: set[str] = set()
    for i, module in enumerate(content.program):
        first_id = module.scenarios[0]
        first = content.scenarios[first_id]
        expected = before - NEVER_CARRIED - LEFT_OFF.get(first_id, set())
        assert expected <= set(first.bricks), (first_id, expected - set(first.bricks))
        if "hooks" in first.bricks:  # the hooks shown before stay active
            assert hooks_before <= set(first.hooks or LAUNCH_HOOKS), first_id
        if "mcp" in before and "mcp" in first.bricks:  # lazy loading, to keep room
            assert first.mcp_lazy, first_id
        if i > 0:  # the instructions say which brick stays off
            assert "raisonnement" in first.description_fr, first_id
        if "rag" in LEFT_OFF.get(first_id, set()):
            assert "RAG" in first.description_fr, first_id
        # A module started directly starts from the demonstration memory.
        assert first.restore_memory == ("global_memory" in first.bricks), first_id
        for scenario_id in module.scenarios:
            scenario = content.scenarios[scenario_id]
            before |= set(scenario.bricks)
            if "hooks" in scenario.bricks:
                hooks_before |= set(scenario.hooks or LAUNCH_HOOKS)


def test_reasoning_stays_off_after_module_1_and_variants_keep_their_bricks():
    content = _content()
    first_module = set(content.program[0].scenarios)
    for scenario_id, scenario in content.scenarios.items():
        if scenario_id not in first_module:
            assert "reasoning" not in scenario.bricks, scenario_id
        # Only a module's start (or the memory's own scenario) restores the memory.
        starts = {m.scenarios[0] for m in content.program} | {"global_memory"}
        assert not scenario.restore_memory or scenario_id in starts, scenario_id
        assert not scenario.expects_overflow, scenario_id  # AD-9: none today (story 10b)
    for variant_id, first_id in VARIANTS.items():
        variant, first = content.scenarios[variant_id], content.scenarios[first_id]
        extra = LEFT_OFF.get(first_id, set())
        assert set(variant.bricks) == set(first.bricks) | extra, variant_id
        assert variant.mcp_servers == first.mcp_servers and variant.hooks == first.hooks


def test_business_scenarios_fix_their_bricks_and_hooks():
    content = _content()
    soc, iam, sovereignty = (content.scenarios[i] for i in ("soc", "iam", "sovereignty"))

    assert soc.bricks == ["short_memory", "system_prompt", "tools", "hooks"]
    assert soc.tools == ["read_file"] and soc.hooks == ["h1", "h2"]
    assert iam.bricks == ["short_memory", "system_prompt", "mcp"]
    assert iam.mcp_servers == ["mslearn"] and not iam.mcp_lazy  # AD-9: full documentation
    # Sovereignty: two public servers, two jurisdictions, in lazy loading (AD-9).
    assert set(sovereignty.mcp_servers) == {"mslearn", "datagouv"} and sovereignty.mcp_lazy
    for scenario_id in _business(content):
        scenario = content.scenarios[scenario_id]
        assert len(scenario.prompts) >= 2, scenario_id
        assert "minutes" in scenario.description_fr, scenario_id  # its length
        assert "À retenir" in scenario.description_fr, scenario_id  # the key message
    # The SOC's files: fictitious (NFR-11); the second prompt names no file.
    alerts = read_file("alertes_siem.log")
    assert "FICTIF" in alerts and "UTC" in alerts and "adm.leroy" in alerts
    events = [line for line in alerts.splitlines() if line and not line.startswith("#")]
    assert f"# {len(events)} événements" in alerts
    assert "Début de la fenêtre de maintenance" in alerts and "Fin de la fenêtre" in alerts
    assert "confidentiel/comptes_privilegies.txt" in read_file(".")
    assert "confidentiel/" not in soc.prompts[1] and "fichiers disponibles" in soc.prompts[1]
    assert "Alertes SIEM (SOC)" in soc.description_fr
    assert "Comptes à privilèges (SOC, confidentiel)" in soc.description_fr


def test_soc_presets_force_the_two_files():
    from wavestack.tools.registry import load_tools_content

    presets = {p.label_fr: p.args for p in load_tools_content().tools["read_file"].presets}
    assert presets["Alertes SIEM (SOC)"] == {"path": "alertes_siem.log"}
    assert presets["Comptes à privilèges (SOC, confidentiel)"] == {
        "path": "confidentiel/comptes_privilegies.txt"
    }


def test_soc_scenario_logs_the_reads_and_blocks_the_privileged_accounts():
    outputs = [
        call("read_file", path="alertes_siem.log"),
        "Incident : compromission probable du compte adm.leroy.",
        call("read_file", path="."),
        call("read_file", path="confidentiel/comptes_privilegies.txt"),
        "La lecture a été bloquée par le harnais : j'escalade.",
    ]
    _, session = hooks_session(outputs)
    session.launch_scenario("soc")
    session.join()
    first, second = session._scenarios.scenarios["soc"].prompts

    allowed = _run(session, first)
    blocked = _run(session, second)

    assert allowed["tool_ended"][0]["status"] == "ok"
    assert ("h1", "before_tool", "allow") in decisions(allowed)
    assert ("h1", "before_tool", "allow") in decisions(blocked)  # the listing
    assert ("h1", "before_tool", "block") in decisions(blocked)
    assert [e["tool"] for e in blocked["tool_started"]] == ["read_file"]  # "." only
    audit = "\n".join(audit_lines())
    assert "alertes_siem.log" in audit and "bloqué par H1" in audit
    assert "adm.nguyen" not in str(blocked)  # the file's content never reaches the context
    session.close()


def test_a_module_start_restores_the_demonstration_memory():
    session = booted_session(FakeEngine())
    session.launch_scenario("global_memory")
    session.join()
    demo = [e.text for e in session._memory]
    session.edit_memory("delete", session._memory[0].id)
    session.join()

    session.launch_scenario("network_tools")  # a module's second scenario: untouched
    session.join()
    assert len(session._memory) == len(demo) - 1
    session.launch_scenario("native_tools")  # a module's first: restored
    session.join()
    assert [e.text for e in session._memory] == demo
    session.close()


# ---------- AD-9: every scenario within the default window ----------


def _public_tools(server_id: str) -> tuple[list[dict], str]:
    """The snapshot `scripts/snapshot_mcp.py` wrote, else the plausible fixture."""
    snapshot = config.content_dir() / "mcp_snapshots" / f"{server_id}.json"
    path, source = (
        (snapshot, "instantané")
        if snapshot.exists()
        else (
            FIXTURES / f"{server_id}.json",
            "fixture plausible, à régénérer par scripts/snapshot_mcp.py sur le PC cible",
        )
    )
    return json.loads(path.read_text(encoding="utf-8"))["tools"], source


class PublicServers:
    """data.gouv.fr and Microsoft Learn, answered in process, by host."""

    def __init__(self) -> None:
        self.sources = {}
        self.servers = {}
        for server_id, host in (
            ("datagouv", "mcp.data.gouv.fr"),
            ("mslearn", "learn.microsoft.com"),
        ):
            tools, self.sources[server_id] = _public_tools(server_id)
            self.servers[host] = McpWeb(tools)

    async def __call__(self, request):  # noqa: ANN001, ANN204
        return await self.servers[request.url.host](request)


def _wait_mcp(mark: int, timeout: float = 30) -> None:
    """Until every server contacted since `mark` answered."""
    started: list[str] = []
    ended: list[str] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = get_journal().events_since(mark)
        started = [e.payload["server"] for e in events if e.kind == "mcp_connect_started"]
        ended = [e.payload["server"] for e in events if e.kind == "mcp_connect_ended"]
        if all(s in ended for s in started):
            return
        time.sleep(0.05)
    raise AssertionError(f"serveurs MCP sans réponse : {started} / {ended}")


def _gguf_tokenizer():  # noqa: ANN202 - `VocabTokenizer`, imported only when used
    """The GGUF's tokenizer when `WAVESTACK_TEST_GGUF` points to one, else `None`."""
    path = os.environ.get("WAVESTACK_TEST_GGUF")
    if not path or not Path(path).is_file():
        return None
    from wavestack.models.engine import VocabTokenizer

    return VocabTokenizer(path)


def _verdict(
    scenario: scenarios.Scenario, used: int, ctx: dict, prompt: int, room: int = 0
) -> str | None:
    """Why the preview (`used` tokens) does not suit the scenario, or `None`: it must fit
    with the safety factor, its first prompt (`prompt` tokens) and `room` for a first tool
    result, or overflow when the scenario says so (`expects_overflow`, AD-9)."""
    if scenario.expects_overflow:
        return None if ctx["overflow"] or used + prompt > ctx["usable"] else "tient"
    if ctx["overflow"] or used * SAFETY + prompt + room > ctx["usable"]:
        return f"déborde : {used} × {SAFETY} + {prompt} + {room} > {ctx['usable']}"
    return None


def test_verdict_honours_expects_overflow_the_safety_factor_and_the_room():
    fits = {"usable": 3584, "overflow": False}
    full = {"usable": 3584, "overflow": True}
    plain = scenarios.Scenario(title_fr="t", description_fr="d", prompts=["x" * 40])
    over = plain.model_copy(update={"expects_overflow": True})
    assert _verdict(plain, 1000, fits, 20) is None and _verdict(plain, 3584, full, 20)
    assert _verdict(over, 3584, full, 20) is None and _verdict(over, 1000, fits, 20) == "tient"
    assert _verdict(plain, 3250, fits, 20)  # × 1,1
    assert _verdict(plain, 2000, fits, 20, room=1200) is None
    assert _verdict(plain, 2300, fits, 20, room=1200)  # no room for a bounded result


def test_every_scenario_fits_the_default_window_with_its_first_prompt(index, loop, web):  # noqa: F811
    """Counted by the GGUF's tokenizer (`WAVESTACK_TEST_GGUF`), else as the cloud estimate
    does at 2 characters per token, with a safety factor, the reasoning reserve, the RAG
    excerpts at their declared maximum, the demonstration memory, the real local MCP server
    and the public servers' tools (snapshot or fixture); and, when the first prompt calls a
    public server or a network tool, the room of its first bounded result (lot B)."""
    public = PublicServers()
    web(public)
    place_model()
    values = config._deep_merge(
        config.load_config().values,
        {
            "rag": rag_values(index),
            "memory": {"load_margin_mb": 1},
            "cloud": {"chars_per_token": CHARS_PER_TOKEN},
        },
    )
    cfg = config.Config(values=values)
    entry = cfg.cloud_model("mistral")  # reasoning on demand, 4 096-token window
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    provider = Provider(GROQ_TEXT)
    session = AppSession(cfg, cloud_factory=provider.factory, embedder_factory=Embedders())
    session.boot_cloud(entry).result()
    session.attach_loop(loop)
    content = session._scenarios
    tokenizer = _gguf_tokenizer()

    def count(text: str) -> int:
        return (
            -(-len(text) // CHARS_PER_TOKEN) if tokenizer is None else len(tokenizer.tokenize(text))
        )

    measured = {}
    local_answer = ""
    try:
        for scenario_id in [i for m in content.program for i in m.scenarios] + content.transverse:
            scenario = content.scenarios[scenario_id]
            mark = get_journal().last_seq()
            session.launch_scenario(scenario_id)
            session.join()
            _wait_mcp(mark)
            session.join()
            by_hand = BY_HAND.get(scenario_id, {})
            for brick in by_hand.get("bricks", []):
                session.set_brick(brick, True)
            for server_id in by_hand.get("mcp_servers", []):
                session.set_mcp_server(server_id, True)
            session.join()
            _wait_mcp(mark)
            session.join()
            session._emit_preview()
            events = get_journal().events_since(mark)
            ctx = [e.payload for e in events if e.kind == "context_preview"][-1]
            failed = [e.payload for e in events if e.kind == "mcp_connect_ended"]
            assert all(p["status"] == "ok" for p in failed), (scenario_id, failed)
            if scenario_id in LOCAL_FIRST and not local_answer:  # the real local server
                local_answer = session._registry.get(LOCAL_FIRST_CALL[0]).run(**LOCAL_FIRST_CALL[1])
            if tokenizer is not None:  # the GGUF's count decides, the overflow with it
                used = count("".join(s["text"] for s in ctx["segments"]))
                ctx = ctx | {"overflow": used > ctx["usable"]}
            else:
                used = ctx["used"]
            room = cfg.tool_result_max_tokens if scenario_id in FIRST_RESULT_ROOM else 0
            if scenario_id in LOCAL_FIRST:
                room = count(local_answer)
            measured[scenario_id] = (used, ctx["usable"], room)
            assert ctx["window"] == 4096, scenario_id
            assert ctx["reserve"] == (1536 if "reasoning" in scenario.bricks else 512), scenario_id
            verdict = _verdict(scenario, used, ctx, count(scenario.prompts[0]), room)
            assert verdict is None, (scenario_id, verdict)
            segments = " ".join(s["text"] for s in ctx["segments"])
            if "rag" in scenario.bricks:  # counted: the brick is available here
                assert any(s["kind"] == "rag_excerpt" for s in ctx["segments"]), scenario_id
            mcp_servers = scenario.mcp_servers or by_hand.get("mcp_servers") or ["local"]
            if "mcp" in scenario.bricks and not scenario.mcp_lazy:
                for server_id in mcp_servers:
                    assert f"{server_id}__" in segments, (scenario_id, server_id)
            if scenario_id in BY_HAND:  # the servers turned on by hand are in the context
                assert all(f"{s}__" in segments for s in mcp_servers), (scenario_id, segments)
        # Lot B (B3): the full documentation, 3 204 tokens on the target PC, is not underrated.
        assert measured["mcp_full"][0] > 2800, measured["mcp_full"]
        assert local_answer.startswith("MCP : ") and count(local_answer) < LOCAL_ANSWER_MAX
        counted = "tokenizer du GGUF" if tokenizer is not None else f"{CHARS_PER_TOKEN} car./token"
        print(f"\nAD-9, aperçu (sans le prompt, {counted}) / utilisables, marge, place réservée :")
        for scenario_id, (used, usable, room) in measured.items():
            print(
                f"  {scenario_id:<14} {used:>5} / {usable}  marge {usable - used:>5}  {room or ''}"
            )
        for server_id, source in public.sources.items():
            print(f"  outils de {server_id} : {source}")
    finally:
        if tokenizer is not None:
            tokenizer.close()
        session.close()


def test_business_mcp_servers_are_drawn_unavailable_with_their_reason_offline(loop, web):  # noqa: F811
    server = web(McpWeb([]))
    server.offline = True
    session = mcp_session(loop, ["Voilà."])  # a model that calls tools

    for scenario_id in ("iam", "sovereignty"):
        mark = get_journal().last_seq()
        session.launch_scenario(scenario_id)
        session.join()
        _wait_mcp(mark)
        session.join()
        for server_id in session._scenarios.scenarios[scenario_id].mcp_servers:
            drawn = node(session, f"mcp.{server_id}")
            assert drawn is not None and drawn["hosting"] == "network", scenario_id
            assert (drawn["contact"], drawn["available"]) == ("unavailable", False)
            assert "injoignable" in drawn["reason_fr"]
        assert _run(session, "Bonjour")["turn_ended"][0]["status"] == "completed"
    session.close()


# ---------- scripts/snapshot_mcp.py ----------


@pytest.fixture
def snapshot_script(monkeypatch):
    """The script, loaded without widening this process's network guard."""
    monkeypatch.setattr(guard, "install", lambda *a, **k: None)
    path = config.repo_root() / "scripts" / "snapshot_mcp.py"
    spec = importlib.util.spec_from_file_location("snapshot_mcp", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_script_writes_each_public_servers_tools(snapshot_script, web, tmp_path, capsys):  # noqa: F811
    web(PublicServers())

    assert snapshot_script.main(["--out", str(tmp_path)]) == 0

    for server_id in ("datagouv", "mslearn"):
        written = json.loads((tmp_path / f"{server_id}.json").read_text(encoding="utf-8"))
        expected, _ = _public_tools(server_id)
        assert written["server"] == server_id and written["url"].startswith("https://")
        assert [t["name"] for t in written["tools"]] == [t["name"] for t in expected]
        assert written["tools"][0]["inputSchema"]["type"] == "object"
    assert "outils enregistrés" in capsys.readouterr().out


def test_snapshot_script_reports_an_unreachable_server(snapshot_script, web, tmp_path, capsys):  # noqa: F811
    server = web(McpWeb([]))
    server.offline = True

    assert snapshot_script.main(["--server", "mslearn", "--out", str(tmp_path)]) == 1

    assert "injoignable" in capsys.readouterr().err and not list(tmp_path.iterdir())
