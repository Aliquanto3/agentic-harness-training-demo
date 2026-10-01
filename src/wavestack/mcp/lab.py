"""The MCP workshop (`/mcp`, corrections of 2026-09-30, story 6): the protocol laid bare.

The workshop opens connections of its own, never the brick's (a sandbox): a
`LabConnection` is an `McpConnection` whose transport is tapped. Every JSON-RPC message
the SDK's session writes to the transport, or reads from it, is captured as it passes,
serialized as the transport serializes it (`model_dump_json(by_alias=True,
exclude_unset=True)`), and handed to the session, which emits it as `mcp_lab_message`.
The capture is real, never reconstructed: `mcp.Client` accepts any `Transport` (an async
context manager yielding the read and write streams), and the tap wraps both streams
between the transport and the session.

Also here: the page's texts (`content/mcp_lab.yaml`, AD-19) and the line a tool gets in
`load_tool_doc`'s catalog (AD-25), shared with the session's `_doc_catalog`.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace
from typing import Any

import yaml
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp_types import CallToolResult, JSONRPCNotification, JSONRPCRequest
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.mcp.connection import McpConnection
from wavestack.mcp.servers import McpServer
from wavestack.trace.scope import TraceScope

# The methods the workshop explains, in the order of a real exchange.
METHODS = ("initialize", "notifications/initialized", "tools/list", "tools/call")
TRANSPORTS = ("stdio", "streamable_http")


# ---------- the page's texts (content/mcp_lab.yaml, AD-19) ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransportText(_Strict):
    label_text: str = Field(min_length=1)
    explain_text: str = Field(min_length=1)


class McpLabContent(_Strict):
    """`content/mcp_lab.yaml`: the page's pedagogical texts, a text per transport and per
    JSON-RPC method the page explains (the interface's labels are in `ui.yaml`, `mcp`)."""

    title_text: str = Field(min_length=1)
    intro_text: str = Field(min_length=1)
    busy_text: str = Field(min_length=1)
    servers_title_text: str = Field(min_length=1)
    servers_help_text: str = Field(min_length=1)
    handshake_title_text: str = Field(min_length=1)
    handshake_help_text: str = Field(min_length=1)
    handshake_empty_text: str = Field(min_length=1)
    tools_title_text: str = Field(min_length=1)
    tools_help_text: str = Field(min_length=1)
    tools_empty_text: str = Field(min_length=1)
    call_title_text: str = Field(min_length=1)
    call_help_text: str = Field(min_length=1)
    call_empty_text: str = Field(min_length=1)
    context_title_text: str = Field(min_length=1)
    context_help_text: str = Field(min_length=1)
    context_empty_text: str = Field(min_length=1)
    reinjected_help_text: str = Field(min_length=1)
    transports: dict[str, TransportText]
    methods: dict[str, str]

    @model_validator(mode="after")
    def _every_transport_and_method(self) -> McpLabContent:
        if set(self.transports) != set(TRANSPORTS):
            raise ValueError(f"transports : il faut exactement {', '.join(TRANSPORTS)}")
        if set(self.methods) != set(METHODS):
            raise ValueError(f"methods : il faut exactement {', '.join(METHODS)}")
        if not all(text.strip() for text in self.methods.values()):
            raise ValueError("methods : un texte vide")
        return self


_CONTENT: dict[str, tuple[int, McpLabContent]] = {}  # the latest read, by path


def load_lab_content(lang: str = config.DEFAULT_LANGUAGE) -> McpLabContent:
    """Read `content/mcp_lab.yaml` in `lang` (the session's), again once the file changed.
    Raises on a missing or invalid file. Only the latest read of a file is kept."""
    path = config.content_file("mcp_lab.yaml", lang)
    mtime = path.stat().st_mtime_ns
    kept = _CONTENT.get(str(path))
    if kept is not None and kept[0] == mtime:
        return kept[1]
    content = McpLabContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    _CONTENT[str(path)] = (mtime, content)
    return content


load_lab_content.cache_clear = _CONTENT.clear  # type: ignore[attr-defined]


# ---------- the lazy loading's catalog line (AD-25) ----------


def catalog_line(name: str, description: str | None, max_chars: int) -> str:
    """A tool's line in `load_tool_doc`'s description: its exposed name, then the first line
    of its description, cut at `max_chars` characters."""
    first = next(iter((description or "").strip().splitlines()), "").strip()
    if len(first) > max_chars:
        first = first[:max_chars].rstrip() + "…"
    return f"- {name} : {first}" if first else f"- {name}"


# ---------- the servers as the page draws them ----------


def transport_of(server: McpServer) -> str:
    return "streamable_http" if server.network else "stdio"


def launch_command(server: McpServer, lang: str) -> str | None:
    """The local server's launch command, as `McpConnection._transport` writes it."""
    if server.network:
        return None
    return f"python -m wavestack.mcp.local_server {lang}"


# ---------- the capture of the JSON-RPC messages ----------

Emit = Callable[[dict[str, Any], str], None]  # (payload of `mcp_lab_message`, step_id)


class Capture:
    """The messages of one lab connection, as they pass the transport. `begin(step_id)`
    starts an exchange (a connection, a call): each message is timed from it, and a
    response from its request (its round trip). The last text received per method is kept
    (`received`), for the raw answer of `tools/call`."""

    def __init__(self, emit: Emit) -> None:
        self._emit = emit
        self._lock = threading.Lock()
        self._step_id = ""
        self._started = time.monotonic()
        self._pending: dict[Any, tuple[str, float]] = {}  # request id -> (method, sent at)
        self._received: dict[str, str] = {}

    def begin(self, step_id: str) -> None:
        with self._lock:
            self._step_id = step_id
            self._started = time.monotonic()
            self._received.clear()

    def received(self, method: str) -> str | None:
        with self._lock:
            return self._received.get(method)

    def record(self, direction: str, message: Any) -> None:
        """Never raises: a capture that fails must not break the exchange it watches."""
        try:
            text = message.model_dump_json(by_alias=True, exclude_unset=True)
            now = time.monotonic()
            with self._lock:
                step_id = self._step_id
                if isinstance(message, JSONRPCRequest | JSONRPCNotification):
                    method = message.method
                    if isinstance(message, JSONRPCRequest):
                        self._pending[message.id] = (method, now)
                    since = self._started
                else:  # a response or an error: timed from its request
                    method, since = self._pending.pop(
                        getattr(message, "id", None), ("", self._started)
                    )
                    if direction == "from_server" and method:
                        self._received[method] = text
            payload = {
                "direction": direction,
                "method": method,
                "jsonrpc": text,
                "elapsed_ms": max(0, round((now - since) * 1000)),
                "reconstructed": False,
            }
            self._emit(payload, step_id)
        except Exception:  # noqa: BLE001, S110 - the exchange goes on uncaptured
            pass


class _ReadTap:
    """The transport's read stream, each `SessionMessage` captured as the session reads it;
    anything else (`last_context`) is the inner stream's."""

    def __init__(self, inner: Any, capture: Capture) -> None:
        self._inner, self._capture = inner, capture

    def _seen(self, item: Any) -> Any:
        message = getattr(item, "message", None)
        if message is not None:
            self._capture.record("from_server", message)
        return item

    async def receive(self) -> Any:
        return self._seen(await self._inner.receive())

    def __aiter__(self) -> _ReadTap:
        return self

    async def __anext__(self) -> Any:
        return self._seen(await self._inner.__anext__())

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> _ReadTap:
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> bool | None:
        return await self._inner.__aexit__(*exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _WriteTap:
    """The transport's write stream, each `SessionMessage` captured as the session sends it."""

    def __init__(self, inner: Any, capture: Capture) -> None:
        self._inner, self._capture = inner, capture

    async def send(self, item: Any, /) -> None:
        message = getattr(item, "message", None)
        if message is not None:
            self._capture.record("to_server", message)
        await self._inner.send(item)

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> _WriteTap:
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc: Any) -> bool | None:
        return await self._inner.__aexit__(*exc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@asynccontextmanager
async def tapped(transport: Any, capture: Capture) -> AsyncIterator[tuple[_ReadTap, _WriteTap]]:
    """A `Transport` for `mcp.Client`: `transport`'s streams, tapped."""
    async with transport as (read_stream, write_stream):
        yield _ReadTap(read_stream, capture), _WriteTap(write_stream, capture)


class LabConnection(McpConnection):
    """The workshop's own connection: the brick's `McpConnection`, its transport tapped, its
    trace scope the workshop's (context `mcp_lab`), which the HTTP client's hook reads, so
    that a public server's `outbound_request` carries it (AD-15)."""

    def __init__(
        self,
        server: McpServer,
        loop: Any,
        *,
        capture: Capture,
        scope: TraceScope,
        connect_timeout: float,
        call_timeout: float,
        language: str = "fr",
    ) -> None:
        super().__init__(
            server,
            loop,
            connect_timeout=connect_timeout,
            call_timeout=call_timeout,
            language=language,
        )
        self.capture = capture
        self.idle_scope = self.scope = scope

    def begin(self, step_id: str) -> None:
        """A new exchange: its messages and its outbound requests under `step_id`."""
        self.capture.begin(step_id)
        self.idle_scope = self.scope = replace(self.idle_scope, step_id=step_id)

    def _transport(self, stack: AsyncExitStack) -> Any:
        inner = super()._transport(stack)
        if isinstance(inner, StdioServerParameters):
            inner = stdio_client(inner)
        return tapped(inner, self.capture)

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    def call_result(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """From another thread: the call's `CallToolResult` as the server answered it (an
        `is_error` result included); raises what the call raised (`MCPError` for a JSON-RPC
        error answer, `TimeoutError`, `ConnectionError`…)."""
        submitted = asyncio.run_coroutine_threadsafe(
            self._submit(name, arguments, self.idle_scope), self.loop
        )
        try:
            return submitted.result(self.call_timeout + 1)
        except BaseException:
            submitted.cancel()
            raise


# ---------- the last session, rebuilt by the page (AD-1) ----------

KINDS = ("mcp_lab_message", "mcp_lab_connect_ended", "mcp_lab_call_ended")


def step_number(step_id: str | None) -> int | None:
    """`mcp{n}` -> n; anything else -> None."""
    if not step_id or not step_id.startswith("mcp") or not step_id[3:].isdigit():
        return None
    return int(step_id[3:])


def last_session(envelopes: Sequence[Any], first: int) -> list[dict[str, Any]]:
    """The envelopes of the workshop's last connection and of the calls made on it, from its
    exchange `mcp{first}` on: its JSON-RPC messages, the ends of its exchanges and the
    requests a public server received (`outbound_request` in the context `mcp_lab`)."""
    if first <= 0:
        return []
    kept = []
    for envelope in envelopes:
        if envelope.context_id != "mcp_lab":
            continue
        if envelope.kind not in KINDS and envelope.kind != "outbound_request":
            continue
        number = step_number(envelope.step_id)
        if number is not None and number >= first:
            kept.append(envelope.model_dump(mode="json"))
    return kept
