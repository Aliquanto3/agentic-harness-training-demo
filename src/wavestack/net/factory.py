"""Traced HTTP client factory: the only place that creates HTTP clients (AD-15).

A destination outside `allowed_hosts` and the loopback range is refused
(`NetworkBlocked`) before anything is sent or traced. Every other destination
outside the loopback range emits `outbound_request` (address, headers and exact
body) via the journal, before the request is sent, tagged with the scope's
`origin`. The hook runs again on every redirect hop, with that hop's headers.

Headers are traced in the order and case they are sent. Only the closed
allow-list `config.PUBLIC_HEADERS` keeps its value: any other header (a cloud key
under whatever name its entry declares, which may not be a public one, a cookie,
`Mcp-Session-Id`, `Last-Event-ID`, an unknown one) keeps its name, but its value
becomes `MASKED` here, before `emit`, so it never enters the journal (AD-15,
story 23). Only request-level headers are seen: what the transport adds below
the event hook (proxy credentials, HTTP/2 pseudo-headers) is neither traced nor
shown.

A response of status 400 or more from the same destinations emits `outbound_response`
(status and headers received, story recette 02/10, R2), so a provider's refusal leaves
its proof in the journal: the same masking, against the closed allow-list
`config.PUBLIC_RESPONSE_HEADERS` and the quota prefixes `config.PUBLIC_RESPONSE_PREFIXES`.

Two clients share this setup: a synchronous `httpx.Client` and an
`httpx2.AsyncClient` (MCP Streamable HTTP). Both reach the outside through the
workstation's proxy, confiscated by the guard (story 1e): `trust_env=False`, and
explicit proxy mounts built from `guard.office_proxies()`, since no other client
of the process can find that proxy any more.
"""

from __future__ import annotations

import ipaddress
import ssl
from collections.abc import Callable

import httpx
import httpx2
import truststore

from wavestack.config import (
    PUBLIC_HEADERS,
    PUBLIC_RESPONSE_HEADERS,
    PUBLIC_RESPONSE_PREFIXES,
    load_config,
)
from wavestack.messages import Message
from wavestack.net.guard import NetworkBlocked, is_host_allowed, is_loopback, office_proxies
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import TraceScope, current

# The body traced for an async redirect hop, whose stream cannot be read again here.
REDIRECT_BODY_NOT_READ = "(corps non relu : redirection)"

# The value traced in place of any header outside `PUBLIC_HEADERS`.
MASKED = "[masqué]"


def user_agent() -> str:
    """Wikimedia's robot policy wants a way to contact the client (403 without one): the
    `[net] contact` of the configuration (lot D). ASCII only, as header values must be."""
    return f"WaveStack/0.1 (demonstrateur pedagogique; {load_config().net_contact})"


def _check_and_trace(
    request: httpx.Request | httpx2.Request,
    scope: TraceScope,
    extra: dict[str, object] | None = None,
) -> None:
    host = request.url.host
    if not is_host_allowed(host, load_config().allowed_hosts):
        raise NetworkBlocked(Message("net.host_refused", host=host))
    if not _traced(request):
        return  # AD-15: only destinations outside the loopback range are traced
    get_journal().emit(
        "outbound_request",
        {
            "origin": scope.origin or "brick",
            "method": request.method,
            "url": str(request.url),
            "headers": _headers(request),
            "body": _body(request).decode("utf-8", "replace"),
        }
        | (extra or {}),
        scope=scope,
    )


def _traced(request: httpx.Request | httpx2.Request) -> bool:
    """Whether the factory traces this request and its error response: any destination
    outside the loopback range (AD-15). The one predicate of both hooks."""
    return not is_loopback(request.url.host)


def _trace_response(response: httpx.Response | httpx2.Response, scope: TraceScope) -> None:
    """R2: a refusal (status 400 or more) from a traced destination, with its status and
    headers as received, before the caller reads its body."""
    request = response.request
    if response.status_code < 400 or not _traced(request):
        return
    get_journal().emit(
        "outbound_response",
        {
            "origin": scope.origin or "brick",
            "method": request.method,
            "url": str(request.url),
            "status": response.status_code,
            "headers": _masked(response.headers.raw, _public_response_header),
        },
        scope=scope,
    )


def _public_response_header(name: str) -> bool:
    lowered = name.lower()
    return lowered in PUBLIC_RESPONSE_HEADERS or lowered.startswith(PUBLIC_RESPONSE_PREFIXES)


def _masked(
    raw: list[tuple[bytes, bytes]], public: Callable[[str], bool]
) -> list[dict[str, object]]:
    """Headers in order and case (decoded in latin-1), each value whose name is not
    `public` replaced by `MASKED` before it can reach the journal."""
    headers: list[dict[str, object]] = []
    for raw_name, raw_value in raw:
        name = raw_name.decode("latin-1")
        if public(name):
            headers.append({"name": name, "value": raw_value.decode("latin-1"), "masked": False})
        else:
            headers.append({"name": name, "value": MASKED, "masked": True})
    return headers


def _headers(request: httpx.Request | httpx2.Request) -> list[dict[str, object]]:
    """The headers as sent (order and case of `headers.raw`, decoded in latin-1), each value
    outside `PUBLIC_HEADERS` replaced by `MASKED` before it can reach the journal."""
    return _masked(request.headers.raw, lambda name: name.lower() in PUBLIC_HEADERS)


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


def _trace_sync_response(response: httpx.Response) -> None:
    _trace_response(response, current())


def _ssl_context() -> ssl.SSLContext:
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


# Story 1e: the loopback never goes through the proxy, whatever NO_PROXY says.
_LOOPBACK_PATTERNS = ("all://127.0.0.1", "all://localhost", "all://[::1]")


def _is_ip(host: str, version: int) -> bool:
    try:
        return ipaddress.ip_address(host.split("/")[0]).version == version
    except ValueError:
        return False


def _proxy_map() -> dict[str, str | None]:
    """URL pattern -> proxy URL (`None`: direct), from the confiscated proxy.

    The rule of httpx 0.28 (`httpx._utils.get_environment_proxies`, private, hence copied):
    schemes `http`, `https`, `all`; a URL without a scheme gets `http://`; `NO_PROXY`
    (`*` = no proxy at all, IPv4, IPv6, `localhost`, a domain and its subdomains).
    Plus the loopback, always direct.
    """
    proxies = office_proxies()
    mounts: dict[str, str | None] = {}
    for scheme in ("http", "https", "all"):
        if url := proxies.get(scheme):
            mounts[f"{scheme}://"] = url if "://" in url else f"http://{url}"
    if not mounts:
        return {}
    for host in (h.strip() for h in proxies.get("no", "").split(",")):
        if host == "*":
            return {}
        if not host:
            continue
        if "://" in host:
            mounts[host] = None
        elif _is_ip(host, 4) or host.lower() == "localhost":
            mounts[f"all://{host}"] = None
        elif _is_ip(host, 6):  # a subnet stays outside the brackets (`[fe80::]/10`)
            address, slash, subnet = host.partition("/")
            mounts[f"all://[{address}]{slash}{subnet}"] = None
        else:
            mounts[f"all://*{host}"] = None
    for pattern in _LOOPBACK_PATTERNS:
        mounts[pattern] = None
    return mounts


def _proxy_mounts[T](transport: Callable[[str], T]) -> dict[str, T | None]:
    """The mounts of a factory client: one proxy `transport(url)` per scheme, `None` for a
    destination reached directly (the client's own transport)."""
    return {
        pattern: None if url is None else transport(url) for pattern, url in _proxy_map().items()
    }


def create_client(
    *, timeout: float | httpx.Timeout = 5.0, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """Synchronous httpx client: truststore certs, the workstation's proxy (confiscated by
    the guard, story 1e), traced requests.

    Redirects are never followed (AD-15): a caller that accepts one re-checks it by hand,
    and a 3xx from a cloud model is an error, so its key never reaches another host.
    `transport` is for tests only (`httpx.MockTransport`): nothing leaves the machine, and
    no proxy is mounted (as httpx does with an injected transport).
    """
    verify = _ssl_context()
    mounts = None
    if transport is None:
        mounts = _proxy_mounts(lambda url: httpx.HTTPTransport(proxy=url, verify=verify))
    return httpx.Client(
        verify=verify,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
        mounts=mounts,
        headers={"User-Agent": user_agent()},
        event_hooks={"request": [_trace_request], "response": [_trace_sync_response]},
    )


def _loopback_only(request: httpx.Request) -> None:
    host = request.url.host
    if not is_loopback(host):
        raise NetworkBlocked(Message("net.loopback_refused", host=host))


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
    annotate: Callable[[httpx2.Request], dict[str, object]] | None = None,
) -> httpx2.AsyncClient:
    """Asynchronous httpx2 client, same configuration as `create_client`.

    Requests may leave from a task that does not see the caller's `TraceScope`
    (the MCP transport's writer task): `scope()` gives the one to trace with.
    The read timeout stays long, since a server may hold an event stream open;
    each MCP call is bounded by its own deadline. `annotate(request)` (lot 4 of 2026-10-04,
    the MCP workshop): fields added to the request's `outbound_request` (`message_seq`).
    """

    async def trace(request: httpx2.Request) -> None:
        _check_and_trace(request, scope(), annotate(request) if annotate else None)

    async def trace_response(response: httpx2.Response) -> None:
        _trace_response(response, scope())

    verify = _ssl_context()
    mounts = None
    if transport is None:
        mounts = _proxy_mounts(lambda url: httpx2.AsyncHTTPTransport(proxy=url, verify=verify))
    return httpx2.AsyncClient(
        verify=verify,
        timeout=httpx2.Timeout(timeout, read=300.0),
        trust_env=False,
        transport=transport,
        mounts=mounts,
        headers={"User-Agent": user_agent()},
        event_hooks={"request": [trace], "response": [trace_response]},
    )
