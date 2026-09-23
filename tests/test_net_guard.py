from __future__ import annotations

import asyncio
import socket
import sys

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
