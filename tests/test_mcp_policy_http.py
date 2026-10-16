"""Story 1 of the V1.1 vague 2 (CAP-2, CAP-3): the HTTP intentions and the security
journal's routes."""

from __future__ import annotations

from test_mcp import loop, mcp_session  # noqa: F401
from test_mcp_lab import HEADERS, _client


def test_mcp_tool_rule_http(loop):  # noqa: F811
    session = mcp_session(loop)
    client = _client(session)

    ok = client.post(
        "/api/intentions/mcp_tool_rule",
        json={"tool": "local__define_term", "rule": "deny"},
        headers=HEADERS,
    )
    bad = client.post(
        "/api/intentions/mcp_tool_rule",
        json={"tool": "local__define_term", "rule": "nope"},
        headers=HEADERS,
    )

    assert ok.status_code == 200
    assert bad.status_code == 422
    assert session._mcp_policy.rule_of("local__define_term") == "deny"
    session.close()


def test_mcp_tool_authorize_http_unknown_request_is_a_no_op(loop):  # noqa: F811
    session = mcp_session(loop)
    client = _client(session)

    response = client.post(
        "/api/intentions/mcp_tool_authorize",
        json={"request_id": "nope", "decision": "allow_once"},
        headers=HEADERS,
    )

    assert response.status_code == 200  # the first answer wins; a stale one is ignored
    session.close()


def test_mcp_tool_authorize_http_invalid_decision(loop):  # noqa: F811
    session = mcp_session(loop)
    client = _client(session)

    response = client.post(
        "/api/intentions/mcp_tool_authorize",
        json={"request_id": "nope", "decision": "nope"},
        headers=HEADERS,
    )

    assert response.status_code == 422
    session.close()


def test_security_journal_http_json_and_csv(loop):  # noqa: F811
    session = mcp_session(loop)
    session._security_journal.record("mcp_tool", "local__define_term", "deny", "refusé")
    client = _client(session)

    body = client.get("/api/security_journal").json()
    assert body["denied_count"] == 1
    assert body["entries"][-1]["name"] == "local__define_term"

    csv = client.get("/api/security_journal.csv")
    assert csv.status_code == 200
    assert csv.headers["content-type"].startswith("text/csv")
    assert "local__define_term" in csv.text
    session.close()
