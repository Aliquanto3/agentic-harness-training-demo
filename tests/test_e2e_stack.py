"""Lot D: the end-to-end launcher cuts WaveStack's outbound network itself (no browser).

`tools/e2e/stack.py` gives WaveStack proxy variables that name a loopback port on which
nothing listens: a request to a public host passes the guard, is traced, then fails; the
loopback (fake servers) bypasses the proxy, and so do the launcher's own requests.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socketserver
import sys
import threading
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

from wavestack.net import guard
from wavestack.net.factory import create_client
from wavestack.trace.journal import get_journal

_PATH = Path(__file__).resolve().parents[1] / "tools" / "e2e" / "stack.py"

_INHERITED = {
    "HTTPS_PROXY": "http://proxy.entreprise.example:8080",
    "http_proxy": "http://proxy.entreprise.example:8080",
    "Ftp_Proxy": "http://proxy.entreprise.example:8080",
    "NO_PROXY": "intranet.example",
}


@contextmanager
def _load_stack():
    spec = importlib.util.spec_from_file_location("e2e_stack", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["e2e_stack"] = module  # its dataclass looks its module up while defined
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("e2e_stack", None)


@pytest.fixture
def stack():
    with _load_stack() as module:
        yield module


@pytest.fixture
def closed_port(stack):
    with stack.closed_port() as port:
        yield port


def _apply_proxies(env: dict[str, str], monkeypatch) -> None:
    """Applies `env`'s proxy variables to this process as the launched one ends up with them
    (story 1e): its guard copies them at start-up, for the factory alone, then removes them
    from its environment."""
    for name in [n for n in os.environ if n.lower().endswith("_proxy")]:
        monkeypatch.delenv(name)
    for name, value in env.items():
        if name.lower().endswith("_proxy"):
            monkeypatch.setenv(name, value)
    monkeypatch.setattr(guard, "_proxies", urllib.request.getproxies_environment())
    for name in [n for n in os.environ if n.lower().endswith("_proxy")]:
        monkeypatch.delenv(name)


@pytest.fixture
def workstation_proxy(monkeypatch):
    """A workstation behind an office proxy."""
    for name, value in _INHERITED.items():
        monkeypatch.setenv(name, value)


@pytest.fixture
def launched_env(stack, tmp_path, closed_port, workstation_proxy, monkeypatch):
    """The environment WaveStack gets from the launcher, applied to this process."""
    env = stack._env(tmp_path, closed_port)
    _apply_proxies(env, monkeypatch)
    return env


def test_env_replaces_the_inherited_proxies_and_bypasses_the_loopback(launched_env, closed_port):
    proxies = {k.lower(): v for k, v in launched_env.items() if k.lower().endswith("_proxy")}
    closed = f"http://127.0.0.1:{closed_port}"
    assert proxies == {
        "http_proxy": closed,
        "https_proxy": closed,
        "all_proxy": closed,
        "no_proxy": "127.0.0.1,localhost,::1",
    }
    if sys.platform != "win32":  # both spellings, whichever one a library reads
        assert launched_env["HTTPS_PROXY"] == launched_env["https_proxy"] == closed
    assert "proxy.entreprise.example" not in str(launched_env)


def test_network_option_keeps_the_workstation_proxies(stack, tmp_path, workstation_proxy):
    env = stack._env(tmp_path, None)
    assert env["HTTPS_PROXY"] == _INHERITED["HTTPS_PROXY"]
    assert env["NO_PROXY"] == _INHERITED["NO_PROXY"]


def test_public_host_is_traced_then_fails_through_the_closed_proxy(launched_env):
    before = get_journal().last_seq()
    with create_client() as client, pytest.raises(httpx.ConnectError):
        client.get("https://fr.wikipedia.org/wiki/Mont-Saint-Michel")
    (event,) = get_journal().events_since(before)
    assert event.kind == "outbound_request"
    assert event.payload["url"] == "https://fr.wikipedia.org/wiki/Mont-Saint-Michel"


class _RecordingProxy(socketserver.StreamRequestHandler):
    """A loopback proxy that records each request line and refuses it."""

    lines: list[str] = []

    def handle(self):
        self.lines.append(self.rfile.readline().decode("ascii").strip())
        self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")


@contextmanager
def _serve(server: socketserver.BaseServer) -> Iterator[int]:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


def test_public_host_goes_through_the_launcher_proxy(
    stack, tmp_path, workstation_proxy, monkeypatch
):
    """The proxy the launcher names is the one used: here a listening stub in its place."""
    _RecordingProxy.lines = []
    with _serve(socketserver.ThreadingTCPServer(("127.0.0.1", 0), _RecordingProxy)) as port:
        _apply_proxies(stack._env(tmp_path, port), monkeypatch)
        with create_client() as client, pytest.raises(httpx.ProxyError):
            client.get("https://fr.wikipedia.org/wiki/Mont-Saint-Michel")
    assert _RecordingProxy.lines == ["CONNECT fr.wikipedia.org:443 HTTP/1.1"]


class _Local(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server's name
        body = json.dumps([{"path": self.path}]).encode() if "_e2e" in self.path else b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def test_loopback_is_reached_directly_and_not_traced(launched_env):
    before = get_journal().last_seq()
    with _serve(ThreadingHTTPServer(("127.0.0.1", 0), _Local)) as port:
        with create_client() as client:
            response = client.get(f"http://127.0.0.1:{port}/health")
    assert response.text == "ok"
    assert get_journal().events_since(before) == []


def test_launcher_reaches_the_loopback_whatever_the_workstation_proxy(tmp_path, monkeypatch):
    """`wait_http`, `fake_requests`, `local_requests`: a proxy with no `NO_PROXY` is ignored.
    The launcher is loaded after the proxy is set, as on the workstation (an opener reads
    the proxies when it is built)."""
    for name in [n for n in os.environ if n.lower().endswith("_proxy")]:
        monkeypatch.delenv(name)
    with _load_stack() as reference, reference.closed_port() as closed:
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{closed}")
        with (
            _load_stack() as stack,
            _serve(ThreadingHTTPServer(("127.0.0.1", 0), _Local)) as port,
        ):
            url = f"http://127.0.0.1:{port}"
            stack.wait_http(f"{url}/health", timeout_s=3)
            running = stack.Stack(
                app_url=url, fake_url=url, data_dir=tmp_path, log_dir=tmp_path, app_port=0, env={}
            )
            assert running.fake_requests() == [{"path": "/_e2e/requests"}]
            assert running.local_requests(url) == [{"path": "/_e2e/requests"}]
