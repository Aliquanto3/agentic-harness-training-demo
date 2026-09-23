"""Network guard: a `sys.addaudithook` blocking any host outside the allow-list (AD-15).

Filters `socket.getaddrinfo` (hostnames — the only event seen on every loop,
Windows ProactorEventLoop included) and `socket.connect` (literal IPs).
Installed at the very start of `cli`, before any third-party import, and
again in every child process (probe, local MCP server).
"""

from __future__ import annotations

import ipaddress
import sys
from urllib.parse import urlparse
from urllib.request import getproxies

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


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
    """Install the audit hook. Cannot be uninstalled (Python limitation); call once."""

    def hook(event: str, args: tuple[object, ...]) -> None:
        if event == "socket.getaddrinfo":
            host = args[0]
            if host is not None and not is_host_allowed(str(host), allowed_hosts):
                raise NetworkBlocked(f"Hôte réseau non autorisé : {host}")
        elif event == "socket.connect":
            sock_address = args[1]
            if isinstance(sock_address, tuple) and sock_address:
                host = str(sock_address[0])
                if not is_host_allowed(host, allowed_hosts):
                    raise NetworkBlocked(f"Adresse réseau non autorisée : {host}")

    sys.addaudithook(hook)
