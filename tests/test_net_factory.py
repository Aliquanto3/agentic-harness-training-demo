from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import httpx2
import pytest

from wavestack.config import (
    DEFAULT_NET_CONTACT,
    PUBLIC_RESPONSE_HEADERS,
    PUBLIC_RESPONSE_PREFIXES,
    load_config,
)
from wavestack.net import guard
from wavestack.net.factory import (
    MASKED,
    PUBLIC_HEADERS,
    _proxy_map,
    _trace_request,
    create_async_client,
    create_client,
)
from wavestack.net.guard import NetworkBlocked
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import TraceScope


def test_loopback_requests_are_not_traced():
    before = get_journal().last_seq()
    _trace_request(httpx.Request("GET", "http://127.0.0.1:11434/api/tags"))
    assert get_journal().events_since(before) == []


def test_non_loopback_requests_emit_outbound_request():
    before = get_journal().last_seq()
    _trace_request(httpx.Request("GET", "https://huggingface.co/"))
    events = get_journal().events_since(before)
    assert len(events) == 1
    assert events[0].kind == "outbound_request"
    assert events[0].payload["url"] == "https://huggingface.co/"


def _client(handler):
    return create_client(transport=httpx.MockTransport(handler))


def _as_traced(raw: list[tuple[bytes, bytes]]) -> list[dict[str, object]]:
    """The expected trace of headers sent: all public here, so in clear, in order and case."""
    return [
        {"name": name.decode("latin-1"), "value": value.decode("latin-1"), "masked": False}
        for name, value in raw
    ]


def test_host_outside_allowed_hosts_is_refused_before_sending_or_tracing():
    sent = []
    before = get_journal().last_seq()
    with _client(lambda r: sent.append(r) or httpx.Response(200)) as client:
        with pytest.raises(NetworkBlocked):
            client.get("https://example.com/")
    assert sent == [] and get_journal().events_since(before) == []


def test_trace_carries_the_exact_body_before_sending():
    sent = []
    before = get_journal().last_seq()
    with _client(lambda r: sent.append(r) or httpx.Response(200)) as client:
        client.post("https://fr.wikipedia.org/x", content=b'{"q": "Paris"}')
    (event,) = get_journal().events_since(before)
    assert event.payload == {
        "origin": "brick",
        "method": "POST",
        "url": "https://fr.wikipedia.org/x",
        "headers": _as_traced(sent[0].headers.raw),
        "body": '{"q": "Paris"}',
    }
    assert sent[0].content == b'{"q": "Paris"}'
    assert sent[0].headers["user-agent"].startswith("WaveStack/")


def test_every_redirect_hop_is_checked_again():
    def handler(request):
        if request.url.host == "fr.wikipedia.org":
            return httpx.Response(302, headers={"location": "https://example.com/"})
        return httpx.Response(200)

    sent = []
    before = get_journal().last_seq()
    with _client(lambda r: sent.append(r) or handler(r)) as client:
        with pytest.raises(NetworkBlocked):
            client.get("https://fr.wikipedia.org/wiki/Paris", follow_redirects=True)
    assert [r.url.host for r in sent] == ["fr.wikipedia.org"]
    assert [e.payload["url"] for e in get_journal().events_since(before)] == [
        "https://fr.wikipedia.org/wiki/Paris"
    ]


# Lot D: Wikimedia answers 403 to a user agent without a way to contact its client.
_CONTACT = re.compile(r"https://\S+|[\w.+-]+@[\w-]+\.[\w.-]+")


def _assert_user_agent_has_a_contact(user_agent: str) -> None:
    assert user_agent.startswith("WaveStack/")
    assert user_agent.isascii()
    assert _CONTACT.search(user_agent), user_agent


def _sent_user_agent() -> str:
    sent = []
    with _client(lambda r: sent.append(r) or httpx.Response(200)) as client:
        client.get("https://fr.wikipedia.org/wiki/Paris")
    return sent[0].headers["user-agent"]


def _set_contact(value: object) -> None:
    path = Path(os.environ["WAVESTACK_DATA_DIR"]) / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"net": {"contact": value}}), encoding="utf-8")


def test_sent_user_agent_carries_the_configured_contact_in_ascii():
    assert load_config().net_contact == DEFAULT_NET_CONTACT
    user_agent = _sent_user_agent()
    _assert_user_agent_has_a_contact(user_agent)
    assert DEFAULT_NET_CONTACT in user_agent


def test_a_net_contact_override_is_sent():
    _set_contact("formation-ia@exemple.fr")
    user_agent = _sent_user_agent()
    _assert_user_agent_has_a_contact(user_agent)
    assert "formation-ia@exemple.fr" in user_agent
    assert DEFAULT_NET_CONTACT not in user_agent


@pytest.mark.parametrize("value", ["", "   ", 42, "équipe@exemple.fr", "a) b", "x\r\nX: y"])
def test_an_invalid_net_contact_falls_back_to_the_default(value):
    _set_contact(value)
    user_agent = _sent_user_agent()
    _assert_user_agent_has_a_contact(user_agent)
    assert DEFAULT_NET_CONTACT in user_agent


# ---------- story 6: the async client (MCP Streamable HTTP) ----------


def _async_exchange(url: str, scope: TraceScope) -> list[httpx2.Request]:
    sent: list[httpx2.Request] = []

    async def handler(request):
        sent.append(request)
        return httpx2.Response(200)

    async def run():
        async with create_async_client(lambda: scope, httpx2.MockTransport(handler)) as client:
            await client.post(url, content=b'{"jsonrpc": "2.0"}')

    asyncio.run(run())
    return sent


def test_async_client_traces_with_the_given_scope_before_sending():
    scope = TraceScope(turn_id="t9", component="mcp.mslearn", origin="brick")
    before = get_journal().last_seq()

    sent = _async_exchange("https://learn.microsoft.com/api/mcp", scope)

    (event,) = get_journal().events_since(before)
    assert (event.turn_id, event.component) == ("t9", "mcp.mslearn")
    assert event.payload == {
        "origin": "brick",
        "method": "POST",
        "url": "https://learn.microsoft.com/api/mcp",
        "headers": _as_traced(sent[0].headers.raw),
        "body": '{"jsonrpc": "2.0"}',
    }
    _assert_user_agent_has_a_contact(sent[0].headers["user-agent"])


def test_async_client_refuses_a_host_outside_the_list_before_sending():
    before = get_journal().last_seq()
    with pytest.raises(NetworkBlocked):
        _async_exchange("https://example.com/mcp", TraceScope())
    assert get_journal().events_since(before) == []


# ---------- story 23: the headers sent, secrets masked before the journal ----------

SECRET = "sk-SENTINEL-0123456789abcdef-SECRET"


def _headers_of(event) -> list[tuple[str, str, bool]]:
    return [(h["name"], h["value"], h["masked"]) for h in event.payload["headers"]]


def test_get_traces_its_headers_in_the_order_sent_with_the_contact():
    sent = []
    before = get_journal().last_seq()
    with _client(lambda r: sent.append(r) or httpx.Response(200)) as client:
        client.get("https://calendrier.api.gouv.fr/jours-feries/metropole/2026.json")
    (event,) = get_journal().events_since(before)

    names = [name for name, _, _ in _headers_of(event)]
    assert names == [n.decode("latin-1") for n, _ in sent[0].headers.raw]
    assert names[:4] == ["Host", "Accept", "Accept-Encoding", "Connection"]
    headers = {name: (value, masked) for name, value, masked in _headers_of(event)}
    assert headers["Host"] == ("calendrier.api.gouv.fr", False)
    assert headers["Accept"] == ("*/*", False)
    user_agent, masked = headers["User-Agent"]
    assert not masked and user_agent.startswith("WaveStack/0.1 (demonstrateur pedagogique; ")
    assert DEFAULT_NET_CONTACT in user_agent
    assert not any(masked for _, _, masked in _headers_of(event))


def test_post_traces_content_type_and_length_in_clear():
    before = get_journal().last_seq()
    with _client(lambda r: httpx.Response(200)) as client:
        client.post(
            "https://fr.wikipedia.org/x",
            content=b'{"q":1}',
            headers={"Content-Type": "application/json"},
        )
    (event,) = get_journal().events_since(before)
    headers = {name: (value, masked) for name, value, masked in _headers_of(event)}
    assert headers["Content-Type"] == ("application/json", False)
    assert headers["Content-Length"] == ("7", False)


_SECRET_HEADERS = {
    "Authorization": f"Bearer {SECRET}",
    "x-api-key": SECRET,
    "Cookie": f"session={SECRET}",
    "Proxy-Authorization": f"Basic {SECRET}",
    "Mcp-Session-Id": SECRET,
    "X-Custom": SECRET,
    "Last-Event-ID": SECRET,  # a server-issued resume cursor, like Mcp-Session-Id
}


def _assert_secrets_masked(event) -> None:
    traced = {name: (value, masked) for name, value, masked in _headers_of(event)}
    for name in _SECRET_HEADERS:
        assert traced[name] == (MASKED, True), name
    assert traced["User-Agent"][1] is False
    text = event.model_dump_json()
    for fragment in (SECRET, SECRET[:4], SECRET[-4:], "SENTINEL"):
        assert fragment not in text


def test_every_header_outside_the_allow_list_is_masked_before_the_journal():
    sent = []
    before = get_journal().last_seq()
    with _client(lambda r: sent.append(r) or httpx.Response(200)) as client:
        client.get("https://fr.wikipedia.org/wiki/Paris", headers=_SECRET_HEADERS)
    (event,) = get_journal().events_since(before)

    _assert_secrets_masked(event)
    assert sent[0].headers["authorization"] == f"Bearer {SECRET}"  # sent unchanged


def test_the_allow_list_is_closed_and_the_mask_is_one_constant():
    assert PUBLIC_HEADERS == {
        "host",
        "accept",
        "accept-encoding",
        "accept-language",
        "cache-control",
        "connection",
        "content-length",
        "content-type",
        "mcp-protocol-version",
        "user-agent",
    }
    assert MASKED == "[masqué]"


def test_async_client_masks_the_same_headers():
    scope = TraceScope(component="mcp.datagouv", origin="brick")

    async def handler(request):
        return httpx2.Response(200)

    async def run():
        async with create_async_client(lambda: scope, httpx2.MockTransport(handler)) as client:
            await client.post(
                "https://mcp.data.gouv.fr/mcp",
                content=b"{}",
                headers={**_SECRET_HEADERS, "Mcp-Protocol-Version": "2025-06-18"},
            )

    before = get_journal().last_seq()
    asyncio.run(run())
    (event,) = get_journal().events_since(before)

    _assert_secrets_masked(event)
    traced = {name: (value, masked) for name, value, masked in _headers_of(event)}
    assert traced["Mcp-Protocol-Version"] == ("2025-06-18", False)


# ---------- recette du 02/10 (R2): an error response leaves its proof ----------

_REFUSAL_HEADERS = [
    ("Content-Type", "application/json"),
    ("x-request-id", SECRET),
    ("X-RateLimit-Limit-Req-Minute", "0"),
    ("Set-Cookie", f"session={SECRET}"),
    ("ratelimit-reset", "60"),
    ("Retry-After", "60"),
    ("Date", "Fri, 02 Oct 2026 09:00:00 GMT"),
]
_REFUSAL_TRACED = [
    {"name": "Content-Type", "value": "application/json", "masked": False},
    {"name": "x-request-id", "value": MASKED, "masked": True},
    {"name": "X-RateLimit-Limit-Req-Minute", "value": "0", "masked": False},
    {"name": "Set-Cookie", "value": MASKED, "masked": True},
    {"name": "ratelimit-reset", "value": "60", "masked": False},
    {"name": "Retry-After", "value": "60", "masked": False},
    {"name": "Date", "value": "Fri, 02 Oct 2026 09:00:00 GMT", "masked": False},
]


def _refusal(request) -> httpx.Response:  # noqa: ANN001
    return httpx.Response(429, headers=_REFUSAL_HEADERS, content=b'{"message": "Rate limit"}')


def _assert_refusal_traced(events, origin: str) -> None:
    assert [e.kind for e in events] == ["outbound_request", "outbound_response"]
    response = events[1]
    # `content-length` is added by the response itself: public, after the headers given.
    headers = [h for h in response.payload["headers"] if h["name"].lower() != "content-length"]
    assert {**response.payload, "headers": headers} == {
        "origin": origin,
        "method": "POST",
        "url": "https://fr.wikipedia.org/x",
        "status": 429,
        "headers": _REFUSAL_TRACED,
    }
    text = response.model_dump_json()
    for fragment in (SECRET, SECRET[:4], SECRET[-4:], "SENTINEL"):
        assert fragment not in text


def test_an_error_response_is_traced_with_its_quota_headers_and_the_rest_masked():
    before = get_journal().last_seq()
    with _client(_refusal) as client:
        response = client.post("https://fr.wikipedia.org/x", content=b"{}")
    assert response.status_code == 429 and response.headers["x-request-id"] == SECRET
    _assert_refusal_traced(get_journal().events_since(before), "brick")


def test_the_async_client_traces_an_error_response_the_same_way():
    scope = TraceScope(component="mcp.datagouv", origin="brick")

    async def handler(request):
        return httpx2.Response(429, headers=_REFUSAL_HEADERS, content=b"{}")

    async def run():
        async with create_async_client(lambda: scope, httpx2.MockTransport(handler)) as client:
            await client.post("https://fr.wikipedia.org/x", content=b"{}")

    before = get_journal().last_seq()
    asyncio.run(run())
    _assert_refusal_traced(get_journal().events_since(before), "brick")


@pytest.mark.parametrize("status", [200, 204, 302, 399])
def test_a_response_below_400_is_not_traced(status):
    before = get_journal().last_seq()
    with _client(lambda r: httpx.Response(status, headers={"x-ratelimit-limit": "0"})) as client:
        client.get("https://fr.wikipedia.org/wiki/Paris")
    assert [e.kind for e in get_journal().events_since(before)] == ["outbound_request"]


def test_an_error_response_from_the_loopback_is_not_traced():
    before = get_journal().last_seq()
    with _client(lambda r: httpx.Response(500)) as client:
        assert client.get("http://127.0.0.1:11434/api/tags").status_code == 500
    assert get_journal().events_since(before) == []


def test_both_hooks_ask_the_same_predicate(monkeypatch):
    """`_traced` decides for the request and its error response alike (the E2E graft)."""
    from wavestack.net import factory

    monkeypatch.setattr(factory, "_traced", lambda request: True)
    before = get_journal().last_seq()
    with _client(lambda r: httpx.Response(500)) as client:
        client.get("http://127.0.0.1:11434/api/tags")
    assert [e.kind for e in get_journal().events_since(before)] == [
        "outbound_request",
        "outbound_response",
    ]

    monkeypatch.setattr(factory, "_traced", lambda request: False)
    before = get_journal().last_seq()
    with _client(_refusal) as client:
        client.post("https://fr.wikipedia.org/x", content=b"{}")
    assert get_journal().events_since(before) == []


def test_the_response_allow_list_is_closed():
    assert PUBLIC_RESPONSE_HEADERS == {"content-type", "content-length", "date", "retry-after"}
    assert PUBLIC_RESPONSE_PREFIXES == ("x-ratelimit-", "ratelimit-")


def test_each_redirect_hop_traces_its_own_headers():
    def handler(request):
        if request.url.path == "/wiki/Paris":
            return httpx.Response(302, headers={"location": "https://fr.wikipedia.org/wiki/Lyon"})
        return httpx.Response(200)

    sent = []
    before = get_journal().last_seq()
    with _client(lambda r: sent.append(r) or handler(r)) as client:
        client.get(
            "https://fr.wikipedia.org/wiki/Paris",
            headers={"Accept-Language": "fr"},
            follow_redirects=True,
        )
    events = get_journal().events_since(before)

    assert [e.payload["url"] for e in events] == [
        "https://fr.wikipedia.org/wiki/Paris",
        "https://fr.wikipedia.org/wiki/Lyon",
    ]
    for event, request in zip(events, sent, strict=True):
        assert event.payload["headers"] == _as_traced(request.headers.raw)
        assert ("Accept-Language", "fr", False) in _headers_of(event)


# ---------- story 1e: the factory alone holds the workstation's proxy ----------


class _RecordingProxy(socketserver.StreamRequestHandler):
    """A loopback proxy that records each request (line and headers) and refuses it."""

    requests: list[list[str]] = []

    def handle(self):
        lines = []
        while line := self.rfile.readline().decode("latin-1").strip():
            lines.append(line)
        self.requests.append(lines)
        self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")


class _Local(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server's name
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@contextmanager
def _serve(server: socketserver.BaseServer) -> Iterator[int]:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def proxy_port() -> Iterator[int]:
    _RecordingProxy.requests = []
    with _serve(socketserver.ThreadingTCPServer(("127.0.0.1", 0), _RecordingProxy)) as port:
        yield port


def _confiscated(monkeypatch, **proxies: str) -> None:
    """The guard's copy of the workstation's proxy, as `install` would have taken it."""
    monkeypatch.setattr(guard, "_proxies", proxies)


WIKI = "https://fr.wikipedia.org/wiki/Mont-Saint-Michel"
CONNECT_WIKI = "CONNECT fr.wikipedia.org:443 HTTP/1.1"


def test_factory_goes_out_through_the_confiscated_proxy_after_tracing(proxy_port, monkeypatch):
    _confiscated(monkeypatch, https=f"http://127.0.0.1:{proxy_port}")
    assert not [n for n in os.environ if n.lower().endswith("_proxy")]  # only the copy
    before = get_journal().last_seq()
    with create_client() as client, pytest.raises(httpx.ProxyError):
        client.get(WIKI)
    (event,) = get_journal().events_since(before)
    assert (event.kind, event.payload["url"]) == ("outbound_request", WIKI)
    assert [r[0] for r in _RecordingProxy.requests] == [CONNECT_WIKI]


def test_async_factory_goes_out_through_the_same_proxy(proxy_port, monkeypatch):
    _confiscated(monkeypatch, https=f"http://127.0.0.1:{proxy_port}")

    async def run():
        async with create_async_client(TraceScope) as client:
            await client.get(WIKI)

    before = get_journal().last_seq()
    with pytest.raises(httpx2.ProxyError):
        asyncio.run(run())
    assert [e.kind for e in get_journal().events_since(before)] == ["outbound_request"]
    assert [r[0] for r in _RecordingProxy.requests] == [CONNECT_WIKI]


def test_factory_refuses_a_host_off_the_list_before_the_proxy(proxy_port, monkeypatch):
    _confiscated(monkeypatch, https=f"http://127.0.0.1:{proxy_port}")
    before = get_journal().last_seq()
    with create_client() as client, pytest.raises(NetworkBlocked):
        client.get("https://example.com/")
    assert _RecordingProxy.requests == [] and get_journal().events_since(before) == []


def test_a_proxy_without_scheme_is_taken_as_http(proxy_port, monkeypatch):
    _confiscated(monkeypatch, https=f"127.0.0.1:{proxy_port}")
    with create_client() as client, pytest.raises(httpx.ProxyError):
        client.get(WIKI)
    assert [r[0] for r in _RecordingProxy.requests] == [CONNECT_WIKI]


def test_proxy_credentials_reach_the_proxy_only(proxy_port, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    _confiscated(monkeypatch, https=f"http://user:s3cr3t@127.0.0.1:{proxy_port}")
    before = get_journal().last_seq()
    with create_client() as client, pytest.raises(httpx.ProxyError):
        client.get(WIKI)
    credentials = base64.b64encode(b"user:s3cr3t").decode()
    (request,) = _RecordingProxy.requests
    assert request[0] == CONNECT_WIKI
    assert f"Proxy-Authorization: Basic {credentials}" in request
    traced = "".join(e.model_dump_json() for e in get_journal().events_since(before))
    for text in (traced, caplog.text):
        assert "s3cr3t" not in text and credentials not in text


def test_the_loopback_never_goes_through_the_proxy(proxy_port, monkeypatch):
    proxy = f"http://127.0.0.1:{proxy_port}"
    _confiscated(monkeypatch, http=proxy, https=proxy, all=proxy)  # and no NO_PROXY
    before = get_journal().last_seq()
    with _serve(ThreadingHTTPServer(("127.0.0.1", 0), _Local)) as port:
        with create_client() as client:
            assert client.get(f"http://127.0.0.1:{port}/").text == "ok"
            assert client.get(f"http://localhost:{port}/").text == "ok"
    assert _RecordingProxy.requests == [] and get_journal().events_since(before) == []


def test_no_proxy_follows_the_httpx_rule(monkeypatch):
    proxy = "http://127.0.0.1:9000"
    loopback = {"all://127.0.0.1": None, "all://localhost": None, "all://[::1]": None}
    _confiscated(
        monkeypatch,
        https=proxy,
        all="127.0.0.1:9000",
        no="intranet.example, 10.0.0.0/8,fe80::1,fd00::/8",
    )
    assert _proxy_map() == {
        "https://": proxy,
        "all://": proxy,
        "all://*intranet.example": None,
        "all://10.0.0.0/8": None,
        "all://[fe80::1]": None,
        "all://[fd00::]/8": None,
        **loopback,
    }
    _confiscated(monkeypatch, https=proxy, no="intranet.example,*")
    assert _proxy_map() == {}
    _confiscated(monkeypatch, no="intranet.example")
    assert _proxy_map() == {}


def test_factory_clients_build_with_no_proxy_subnets(monkeypatch):
    """An IPv6 subnet inside the brackets (`[fe80::/10]`) is an invalid URL for httpx: every
    factory client would fail to build."""
    _confiscated(monkeypatch, https="http://127.0.0.1:9", no="10.0.0.0/8,fe80::/10")
    with create_client():
        pass

    async def build():
        async with create_async_client(TraceScope):
            pass

    asyncio.run(build())


def test_async_factory_reaches_the_loopback_directly(proxy_port, monkeypatch):
    proxy = f"http://127.0.0.1:{proxy_port}"
    _confiscated(monkeypatch, http=proxy, https=proxy, all=proxy)  # and no NO_PROXY

    async def get(url: str) -> str:
        async with create_async_client(TraceScope) as client:
            return (await client.get(url)).text

    before = get_journal().last_seq()
    with _serve(ThreadingHTTPServer(("127.0.0.1", 0), _Local)) as port:
        assert asyncio.run(get(f"http://127.0.0.1:{port}/")) == "ok"
    assert _RecordingProxy.requests == [] and get_journal().events_since(before) == []


def test_proxy_credentials_stay_hidden_when_the_proxy_is_unreachable(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    with socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler) as server:
        closed = server.server_address[1]  # closed once the server is
    _confiscated(monkeypatch, https=f"http://user:s3cr3t@127.0.0.1:{closed}")
    before = get_journal().last_seq()
    with create_client() as client, pytest.raises(httpx.ConnectError) as raised:
        client.get(WIKI)
    credentials = base64.b64encode(b"user:s3cr3t").decode()
    traced = "".join(e.model_dump_json() for e in get_journal().events_since(before))
    assert traced  # the request was traced before the proxy failed
    for text in (traced, caplog.text, str(raised.value)):
        assert "s3cr3t" not in text and credentials not in text


def test_a_no_proxy_host_is_reached_directly(proxy_port, monkeypatch):
    """Direct, the host is resolved here: the session guard (nothing allowed) refuses it."""
    _confiscated(monkeypatch, https=f"http://127.0.0.1:{proxy_port}", no="wikipedia.org")
    with create_client() as client, pytest.raises(NetworkBlocked):
        client.get(WIKI)
    assert _RecordingProxy.requests == []


def test_an_injected_transport_mounts_no_proxy(monkeypatch):
    _confiscated(monkeypatch, https="http://127.0.0.1:9", all="http://127.0.0.1:9")
    with create_client(transport=httpx.MockTransport(lambda r: httpx.Response(204))) as client:
        assert client.get(WIKI).status_code == 204

    async def run():
        transport = httpx2.MockTransport(lambda r: httpx2.Response(204))
        async with create_async_client(TraceScope, transport) as client:
            return (await client.get(WIKI)).status_code

    assert asyncio.run(run()) == 204
