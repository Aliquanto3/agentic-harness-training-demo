from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import textwrap

import pytest

from wavestack.net.guard import NetworkBlocked, find_blocked, is_host_allowed, office_proxies


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


def test_find_blocked_walks_causes_contexts_and_groups():
    blocked = NetworkBlocked("Hôte réseau non autorisé : x")
    try:
        try:
            raise blocked
        except NetworkBlocked as exc:
            raise RuntimeError("wrapped") from exc
    except RuntimeError as exc:
        wrapped = exc
    assert find_blocked(ExceptionGroup("g", [ValueError(), wrapped])) is blocked
    assert find_blocked(ValueError()) is None and find_blocked(None) is None


@pytest.mark.skipif(sys.platform != "win32", reason="ProactorEventLoop is Windows-only")
def test_guard_blocks_the_real_mcp_client_under_proactor_event_loop():
    """AD-15: the MCP SDK's own HTTP client (no factory) is still refused by the guard."""
    from mcp import Client

    async def _connect() -> None:
        async with Client("https://blocked.example.test/mcp", mode="legacy", cache=None):
            pass

    policy = asyncio.WindowsProactorEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    try:
        with pytest.raises(Exception) as raised:  # noqa: B017 - the SDK wraps it in a group
            asyncio.run(asyncio.wait_for(_connect(), 20))
    finally:
        asyncio.set_event_loop_policy(None)
    assert find_blocked(raised.value) is not None


# The session guard (conftest) cannot be uninstalled: each case below runs in a
# child process with a simulated resolver, installed before the guard. The
# connect filter is exercised by `sys.audit`, never by a real connection.
_CHILD_PREAMBLE = """
import asyncio, socket, sys, urllib.request
from wavestack.net.guard import NetworkBlocked, install

for lookup in ("getproxies_registry", "getproxies_macosx_sysconf"):  # this machine's proxy
    if hasattr(urllib.request, lookup):
        setattr(urllib.request, lookup, lambda: {})

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
# BEFORE_INSTALL
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

def record_connects():
    # Same, noting each address the guard let through.
    reached = []
    def hook(event, args):
        if event == "socket.connect" and isinstance(args[1], tuple):
            reached.append(args[1][:2])
            raise ReachedConnect
    sys.addaudithook(hook)
    return reached

def blocked(fn, *args):
    # True when `fn` fails on the guard, however a library wraps the refusal.
    from wavestack.net.guard import find_blocked
    try:
        fn(*args)
    except Exception as exc:
        return find_blocked(exc) is not None
    return False
"""

# Story 1e: a recording proxy on the loopback, started in the child before the guard and
# named by `HTTPS_PROXY`, as on the office PC. It notes each request line and refuses it.
_FAKE_PROXY = r"""
import os, socketserver, threading

PROXY_LINES = []

class RecordingProxy(socketserver.StreamRequestHandler):
    def handle(self):
        PROXY_LINES.append(self.rfile.readline().decode("ascii").strip())
        self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")

_proxy_server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), RecordingProxy)
threading.Thread(target=_proxy_server.serve_forever, daemon=True).start()
PROXY = f"http://127.0.0.1:{_proxy_server.server_address[1]}"
os.environ["HTTPS_PROXY"] = os.environ["https_proxy"] = PROXY
"""


def _run_guarded(body: str, before_install: str = "", **extra_env: str) -> None:
    """Runs `body` in a child process under the guard, without this machine's proxy;
    `before_install` runs just before `install` (a proxy to confiscate, a registry)."""
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    env.update(extra_env)
    preamble = _CHILD_PREAMBLE.replace("# BEFORE_INSTALL\n", textwrap.dedent(before_install))
    result = subprocess.run(
        [sys.executable, "-c", preamble + textwrap.dedent(body)],
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


def test_a_no_proxy_host_is_not_taken_for_a_proxy() -> None:
    """NO_PROXY names hosts that bypass the proxy: the guard does not accept them."""
    _run_guarded(
        """
        FAKE_DNS["intranet.example"] = "10.1.2.3"
        assert refused(socket.getaddrinfo, "intranet.example", 443)
        assert not refused(socket.getaddrinfo, "proxy.corp.test", 8080)
        """,
        HTTPS_PROXY="http://proxy.corp.test:8080",
        NO_PROXY="intranet.example",
    )


# ---------- story 1e: the guard confiscates the workstation's proxy ----------


def test_install_confiscates_the_proxy_from_the_environment() -> None:
    _run_guarded(
        """
        import os, urllib.request
        from wavestack.net.guard import office_proxies
        assert not [n for n in os.environ if n.lower().endswith("_proxy")]
        assert urllib.request.getproxies() == {}
        if sys.platform == "win32":
            assert urllib.request.getproxies_registry() == {}
        assert office_proxies() == {"https": "http://127.0.0.1:9000"}
        """,
        HTTPS_PROXY="http://127.0.0.1:9000",
        https_proxy="http://127.0.0.1:9000",
    )


def test_install_copies_then_blinds_the_windows_registry_proxy() -> None:
    _run_guarded(
        """
        import urllib.request
        from wavestack.net.guard import office_proxies
        assert office_proxies() == {"https": "127.0.0.1:9000"}
        assert urllib.request.getproxies_registry() == {}
        assert urllib.request.getproxies() == {}
        """,
        # Set on every platform: `getproxies` only falls back on it under Windows.
        before_install="""
        urllib.request.getproxies_registry = lambda: {"https": "127.0.0.1:9000"}
        urllib.request.getproxies = lambda: (
            urllib.request.getproxies_environment() or urllib.request.getproxies_registry()
        )
        """,
    )


def test_a_second_install_keeps_the_first_copy() -> None:
    _run_guarded(
        """
        import os
        from wavestack.net.guard import office_proxies
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:1"
        install([])
        assert office_proxies() == {"https": "http://127.0.0.1:9000"}
        assert "HTTPS_PROXY" not in os.environ
        """,
        HTTPS_PROXY="http://127.0.0.1:9000",
    )


def test_a_client_outside_the_factory_no_longer_reaches_the_loopback_proxy() -> None:
    """The defect of story 1e: `httpx` and `urllib` would tunnel `CONNECT example.com:443`
    through the loopback proxy, unseen. Without it they resolve the host: refused."""
    _run_guarded(
        """
        import urllib.request
        import httpx
        with httpx.Client() as client:
            assert blocked(client.get, "https://example.com/")
        assert blocked(urllib.request.urlopen, "https://example.com/")
        assert PROXY_LINES == [], PROXY_LINES
        """,
        before_install=_FAKE_PROXY,
    )


@pytest.mark.skipif(sys.platform != "win32", reason="ProactorEventLoop is Windows-only")
def test_the_mcp_sdk_without_factory_is_refused_under_proactor_despite_the_proxy() -> None:
    _run_guarded(
        """
        from mcp import Client
        from wavestack.net.guard import find_blocked

        async def connect():
            async with Client("https://blocked.example.test/mcp", mode="legacy", cache=None):
                pass

        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        try:
            asyncio.run(asyncio.wait_for(connect(), 20))
        except BaseException as exc:
            assert find_blocked(exc) is not None, repr(exc)
        else:
            raise AssertionError("the MCP client connected")
        assert PROXY_LINES == [], PROXY_LINES
        """,
        before_install=_FAKE_PROXY,
    )


def test_a_child_process_inherits_no_proxy() -> None:
    _run_guarded(
        """
        import subprocess
        child = (
            "import os, urllib.request\\n"
            "urllib.request.getproxies_registry = lambda: {}\\n"
            "from wavestack.net import guard\\n"
            "names = [n for n in os.environ if n.lower().endswith('_proxy')]\\n"
            "guard.install([])\\n"
            "print(names, guard.office_proxies())\\n"
        )
        out = subprocess.run(
            [sys.executable, "-c", child], capture_output=True, text=True, check=True
        ).stdout
        assert out.strip() == "[] {}", out
        """,
        HTTPS_PROXY="http://127.0.0.1:9000",
        NO_PROXY="intranet.example",
    )


def test_a_remote_proxy_serves_the_factory_only() -> None:
    """The factory goes out through `proxy.corp.test` (accepted from the copy); a client
    outside it connects directly: refused off the list, untraced on it (ceiling, covered
    for `src/` by `test_net_single_factory`)."""
    _run_guarded(
        """
        import httpx
        from wavestack.net.factory import create_client
        reached = record_connects()
        with create_client() as client:
            try:
                client.get("https://fr.wikipedia.org/wiki/Paris")
            except ReachedConnect:
                pass
        assert reached == [("203.0.113.9", 8080)], reached
        with httpx.Client() as client:
            assert blocked(client.get, "https://example.com/")
            try:
                client.get("https://fr.wikipedia.org/wiki/Paris")
            except ReachedConnect:
                pass
        assert reached == [("203.0.113.9", 8080), ("185.15.58.224", 443)], reached
        """,
        HTTPS_PROXY="http://proxy.corp.test:8080",
    )


def test_the_test_session_holds_no_proxy() -> None:
    """conftest removes this machine's proxy before any guard install (`wavestack.cli`
    installs one when imported): the suite runs the same with or without `HTTPS_PROXY`."""
    assert office_proxies() == {}
    assert not [n for n in os.environ if n.lower().endswith("_proxy")]
