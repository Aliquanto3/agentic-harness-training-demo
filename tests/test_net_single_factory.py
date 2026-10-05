"""Story 1e: `net/factory.py` is the only module of `src/` that creates an HTTP client.

The guard confiscates the workstation's proxy and hands it to the factory alone, so a
client created elsewhere finds no proxy and meets the guard at `getaddrinfo`. Code that
knew the proxy's address would still pass (the guard's ceiling, AD-15): this static test
keeps such clients out of `src/`, and the guard's copy of the proxy inside `net/`. Calls
are resolved through the module's imports (`import httpx as h`,
`from urllib.request import urlopen`).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "wavestack"
NET = SRC / "net"
FACTORY = NET / "factory.py"

_HTTP_VERBS = ("request", "stream", "get", "options", "head", "post", "put", "patch", "delete")

# Qualified names whose call creates an HTTP client, or sends with a throwaway one.
FORBIDDEN = {
    "httpx.Client",
    "httpx.AsyncClient",
    "httpx2.Client",
    "httpx2.AsyncClient",
    *(f"{module}.{verb}" for module in ("httpx", "httpx2") for verb in _HTTP_VERBS),
    "requests.Session",
    "requests.session",
    *(f"requests.{verb}" for verb in _HTTP_VERBS if verb != "stream"),
    "urllib3.PoolManager",
    "urllib3.ProxyManager",
    "urllib3.request",
    "aiohttp.ClientSession",
    "aiohttp.request",
    "urllib.request.urlopen",
    "urllib.request.urlretrieve",
    "urllib.request.build_opener",
    "http.client.HTTPConnection",
    "http.client.HTTPSConnection",
    "mcp.Client",  # given a URL, the MCP SDK opens its own HTTP client
    "mcp.client.sse.sse_client",
}
# The MCP SDK opens its own client unless it is given the factory's (`http_client=`).
NEEDS_HTTP_CLIENT = "mcp.client.streamable_http.streamable_http_client"

# The guard's copy of the proxy: for `net/` only (AD-15).
PROXY_COPY = {"wavestack.net.guard.office_proxies", "wavestack.net.guard._proxies"}

# (file relative to src/wavestack, enclosing function, qualified name) -> why it may stay.
EXEMPTIONS = {
    ("cli.py", "_existing_instance_health", "urllib.request.urlopen"): (
        "loopback only (127.0.0.1), urllib before any client is built; no proxy to find "
        "once the guard has confiscated it"
    ),
    ("cli.py", "_existing_instance_ready", "urllib.request.urlopen"): (
        "same: loopback only, at start-up"
    ),
    ("mcp/connection.py", "_serve", "mcp.Client"): (
        "given the transport built by `_transport`: `streamable_http_client` with the "
        "factory's `create_async_client`, or a local stdio server"
    ),
    ("mcp/lab.py", "_serve", "mcp.Client"): (
        "lot 4 of 2026-10-04, the MCP workshop's own `_serve`: the same transports, the "
        "factory's `create_async_client` for a public server"
    ),
}


class _Finder(ast.NodeVisitor):
    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}
        self.functions: list[str] = []
        self.clients: list[tuple[int, str, str | None]] = []
        self.proxy_reads: list[tuple[int, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self.aliases[alias.asname] = alias.name
            else:
                head = alias.name.split(".")[0]
                self.aliases[head] = head

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and not node.level:
            for alias in node.names:
                name = f"{node.module}.{alias.name}"
                self.aliases[alias.asname or alias.name] = name
                if name in PROXY_COPY:
                    self.proxy_reads.append((node.lineno, name))

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.functions.append(node.name)
        self.generic_visit(node)
        self.functions.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def _qualified(self, node: ast.expr) -> str | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        head = self.aliases.get(node.id, node.id)
        return ".".join([head, *reversed(parts)])

    def _check_proxy_read(self, node: ast.Name | ast.Attribute) -> None:
        name = self._qualified(node)
        if name in PROXY_COPY:
            self.proxy_reads.append((node.lineno, name))
        self.generic_visit(node)

    visit_Name = _check_proxy_read
    visit_Attribute = _check_proxy_read

    def visit_Call(self, node: ast.Call) -> None:
        name = self._qualified(node.func)
        if name in FORBIDDEN or (name == NEEDS_HTTP_CLIENT and not _given_a_client(node)):
            self.clients.append((node.lineno, name, self.functions[0] if self.functions else None))
        self.generic_visit(node)


def _given_a_client(call: ast.Call) -> bool:
    """`http_client=` is passed, and not as the constant `None`."""
    return any(
        k.arg == "http_client" and not (isinstance(k.value, ast.Constant) and k.value.value is None)
        for k in call.keywords
    )


def _find(source: str) -> _Finder:
    finder = _Finder()
    finder.visit(ast.parse(source))
    return finder


def test_only_the_factory_creates_http_clients():
    offences = []
    used = set()
    for path in sorted(SRC.rglob("*.py")):
        if path == FACTORY:
            continue
        relative = path.relative_to(SRC).as_posix()
        for line, name, function in _find(path.read_text("utf-8")).clients:
            if (relative, function, name) in EXEMPTIONS:
                used.add((relative, function, name))
            else:
                offences.append(f"src/wavestack/{relative}:{line}: {name}")
    assert not offences, "HTTP client outside net/factory.py (story 1e):\n" + "\n".join(offences)
    assert used == set(EXEMPTIONS), f"stale exemptions: {set(EXEMPTIONS) - used}"


def test_only_net_reads_the_guard_copy_of_the_proxy():
    offences = [
        f"src/wavestack/{path.relative_to(SRC).as_posix()}:{line}: {name}"
        for path in sorted(SRC.rglob("*.py"))
        if NET not in path.parents
        for line, name in _find(path.read_text("utf-8")).proxy_reads
    ]
    assert not offences, "proxy copy read outside net/ (story 1e):\n" + "\n".join(offences)


def test_the_finder_sees_every_spelling():
    source = """
import httpx
import httpx2 as h2
import urllib.request
import requests
from http.client import HTTPSConnection
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from wavestack.net import guard
from wavestack.net.guard import office_proxies

def f():
    httpx.Client(trust_env=True)
    h2.AsyncClient()
    urllib.request.urlopen("https://example.com")
    HTTPSConnection("example.com")
    streamable_http_client("https://example.com/mcp")
    streamable_http_client("https://example.com/mcp", http_client=None)
    streamable_http_client("https://example.com/mcp", http_client=http)
    httpx.get("https://example.com")
    requests.Session()
    Client("https://example.com/mcp")
    return guard._proxies, office_proxies()
"""
    finder = _find(source)
    assert finder.clients == [
        (13, "httpx.Client", "f"),
        (14, "httpx2.AsyncClient", "f"),
        (15, "urllib.request.urlopen", "f"),
        (16, "http.client.HTTPSConnection", "f"),
        (17, NEEDS_HTTP_CLIENT, "f"),
        (18, NEEDS_HTTP_CLIENT, "f"),
        (20, "httpx.get", "f"),
        (21, "requests.Session", "f"),
        (22, "mcp.Client", "f"),
    ]
    assert finder.proxy_reads == [
        (10, "wavestack.net.guard.office_proxies"),
        (23, "wavestack.net.guard._proxies"),
        (23, "wavestack.net.guard.office_proxies"),
    ]
