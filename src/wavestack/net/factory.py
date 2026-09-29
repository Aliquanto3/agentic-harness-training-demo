"""Traced HTTP client factory: the only place that creates HTTP clients (AD-15).

A destination outside `allowed_hosts` and the loopback range is refused
(`NetworkBlocked`) before anything is sent or traced. Every other destination
outside the loopback range emits `outbound_request` (address and exact body)
via the journal, before the request is sent, tagged with the scope's `origin`.
The hook runs again on every redirect hop. Two clients share this setup: a
synchronous `httpx.Client` and an `httpx2.AsyncClient` (MCP Streamable HTTP).
"""

from __future__ import annotations

import ssl
from collections.abc import Callable

import httpx
import httpx2
import truststore

from wavestack.config import load_config
from wavestack.net.guard import NetworkBlocked, is_host_allowed, is_loopback
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import TraceScope, current

# The body traced for an async redirect hop, whose stream cannot be read again here.
REDIRECT_BODY_NOT_READ = "(corps non relu : redirection)"


def user_agent() -> str:
    """Wikimedia's robot policy wants a way to contact the client (403 without one): the
    `[net] contact` of the configuration (lot D). ASCII only, as header values must be."""
    return f"WaveStack/0.1 (demonstrateur pedagogique; {load_config().net_contact})"


def _check_and_trace(request: httpx.Request | httpx2.Request, scope: TraceScope) -> None:
    host = request.url.host
    if not is_host_allowed(host, load_config().allowed_hosts):
        raise NetworkBlocked(f"Hôte réseau non autorisé : {host}")
    if is_loopback(host):
        return  # AD-15: only destinations outside the loopback range are traced
    get_journal().emit(
        "outbound_request",
        {
            "origin": scope.origin or "brick",
            "method": request.method,
            "url": str(request.url),
            "body": _body(request).decode("utf-8", "replace"),
        },
        scope=scope,
    )


def _body(request: httpx.Request | httpx2.Request) -> bytes:
    """The exact body; a redirect hop's request carries it as a stream not read yet."""
    try:
        return request.content
    except (httpx.RequestNotRead, httpx2.RequestNotRead):
        if isinstance(request, httpx.Request):
            return request.read()  # a byte stream, read again when sent
        return REDIRECT_BODY_NOT_READ.encode()  # an async hop: its stream cannot be re-read


def _trace_request(request: httpx.Request) -> None:
    _check_and_trace(request, current())


def _ssl_context() -> ssl.SSLContext:
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def create_client(
    *, timeout: float | httpx.Timeout = 5.0, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """Synchronous httpx client: truststore certs, env proxy, traced requests.

    Redirects are never followed (AD-15): a caller that accepts one re-checks it by hand,
    and a 3xx from a cloud model is an error, so its key never reaches another host.
    `transport` is for tests only (`httpx.MockTransport`): nothing leaves the machine.
    """
    return httpx.Client(
        verify=_ssl_context(),
        timeout=timeout,
        follow_redirects=False,
        trust_env=True,
        transport=transport,
        headers={"User-Agent": user_agent()},
        event_hooks={"request": [_trace_request]},
    )


def _loopback_only(request: httpx.Request) -> None:
    host = request.url.host
    if not is_loopback(host):
        raise NetworkBlocked(f"Hôte hors boucle locale refusé : {host}")


def create_loopback_client(
    *, timeout: float | httpx.Timeout = 5.0, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """Synchronous httpx client for an already-running local server (Ollama, llama-server):
    no proxy (`trust_env=False`: an office `HTTP_PROXY` would receive `127.0.0.1`, story 1e),
    no redirect, and any host outside the loopback range refused (`NetworkBlocked`) before
    anything is sent. Loopback requests are never traced as `outbound_request` (AD-15).
    `transport` is for tests only (`httpx.MockTransport`)."""
    return httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
        headers={"User-Agent": user_agent()},
        event_hooks={"request": [_loopback_only]},
    )


def create_async_client(
    scope: Callable[[], TraceScope],
    transport: httpx2.AsyncBaseTransport | None = None,
    *,
    timeout: float = 30.0,
) -> httpx2.AsyncClient:
    """Asynchronous httpx2 client, same configuration as `create_client`.

    Requests may leave from a task that does not see the caller's `TraceScope`
    (the MCP transport's writer task): `scope()` gives the one to trace with.
    The read timeout stays long, since a server may hold an event stream open;
    each MCP call is bounded by its own deadline.
    """

    async def trace(request: httpx2.Request) -> None:
        _check_and_trace(request, scope())

    return httpx2.AsyncClient(
        verify=_ssl_context(),
        timeout=httpx2.Timeout(timeout, read=300.0),
        trust_env=True,
        transport=transport,
        headers={"User-Agent": user_agent()},
        event_hooks={"request": [trace]},
    )
