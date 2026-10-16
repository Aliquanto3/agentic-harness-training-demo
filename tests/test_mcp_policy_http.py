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

    garbage = client.post(  # not an exposed name: never stored in the session
        "/api/intentions/mcp_tool_rule",
        json={"tool": "x" * 5000, "rule": "deny"},
        headers=HEADERS,
    )

    assert ok.status_code == 200
    assert bad.status_code == 422
    assert garbage.status_code == 422
    assert session._mcp_policy.rules() == {"local__define_term": "deny"}
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


# ---------- story 3 (CAP-4): GitHub's device flow, the HTTP routes ----------


def test_github_state_starts_disconnected(loop):  # noqa: F811
    session = mcp_session(loop)
    client = _client(session)

    body = client.get("/api/mcp_lab").json()

    assert body["github"] == {"status": "disconnected"}
    session.close()


def test_github_connect_http_starts_the_device_flow(loop):  # noqa: F811
    session = mcp_session(loop)
    session._github.start = lambda: {"user_code": "ABCD-1234", "verification_uri": "u"}
    client = _client(session)

    response = client.post("/api/intentions/github_connect", json={}, headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == {"user_code": "ABCD-1234", "verification_uri": "u"}
    session.close()


def test_github_connect_http_refuses_on_a_network_failure(loop):  # noqa: F811
    import httpx

    session = mcp_session(loop)

    def failing():
        raise httpx.ConnectError("no route")

    session._github.start = failing
    client = _client(session)

    response = client.post("/api/intentions/github_connect", json={}, headers=HEADERS)

    assert response.status_code == 409
    session.close()


def test_github_disconnect_http_clears_the_token(loop):  # noqa: F811
    import time

    from wavestack.mcp import github_auth

    session = mcp_session(loop)
    session._github._token = github_auth.GithubToken(
        access_token="gho_x",
        refresh_token="r",
        obtained_at=time.time(),
        expires_in=28800,
        refresh_expires_in=15897600,
    )
    client = _client(session)

    response = client.post("/api/intentions/github_disconnect", json={}, headers=HEADERS)

    assert response.status_code == 200
    assert client.get("/api/mcp_lab").json()["github"] == {"status": "disconnected"}
    session.close()
