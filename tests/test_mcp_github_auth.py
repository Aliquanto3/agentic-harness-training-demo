"""Story 3 (V1.1 vague 2, CAP-4): GitHub's device flow and token, no real network (a fake
transport answers in process)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from urllib.parse import parse_qsl

import httpx
import httpx2

from wavestack.mcp import github_auth
from wavestack.net.factory import MASKED, _masked_body


class FakeGithub:
    """Answers the device/token endpoints; `errors` queues one `error` field per poll."""

    def __init__(self) -> None:
        self.errors: list[str | None] = []
        self.refresh_calls: list[str] = []
        self.token_requests: list[dict[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = dict(httpx.QueryParams(request.content.decode()))
        if request.url.path == "/login/device/code":
            return httpx.Response(
                200,
                json={
                    "device_code": "dev123",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://github.com/login/device",
                    "expires_in": 900,
                    "interval": 5,
                },
            )
        assert request.url.path == "/login/oauth/access_token"
        self.token_requests.append(body)
        if body.get("grant_type") == "refresh_token":
            self.refresh_calls.append(body["refresh_token"])
            return httpx.Response(
                200,
                json={
                    "access_token": "gho_refreshed",
                    "refresh_token": "refresh2",
                    "expires_in": 28800,
                    "refresh_token_expires_in": 15897600,
                },
            )
        error = self.errors.pop(0) if self.errors else None
        if error:
            return httpx.Response(200, json={"error": error})
        return httpx.Response(
            200,
            json={
                "access_token": "gho_token",
                "refresh_token": "refresh1",
                "expires_in": 28800,
                "refresh_token_expires_in": 15897600,
            },
        )


def auth(server: FakeGithub, tmp_path) -> github_auth.GithubAuth:
    return github_auth.GithubAuth(
        transport=httpx.MockTransport(server), path=tmp_path / "github_token.json"
    )


def test_device_flow_then_poll_obtains_the_token(tmp_path):
    server = FakeGithub()
    a = auth(server, tmp_path)

    started = a.start()
    assert started == {
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
    }
    assert a.state() == {
        "status": "waiting",
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
    }
    assert a.poll() is True
    state = a.state()
    assert state["status"] == "connected" and state["expires_in_s"] <= 28800
    assert a.headers() == {
        "Authorization": "Bearer gho_token",
        "X-MCP-Toolsets": github_auth.TOOLSETS,
    }


def test_authorization_pending_keeps_waiting(tmp_path):
    server = FakeGithub()
    server.errors = ["authorization_pending"]
    a = auth(server, tmp_path)
    a.start()

    assert a.poll() is False
    assert a.state()["status"] == "waiting"
    a._device["next_poll"] = 0.0  # don't wait the real interval out in a test
    assert a.poll() is True  # the queued error was consumed once
    assert a.state()["status"] == "connected"


def test_expired_token_error_clears_the_device_flow(tmp_path):
    server = FakeGithub()
    server.errors = ["expired_token"]
    a = auth(server, tmp_path)
    a.start()

    assert a.poll() is False
    assert a.state() == {"status": "error", "error_key": "mcp.github.error.expired_token"}
    assert a.headers() is None


def test_the_token_survives_a_restart_from_the_same_file(tmp_path):
    server = FakeGithub()
    a = auth(server, tmp_path)
    a.start()
    a.poll()

    restarted = auth(server, tmp_path)
    assert restarted.state()["status"] == "connected"
    assert restarted.headers()["Authorization"] == "Bearer gho_token"


def test_disconnect_clears_memory_and_the_file(tmp_path):
    server = FakeGithub()
    a = auth(server, tmp_path)
    a.start()
    a.poll()

    a.disconnect()

    assert a.state() == {"status": "disconnected"}
    assert auth(server, tmp_path).state() == {"status": "disconnected"}


def test_an_expired_access_token_is_refreshed_without_a_client_secret(tmp_path):
    server = FakeGithub()
    a = auth(server, tmp_path)
    a.start()
    a.poll()
    # Force expiry without waiting 8h; the refresh token's own (6-month) window stays open.
    import time
    from dataclasses import replace

    with a._lock:
        a._token = replace(a._token, obtained_at=time.time() - a._token.expires_in - 1)

    headers = a.headers()

    assert server.refresh_calls == ["refresh1"]  # no client_secret field was ever sent
    assert all("client_secret" not in r for r in server.token_requests)
    assert headers["Authorization"] == "Bearer gho_refreshed"


def test_a_refresh_token_past_its_own_expiry_turns_the_state_expired(tmp_path):
    server = FakeGithub()
    a = auth(server, tmp_path)
    a.start()
    a.poll()
    import time
    from dataclasses import replace

    with a._lock:
        a._token = replace(
            a._token, obtained_at=time.time() - 10, expires_in=1, refresh_expires_in=1
        )

    assert a.headers() is None
    assert a.state() == {"status": "expired"}  # flow 4: « Se reconnecter », not « non connecté »


def test_a_refresh_token_is_never_traced_in_clear():
    body = "client_id=Ov23li3Ovj8ZnyXMFUPQ&grant_type=refresh_token&refresh_token=super-secret"
    masked = _masked_body(body.encode(), "application/x-www-form-urlencoded")

    assert "super-secret" not in masked
    assert dict(parse_qsl(masked))["refresh_token"] == MASKED


def test_an_ordinary_body_is_left_alone():
    body = json.dumps({"jsonrpc": "2.0", "method": "tools/list"})

    assert _masked_body(body.encode(), "application/json") == body


def _expire_access(a: github_auth.GithubAuth) -> None:
    with a._lock:
        a._token = replace(a._token, obtained_at=time.time() - a._token.expires_in - 1)


def connected_auth(server: FakeGithub, tmp_path) -> github_auth.GithubAuth:
    a = auth(server, tmp_path)
    a.start()
    a.poll()
    return a


def proxy_page(request: httpx.Request) -> httpx.Response:
    """A corporate proxy or captive portal answering 200 with its own HTML page."""
    return httpx.Response(200, text="<html>Zscaler</html>")


def test_a_proxy_page_on_start_is_a_value_error_never_a_crash(tmp_path):
    a = github_auth.GithubAuth(transport=httpx.MockTransport(proxy_page), path=tmp_path / "t.json")

    try:
        a.start()
    except ValueError:
        pass
    else:
        raise AssertionError("a non-JSON answer must raise ValueError")
    assert a.state() == {"status": "disconnected"}


def test_a_proxy_page_while_polling_keeps_waiting(tmp_path):
    server = FakeGithub()
    a = auth(server, tmp_path)
    a.start()
    a._client._transport = httpx.MockTransport(proxy_page)

    assert a.poll() is False  # never raises: GET /api/mcp_lab stays a 200
    assert a.state()["status"] == "waiting"


def test_a_refused_refresh_turns_the_state_expired_then_disconnect_clears_it(tmp_path):
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "bad_refresh_token"})

    a = connected_auth(FakeGithub(), tmp_path)
    _expire_access(a)
    a._client._transport = httpx.MockTransport(refuse)

    assert a.access_token() is None
    assert a.state() == {"status": "expired"}
    assert not (tmp_path / "github_token.json").exists()
    a.disconnect()
    assert a.state() == {"status": "disconnected"}


def test_a_network_failure_on_refresh_keeps_the_token_and_retries_later(tmp_path):
    calls = []

    def proxy(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return proxy_page(request)

    a = connected_auth(FakeGithub(), tmp_path)
    _expire_access(a)
    a._client._transport = httpx.MockTransport(proxy)

    assert a.access_token() is None
    assert a.access_token() is None  # within the retry delay: no second request
    assert len(calls) == 1
    assert a.state() == {"status": "error", "error_key": github_auth.NETWORK_ERROR}
    assert (tmp_path / "github_token.json").exists()  # the 6-month refresh token is kept


def test_an_expired_access_token_shows_connected_once_refreshed(tmp_path):
    a = connected_auth(FakeGithub(), tmp_path)
    _expire_access(a)

    a.access_token()  # what GET /api/mcp_lab does before reading the state
    state = a.state()

    assert state["status"] == "connected" and state["expires_in_s"] > 28000


def test_the_bearer_is_refreshed_per_request_on_a_long_lived_connection(tmp_path):
    a = connected_auth(FakeGithub(), tmp_path)
    seen = []

    def mcp(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["authorization"])
        return httpx2.Response(401 if seen[-1] == "Bearer gho_token" and len(seen) > 1 else 200)

    async def two_requests() -> list[int]:
        headers = a.headers()
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(mcp), headers=headers, auth=a.bearer
        ) as client:
            first = await client.post("https://api.githubcopilot.com/mcp/")
            _expire_access(a)  # 8 h later, the same connection
            second = await client.post("https://api.githubcopilot.com/mcp/")
        return [first.status_code, second.status_code]

    assert asyncio.run(two_requests()) == [200, 200]
    assert seen == ["Bearer gho_token", "Bearer gho_refreshed"]


def test_the_token_file_is_written_atomically(tmp_path):
    connected_auth(FakeGithub(), tmp_path)

    assert json.loads((tmp_path / "github_token.json").read_text())["access_token"] == "gho_token"
    assert not list(tmp_path.glob("*.tmp"))
