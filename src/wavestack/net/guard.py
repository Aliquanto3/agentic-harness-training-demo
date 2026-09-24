"""Network guard: a `sys.addaudithook` blocking any host outside the allow-list (AD-15).

Filters `socket.getaddrinfo` (hostnames — the only event seen on every loop,
Windows ProactorEventLoop included) and `socket.connect` (IPs). A connect is
accepted when its IP was returned by resolving an allowed host (or the proxy),
so the wrapped `socket.getaddrinfo` records those addresses.
Installed at the very start of `cli`, before any third-party import, and
again in every child process (probe, local MCP server).
"""

from __future__ import annotations

import ipaddress
import socket
import sys
from urllib.parse import urlparse
from urllib.request import getproxies

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

# ponytail: an IP learned for an allowed host stays accepted for the whole
# process (same server or shared CDN included); per-host expiry if that matters.
_resolved: set[str] = set()


class NetworkBlocked(Exception):
    """Raised when the network guard refuses a destination."""


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


def _proxy_hosts() -> set[str]:
    hosts = set()
    for url in getproxies().values():
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


def install(allowed_hosts: list[str]) -> None:
    """Install the audit hook and wrap `socket.getaddrinfo` for the whole process.

    Cannot be uninstalled (Python limitation): call once, before any third-party
    import.
    """

    def check_host(host: object) -> None:
        if isinstance(host, bytes):  # anyio (httpx async) passes IDNA-encoded bytes
            try:
                host = host.decode("ascii")
            except UnicodeDecodeError:
                raise NetworkBlocked(f"Hôte réseau non autorisé : {host!r}") from None
        if host is not None and not is_host_allowed(str(host), allowed_hosts):
            raise NetworkBlocked(f"Hôte réseau non autorisé : {host}")

    def hook(event: str, args: tuple[object, ...]) -> None:
        if event == "socket.getaddrinfo":
            check_host(args[0])
        elif event == "socket.connect":
            sock_address = args[1]
            if isinstance(sock_address, tuple) and sock_address:
                host = str(sock_address[0])
                if host not in _resolved and not is_host_allowed(host, allowed_hosts):
                    raise NetworkBlocked(f"Adresse réseau non autorisée : {host}")

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
