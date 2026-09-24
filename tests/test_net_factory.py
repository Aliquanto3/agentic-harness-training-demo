from __future__ import annotations

import httpx
import pytest

from wavestack.net.factory import _trace_request, create_client
from wavestack.net.guard import NetworkBlocked
from wavestack.trace.journal import get_journal


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
