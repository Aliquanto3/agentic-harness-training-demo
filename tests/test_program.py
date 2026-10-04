"""Story 21: the programme in FR-38's order, cumulative modules (CAP-40), every scenario
within the default window (AD-9), and the business scenarios (FR-40, CAP-42).

The checks follow structural rules, not a list of scenario ids: a scenario added to
`content/scenarios.yaml` by the rules of its header needs no change here (FR-40).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
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
# The exceptions written at the top of content/scenarios.yaml (AD-9): shown in their own
# module, never carried into the next ones (story 27: the RAG joins the reasoning, D5).
NEVER_CARRIED = {"reasoning", "rag"}
# The phrases the first scenario of each later module uses to say so (one of them).
NEVER_CARRIED_FR = {
    "reasoning": ("sauf le raisonnement", "sans le raisonnement"),
    "rag": ("sauf le raisonnement et le RAG", "sans le raisonnement ni le RAG"),
}
# Variants of a module's first scenario (a sub-option): the same bricks.
VARIANTS = {"network_tools": "native_tools", "rag_rerank": "rag", "mcp_lazy": "mcp_full"}
LAUNCH_HOOKS = {"h1", "h2", "h3"}  # `hooks` absent: the launch values (story 8)
# Lot B (B3): without `WAVESTACK_TEST_GGUF`, the test session estimates 2 characters per
# token, calibrated on the target PC (`mcp_full`: 3 204 tokens by Qwen3.5's tokenizer, 1 530
# at 4 characters per token). Lot J: with it, the session boots that GGUF in local mode and
# the gauge is exact, template included (counting the chat rendering with the local tokenizer
# gave 2 572 for `mcp_full`, 20 % under the local gauge).
CHARS_PER_TOKEN = 2
SAFETY = 1.1  # AD-9: room for the template and what the estimate still misses
EXACT = 1.0  # lot J: the local gauge counts every token, template included
# Lot B (N3): the scenarios whose first prompt calls a public MCP server or a network tool,
# which must leave room for its first result, bounded to `[tools] result_max_tokens`.
# `data_flows`: the MCP brick, local and data.gouv.fr, active at launch (story 27).
FIRST_RESULT_ROOM = {"network_tools", "data_flows", "iam", "sovereignty"}
# `mcp_full` and `mcp_lazy`: their first prompt (« Que veut dire MCP ? … ») calls the local
# server's `define_term`, whose real answer is measured in the test (227 characters, 114
# tokens at 2 characters per token) and must fit too.
LOCAL_FIRST = {"mcp_full", "mcp_lazy"}
LOCAL_FIRST_CALL = ("local__define_term", {"term": "MCP"})
LOCAL_ANSWER_MAX = 200  # the measure above, with margin: a longer answer revisits the room
# Lot K (A5): every prompt, not the first only, after the scenario's previous exchanges, as
# the short memory keeps them all (D18 of 2026-10-01: the whole history, cumulated). Each
# exchange: its prompt, its tool result (at most the bound), its answer and the template's
# tags. The answers are counted at the size measured on the target PC (lot K,
# `resultats-lot-k-2026-09-29.md`, `subagent`: 470, 245, 223 and 213 tokens), not at the
# output reserve: at the reserve, `subagent` p4 overflowed by 9 tokens (1 326 + 2 267 >
# 3 584) whereas the real gauge read 2 997 / 3 584. The whole history is counted with the
# GGUF's tokenizer (`WAVESTACK_TEST_GGUF`, the exact gauge where the overflow was raised);
# the 2-character estimate already counts `subagent`'s context 40 % over (1 848 against
# 1 326 exact), so there only the previous exchange is added, its answer at the reserve as
# before (the worst case of one exchange, never weaker than the check it replaces). The
# scenarios whose instructions empty the conversation between their prompts are counted
# without history (« Vider la conversation » : two public search results, 1 200 tokens each
# at most, never fit together).
CLEARED_BETWEEN_PROMPTS = {"iam", "sovereignty"}
EXCHANGE_TEMPLATE = 40  # the tags of an exchange's four messages (user, call, result, answer)
# The first answer of a scenario, then each following one: the measures rounded up (470, then
# 245, 223 and 213 tokens).
MEASURED_ANSWERS = (500, 250)
_PUBLIC_SUBJECTS = ("data.gouv.fr", "Microsoft Learn")  # results that fill the bound
# The network tools' results are short: 11 public holidays, a Wikipedia summary (≈ 800
# characters); their first prompt keeps the bound's room (lot B), the next ones this.
_NETWORK_SUBJECTS = ("Wikipédia", "jours fériés")
NETWORK_TOOL_RESULT = 400
_FILE = re.compile(r"\b([\w/]+\.(?:txt|log|md))\b")
FIXTURES = Path(__file__).parent / "fixtures" / "mcp_tools"


def _content() -> scenarios.ScenariosContent:
    session = booted_session(FakeEngine())  # no asyncio loop: no MCP server is contacted
    content = session._scenarios
    session.close()
    return content


def _business(content: scenarios.ScenariosContent) -> list[str]:
    return [i for i in content.transverse if content.scenarios[i].title_text.startswith("Métier ")]


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
    for module in content.program:
        first_id = module.scenarios[0]
        first = content.scenarios[first_id]
        expected = before - NEVER_CARRIED
        assert expected <= set(first.bricks), (first_id, expected - set(first.bricks))
        if "hooks" in first.bricks:  # the hooks shown before stay active
            assert hooks_before <= set(first.hooks or LAUNCH_HOOKS), first_id
        if "mcp" in before and "mcp" in first.bricks:  # lazy loading, to keep room
            assert first.mcp_lazy, first_id
        for brick in NEVER_CARRIED & before:  # the instructions say which brick stays off
            said = [p for p in NEVER_CARRIED_FR[brick] if p in first.description_text]
            assert said, (first_id, brick, NEVER_CARRIED_FR[brick])
        # A module started directly starts from the demonstration memory.
        assert first.restore_memory == ("global_memory" in first.bricks), first_id
        for scenario_id in module.scenarios:
            scenario = content.scenarios[scenario_id]
            before |= set(scenario.bricks)
            if "hooks" in scenario.bricks:
                hooks_before |= set(scenario.hooks or LAUNCH_HOOKS)


def test_reasoning_and_rag_stay_in_their_module_and_variants_keep_their_bricks():
    content = _content()
    # No module start after the one that introduces them carries them (story 27, D5); the
    # later scenarios of a module, the transverse and business ones set their bricks freely.
    before: set[str] = set()
    for module in content.program:
        first_id = module.scenarios[0]
        carried = NEVER_CARRIED & before & set(content.scenarios[first_id].bricks)
        assert not carried, (first_id, carried)
        for scenario_id in module.scenarios:
            before |= set(content.scenarios[scenario_id].bricks)
    for scenario_id, scenario in content.scenarios.items():
        # Only a module's start (or the memory's own scenario) restores the memory.
        starts = {m.scenarios[0] for m in content.program} | {"global_memory"}
        assert not scenario.restore_memory or scenario_id in starts, scenario_id
        assert not scenario.expects_overflow, scenario_id  # AD-9: none today (story 10b)
    for variant_id, first_id in VARIANTS.items():
        variant, first = content.scenarios[variant_id], content.scenarios[first_id]
        assert set(variant.bricks) == set(first.bricks), variant_id
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
        assert "minutes" in scenario.description_text, scenario_id  # its length
        assert "À retenir" in scenario.description_text, scenario_id  # the key message
    # The SOC's files: fictitious (NFR-11); the second prompt names no file.
    alerts = read_file("alertes_siem.log")
    assert "FICTIF" in alerts and "UTC" in alerts and "adm.leroy" in alerts
    events = [line for line in alerts.splitlines() if line and not line.startswith("#")]
    assert f"# {len(events)} événements" in alerts
    assert "Début de la fenêtre de maintenance" in alerts and "Fin de la fenêtre" in alerts
    assert "confidentiel/comptes_privilegies.txt" in read_file(".")
    assert "confidentiel/" not in soc.prompts[1] and "fichiers disponibles" in soc.prompts[1]
    assert "Alertes SIEM (SOC)" in soc.description_text
    assert "Comptes à privilèges (SOC, confidentiel)" in soc.description_text


def test_data_flows_is_active_at_launch():
    """Story 27 (X1): the tools and the MCP brick, the local server and data.gouv.fr, in lazy
    loading, with nothing to turn on by hand."""
    data_flows = _content().scenarios["data_flows"]

    assert data_flows.bricks == ["short_memory", "system_prompt", "tools", "mcp"]
    assert data_flows.mcp_servers == ["local", "datagouv"] and data_flows.mcp_lazy
    assert "qualité de l'air" in data_flows.prompts[0] and "data.gouv.fr" in data_flows.prompts[0]
    assert (
        "Décochez puis" in data_flows.description_text
        and "indisponible" in data_flows.description_text
    )


def test_small_model_prompts_name_the_tool_or_skill_and_the_fallback():
    """Story 27: for a small model, the prompts name the tool or skill expected, and the
    instructions give the forced action to fall back on, with its exact labels."""
    from wavestack.skills import load_skills_content
    from wavestack.tools.registry import load_tools_content

    content = _content()
    scenario = content.scenarios
    # MCP, both modes: the same need, the glossary's tool asked for (`mcp_full`: < 120 chars).
    first = scenario["mcp_full"].prompts[0]
    assert first == scenario["mcp_lazy"].prompts[0] and len(first) < 120
    assert "veut dire MCP" in first and "local__define_term" in first
    assert "data.gouv.fr" in scenario["mcp_lazy"].prompts[1]
    assert "Charger la documentation" in scenario["mcp_lazy"].description_text
    # IAM and sovereignty: the prompts name tools the public servers really have.
    snapshots = {s: {t["name"] for t in _public_tools(s)[0]} for s in ("datagouv", "mslearn")}
    for scenario_id in ("iam", "sovereignty"):
        for prompt in scenario[scenario_id].prompts:
            named = re.findall(r"\b([a-z0-9]+)__([A-Za-z0-9_]+)\b", prompt)
            assert named, (scenario_id, prompt)
            for server_id, tool in named:
                assert server_id in scenario[scenario_id].mcp_servers, (scenario_id, server_id)
                assert server_id in snapshots, (
                    f"{scenario_id} : serveur {server_id} sans instantané"
                )
                assert tool in snapshots[server_id], (scenario_id, server_id, tool)
    # Lot K (A5): no « Charge la documentation » (the small model then stops after loading).
    assert not any("Charge la documentation" in p for p in scenario["sovereignty"].prompts)
    assert not any("Charge la documentation" in p for p in scenario["mcp_lazy"].prompts)
    assert all("deux liens Microsoft Learn" in p for p in scenario["iam"].prompts)
    # Lot K, suite (K2): within the 512 tokens of the output reserve, the links first.
    for prompt in scenario["iam"].prompts:
        assert "5 lignes au plus" in prompt, prompt
        assert prompt.index("deux liens") < prompt.index("l'explication"), prompt
    first_sovereignty = scenario["sovereignty"].prompts[0]
    assert "5 lignes au plus" in first_sovereignty
    assert "trois jeux au plus" in first_sovereignty
    assert "chacun avec son lien data.gouv.fr en premier" in first_sovereignty
    # Skills: the skill and the meta-tool named, « Déclencher le skill » on its label.
    skills = scenario["skills"]
    label = load_skills_content(["meeting_minutes"]).skills["meeting_minutes"].label_text
    assert "meeting_minutes" in skills.prompts[0] and "load_skill" in skills.prompts[0]
    assert "compte rendu" in skills.prompts[0]  # the fake provider's trigger (E2E)
    # Lot K (A7): the meeting of the prompt, never the demo file's notes.
    assert "à partir des éléments ci-dessous, sans lire de fichier" in skills.prompts[0]
    skill = load_skills_content(["meeting_minutes"]).skills["meeting_minutes"]
    assert "notes_reunion.txt" not in skill.description  # the catalog invites no reading
    assert "Seulement si le message ne donne aucune note" in skill.body
    assert "sans lire de fichier" in skill.body
    assert (
        "Déclencher le skill" in skills.description_text
        and f"« {label} »" in skills.description_text
    )
    # Compression: read_file named, and the preset to force it with.
    compression = scenario["compression"]
    presets = {p.label_text: p.args for p in load_tools_content().tools["read_file"].presets}
    assert presets["Journal de sauvegarde (compression)"] == {"path": "journal_serveur.log"}
    assert presets["Guide du harnais (prose, compression)"] == {"path": "guide_harnais.md"}
    for label in ("Journal de sauvegarde (compression)", "Guide du harnais (prose, compression)"):
        assert f"« {label} »" in compression.description_text, label
    assert "« Forcer l'appel » sur « Lecture de fichier »" in compression.description_text
    assert "read_file" in compression.prompts[0] and "journal_serveur.log" in compression.prompts[0]
    assert "extraits RAG" not in compression.description_text
    # SOC: the exact file name, then the refusal not to get round (D6).
    soc = scenario["soc"]
    assert "alertes_siem.log" in soc.prompts[0] and "nom exact" in soc.prompts[0]
    assert "ne la contourne pas" in soc.prompts[1] and "transmettre" in soc.prompts[1]
    # Lot K, suite (K2): the one to escalate to, named (the 2B wrote « au Démonstrateur »).
    assert "analyste" in soc.prompts[1] and "habilité" in soc.prompts[1]
    assert "3 lignes au plus" in soc.prompts[1]
    assert "confidentiel" not in soc.prompts[1]  # the fake provider's own trigger (E2E)
    assert (
        "analyste habilité" in soc.description_text and "concluez vous-même" in soc.description_text
    )
    assert "« Forcer l'appel » sur « Lecture de fichier »" in soc.description_text
    assert "en 8 lignes au plus" in soc.prompts[0]  # lot K: within the output reserve
    # Lot K (decision of 2026-09-29): the MCP tool's call forced, with its preset, then the
    # replay (the button's text: « Forcer l'appel · <tool> »).
    from wavestack.mcp.servers import load_mcp_content

    presets = {
        tool: {p.label_text: p.args for p in listed}
        for tool, listed in load_mcp_content().call_presets.items()
    }
    assert presets["local__define_term"] == {"MCP": {"term": "MCP"}}
    assert presets["datagouv__search_datasets"] == {"cybersécurité": {"query": "cybersécurité"}}
    for scenario_id, tool, preset in (
        ("mcp_full", "local__define_term", "MCP"),
        ("mcp_lazy", "local__define_term", "MCP"),
        ("iam", "mslearn__microsoft_docs_search", "MFA des administrateurs (IAM)"),
        ("iam", "mslearn__microsoft_docs_search", "PIM juste-à-temps (IAM)"),
        ("sovereignty", "datagouv__search_datasets", "cybersécurité"),
        (
            "sovereignty",
            "mslearn__microsoft_docs_search",
            "Journalisation des connexions admin (Souveraineté)",
        ),
    ):
        text = scenario[scenario_id].description_text
        assert f"« Forcer l'appel · {tool} »" in text, (scenario_id, tool)
        assert f"préréglage « {preset} »" in text and preset in presets[tool], (scenario_id, preset)
        assert "« Rejouer le dernier prompt »" in text, scenario_id
    # Sovereignty: the first prompt's fallback, then the clearing, then the second's.
    text = scenario["sovereignty"].description_text
    assert (
        text.index("« Forcer l'appel · datagouv__search_datasets »")
        < text.index("« Vider la conversation »")
        < text.index("« Forcer l'appel · mslearn__microsoft_docs_search »")
    )
    assert all("ne se force pas" not in s.description_text for s in scenario.values())
    # Lot K, suite (K3, decision of 2026-09-29): with the 2B, the fallback is the lesson. Both
    # instructions tell what one sees, why, and « Forcer l'appel » as the harness's proof.
    for scenario_id in ("mcp_lazy", "sovereignty"):
        text = scenario[scenario_id].description_text
        seen = ("Ce qu'on observe", "load_tool_doc", "répond de tête", "« j'ai cherché »")
        assert all(words in text for words in seen), scenario_id
        assert "Orchestration ne montre" in text, scenario_id
        assert (
            "Pourquoi : un petit modèle enchaîne mal deux appels et prend la documentation pour "
            "la réponse" in text
        ), scenario_id
        assert "C'est la démonstration" in text, scenario_id
        assert "le harnais garantit l'appel que le modèle ne fait pas" in text, scenario_id
        assert (
            text.index("Ce qu'on observe")
            < text.index("Pourquoi")
            < text.index("C'est la démonstration")
            < text.index("« Forcer l'appel · ")
        ), scenario_id
    # The local glossary runs on the loopback, never traced as an outbound request (AD-15):
    # « requête sortante » for the public servers of Souveraineté only.
    assert "ni requête sortante" in scenario["sovereignty"].description_text
    assert "aucun appel de local__define_term" in scenario["mcp_lazy"].description_text
    assert "requête sortante" not in scenario["mcp_lazy"].description_text
    # Two public search results do not fit together: the conversation emptied between them.
    for scenario_id in CLEARED_BETWEEN_PROMPTS:
        assert "« Vider la conversation »" in scenario[scenario_id].description_text, scenario_id


# The bound of the five-point summary, by language: one line a point, 80 words at most.
SUMMARY_BOUND = {
    "fr": ("cinq points d'une ligne", "80 mots au plus"),
    "en": ("five one-line points", "80 words at most"),
    "de": ("fünf einzeiligen Punkten", "höchstens 80 Wörtern"),
}


@pytest.mark.parametrize("lang", sorted(SUMMARY_BOUND))
def test_subagent_summary_is_bounded_in_every_language(lang):
    """Finition V1 (#23, #29): the five-point summary overflowed the 512-token output reserve,
    the 2B's final answer (recette of 2026-10-02, R12) and Sonnet 5's sub-agent (S6 of
    2026-10-03). Prompt 1 and the « Résumer le guide du harnais » preset both bound it."""
    from wavestack.subagent import load_subagent_content

    french = _content()
    fields = ("bricks", "tools", "mcp_servers", "skills", "hooks")
    known = {f: {i for s in french.scenarios.values() for i in getattr(s, f) or []} for f in fields}
    prompt = scenarios.load_scenarios(known, lang).scenarios["subagent"].prompts[0]
    preset = load_subagent_content(lang).presets[0].args["task"]
    for text in (prompt, preset):
        assert all(bound in text for bound in SUMMARY_BOUND[lang]), text


def test_call_presets_name_real_tools_and_their_arguments(loop):  # noqa: F811
    """Lot K: every tool of `call_presets` (content/mcp.yaml) is a tool of its server (the
    local server's own list, a public server's snapshot or fixture), and every argument of
    its presets a property of that tool's schema: a renamed argument would silently empty
    the preset (the session keeps only the declared parameters)."""
    from test_mcp import enable

    from wavestack.mcp.servers import load_mcp_content

    session = mcp_session(loop)
    enable(session)
    schemas = {
        name: (session._registry.get(name).schema or {}).get("properties", {})
        for name in session._mcp_tools("local")
    }
    session.close()
    for server_id in ("datagouv", "mslearn"):
        for tool in _public_tools(server_id)[0]:
            properties = tool.get("inputSchema", {}).get("properties", {})
            schemas[f"{server_id}__{tool['name']}"] = properties
    presets = load_mcp_content().call_presets
    assert presets
    for tool, listed in presets.items():
        assert tool in schemas, f"call_presets : outil inconnu {tool}"
        for preset in listed:
            unknown = sorted(set(preset.args) - set(schemas[tool]))
            assert preset.args and not unknown, (tool, preset.label_text, unknown)


def test_meta_tools_say_which_is_which():
    """Story 27 (H2): `load_tool_doc` loads no skill; `load_skill` loads a skill of the
    « Skills disponibles » list by its name, and is not an MCP tool."""
    from wavestack.mcp.servers import load_mcp_content
    from wavestack.skills import load_skills_content

    tool_doc = load_mcp_content().load_tool_doc.intro
    skills = load_skills_content([])
    assert "ne charge pas de skill" in tool_doc
    assert "Skills disponibles" in skills.load_skill.description
    assert "meeting_minutes" in skills.load_skill.description
    assert "pas un outil MCP" in skills.load_skill.description
    assert skills.catalog_intro.startswith("Skills disponibles.")
    assert "appelle l'outil load_skill" in skills.catalog_intro


def test_soc_presets_force_the_two_files():
    from wavestack.tools.registry import load_tools_content

    presets = {p.label_text: p.args for p in load_tools_content().tools["read_file"].presets}
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
    scenario: scenarios.Scenario,
    used: int,
    ctx: dict,
    prompt: int,
    room: int = 0,
    safety: float = SAFETY,
) -> str | None:
    """Why the preview (`used` tokens) does not suit the scenario, or `None`: it must fit
    with the safety factor, its first prompt (`prompt` tokens) and `room` for a first tool
    result, or overflow when the scenario says so (`expects_overflow`, AD-9)."""
    if scenario.expects_overflow:
        return None if ctx["overflow"] or used + prompt > ctx["usable"] else "tient"
    if ctx["overflow"] or used * safety + prompt + room > ctx["usable"]:
        return f"déborde : {used} × {safety} + {prompt} + {room} > {ctx['usable']}"
    return None


def test_verdict_honours_expects_overflow_the_safety_factor_and_the_room():
    fits = {"usable": 3584, "overflow": False}
    full = {"usable": 3584, "overflow": True}
    plain = scenarios.Scenario(title_text="t", description_text="d", prompts=["x" * 40])
    over = plain.model_copy(update={"expects_overflow": True})
    assert _verdict(plain, 1000, fits, 20) is None and _verdict(plain, 3584, full, 20)
    assert _verdict(over, 3584, full, 20) is None and _verdict(over, 1000, fits, 20) == "tient"
    assert _verdict(plain, 3250, fits, 20)  # × 1,1
    assert _verdict(plain, 2000, fits, 20, room=1200) is None
    assert _verdict(plain, 2300, fits, 20, room=1200)  # no room for a bounded result
    assert _verdict(plain, 3250, fits, 20, safety=EXACT) is None  # an exact count: no factor


def _result_room(
    scenario_id: str,
    scenario: scenarios.Scenario,
    position: int,
    reserve: int,
    bound: int,
    local_answer: str,
    count,  # noqa: ANN001 - the test's token count
) -> int:
    """Lot K: the room the tool result of prompt `position` takes, by what the prompt asks: the
    sub-agent's answer (at most the reserve), the local glossary's measured answer, a public
    server's result (bounded to `[tools] result_max_tokens`, lot B), a network tool's, a
    file `read_file` reads (whole; a confidential one is refused by H1, one the previous
    prompt read is answered from the history), else nothing."""
    prompt = scenario.prompts[position]
    if "subagent" in scenario.bricks and "Délègue" in prompt:
        return reserve
    if LOCAL_FIRST_CALL[0] in prompt:
        return count(local_answer)
    public = re.search(r"\b(?:datagouv|mslearn)__\w+", prompt)
    if public or any(s in prompt for s in _PUBLIC_SUBJECTS):
        return bound
    if position == 0 and scenario_id in FIRST_RESULT_ROOM:
        return bound
    if any(s in prompt for s in _NETWORK_SUBJECTS):
        return NETWORK_TOOL_RESULT
    named = _FILE.search(prompt)
    readable = scenario.tools is None or "read_file" in scenario.tools
    if named and "tools" in scenario.bricks and readable:
        again = position > 0 and named.group(1) in scenario.prompts[position - 1]  # in the history
        if not again and not named.group(1).startswith("confidentiel/"):
            return count(read_file(named.group(1)))
    return 0


def test_every_scenario_fits_the_default_window_with_every_prompt(index, loop, web):  # noqa: F811
    """With `WAVESTACK_TEST_GGUF`, that GGUF booted in local mode: the exact local gauge
    (lot J). Else as the cloud estimate does at 2 characters per token, with a safety factor.
    Both with the reasoning reserve, the RAG excerpts at their declared maximum, the
    demonstration memory, the real local MCP server and the public servers' tools (snapshot
    or fixture); and, when the first prompt calls a public server or a network tool, the room
    of its first bounded result (lot B).

    Lot K (A5): every prompt of the scenario, in order, after its previous exchanges when the
    short memory keeps them (D18: each its prompt, its result, an answer of the measured size
    `MEASURED_ANSWERS`, the template's tags; all of them with the GGUF's tokenizer; with the
    2-character estimate, the last one only, its answer at the reserve), except where the
    instructions empty the conversation between the prompts (`CLEARED_BETWEEN_PROMPTS`)."""
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
    tokenizer = _gguf_tokenizer()
    if tokenizer is not None:  # the local rendering, its template and its gauge (lot J)
        session = AppSession(cfg, embedder_factory=Embedders())
        assert session.boot(os.environ["WAVESTACK_TEST_GGUF"]).result() == "ok"
        safety = EXACT
    else:
        entry = cfg.cloud_model("mistral")  # reasoning on demand, 4 096-token window
        config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
        provider = Provider(GROQ_TEXT)
        session = AppSession(cfg, cloud_factory=provider.factory, embedder_factory=Embedders())
        session.boot_cloud(entry).result()
        safety = SAFETY
    session.attach_loop(loop)
    content = session._scenarios

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
            session.launch_scenario(scenario_id)  # nothing turned on by hand (story 27)
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
            used = ctx["used"]  # exact in local mode, the 2-character estimate otherwise
            assert ctx["window"] == 4096, scenario_id
            reserve = ctx["reserve"]
            assert reserve == (1536 if "reasoning" in scenario.bricks else 512), scenario_id
            keeps = "short_memory" in scenario.bricks and scenario_id not in CLEARED_BETWEEN_PROMPTS
            history = 0
            for n in range(len(scenario.prompts)):
                room = _result_room(
                    scenario_id,
                    scenario,
                    n,
                    reserve,
                    cfg.tool_result_max_tokens,
                    local_answer,
                    count,
                )
                prompt = count(scenario.prompts[n])
                measured[(scenario_id, n + 1)] = (used, ctx["usable"], history, room)
                verdict = _verdict(scenario, used, ctx, history + prompt, room, safety)
                assert verdict is None, (scenario_id, f"prompt {n + 1}", verdict)
                if keeps:  # this exchange joins the history the next prompt reads; its
                    # result at most the bound (`compression`: Headroom on for the second
                    # prompt), its answer of the measured size (D18)
                    kept = min(room, cfg.tool_result_max_tokens)
                    if tokenizer is not None:  # the whole history, answers as measured
                        answer = min(reserve, MEASURED_ANSWERS[min(n, len(MEASURED_ANSWERS) - 1)])
                        history += prompt + kept + answer + EXCHANGE_TEMPLATE
                    else:  # the previous exchange, its answer at the reserve (the worst case)
                        history = prompt + kept + reserve + EXCHANGE_TEMPLATE
            segments = " ".join(s["text"] for s in ctx["segments"])
            if "rag" in scenario.bricks:  # counted: the brick is available here
                assert any(s["kind"] == "rag_excerpt" for s in ctx["segments"]), scenario_id
            # Every server's tools are counted: their documentation, or in lazy loading their
            # line in `load_tool_doc`'s description.
            mcp_servers = scenario.mcp_servers or ["local"]
            if "mcp" in scenario.bricks:
                for server_id in mcp_servers:
                    assert f"{server_id}__" in segments, (scenario_id, server_id)
        # Lot B (B3): the full documentation, 3 204 tokens on the target PC, is not underrated.
        assert measured[("mcp_full", 1)][0] > 2800, measured[("mcp_full", 1)]
        assert local_answer.startswith("MCP : ") and count(local_answer) < LOCAL_ANSWER_MAX
        counted = (
            "jauge locale du GGUF" if tokenizer is not None else f"{CHARS_PER_TOKEN} car./token"
        )
        print(
            f"\nAD-9, aperçu (sans le prompt, {counted}) / utilisables, marge ; historique "
            "simulé et place du résultat, par prompt :"
        )
        for (scenario_id, n), (used, usable, history, room) in measured.items():
            print(
                f"  {scenario_id:<14} p{n}  {used:>5} / {usable}  marge {usable - used:>5}"
                f"  historique {history:>5}  résultat {room:>5}"
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

    for scenario_id in ("iam", "sovereignty", "data_flows"):
        mark = get_journal().last_seq()
        session.launch_scenario(scenario_id)
        session.join()
        _wait_mcp(mark)
        session.join()
        servers = session._scenarios.scenarios[scenario_id].mcp_servers
        public = [s for s in servers if session._mcp_servers[s].network]
        assert public, scenario_id
        for server_id in public:  # the public servers only: the local one stays reachable
            drawn = node(session, f"mcp.{server_id}")
            assert drawn is not None and drawn["hosting"] == "network", scenario_id
            assert (drawn["contact"], drawn["available"]) == ("unavailable", False)
            assert "injoignable" in drawn["reason_text"]
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
