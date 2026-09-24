"""Traced HTTP client factory: the only place that creates HTTP clients (AD-15).

A destination outside `allowed_hosts` and the loopback range is refused
(`NetworkBlocked`) before anything is sent or traced. Every other destination
outside the loopback range emits `outbound_request` (address and exact body)
via the journal, before the request is sent, tagged with the current scope's
`origin`. The hook runs again on every redirect hop.
"""

from __future__ import annotations

import ssl

import httpx
import truststore

from wavestack.config import load_config
from wavestack.net.guard import NetworkBlocked, is_host_allowed, is_loopback
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import current

# Wikimedia refuses generic user agents; header values must stay ASCII.
USER_AGENT = "WaveStack/0.1 (demonstrateur pedagogique)"


def _trace_request(request: httpx.Request) -> None:
    host = request.url.host
    if not is_host_allowed(host, load_config().allowed_hosts):
        raise NetworkBlocked(f"Hôte réseau non autorisé : {host}")
    if is_loopback(host):
        return  # AD-15: only destinations outside the loopback range are traced
    scope = current()
    get_journal().emit(
        "outbound_request",
        {
            "origin": scope.origin or "brick",
            "method": request.method,
            "url": str(request.url),
            "body": request.content.decode("utf-8", "replace"),
        },
    )


def create_client(
    *, timeout: float = 5.0, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """Synchronous httpx client: truststore certs, env proxy, traced requests.

    `transport` is for tests only (`httpx.MockTransport`): nothing leaves the machine.
    """
    ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return httpx.Client(
        verify=ctx,
        timeout=timeout,
        trust_env=True,
        transport=transport,
        headers={"User-Agent": USER_AGENT},
        event_hooks={"request": [_trace_request]},
    )
