from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import textwrap

import pytest

from wavestack.net.guard import NetworkBlocked, is_host_allowed


def test_loopback_always_allowed():
    assert is_host_allowed("127.0.0.1", [])
    assert is_host_allowed("localhost", [])


def test_wildcard_suffix_matches():
    assert is_host_allowed("models.hf.co", ["*.hf.co"])
    assert is_host_allowed("hf.co", ["*.hf.co"])
    assert not is_host_allowed("hf.co.evil.test", ["*.hf.co"])


def test_disallowed_host_rejected():
    assert not is_host_allowed("example.test", [])


def test_guard_blocks_disallowed_host_via_audit_hook():
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("blocked.example.test", 80)


@pytest.mark.skipif(sys.platform != "win32", reason="ProactorEventLoop is Windows-only")
def test_guard_blocks_under_proactor_event_loop():
    async def _resolve() -> None:
        loop = asyncio.get_running_loop()
        await loop.getaddrinfo("blocked.example.test", 80)

    policy = asyncio.WindowsProactorEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    try:
        with pytest.raises(NetworkBlocked):
            asyncio.run(_resolve())
    finally:
        asyncio.set_event_loop_policy(None)


# The session guard (conftest) cannot be uninstalled: each case below runs in a
# child process with a simulated resolver, installed before the guard. The
# connect filter is exercised by `sys.audit`, never by a real connection.
_CHILD_PREAMBLE = """
import asyncio, socket, sys, urllib.request
from wavestack.net.guard import NetworkBlocked, install

urllib.request.getproxies_registry = lambda: {}  # ignore this machine's proxy

FAKE_DNS = {
    "fr.wikipedia.org": "185.15.58.224",
    "huggingface.co": "18.155.129.60",
    "cdn-lfs.hf.co": "18.155.129.61",
    "v6.hf.co": "2001:db8::1",
    "proxy.corp.test": "203.0.113.9",
    "example.com": "93.184.215.14",
}

def fake_getaddrinfo(host, port, *args, **kwargs):
    sys.audit("socket.getaddrinfo", host, port, 0, 0, 0)  # like the real resolver
    ip = FAKE_DNS.get(host, host)
    if ":" in ip:
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, port, 0, 0))]
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

socket.getaddrinfo = fake_getaddrinfo
install(["fr.wikipedia.org", "huggingface.co", "*.hf.co"])

def connect(address):
    sys.audit("socket.connect", None, address)

def refused(fn, *args):
    try:
        fn(*args)
    except NetworkBlocked:
        return True
    return False

class ReachedConnect(Exception):
    pass

def stop_at_connect():
    # Added after the guard: raised only once the guard let `connect` through.
    def hook(event, args):
        if event == "socket.connect":
            raise ReachedConnect
    sys.addaudithook(hook)
"""

_PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")


def _run_guarded(body: str, **extra_env: str) -> None:
    env = {k: v for k, v in os.environ.items() if k.lower() not in _PROXY_VARS}
    env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-c", _CHILD_PREAMBLE + textwrap.dedent(body)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            """
            socket.getaddrinfo("fr.wikipedia.org", 443)
            assert not refused(connect, ("185.15.58.224", 443))
            """,
            id="allowed-host",
        ),
        pytest.param(
            """
            socket.getaddrinfo("huggingface.co", 443)
            assert not refused(connect, ("18.155.129.60", 443))
            """,
            id="regression-allowed-host-public-ip",
        ),
        pytest.param(
            """
            assert refused(socket.getaddrinfo, "example.com", 443)
            assert refused(connect, ("93.184.215.14", 443))
            """,
            id="refused-host-learns-nothing",
        ),
        pytest.param(
            """
            assert refused(sys.audit, "socket.getaddrinfo", "example.com", 443, 0, 0, 0)
            """,
            id="audit-hook-refuses-host",
        ),
        pytest.param(
            """
            assert refused(connect, ("198.51.100.7", 443))
            """,
            id="unknown-literal-ip",
        ),
        pytest.param(
            """
            assert refused(socket.getaddrinfo, "198.51.100.7", 443)
            assert refused(connect, ("198.51.100.7", 443))
            """,
            id="literal-ip-via-getaddrinfo",
        ),
        pytest.param(
            """
            socket.getaddrinfo("cdn-lfs.hf.co", 443)
            assert not refused(connect, ("18.155.129.61", 443))
            """,
            id="wildcard",
        ),
        pytest.param(
            """
            FAKE_DNS[b"cdn-lfs.hf.co"] = "18.155.129.61"
            socket.getaddrinfo(b"cdn-lfs.hf.co", 443)
            assert not refused(connect, ("18.155.129.61", 443))
            assert refused(socket.getaddrinfo, b"example.com", 443)
            assert refused(socket.getaddrinfo, b"\\xff.hf.co", 443)
            """,
            id="bytes-host-anyio",
        ),
        pytest.param(
            """
            assert not refused(connect, ("127.0.0.1", 11434))
            """,
            id="loopback",
        ),
        pytest.param(
            """
            socket.getaddrinfo("v6.hf.co", 443)
            assert not refused(connect, ("2001:db8::1", 443, 0, 0))
            """,
            id="ipv6",
        ),
        pytest.param(
            """
            stop_at_connect()
            try:
                socket.create_connection(("fr.wikipedia.org", 443))
            except ReachedConnect:
                pass
            else:
                raise AssertionError("connect never reached")
            """,
            id="create-connection",
        ),
        pytest.param(
            """
            async def resolve():
                await asyncio.get_running_loop().getaddrinfo("fr.wikipedia.org", 443)

            asyncio.run(resolve())
            assert not refused(connect, ("185.15.58.224", 443))
            """,
            id="asyncio-getaddrinfo",
        ),
    ],
)
def test_guard_connect_filter(body: str) -> None:
    _run_guarded(body)


def test_guard_accepts_resolved_proxy_addresses() -> None:
    _run_guarded(
        """
        socket.getaddrinfo("proxy.corp.test", 8080)
        assert not refused(connect, ("203.0.113.9", 8080))
        """,
        HTTPS_PROXY="http://proxy.corp.test:8080",
    )


def test_guard_refuses_proxy_host_when_no_proxy_set() -> None:
    _run_guarded(
        """
        assert refused(socket.getaddrinfo, "proxy.corp.test", 8080)
        assert refused(connect, ("203.0.113.9", 8080))
        """
    )
