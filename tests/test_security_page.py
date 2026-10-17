"""Story 10 of the V1.1 vague 2 (CAP-3, CAP-8, CAP-9): the page Sécurité."""

from __future__ import annotations

import csv
import io

import httpx2
import pytest
from test_mcp import McpWeb, loop, mcp_session, web  # noqa: F401
from test_mcp_github import GITHUB_TOOLS, connected
from test_mcp_lab import _client, lab_call

from wavestack.mcp.security_log import SecurityJournal
from wavestack.tools.registry import ToolError
from wavestack.trace.catalog import SecurityEventPayload
from wavestack.trace.journal import get_journal


def test_security_state_computes_the_question_cards_from_policy_and_journal(loop):  # noqa: F811
    """Nothing frozen: the figures come from the live policy and this session's journal."""
    session = mcp_session(loop)
    session._security_journal.record("mcp_tool", "local__create_path", "allow_once", "autorisé")
    session._security_journal.record("mcp_tool", "github__merge_pull_request", "deny", "refusé")
    session._security_journal.record("guardrail", "guardrails.pii", "blocked", "bloqué")

    state = session.security_state()

    # The 7-row matrix, read live from `ToolPolicy` (never a duplicated number).
    assert len(state["risk_matrix"]) == 7
    write_rows = [r for r in state["risk_matrix"] if r["write"]]
    assert {r["id"] for r in write_rows} == {"create_path", "github_write"}
    # The write tools themselves: create_path (ask), merge and create PR (deny).
    can_write = state["questions"]["can_write"]
    assert can_write["count"] == 3
    assert "1 sur demande" in can_write["detail_text"]
    assert "2 refusés" in can_write["detail_text"]
    # Every local tool, `define_term` included, each with its own rule (never an empty detail).
    tool_rules = state["controls"]["tool_rules"]
    assert tool_rules["count"] == 5
    assert tool_rules["ask_count"] == 2
    assert tool_rules["deny_count"] == 0
    assert tool_rules["allow_count"] == 3
    assert len(tool_rules["tools"]) == 5
    assert all(tool["label_text"] and tool["rule"] for tool in tool_rules["tools"])

    assert state["questions"]["authorized_by_you"]["count"] == 1
    assert state["questions"]["blocked"]["count"] == 2  # 1 tool deny + 1 guardrail blocked
    assert state["questions"]["not_covered"]["count"] == len(state["limits"]) == 12

    # Changing a rule changes the matrix live, without touching this method; a row whose
    # tools no longer share one rule says so (never one tool standing for the others).
    session._mcp_policy.set_rule("github__merge_pull_request", "allow")
    session._mcp_policy.set_rule("mslearn__search", "deny")
    state2 = session.security_state()
    rows = {r["id"]: r for r in state2["risk_matrix"]}
    assert rows["github_write"]["rule"] == "mixed"
    assert rows["network"]["rule"] == "mixed"
    assert "1 autorisé" in state2["questions"]["can_write"]["detail_text"]
    for tool in ("github__merge_pull_request", "github__create_pull_request", "mslearn__search"):
        session._mcp_policy.set_rule(tool, "allow")
    rows = {r["id"]: r for r in session.security_state()["risk_matrix"]}
    assert rows["github_write"]["rule"] == "mixed"  # any other GitHub write stays denied
    assert rows["network"]["rule"] == "allow"
    session.close()


def test_question_cards_keep_the_session_count_past_the_journal_window(loop):  # noqa: F811
    """The journal keeps 500 entries; the cards and the bar count the whole session."""
    session = mcp_session(loop)
    for _ in range(600):
        session._security_journal.record("mcp_tool", "github__merge_pull_request", "deny", "x")

    state = session.security_state()

    assert len(session.security_journal_entries()) == 500
    assert state["questions"]["blocked"]["count"] == 600
    assert state["counts"]["denied_count"] == 600 and state["counts"]["total"] == 600
    assert session.security_journal_entries()[-1]["n"] == 600
    session.close()


def test_security_event_carries_the_entry_rank_and_the_session_counters(loop):  # noqa: F811
    session = mcp_session(loop)
    session._security_journal.record("mcp_tool", "local__create_path", "allow_once", "ok")
    mark = get_journal().last_seq()
    with pytest.raises(ToolError):
        session._mcp_conversation_policy("github__merge_pull_request")

    event = next(e for e in get_journal().events_since(mark) if e.kind == "security_event")
    SecurityEventPayload.model_validate(event.payload)
    assert event.payload["n"] == 2
    assert event.payload["allow_once_count"] == 1
    assert event.payload["tool_denied_count"] == 1
    assert event.payload["label_text"] == "GitHub : fusion de PR"
    session.close()


def test_csv_cells_never_read_as_a_formula():
    journal = SecurityJournal()
    journal.record("mcp_tool", "=HYPERLINK(1)", "deny", "-2+3")
    rows = list(csv.reader(io.StringIO(journal.to_csv())))
    assert rows[1][2] == "'=HYPERLINK(1)" and rows[1][4] == "'-2+3"


def test_security_label_text_is_readable_not_technical(loop):  # noqa: F811
    session = mcp_session(loop)
    assert (
        session._security_label_text("mcp_tool", "local__create_path") == "Créer fichier ou dossier"
    )
    assert (
        session._security_label_text("guardrail", "guardrails.pii")
        == "Garde-fou Données personnelles"
    )
    # An unmapped tool keeps its raw name rather than failing.
    assert (
        session._security_label_text("mcp_tool", "github__unknown_tool") == "github__unknown_tool"
    )
    session.close()


def test_security_journal_entries_carry_a_label_text(loop):  # noqa: F811
    session = mcp_session(loop)
    session._security_journal.record("mcp_tool", "local__create_path", "deny", "refusé")
    client = _client(session)

    body = client.get("/api/security_journal").json()

    assert body["entries"][-1]["label_text"] == "Créer fichier ou dossier"
    session.close()


def test_github_write_refusal_names_what_did_not_reach_github(loop):  # noqa: F811
    """Flux 1, étape 7 (EXPERIENCE.md) : la ligne dépliée de la fusion refusée dit
    « Envoyé à GitHub : non », pas seulement « l'outil n'a pas été exécuté »."""
    session = mcp_session(loop)
    with pytest.raises(ToolError):
        session._mcp_conversation_policy("github__merge_pull_request")
    entries = session.security_journal_entries()
    assert "Envoyé à GitHub : non" in entries[-1]["reason_text"]
    session.close()


def test_api_security_controls_carry_enough_detail_to_render(loop):  # noqa: F811
    """Dépli vide corrigé (rapport vague 2) : chaque contrôle a de quoi afficher un détail,
    jamais un corps vide. « Autorisations des outils » doit lister chaque outil et sa règle
    effective, pas seulement des compteurs."""
    session = mcp_session(loop)
    controls = session.security_state()["controls"]

    tr = controls["tool_rules"]
    assert tr["tools"], "tool_rules must list each local tool and its rule, not just counts"
    assert all(tool["label_text"] and tool["rule"] for tool in tr["tools"])

    for g in controls["guardrails"]:
        assert g["install_text"] or g.get("mode")  # a reason to install, or the active mode

    assert all(h["label_text"] for h in controls["hooks"])

    gh = controls["github"]
    assert gh["scope"] and gh["server"]
    session.close()


def test_api_security_http(loop):  # noqa: F811
    session = mcp_session(loop)
    client = _client(session)
    response = client.get("/api/security")
    assert response.status_code == 200
    body = response.json()
    assert "risk_matrix" in body and "controls" in body and "limits" in body
    assert len(body["controls"]["hooks"]) >= 1
    assert isinstance(body["controls"]["network_whitelist"], list)
    session.close()


class _Github403(McpWeb):
    """GitHub answering `tools/call` with a 403 (an account without the right)."""

    async def __call__(self, request):  # noqa: ANN001, ANN204
        if request.method == "POST" and b'"tools/call"' in request.content:
            self.sent.append(request)
            return httpx2.Response(403, json={"message": "Resource not accessible"})
        return await super().__call__(request)


def test_a_github_403_is_journalled_as_refused_by_github_and_counted_blocked(loop, web):  # noqa: F811
    """mcp-tools.md, third refusal level: the call left (« Envoyé à GitHub : oui »), GitHub
    refused it; journalled and counted in « Qu'est-ce qui a été bloqué ? »."""
    web(_Github403(GITHUB_TOOLS))
    session = mcp_session(loop)
    connected(session)

    _, ended = lab_call(session, "github", "list_secret_scanning_alerts")

    assert ended["status"] == "error", ended
    last = session.security_journal_entries()[-1]
    assert last["decision"] == "deny"
    assert "403" in last["reason_text"] and "Envoyé à GitHub : oui" in last["reason_text"]
    assert session.security_state()["questions"]["blocked"]["count"] == 1
    session.close()
