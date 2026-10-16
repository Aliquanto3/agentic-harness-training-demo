"""CAP-4: GitHub's remote MCP server, reached by the OAuth App WaveStack's device flow.

Decisions (this story, 2026-10-16):
- Scope: `read:user` only, the minimum the real test of 2026-10-16 validated (this Client ID,
  this scope: the device flow lists the remote server's tools, alerts included, on a public
  repo). No broader scope is requested.
- Renewal: GitHub's device-flow access token expires (8h), but a public OAuth App (no client
  secret) can still redeem its refresh token (6 months) with `grant_type=refresh_token` and
  the client id alone. `access_token()` refreshes it once expired, transparently.
- Storage: the token (access + refresh, their expiry) is written to a local JSON file under
  `config.data_dir()`, outside the repository, so a connection the next day (flow 4 of
  EXPERIENCE.md) still finds it; never logged, journalled or traced. In memory the rest of
  the time.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import httpx2

from wavestack import config
from wavestack.net.factory import create_client

CLIENT_ID = "Ov23li3Ovj8ZnyXMFUPQ"  # WaveStack's OAuth App (public), device flow, no secret.
SCOPE = "read:user"
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
MCP_URL = "https://api.githubcopilot.com/mcp/"
# Without these, the alerts tools are not exposed (mcp-tools.md). No `X-MCP-Readonly`: the
# write tools stay listed, so WaveStack's own policy is the one that refuses them (the first
# of the three refusal levels, demonstrated without GitHub's own 403 first).
TOOLSETS = "secret_protection,dependabot,code_security"
_DEFAULT_EXPIRES_IN = 28800  # 8h, GitHub's stated default (recon of 2026-10-16)
_DEFAULT_REFRESH_EXPIRES_IN = 15897600  # ~6 months
_RETRY_S = 30.0  # a refresh that failed on the network waits this long before the next try
NETWORK_ERROR = "mcp.github.error.network"


@dataclass(frozen=True)
class GithubToken:
    access_token: str
    refresh_token: str
    obtained_at: float
    expires_in: int
    refresh_expires_in: int

    @property
    def expired(self) -> bool:
        return time.time() >= self.obtained_at + self.expires_in

    @property
    def refresh_expired(self) -> bool:
        return time.time() >= self.obtained_at + self.refresh_expires_in

    @property
    def expires_in_s(self) -> int:
        return max(0, round(self.obtained_at + self.expires_in - time.time()))


def _token_file() -> Path:
    return config.data_dir() / "github_token.json"


def _load(path: Path) -> GithubToken | None:
    try:
        return GithubToken(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def _save(path: Path, token: GithubToken | None) -> None:
    try:
        if token is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic: a crash mid-write never leaves a truncated file (the token lost).
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(token)), encoding="utf-8")
            os.replace(tmp, path)
    except OSError:  # a disk that refuses the write: memory still holds the token
        pass


class _Bearer(httpx2.Auth):
    """The bearer token set on each request, not once at connect time: a workshop connection
    outlives the access token's 8 h, so each request gets the token refreshed if need be
    (off the event loop: a refresh is a blocking request)."""

    def __init__(self, auth: GithubAuth) -> None:
        self._auth = auth

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> AsyncGenerator[httpx2.Request, httpx2.Response]:
        token = await asyncio.to_thread(self._auth.access_token)
        if token is not None:  # none: the session refuses the call before it is sent
            request.headers["Authorization"] = f"Bearer {token}"
        yield request


class GithubAuth:
    """One device flow and its token, thread-safe. `transport`/`path` are for tests only (no
    real network, no file under the real data directory)."""

    def __init__(
        self, *, transport: httpx.BaseTransport | None = None, path: Path | None = None
    ) -> None:
        self._client = create_client(timeout=10.0, transport=transport)
        self._path = path or _token_file()
        self._lock = threading.Lock()
        self._token: GithubToken | None = _load(self._path)
        self._device: dict[str, Any] | None = None  # the device flow under way, if any
        self._error: str | None = None
        # Flow 4 (EXPERIENCE.md): the refresh refused, state « expiré » with « Se reconnecter ».
        self._expired = False
        self._retry_at = 0.0  # no refresh attempt before this time (after a network failure)
        self.bearer = _Bearer(self)

    def _post(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        """GitHub's JSON answer. `httpx.HTTPError` on the network, `ValueError` on a body
        that is no JSON object (a proxy's or captive portal's page answered instead)."""
        response = self._client.post(url, data=data, headers={"Accept": "application/json"})
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("GitHub's answer is not a JSON object")
        return body

    # ---------- device flow ----------

    def start(self) -> dict[str, str]:
        """Starts (or restarts) a device flow: the user code and address to show. Raises
        `httpx.HTTPError` on a network failure, `ValueError` on an unexpected answer (the
        caller turns either into a session state)."""
        data = self._post(DEVICE_CODE_URL, {"client_id": CLIENT_ID, "scope": SCOPE})
        try:
            device = {
                "device_code": str(data["device_code"]),
                "user_code": str(data["user_code"]),
                "verification_uri": str(data["verification_uri"]),
                "interval": float(data.get("interval", 5)),
                "next_poll": 0.0,
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("GitHub's device code answer lacks a field") from exc
        with self._lock:
            self._device = device
            self._error = None
        return {"user_code": data["user_code"], "verification_uri": data["verification_uri"]}

    def poll(self) -> bool:
        """Advances a pending device flow by at most one request, never more often than its
        own interval; never raises (a transient error waits for the next poll). `True` once
        the token is obtained."""
        with self._lock:
            device = self._device
        if device is None:
            return self._token is not None
        if time.time() < device["next_poll"]:
            return False
        try:
            data = self._post(
                TOKEN_URL,
                {
                    "client_id": CLIENT_ID,
                    "device_code": device["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
        except (httpx.HTTPError, ValueError):
            with self._lock:
                if self._device is device:
                    device["next_poll"] = time.time() + device["interval"]
            return False
        return self._apply_poll(device, data)

    def _apply_poll(self, device: dict[str, Any], data: dict[str, Any]) -> bool:
        error = data.get("error")
        with self._lock:
            if self._device is not device:
                return self._token is not None  # superseded by a later `start()`
            if error == "authorization_pending" or (not error and "access_token" not in data):
                device["next_poll"] = time.time() + device["interval"]
                return False
            if error == "slow_down":
                device["interval"] += 5
                device["next_poll"] = time.time() + device["interval"]
                return False
            if error:  # expired_token, access_denied, incorrect_client_credentials...
                self._device, self._error = None, f"mcp.github.error.{error}"
                return False
            token = GithubToken(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", ""),
                obtained_at=time.time(),
                expires_in=int(data.get("expires_in", _DEFAULT_EXPIRES_IN)),
                refresh_expires_in=int(
                    data.get("refresh_token_expires_in", _DEFAULT_REFRESH_EXPIRES_IN)
                ),
            )
            self._token, self._device, self._error, self._expired = token, None, None, False
        _save(self._path, token)
        return True

    # ---------- the token, refreshed as needed ----------

    def _refresh(self, token: GithubToken) -> GithubToken | None:
        """`None` when GitHub refuses the refresh token (a fresh device flow is needed).
        Raises `httpx.HTTPError`/`ValueError` on the network or an unexpected body."""
        data = self._post(
            TOKEN_URL,
            {
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
            },
        )
        if data.get("error") or "access_token" not in data:
            return None
        return GithubToken(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", token.refresh_token),
            obtained_at=time.time(),
            expires_in=int(data.get("expires_in", _DEFAULT_EXPIRES_IN)),
            refresh_expires_in=int(data.get("refresh_token_expires_in", token.refresh_expires_in)),
        )

    def access_token(self) -> str | None:
        """A fresh access token (refreshed if it had expired); `None` when there is none, or
        the refresh failed: refused by GitHub, the state turns « expiré » (a fresh device flow
        is needed); on the network, the token is kept and retried after `_RETRY_S`."""
        with self._lock:
            token = self._token
        if token is None:
            return None
        if not token.expired:
            return token.access_token
        if token.refresh_expired:
            self._expire(token)
            return None
        if time.time() < self._retry_at:
            return None
        try:
            refreshed = self._refresh(token)
        except (httpx.HTTPError, ValueError):
            self._retry_at = time.time() + _RETRY_S
            return None
        if refreshed is None:
            self._expire(token)
            return None
        with self._lock:
            if self._token is not token:  # disconnected or replaced meanwhile
                return None
            self._token = refreshed
        _save(self._path, refreshed)
        return refreshed.access_token

    def _expire(self, token: GithubToken) -> None:
        with self._lock:
            if self._token is not token:
                return
            self._token, self._expired = None, True
        _save(self._path, None)

    def disconnect(self) -> None:
        with self._lock:
            self._token, self._device, self._error, self._expired = None, None, None, False
        _save(self._path, None)

    def headers(self) -> dict[str, str] | None:
        """The MCP connection's extra headers, or `None` when there is no usable token (the
        caller must not even attempt the connection then)."""
        token = self.access_token()
        if token is None:
            return None
        return {"Authorization": f"Bearer {token}", "X-MCP-Toolsets": TOOLSETS}

    def state(self) -> dict[str, Any]:
        """`GET /api/mcp_lab`'s `github`: never the token itself. Call `access_token()`
        first: an expired access token is refreshed there, so one still here is a refresh that
        failed on the network (« erreur réseau », retried)."""
        with self._lock:
            token, device, error = self._token, self._device, self._error
            expired = self._expired
        if device is not None:
            return {
                "status": "waiting",
                "user_code": device["user_code"],
                "verification_uri": device["verification_uri"],
            }
        if token is not None:
            if token.expired:
                return {"status": "error", "error_key": NETWORK_ERROR}
            return {"status": "connected", "expires_in_s": token.expires_in_s}
        if error:
            return {"status": "error", "error_key": error}
        return {"status": "expired"} if expired else {"status": "disconnected"}
