from __future__ import annotations

import httpx

from wavestack.net.factory import _trace_request
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
