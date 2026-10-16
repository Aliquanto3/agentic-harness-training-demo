"""Story 1 of the V1.1 vague 2 (CAP-2, CAP-3): the workshop's tool calls enforce the rule
of `wavestack.mcp.policy` (defaults from `mcp-tools.md`) and feed the security journal."""

from __future__ import annotations

import time

import pytest
from test_mcp import enable, loop, mcp_session  # noqa: F401
from test_mcp_lab import connect, lab_call, lab_events, one, wait_idle
from test_tools import call
from test_turn import _run

from wavestack.trace.journal import get_journal


def test_a_default_tool_is_allowed_and_journalled(loop):  # noqa: F811
    session = mcp_session(loop)
    connect(session)
    _, ended = lab_call(session, "local", "define_term", term="harnais")
    assert ended["status"] == "ok"
    entries = session.security_journal_entries()
    assert entries[-1]["decision"] == "allow"
    assert entries[-1]["name"] == "local__define_term"
    session.close()


def test_a_denied_tool_is_never_called_the_connection_stays_open(loop):  # noqa: F811
    session = mcp_session(loop)
    connect(session)
    session.set_mcp_tool_rule("local__define_term", "deny")

    messages, ended = lab_call(session, "local", "define_term", term="harnais")

    assert messages == []  # never sent on the wire
    assert ended["status"] == "error"
    assert ended["error_kind"] == "policy_denied"
    assert "politique de sécurité" in ended["error_text"]
    assert ended["connection"] == "open"
    assert session.security_journal_denied_count() == 1
    session.close()


def test_a_default_rule_change_back_forgets_the_override(loop):  # noqa: F811
    session = mcp_session(loop)
    connect(session)
    session.set_mcp_tool_rule("local__define_term", "deny")
    session.set_mcp_tool_rule("local__define_term", "allow")  # back to mcp-tools.md's default

    _, ended = lab_call(session, "local", "define_term", term="harnais")

    assert ended["status"] == "ok"
    session.close()


def test_an_unknown_rule_is_refused(loop):  # noqa: F811
    session = mcp_session(loop)
    try:
        with pytest.raises(ValueError):
            session.set_mcp_tool_rule("local__define_term", "nope")
    finally:
        session.close()


def test_ask_waits_for_a_decision_then_allows(loop):  # noqa: F811
    session = mcp_session(loop)
    connect(session)
    session.set_mcp_tool_rule("local__define_term", "ask")
    mark = get_journal().last_seq()

    session.mcp_lab_call("local", "define_term", {"term": "harnais"})
    request_id = _wait_for_request(mark)

    session.answer_mcp_authorization(request_id, "allow_once")
    wait_idle(session)

    events = lab_events(mark)
    ended = one(events, "mcp_lab_call_ended")
    assert ended["status"] == "ok"
    requested = one(events, "mcp_lab_authorization_requested")
    assert requested["risk"] == "low"
    resolved = one(events, "mcp_lab_authorization_resolved")
    assert resolved["decision"] == "allow_once"
    decisions = [e["decision"] for e in session.security_journal_entries()]
    assert decisions[-1] == "allow_once"
    session.close()


def test_ask_waits_for_a_decision_then_denies(loop):  # noqa: F811
    session = mcp_session(loop)
    connect(session)
    session.set_mcp_tool_rule("local__define_term", "ask")
    mark = get_journal().last_seq()

    session.mcp_lab_call("local", "define_term", {"term": "harnais"})
    request_id = _wait_for_request(mark)

    session.answer_mcp_authorization(request_id, "deny")
    wait_idle(session)

    events = lab_events(mark)
    ended = one(events, "mcp_lab_call_ended")
    assert ended["status"] == "error" and ended["error_kind"] == "policy_denied"
    assert "refus" in ended["error_text"].lower()
    assert session.security_journal_denied_count() == 1
    session.close()


def _wait_for_request(mark: int, timeout: float = 10) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = lab_events(mark)
        requested = [e.payload for e in events if e.kind == "mcp_lab_authorization_requested"]
        if requested:
            return requested[0]["request_id"]
        time.sleep(0.02)
    raise AssertionError("no authorization request within the timeout")


def test_ask_unanswered_is_refused_after_the_delay(loop, monkeypatch):  # noqa: F811
    from wavestack.session import app_session

    monkeypatch.setattr(app_session, "MCP_ASK_TIMEOUT_S", 0.3)
    session = mcp_session(loop)
    connect(session)
    session.set_mcp_tool_rule("local__define_term", "ask")
    mark = get_journal().last_seq()

    messages, ended = lab_call(session, "local", "define_term", term="harnais")

    assert messages == []  # never sent: the tab was closed, nobody answered
    assert ended["error_kind"] == "policy_denied", ended
    assert ended["connection"] == "open"
    assert one(lab_events(mark), "mcp_lab_authorization_resolved")["decision"] == "timeout"
    assert session.security_journal_entries()[-1]["decision"] == "deny"
    assert session.mcp_lab_state()["tool_rules"] == {"local__define_term": "ask"}
    session.close()


@pytest.mark.parametrize("rule", ["deny", "ask"])
def test_the_conversation_enforces_the_rule_too(loop, rule):  # noqa: F811
    """The brick's tool calls (a normal turn), not only the workshop's: `ask` refuses there,
    no « Autoriser une fois » being reachable from the conversation."""
    session = mcp_session(loop, [call("local__define_term", term="MCP"), "Voilà."])
    session.set_mcp_server("datagouv", False)
    enable(session)
    session.set_mcp_tool_rule("local__define_term", rule)

    events = _run(session, "Que veut dire MCP ?")

    (ended,) = events["tool_ended"]
    assert ended["status"] == "error" and "politique de sécurité" in ended["error_text"]
    assert "Model Context Protocol" not in (ended["result"] or "")  # never executed
    entry = session.security_journal_entries()[-1]
    assert (entry["name"], entry["decision"]) == ("local__define_term", "deny")
    session.close()


def test_the_conversation_journals_an_allowed_call(loop):  # noqa: F811
    session = mcp_session(loop, [call("local__define_term", term="MCP"), "Voilà."])
    session.set_mcp_server("datagouv", False)
    enable(session)

    events = _run(session, "Que veut dire MCP ?")

    assert events["tool_ended"][0]["status"] == "ok"
    assert session.security_journal_entries()[-1]["decision"] == "allow"
    session.close()
