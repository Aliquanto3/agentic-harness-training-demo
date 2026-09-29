from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import httpx
import httpx2
import pytest

from wavestack.config import DEFAULT_NET_CONTACT, load_config
from wavestack.net.factory import (
    MASKED,
    PUBLIC_HEADERS,
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
