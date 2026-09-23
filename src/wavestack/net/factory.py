"""Traced HTTP client factory: the only place that creates HTTP clients (AD-15).

Every outbound destination outside the loopback range emits `outbound_request`
via the journal, before the request is sent, tagged with the current scope's
`origin`.
"""

from __future__ import annotations

import ssl

import httpx
import truststore

from wavestack.net.guard import is_loopback
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import current


def _trace_request(request: httpx.Request) -> None:
    if is_loopback(request.url.host):
        return  # AD-15: only destinations outside the loopback range are traced
    scope = current()
    get_journal().emit(
        "outbound_request",
        {
            "origin": scope.origin or "brick",
            "method": request.method,
            "url": str(request.url),
        },
    )


def create_client(*, timeout: float = 5.0) -> httpx.Client:
    """Synchronous httpx client: truststore certs, env proxy, traced requests."""
    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return httpx.Client(
        verify=ctx,
        timeout=timeout,
        trust_env=True,
        event_hooks={"request": [_trace_request]},
    )
