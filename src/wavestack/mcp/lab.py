"""The MCP workshop (`/mcp`): the protocol laid bare, in sequence (lot 4 of 2026-10-04, AD-27).

The workshop opens connections of its own, never the brick's (a sandbox): a
`LabConnection` is an `McpConnection` whose transport is tapped and whose `_serve` runs
the extended handshake (`initialize`, `notifications/initialized`, then `tools/list`,
`resources/list` and `prompts/list`, each only when the server announces it), then a queue
of operations (`call_tool`, `read_resource`, `get_prompt`). Every JSON-RPC message the
SDK's session writes to the transport, or reads from it, is captured as it passes,
serialized as the transport serializes it (`model_dump_json(by_alias=True,
exclude_unset=True)`), and handed to the session (`Capture`), which emits it as
`mcp_lab_message` with what the page draws from it: its type, its request, its summary,
its error. The capture is real, never reconstructed.

Also here: the page's texts (`content/mcp_lab.yaml`, AD-19), the line a tool gets in
`load_tool_doc`'s catalog (AD-25, shared with the session's `_doc_catalog`), the step
grammar and `last_session` (AD-27).
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Any

import anyio
import httpx2
import yaml
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import (
    CallToolResult,
    GetPromptResult,
    JSONRPCError,
    JSONRPCNotification,
    JSONRPCRequest,
    ReadResourceResult,
)
from mcp_types.jsonrpc import CONNECTION_CLOSED
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wavestack import config
from wavestack.mcp import connection as _connection
from wavestack.mcp.connection import McpConnection, _leaf, describe_error
from wavestack.mcp.servers import McpServer
from wavestack.messages import msg, number
from wavestack.net.guard import find_blocked
from wavestack.trace.scope import TraceScope

# The methods the workshop explains, in the order of a real exchange (AD-27: eight).
METHODS = (
    "initialize",
    "notifications/initialized",
    "tools/list",
    "resources/list",
    "prompts/list",
    "tools/call",
    "resources/read",
    "prompts/get",
)
TRANSPORTS = ("stdio", "streamable_http")
SERVER_IDS = ("local", "datagouv", "mslearn")
COLUMNS = ("user", "model", "host", "client", "server", "source")
EXCHANGES = ("connect", "call", "read", "prompt", "ask")
PIECES = (
    "host",
    "client",
    "server_stdio",
    "server_http",
    "source",
    "model",
    "tool",
    "resource",
    "prompt",
)
BEFORE = ("local", "datagouv", "mslearn")


# ---------- the page's texts (content/mcp_lab.yaml, AD-19) ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransportText(_Strict):
    label_text: str = Field(min_length=1)
    explain_text: str = Field(min_length=1)


class ColumnText(_Strict):
    """A lifeline of the Séquence: its name, its subtitle, its explanation (`explain()`)."""

    name_text: str = Field(min_length=1)
    sub_text: str = ""
    explain_text: str = Field(min_length=1)


class PhaseText(_Strict):
    """A phase of the Séquence: « Pourquoi… ? » and its answer."""

    why_label_text: str = Field(min_length=1)
    why_text: str = Field(min_length=1)


class PrimitiveText(_Strict):
    """A primitive's tab: who chooses it, and the note under the badge."""

    note_text: str = Field(min_length=1)


class ServerSourceText(_Strict):
    """AD-27: the data source behind a server, and what the server does with it (the arrows
    Serveur → Source, never captured)."""

    source_label_text: str = Field(min_length=1)
    source_action_text: str = Field(min_length=1)
    source_explain_text: str = Field(min_length=1)


class PieceText(_Strict):
    """The restaurant analogy, one line per piece (EXPERIENCE.md, Volet Architecture)."""

    place_text: str = Field(min_length=1)
    meaning_text: str = Field(min_length=1)


class BeforeText(_Strict):
    """« Avant MCP »: a schema of principle, nothing captured."""

    banner_text: str = Field(min_length=1)
    integrations: dict[str, str]
    captions: list[str] = Field(min_length=1)
    after_caption_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _every_integration(self) -> BeforeText:
        if set(self.integrations) != set(BEFORE):
            raise ValueError(f"before.integrations : il faut exactement {', '.join(BEFORE)}")
        return self


class McpLabContent(_Strict):
    """`content/mcp_lab.yaml`: the page's pedagogical texts (the interface's labels are in
    `ui.yaml`, `mcp`): a text per transport, per JSON-RPC method, per lifeline, per phase,
    per primitive, per server's source and per piece of the restaurant analogy; « Avant
    MCP »; the template that wraps a resource and its question in the message sent to the
    model (`{uri}`, `{content}`, `{question}`)."""

    title_text: str = Field(min_length=1)
    intro_text: str = Field(min_length=1)
    busy_text: str = Field(min_length=1)
    servers_help_text: str = Field(min_length=1)
    handshake_help_text: str = Field(min_length=1)
    handshake_empty_text: str = Field(min_length=1)
    tools_help_text: str = Field(min_length=1)
    tools_empty_text: str = Field(min_length=1)
    call_help_text: str = Field(min_length=1)
    by_hand_text: str = Field(min_length=1)
    by_model_text: str = Field(min_length=1)
    reinjected_help_text: str = Field(min_length=1)
    context_help_text: str = Field(min_length=1)
    outside_text: str = Field(min_length=1)
    arch_empty_text: str = Field(min_length=1)
    ask_resource_text: str = Field(min_length=1)
    transports: dict[str, TransportText]
    methods: dict[str, str]
    columns: dict[str, ColumnText]
    phases: dict[str, PhaseText]
    primitives: dict[str, PrimitiveText]
    servers: dict[str, ServerSourceText]
    restaurant: dict[str, PieceText]
    before: BeforeText

    @model_validator(mode="after")
    def _every_key(self) -> McpLabContent:
        for name, keys in (
            ("transports", TRANSPORTS),
            ("methods", METHODS),
            ("columns", COLUMNS),
            ("phases", EXCHANGES),
            ("primitives", ("tools", "resources", "prompts")),
            ("servers", SERVER_IDS),
            ("restaurant", PIECES),
        ):
            if set(getattr(self, name)) != set(keys):
                raise ValueError(f"{name} : il faut exactement {', '.join(keys)}")
        if not all(text.strip() for text in self.methods.values()):
            raise ValueError("methods : un texte vide")
        for variable in ("{uri}", "{content}", "{question}"):
            if variable not in self.ask_resource_text:
                raise ValueError(f"ask_resource_text : il manque {variable}")
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


# ---------- why an exchange failed (AD-27, the table of ends) ----------


def error_kind(exc: BaseException) -> str:
    """`unreachable`, `timeout`, `guard_blocked`, `lost`, `jsonrpc_error` or `interrupted`."""
    if find_blocked(exc) is not None:
        return "guard_blocked"
    leaf = _leaf(exc)
    if isinstance(leaf, TimeoutError | httpx2.TimeoutException):
        return "timeout"
    if isinstance(leaf, MCPError):
        return "lost" if leaf.code == CONNECTION_CLOSED else "jsonrpc_error"
    if isinstance(leaf, httpx2.RequestError | httpx2.HTTPStatusError):
        return "unreachable"
    if isinstance(leaf, ConnectionError):
        return "lost"
    if isinstance(leaf, OSError):
        return "unreachable"
    return "interrupted"


# ---------- the summary of a message (AD-27, written in the session's language) ----------

_CAPABILITIES = ("tools", "resources", "prompts", "logging", "completions")


def summary(method: str, message_type: str, data: Any, lang: str) -> str | None:
    """What the arrow says of a message (« 2 outils », « capacités : tools · resources ·
    prompts », « 1 bloc texte »); `None` for a request or a notification."""
    key = "session.mcp_lab.summary"
    if message_type == "error":
        error = data.get("error") or {}
        return msg(
            f"{key}.error", lang, code=error.get("code", ""), message=error.get("message", "")
        )
    if message_type != "response":
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    if method == "initialize":
        caps = result.get("capabilities") or {}
        named = [c for c in _CAPABILITIES if c in caps]  # `experimental` is not a primitive
        if not named:
            return msg(f"{key}.no_capabilities", lang)
        return msg(f"{key}.capabilities", lang, names=" · ".join(named))
    for listed, field_name in (
        ("tools/list", "tools"),
        ("resources/list", "resources"),
        ("prompts/list", "prompts"),
    ):
        if method == listed:
            count = len(result.get(field_name) or [])
            return msg(f"{key}.{field_name}", lang, count=count, n=number(count, lang))
    if method == "tools/call":
        blocks = result.get("content") or []
        texts = sum(1 for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        others = len(blocks) - texts
        parts = []
        if texts or not others:
            parts.append(msg(f"{key}.text_blocks", lang, count=texts, n=number(texts, lang)))
        if others:
            parts.append(msg(f"{key}.other_blocks", lang, count=others, n=number(others, lang)))
        said = " · ".join(parts)
        return msg(f"{key}.is_error", lang, blocks=said) if result.get("isError") else said
    if method == "resources/read":
        contents = result.get("contents") or []
        if len(contents) == 1 and isinstance(contents[0], dict):
            content = contents[0]
            mime = content.get("mimeType") or "?"
            if isinstance(content.get("text"), str):
                lines = len(content["text"].splitlines())
                return msg(
                    f"{key}.text_content", lang, mime=mime, count=lines, n=number(lines, lang)
                )
            size = len(content.get("blob") or "") * 3 // 4
            return msg(f"{key}.blob_content", lang, mime=mime, n=number(size, lang))
        count = len(contents)
        return msg(f"{key}.contents", lang, count=count, n=number(count, lang))
    if method == "prompts/get":
        count = len(result.get("messages") or [])
        return msg(f"{key}.messages", lang, count=count, n=number(count, lang))
    return None


# ---------- the capture of the JSON-RPC messages ----------

# (payload of `mcp_lab_message`, step_id) -> the event's `seq` (None: not emitted).
Emit = Callable[[dict[str, Any], str], int | None]
_KEPT_BODIES = 64  # the messages sent whose `seq` an outbound POST may look for


@dataclass
class _Request:
    method: str
    sent_at: float
    step: str
    seq: int | None


class Capture:
    """The messages of one lab connection, as they pass the transport (AD-27).

    `begin(step)` opens an exchange (or a sub-step): each message is timed from it, and a
    response from its request (its round trip); `end()` closes it, and a message received
    outside any open exchange goes to the connection's first step, `unsolicited`. A request
    and its response pair on (direction of the request, `id`), never on the `id` alone; a
    response carries the step of its request and its `seq` (`reply_to_seq`)."""

    def __init__(self, emit: Emit, first_step: str, lang: Callable[[], str] = lambda: "fr") -> None:
        self._emit = emit
        self._first = first_step
        self._lang = lang
        self._lock = threading.Lock()
        self._step: str | None = None
        self._starts: dict[str, float] = {}
        self._pending: dict[tuple[str, Any], _Request] = {}
        self._received: dict[tuple[str, str], str] = {}  # (step, method) -> response text
        self._errored: dict[str, int | None] = {}  # step -> the request answered by an error
        self._bodies: OrderedDict[str, int | None] = OrderedDict()

    @property
    def step(self) -> str | None:
        return self._step

    def begin(self, step_id: str) -> None:
        with self._lock:
            self._step = step_id
            self._starts.setdefault(step_id, time.monotonic())

    def end(self) -> None:
        with self._lock:
            self._step = None

    def received(self, method: str, step_id: str | None = None) -> str | None:
        """The last response to `method` in `step_id` (the open step), as received."""
        with self._lock:
            return self._received.get((step_id or self._step or "", method))

    def failed_seq(self, step_id: str) -> int | None:
        """The request of `step_id` left without an answer (the last one), else the one
        answered by a JSON-RPC error; `None` when every request was answered."""
        with self._lock:
            waiting = [r.seq for r in self._pending.values() if r.step == step_id]
            if waiting:
                return waiting[-1]
            return self._errored.get(step_id)

    def seq_of(self, body: str) -> int | None:
        """The `seq` of the message sent whose captured text is `body` (an outbound POST):
        the very text, else the same JSON."""
        with self._lock:
            if body in self._bodies:
                return self._bodies[body]
            canonical = _canonical(body)
            if canonical is None:
                return None
            for text, seq in reversed(self._bodies.items()):
                if _canonical(text) == canonical:
                    return seq
        return None

    def record(self, direction: str, message: Any) -> None:
        """Never raises: a capture that fails must not break the exchange it watches."""
        try:
            self._record(direction, message)
        except Exception:  # noqa: BLE001, S110 - the exchange goes on uncaptured
            pass

    def _record(self, direction: str, message: Any) -> None:
        text = message.model_dump_json(by_alias=True, exclude_unset=True)
        data = json.loads(text)
        now = time.monotonic()
        rpc_id = getattr(message, "id", None)
        with self._lock:
            opened = self._step is not None
            step = self._step or self._first
            since, kind = self._starts.get(step, now), "since_start"
            reply_to: int | None = None
            request: _Request | None = None
            if isinstance(message, JSONRPCRequest):
                message_type, method = "request", message.method
            elif isinstance(message, JSONRPCNotification):
                message_type, method = "notification", message.method
            else:
                message_type = "error" if isinstance(message, JSONRPCError) else "response"
                asked = "from_server" if direction == "to_server" else "to_server"
                request = self._pending.pop((asked, rpc_id), None)
                method = request.method if request is not None else ""
                if request is not None:
                    step, since, kind = request.step, request.sent_at, "round_trip"
                    reply_to = request.seq
            is_error = bool(
                message_type == "response"
                and method == "tools/call"
                and isinstance(data.get("result"), dict)
                and data["result"].get("isError")
            )
            error = (
                {
                    "code": int(data["error"].get("code", 0)),
                    "message": data["error"].get("message", ""),
                }
                if message_type == "error" and isinstance(data.get("error"), dict)
                else None
            )
            payload = {
                "direction": direction,
                "method": method,
                "jsonrpc": text,
                "elapsed_ms": max(0, round((now - since) * 1000)),
                "elapsed_kind": kind,
                "reconstructed": False,
                "message_type": message_type,
                "rpc_id": rpc_id if isinstance(rpc_id, int | str) else None,
                "reply_to_seq": reply_to,
                "summary_text": summary(method, message_type, data, self._lang()),
                "error": error,
                "is_error": is_error,
                "unsolicited": not opened,
            }
            seq = self._emit(payload, step)
            if message_type == "request":
                self._pending[(direction, rpc_id)] = _Request(method, now, step, seq)
            if direction == "to_server":
                self._bodies[text] = seq
                while len(self._bodies) > _KEPT_BODIES:
                    self._bodies.popitem(last=False)
            if request is not None and direction == "from_server":
                self._received[(request.step, method)] = text
                if message_type == "error":
                    self._errored[request.step] = request.seq


def _canonical(text: str) -> str | None:
    try:
        return json.dumps(json.loads(text), sort_keys=True, ensure_ascii=False)
    except ValueError:
        return None


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


# ---------- the workshop's connection ----------


@dataclass
class Handshake:
    """What the extended handshake learned (AD-27). A list is `None` when the server does
    not announce it or when it failed (then in `list_errors`)."""

    capabilities: dict[str, Any] = field(default_factory=dict)
    primitives: dict[str, bool] = field(
        default_factory=lambda: {"tools": False, "resources": False, "prompts": False}
    )
    server_info: dict[str, Any] | None = None
    protocol_version: str | None = None
    tools: list[Any] | None = None
    resources: list[Any] | None = None
    prompts: list[Any] | None = None
    list_errors: list[dict[str, Any]] = field(default_factory=list)


_LISTS = (
    ("tools/list", "tools", "list_tools"),
    ("resources/list", "resources", "list_resources"),
    ("prompts/list", "prompts", "list_prompts"),
)
OPERATIONS = ("call_tool", "read_resource", "get_prompt")


class LabConnection(McpConnection):
    """The workshop's own connection: the brick's `McpConnection`, its transport tapped, its
    trace scope the workshop's (context `mcp_lab`), which the HTTP client's hook reads, so
    that a public server's `outbound_request` carries it (AD-15) and the `seq` of the
    message it posts (`message_seq`). `_serve` is the workshop's: the extended handshake,
    then a queue of operations. `on_lost(conn)`: the connection ended without being closed
    (the server gone), called on the loop."""

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
        on_lost: Callable[[LabConnection], None] | None = None,
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
        self.handshake: Handshake | None = None  # filled once `initialize` answered
        self.on_lost = on_lost
        self._closing = False

    def begin(self, step_id: str) -> None:
        """A new exchange (or sub-step): its messages and its outbound requests under it."""
        self.capture.begin(step_id)
        self.idle_scope = self.scope = replace(self.idle_scope, step_id=step_id)

    def _annotate(self, request: httpx2.Request) -> dict[str, Any]:
        """AD-27: an outbound POST names the message it carries (`message_seq`)."""
        if request.method != "POST":
            return {"message_seq": None}
        try:
            body = request.content.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - a stream not read: no message named
            return {"message_seq": None}
        return {"message_seq": self.capture.seq_of(body)}

    def _transport(self, stack: AsyncExitStack) -> Any:
        if self.server.url is None:
            inner: Any = stdio_client(
                StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "wavestack.mcp.local_server", self.language],
                )
            )
        else:
            http = _connection.create_async_client(
                scope=lambda: self.scope, timeout=self.connect_timeout, annotate=self._annotate
            )
            stack.push_async_callback(http.aclose)
            inner = streamable_http_client(self.server.url, http_client=http)
        return tapped(inner, self.capture)

    async def _serve(self, ready: asyncio.Future[Any]) -> None:
        async with AsyncExitStack() as stack:
            transport = self._transport(stack)
            client = await stack.enter_async_context(Client(transport, mode="legacy", cache=None))
            caps = client.server_capabilities
            info = client.server_info
            handshake = self.handshake = Handshake(
                capabilities=caps.model_dump(mode="json", by_alias=True, exclude_none=True),
                primitives={
                    "tools": caps.tools is not None,
                    "resources": caps.resources is not None,
                    "prompts": caps.prompts is not None,
                },
                server_info=info.model_dump(mode="json", by_alias=True, exclude_none=True)
                if info is not None
                else None,
                protocol_version=client.protocol_version,
            )
            for method, attribute, fetch in _LISTS:
                if not handshake.primitives[attribute]:
                    continue
                try:
                    with anyio.fail_after(self.call_timeout):
                        listed = await getattr(client, fetch)()  # one page: no cursor followed
                    setattr(handshake, attribute, list(getattr(listed, attribute)))
                except Exception as exc:  # noqa: BLE001 - a list in error, the rest goes on
                    if error_kind(exc) == "lost":
                        raise
                    handshake.list_errors.append(
                        {
                            "method": method,
                            "error_kind": error_kind(exc),
                            "error_text": describe_error(exc, self.call_timeout),
                        }
                    )
            ready.set_result(handshake)
            while (item := await self._queue.get()) is not None:
                operation, arguments, scope, future = item
                self.scope = scope
                self._calling = True
                try:
                    with anyio.fail_after(self.call_timeout):
                        if operation == "call_tool":
                            result: Any = await client.call_tool(*arguments)
                        elif operation == "read_resource":
                            result = await client.read_resource(*arguments)
                        else:
                            result = await client.get_prompt(*arguments)
                except Exception as exc:  # noqa: BLE001 - handed to the caller
                    if not future.done():
                        future.set_exception(exc)
                except BaseException:  # cancelled while calling: the caller must not wait
                    if not future.done():
                        future.set_exception(ConnectionError("connexion fermée"))
                    raise
                else:
                    if not future.done():
                        future.set_result(result)
                finally:
                    self.scope = self.idle_scope
                    self._calling = False

    async def _run(self, ready: asyncio.Future[Any]) -> None:
        try:
            await super()._run(ready)
        finally:
            opened = ready.done() and not ready.cancelled() and ready.exception() is None
            if opened and not self._closing and self.on_lost is not None:
                try:
                    self.on_lost(self)
                except Exception:  # noqa: BLE001, S110 - the session says it, or not
                    pass

    async def aclose(self) -> None:
        self._closing = True
        await super().aclose()

    def close(self, wait: bool = True) -> None:
        self._closing = True
        super().close(wait)

    @property
    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def requesting(self) -> bool:
        """« Requête MCP en cours » (AD-27): a handshake not finished, or an operation of the
        queue waiting for its answer. The only case where « Arrêter » closes the connection."""
        return self._calling or (self._ready is not None and not self._ready.done())

    async def _submit_operation(
        self, operation: str, arguments: tuple[Any, ...], scope: TraceScope
    ) -> Any:
        if self._task is None or self._task.done():
            raise ConnectionError("connexion fermée")
        future = self.loop.create_future()
        self._queue.put_nowait((operation, arguments, scope, future))
        return await future

    def operation(self, operation: str, *arguments: Any) -> Any:
        """From another thread: `call_tool(name, arguments)`, `read_resource(uri)` or
        `get_prompt(name, arguments)`, as the server answered it (an `isError` result
        included); raises what it raised (`MCPError` for a JSON-RPC error answer,
        `TimeoutError`, `ConnectionError`…)."""
        assert operation in OPERATIONS
        submitted = asyncio.run_coroutine_threadsafe(
            self._submit_operation(operation, arguments, self.idle_scope), self.loop
        )
        try:
            return submitted.result(self.call_timeout + 1)
        except BaseException:
            submitted.cancel()
            raise

    def call_result(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        return self.operation("call_tool", name, arguments)

    def read_result(self, uri: str) -> ReadResourceResult:
        return self.operation("read_resource", uri)

    def prompt_result(self, name: str, arguments: dict[str, str]) -> GetPromptResult:
        return self.operation("get_prompt", name, arguments)


# ---------- the steps and the last session, rebuilt by the page (AD-27) ----------

KINDS = (
    "mcp_lab_exchange_started",
    "mcp_lab_message",
    "mcp_lab_connect_ended",
    "mcp_lab_call_ended",
    "mcp_lab_read_ended",
    "mcp_lab_prompt_ended",
    "mcp_lab_model_started",
    "mcp_lab_model_ended",
    "mcp_lab_ask_ended",
    "mcp_lab_closed",
    "model_call_started",
    "model_call_ended",
    "outbound_request",
    "outbound_response",
)
_STEP = re.compile(r"^mcp(\d+)(\.[ct]\d+)?$")


def step_number(step_id: str | None) -> int | None:
    """`mcp{n}`, `mcp{n}.c{k}`, `mcp{n}.t{k}` -> n; anything else (`mcp_lab`) -> None."""
    match = _STEP.match(step_id or "")
    return int(match.group(1)) if match else None


def last_session(envelopes: Sequence[Any], first: int) -> list[dict[str, Any]]:
    """The envelopes of the workshop's last connection and of the exchanges made on it, from
    its exchange `mcp{first}` on, in the order of their `seq`: the kinds of `KINDS` in the
    context `mcp_lab`, exactly what the page shows live."""
    if first <= 0:
        return []
    kept = []
    for envelope in envelopes:
        if envelope.context_id != "mcp_lab" or envelope.kind not in KINDS:
            continue
        number_ = step_number(envelope.step_id)
        if number_ is not None and number_ >= first:
            kept.append(envelope.model_dump(mode="json"))
    return kept
