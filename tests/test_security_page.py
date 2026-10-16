"""Story 10 of the V1.1 vague 2 (CAP-3, CAP-8, CAP-9): the page Sécurité."""

from __future__ import annotations

import pytest
from test_mcp import loop, mcp_session  # noqa: F401
from test_mcp_lab import _client

from wavestack.tools.registry import ToolError


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
    assert state["questions"]["can_write"]["count"] == 2

    assert state["questions"]["authorized_by_you"]["count"] == 1
    assert state["questions"]["blocked"]["count"] == 2  # 1 tool deny + 1 guardrail blocked
    assert state["questions"]["not_covered"]["count"] == len(state["limits"]) == 12

    # Changing a rule changes the matrix live, without touching this method.
    session._mcp_policy.set_rule("github__merge_pull_request", "allow")
    state2 = session.security_state()
    row = next(r for r in state2["risk_matrix"] if r["id"] == "github_write")
    assert row["rule"] == "allow"
    session.close()


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
