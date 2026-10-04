"""Network guard: a `sys.addaudithook` blocking any host outside the allow-list (AD-15).

Filters `socket.getaddrinfo` (hostnames — the only event seen on every loop,
Windows ProactorEventLoop included), `socket.gethostbyname` (hostnames too,
raised by `gethostbyname_ex` as well), the reverse lookups `socket.gethostbyaddr`
(a name or an IP) and `socket.getnameinfo` (the host of its socket address), and
`socket.connect`, `socket.sendto` and
`socket.sendmsg` (IPs). A connect or a UDP send is accepted when its IP was
returned by resolving an allowed host (or the proxy), so the wrapped
`socket.getaddrinfo` records those addresses. A host name given to
`connect`/`sendto` is resolved by the C layer before the event: an off-list
name's DNS query has then left already, only the connection or the datagram is
refused.
Installed at the very start of `cli`, before any third-party import, and
again in every child process (probe, local MCP server).

The guard also confiscates the workstation's proxy (story 1e): `install` copies
`urllib.request.getproxies()` once, then removes every `*_proxy` variable from
`os.environ` and blinds the system lookup (Windows registry, macOS settings).
Only the factory (`net.factory`) gets the copy, through `office_proxies()`: any
other client (third-party library, MCP SDK without `http_client`, `urllib`)
finds no proxy, connects directly by host name, and so meets `getaddrinfo`,
where an off-list host is refused. A child process inherits no proxy variable;
under Windows, its own `install` copies the registry proxy again, which is
harmless: children need no network, and their clients outside the factory are
blinded the same way. Without this, a loopback
proxy (`HTTPS_PROXY=http://127.0.0.1:9000`) is accepted as loopback and carries
any destination past the guard inside its `CONNECT` tunnel.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
import urllib.request
from urllib.parse import urlparse

# Languages (5/5): `messages` reads `content/messages.yaml` with PyYAML, no network library.
from wavestack.messages import KeyedError, Message

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

# ponytail: an IP learned for an allowed host stays accepted for the whole
# process (same server or shared CDN included); per-host expiry if that matters.
_resolved: set[str] = set()

# Story 1e: the workstation's proxy, taken once by the first `install` (scheme -> URL,
# `no` -> NO_PROXY, as `urllib.request.getproxies()` gives them). Never logged nor traced:
# the URL may carry credentials.
# ponytail: code that targets the proxy's address on purpose (hard-coded, or read from
# this copy) still passes, since loopback stays accepted; native code reading Windows'
# own settings (WinHTTP, PAC) too. `tests/test_net_single_factory.py` covers the first
# case for `src/`; AD-15 states both.
_proxies: dict[str, str] = {}
_confiscated = False

# Restes différés, story 1 (E013): the audit events filtered. A resolution passes the
# host-name check (`gethostbyname_ex` raises `socket.gethostbyname` too); a connect or a
# UDP send, the address check.
# ponytail: `gethostbyname(_ex)` records no address, so a connect to the IP it gave for an
# allowed host is refused (the safe way); wrap them as `getaddrinfo` if a client needs it.
# Finition V1 (#14): the reverse lookups too, `gethostbyaddr` on its name or IP and
# `getnameinfo` on its socket address's host (`_REVERSE_EVENTS`).
# ponytail: `socket.getfqdn()` (no argument, or the machine's own name) is then refused with
# `NetworkBlocked`, which it does not catch; nothing in WaveStack calls it (as for
# `gethostbyname(gethostname())` before).
_RESOLVE_EVENTS = frozenset({"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"})
_REVERSE_EVENTS = frozenset({"socket.getnameinfo"})
_SEND_EVENTS = frozenset({"socket.connect", "socket.sendto", "socket.sendmsg"})

# The system lookups `getproxies()` falls back on, blinded by the confiscation.
_SYSTEM_PROXY_LOOKUPS = ("getproxies_registry", "getproxies_macosx_sysconf")


class NetworkBlocked(KeyedError):
    """Raised when the network guard refuses a destination. Languages (5/5): keyed, placed
    as a cause in the messages that name it (`tools.network.blocked`…), so it is rendered in
    their language; a plain text (a test's) is kept verbatim."""

    def __init__(self, text: str | Message) -> None:
        super().__init__(
            text if isinstance(text, Message) else Message("common.verbatim", text=text)
        )


def is_loopback(host: str) -> bool:
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _matches(host: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        suffix = pattern[1:]  # ".example.com"
        return host == pattern[2:] or host.endswith(suffix)
    return host == pattern


def office_proxies() -> dict[str, str]:
    """The workstation's proxy confiscated by `install` (a copy): for the factory only."""
    return dict(_proxies)


def _confiscate_proxies() -> None:
    """Copy the workstation's proxy once, then take it away from the process (story 1e).

    The copy comes first: once the system lookup is blinded, the registry cannot be read.
    `httpx`, `httpx2` and `urllib` call `getproxies()`, which reads the environment and
    these module attributes again on every call.
    """
    global _confiscated
    if not _confiscated:  # a second `install` keeps the first copy
        _proxies.update(urllib.request.getproxies())
        _confiscated = True
    for name in [n for n in os.environ if n.lower().endswith("_proxy")]:
        del os.environ[name]  # also unset for child processes
    for name in _SYSTEM_PROXY_LOOKUPS:
        if hasattr(urllib.request, name):
            setattr(urllib.request, name, lambda: {})


def _proxy_hosts() -> set[str]:
    hosts = set()
    for scheme, url in _proxies.items():
        if scheme == "no":
            continue  # NO_PROXY lists hosts that bypass the proxy, not proxies
        parsed = urlparse(url if "://" in url else f"http://{url}")
        if parsed.hostname:
            hosts.add(parsed.hostname)
    return hosts


def is_host_allowed(host: str, allowed_hosts: list[str]) -> bool:
    if is_loopback(host):
        return True
    if host in _proxy_hosts():
        return True
    return any(_matches(host, pattern) for pattern in allowed_hosts)


def find_blocked(exc: BaseException | None) -> NetworkBlocked | None:
    """The `NetworkBlocked` behind `exc`: its causes, contexts and exception groups."""
    seen: set[int] = set()
    stack = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, NetworkBlocked):
            return current
        stack += [current.__cause__, current.__context__]
        stack += getattr(current, "exceptions", ())
    return None


def install(allowed_hosts: list[str]) -> None:
    """Install the audit hook and wrap `socket.getaddrinfo` for the whole process.

    Cannot be uninstalled (Python limitation): call once, before any third-party
    import. Confiscates the workstation's proxy first (story 1e, `office_proxies`).
    """
    _confiscate_proxies()

    def check_host(host: object) -> None:
        if isinstance(host, bytes):  # anyio (httpx async) passes IDNA-encoded bytes
            try:
                host = host.decode("ascii")
            except UnicodeDecodeError:
                raise NetworkBlocked(Message("net.host_refused", host=repr(host))) from None
        if host is not None and not is_host_allowed(str(host), allowed_hosts):
            raise NetworkBlocked(Message("net.host_refused", host=str(host)))

    def check_address(sock_address: object) -> None:
        if isinstance(sock_address, tuple) and sock_address:
            host = str(sock_address[0])
            if host not in _resolved and not is_host_allowed(host, allowed_hosts):
                raise NetworkBlocked(Message("net.address_refused", host=host))

    def hook(event: str, args: tuple[object, ...]) -> None:
        if event in _RESOLVE_EVENTS:
            check_host(args[0])
        elif event in _REVERSE_EVENTS:  # (sockaddr,): its host, as a resolution
            sock_address = args[0]
            if not (isinstance(sock_address, tuple) and sock_address):
                raise NetworkBlocked(Message("net.host_refused", host=repr(sock_address)))
            check_host(sock_address[0])
        elif event in _SEND_EVENTS:  # (socket, address); `sendmsg` without one: None
            check_address(args[1])

    # Module attribute, looked up at call time by `socket.create_connection`
    # and asyncio: wrapping it sees every resolution.
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host, *args, **kwargs):
        # The resolver raises the audit event first: a refused host learns nothing.
        results = original_getaddrinfo(host, *args, **kwargs)
        if host is not None:  # a passive lookup returns 0.0.0.0 / ::
            _resolved.update(str(sockaddr[0]) for *_, sockaddr in results)
        return results

    socket.getaddrinfo = getaddrinfo
    sys.addaudithook(hook)
