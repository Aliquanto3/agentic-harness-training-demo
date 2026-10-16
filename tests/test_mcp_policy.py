"""Story 1 of the V1.1 vague 2 (CAP-2, CAP-3): the tool policy and the security journal,
on their own, before `AppSession` wires them into the workshop's calls."""

from __future__ import annotations

import pytest

from wavestack.mcp.policy import ToolPolicy
from wavestack.mcp.security_log import SecurityJournal


def test_defaults_match_mcp_tools_md():
    policy = ToolPolicy()
    assert policy.risk_of("local__list_terms") == "low"
    assert policy.rule_of("local__list_terms") == "allow"
    assert policy.risk_of("local__define_term") == "low"
    assert policy.rule_of("local__define_term") == "allow"


def test_an_unlisted_tool_defaults_to_low_allow():
    policy = ToolPolicy()
    assert (policy.risk_of("datagouv__search"), policy.rule_of("datagouv__search")) == (
        "low",
        "allow",
    )


# ---------- story 3 of the V1.1 vague 2 (CAP-4): GitHub's read/write defaults ----------


def test_github_read_tools_default_to_mid_allow():
    policy = ToolPolicy()
    for tool in (
        "github__list_secret_scanning_alerts",
        "github__list_dependabot_alerts",
        "github__get_file_contents",
        "github__list_issues",
    ):
        assert (policy.risk_of(tool), policy.rule_of(tool)) == ("mid", "allow")


def test_github_write_tools_default_to_high_deny():
    policy = ToolPolicy()
    for tool in ("github__merge_pull_request", "github__create_pull_request"):
        assert (policy.risk_of(tool), policy.rule_of(tool)) == ("high", "deny")


def test_an_unknown_github_tool_is_presumed_to_write():
    """The orchestrator's prudent default: a GitHub tool this table does not name is refused,
    not silently allowed like an ordinary unlisted tool."""
    policy = ToolPolicy()
    assert (policy.risk_of("github__some_new_tool"), policy.rule_of("github__some_new_tool")) == (
        "high",
        "deny",
    )


def test_set_rule_overrides_then_back_to_default_is_still_reported():
    policy = ToolPolicy()
    policy.set_rule("local__define_term", "deny")
    assert policy.rule_of("local__define_term") == "deny"
    policy.set_rule("local__define_term", "allow")  # the default, still told to a reloaded page
    assert policy.rule_of("local__define_term") == "allow"
    assert policy.rules() == {"local__define_term": "allow"}


def test_set_rule_refuses_an_unknown_value():
    policy = ToolPolicy()
    with pytest.raises(ValueError):
        policy.set_rule("local__define_term", "nope")


def test_journal_records_and_counts_denials():
    journal = SecurityJournal()
    journal.record("mcp_tool", "local__list_terms", "allow", "autorisé par la politique")
    journal.record("mcp_tool", "local__define_term", "deny", "refusé par la politique")
    journal.record("guardrail", "toxicity", "blocked", "bloqué par le garde-fou")
    entries = journal.entries()
    assert [e.decision for e in entries] == ["allow", "deny", "blocked"]
    assert journal.denied_count() == 2


def test_journal_csv_has_a_header_and_no_secret_beyond_what_was_recorded():
    journal = SecurityJournal()
    journal.record("mcp_tool", "local__define_term", "deny", "refusé par la politique")
    text = journal.to_csv()
    lines = text.splitlines()
    assert lines[0] == "horodatage,source,nom,decision,raison"
    assert "local__define_term" in lines[1]
    assert "deny" in lines[1]


def test_journal_keeps_only_the_last_entries():
    journal = SecurityJournal()
    for i in range(600):
        journal.record("mcp_tool", f"local__t{i}", "allow", "")
    entries = journal.entries()
    assert len(entries) == 500
    assert entries[0].name == "local__t100"
    assert entries[-1].name == "local__t599"
