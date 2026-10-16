"""Story 3 of the V1.1 vague 2 (CAP-4): GitHub's remote MCP server, reached with the
device-flow token through the Atelier MCP; no real network (`web`, test_mcp.py, answers in
process behind the real async client factory)."""

from __future__ import annotations

import time

from test_mcp import McpWeb, loop, mcp_session, web  # noqa: F401
from test_mcp_lab import connect, lab_call

from wavestack.mcp import github_auth
from wavestack.trace.journal import get_journal

GITHUB_TOOLS = [
    {
        "name": "list_secret_scanning_alerts",
        "description": "List secret scanning alerts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "merge_pull_request",
        "description": "Merge a pull request.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "some_new_tool",
        "description": "A tool mcp-tools.md does not name yet.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def connected(session, server="github"):  # noqa: ANN001
    """Seeds a usable token in memory (no device flow, no disk write), then connects."""
    session._github._token = github_auth.GithubToken(
        access_token="gho_test",
        refresh_token="refresh_test",
        obtained_at=time.time(),
        expires_in=28800,
        refresh_expires_in=15897600,
    )
    return connect(session, server)


def test_the_connection_carries_the_bearer_token_and_toolsets(loop, web):  # noqa: F811
    server = web(McpWeb(GITHUB_TOOLS))
    session = mcp_session(loop)
    connected(session)

    sent = server.sent[0]  # the `initialize` request
    assert sent.headers["authorization"] == "Bearer gho_test"
    assert sent.headers["x-mcp-toolsets"] == github_auth.TOOLSETS
    session.close()


def test_the_token_is_never_traced_in_clear(loop, web):  # noqa: F811
    web(McpWeb(GITHUB_TOOLS))
    session = mcp_session(loop)
    mark = get_journal().last_seq()
    connected(session)

    outbound = [e for e in get_journal().events_since(mark) if e.kind == "outbound_request"]
    assert outbound  # at least the handshake
    for event in outbound:
        for header in event.payload["headers"]:
            if header["name"].lower() == "authorization":
                assert header["masked"] is True
                assert "gho_test" not in header["value"]
    session.close()


def test_a_read_tool_is_allowed_by_default(loop, web):  # noqa: F811
    web(McpWeb(GITHUB_TOOLS))
    session = mcp_session(loop)
    connected(session)

    _, ended = lab_call(session, "github", "list_secret_scanning_alerts")

    assert ended["status"] == "ok"
    assert session.security_journal_entries()[-1]["decision"] == "allow"
    session.close()


def test_a_write_tool_is_denied_by_the_policy_never_sent_to_github(loop, web):  # noqa: F811
    server = web(McpWeb(GITHUB_TOOLS))
    session = mcp_session(loop)
    connected(session)
    calls_before = len(server.sent)

    _, ended = lab_call(session, "github", "merge_pull_request")

    assert ended["status"] == "error" and ended["error_kind"] == "policy_denied"
    assert len(server.sent) == calls_before  # the policy refused before anything was sent
    assert session.security_journal_entries()[-1]["decision"] == "deny"
    session.close()


def test_an_unknown_github_tool_is_denied_by_the_prudent_default(loop, web):  # noqa: F811
    web(McpWeb(GITHUB_TOOLS))
    session = mcp_session(loop)
    connected(session)

    _, ended = lab_call(session, "github", "some_new_tool")

    assert ended["status"] == "error" and ended["error_kind"] == "policy_denied"
    session.close()


def test_without_a_token_the_connection_is_refused_without_any_network_call(loop, web):  # noqa: F811
    server = web(McpWeb(GITHUB_TOOLS))
    session = mcp_session(loop)

    _, _, ended = connect(session, "github")

    assert ended["status"] == "error"
    assert "GitHub" in ended["error_text"]
    assert server.sent == []  # not even attempted
    session.close()


def _expire_access(session) -> None:  # noqa: ANN001
    from dataclasses import replace

    a = session._github
    with a._lock:
        a._token = replace(a._token, obtained_at=time.time() - a._token.expires_in - 1)


def test_an_open_connection_sends_the_refreshed_bearer_after_8_hours(loop, web, tmp_path):  # noqa: F811
    import httpx
    from test_mcp_github_auth import FakeGithub

    server = web(McpWeb(GITHUB_TOOLS))
    session = mcp_session(loop)
    session._github = github_auth.GithubAuth(
        transport=httpx.MockTransport(FakeGithub()), path=tmp_path / "github_token.json"
    )
    connected(session)
    _expire_access(session)  # the same open connection, 8 h later
    mark = len(server.sent)

    _, ended = lab_call(session, "github", "list_secret_scanning_alerts")

    assert ended["status"] == "ok"
    assert {r.headers["authorization"] for r in server.sent[mark:]} == {"Bearer gho_refreshed"}
    session.close()


def test_flow_4_a_call_after_the_refresh_is_refused_says_so_and_sends_nothing(
    loop,  # noqa: F811
    web,  # noqa: F811
    tmp_path,
):
    import httpx

    def refuse(request):  # noqa: ANN001, ANN202
        return httpx.Response(200, json={"error": "bad_refresh_token"})

    server = web(McpWeb(GITHUB_TOOLS))
    session = mcp_session(loop)
    session._github = github_auth.GithubAuth(
        transport=httpx.MockTransport(refuse), path=tmp_path / "github_token.json"
    )
    connected(session)
    _expire_access(session)  # the next day: GitHub refuses the refresh token
    mark = len(server.sent)

    _, ended = lab_call(session, "github", "list_secret_scanning_alerts")

    assert ended["status"] == "error"
    assert "GitHub" in ended["error_text"]
    # no `tools/call` left for GitHub (only the DELETE that closes the stale session)
    assert [r.method for r in server.sent[mark:]] in ([], ["DELETE"])
    assert session.mcp_lab_state()["github"] == {"status": "expired"}
    session.close()
