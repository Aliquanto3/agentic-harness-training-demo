"""One MCP connection, living on FastAPI's asyncio loop (AD-24).

A single long task enters `mcp.Client` (legacy `initialize` handshake, AD-15),
lists the tools, then serves a queue of calls until it is closed: anyio scopes
are closed by the very task that opened them. The worker thread reaches it
through `call`, i.e. `run_coroutine_threadsafe(...).result(timeout)`.

HTTP requests leave from the transport's own writer task, which does not see
the caller's `TraceScope`: the connection holds the scope of the call in
progress (calls are serial), and the factory's hook reads it.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import AsyncExitStack, suppress
from typing import Any

import anyio
import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, TextContent, Tool
from mcp_types.jsonrpc import CONNECTION_CLOSED

from wavestack.mcp.servers import McpServer
from wavestack.net.factory import create_async_client
from wavestack.net.guard import find_blocked
from wavestack.tools.registry import ToolError, Unreachable
from wavestack.trace.scope import TraceScope, current

CLOSE_TIMEOUT_S = 5.0  # the stdio transport itself waits 2 s, then kills the process tree


def _leaf(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def describe_error(exc: BaseException, timeout: float) -> str:
    """AD-16: why a server could not be reached, in French."""
    if (blocked := find_blocked(exc)) is not None:
        return f"Connexion refusée par le harnais ({blocked})."
    leaf = _leaf(exc)
    if isinstance(leaf, TimeoutError | httpx2.TimeoutException):
        return f"Le serveur n'a pas répondu dans le délai ({timeout:g} s)."
    if isinstance(leaf, httpx2.HTTPStatusError):
        return f"Le serveur a répondu par une erreur HTTP {leaf.response.status_code}."
    if isinstance(leaf, httpx2.RequestError):
        return (
            f"Service injoignable ({type(leaf).__name__}) : le poste n'a pas accès à "
            f"{leaf.request.url.host}."
        )
    if isinstance(leaf, MCPError):
        return f"Le serveur a refusé l'échange MCP ({leaf})."
    if isinstance(leaf, ConnectionError):  # raised here when the connection is gone
        return "La connexion au serveur est fermée : décochez puis recochez-le pour la rouvrir."
    if isinstance(leaf, OSError):
        return f"Le processus du serveur n'a pas pu être lancé ({leaf})."
    return f"La connexion au serveur a échoué ({type(leaf).__name__} : {leaf})."


def result_text(result: CallToolResult) -> str:
    """The text blocks' text; any other block is only named."""
    parts = [
        block.text if isinstance(block, TextContent) else f"[bloc {block.type} non affiché]"
        for block in result.content
    ]
    return "\n".join(parts)


class McpConnection:
    def __init__(
        self,
        server: McpServer,
        loop: asyncio.AbstractEventLoop,
        *,
        connect_timeout: float,
        call_timeout: float,
    ) -> None:
        self.server = server
        self.loop = loop
        self.connect_timeout = connect_timeout
        self.call_timeout = call_timeout
        self.idle_scope = TraceScope(brick="mcp", component=server.component, origin="brick")
        self.scope = self.idle_scope  # read by the HTTP client's hook
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._ready: asyncio.Future[list[Tool]] | None = None
        self._task: asyncio.Task[None] | None = None
        self._calling = False  # a call is in progress: closing cancels it at once

    # ---------- on the loop ----------

    def _transport(self, stack: AsyncExitStack) -> Any:
        if self.server.url is None:
            return StdioServerParameters(
                command=sys.executable, args=["-m", "wavestack.mcp.local_server"]
            )
        http = create_async_client(scope=lambda: self.scope, timeout=self.connect_timeout)
        stack.push_async_callback(http.aclose)
        return streamable_http_client(self.server.url, http_client=http)

    async def _serve(self, ready: asyncio.Future[list[Tool]]) -> None:
        async with AsyncExitStack() as stack:
            transport = self._transport(stack)
            client = await stack.enter_async_context(Client(transport, mode="legacy", cache=None))
            listed = await client.list_tools()
            ready.set_result(list(listed.tools))
            while (item := await self._queue.get()) is not None:
                name, arguments, scope, future = item
                self.scope = scope
                self._calling = True
                try:
                    with anyio.fail_after(self.call_timeout):
                        result = await client.call_tool(name, arguments)
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

    async def _run(self, ready: asyncio.Future[list[Tool]]) -> None:
        error: BaseException = ConnectionError("connexion fermée")
        try:
            await self._serve(ready)
        except Exception as exc:  # noqa: BLE001 - becomes a state (AD-16)
            error = exc
        finally:
            if not ready.done():
                ready.set_exception(error)
            while not self._queue.empty():  # calls left behind fail at once
                item = self._queue.get_nowait()
                if item is not None and not item[3].done():
                    item[3].set_exception(error)

    async def start(self) -> list[Tool]:
        """Connect and list the tools, within `connect_timeout`. Raises on failure."""
        self._ready = self.loop.create_future()
        self._task = asyncio.create_task(self._run(self._ready))
        try:
            return await asyncio.wait_for(asyncio.shield(self._ready), self.connect_timeout)
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        """Close the connection: a pending connection or call is cancelled, an idle one
        ends cleanly."""
        task = self._task
        if task is None or task.done():
            return
        if self._calling or (self._ready is not None and not self._ready.done()):
            task.cancel()
        else:
            self._queue.put_nowait(None)
        try:
            await asyncio.wait_for(asyncio.shield(task), CLOSE_TIMEOUT_S)
        except (Exception, asyncio.CancelledError):
            task.cancel()
            with suppress(Exception, asyncio.CancelledError):
                await task

    async def _submit(self, name: str, arguments: dict[str, Any], scope: TraceScope) -> Any:
        if self._task is None or self._task.done():
            raise ConnectionError("connexion fermée")
        future = self.loop.create_future()
        self._queue.put_nowait((name, arguments, scope, future))
        return await future

    # ---------- from any other thread ----------

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        """Call `name` on the worker thread. `is_error` → `ToolError`; transport or delay →
        `Unreachable`, both in French."""
        submitted = asyncio.run_coroutine_threadsafe(
            self._submit(name, arguments, current()), self.loop
        )
        try:
            result = submitted.result(self.call_timeout + 1)
        except MCPError as exc:
            if exc.code == CONNECTION_CLOSED:
                raise Unreachable(describe_error(exc, self.call_timeout)) from None
            # A JSON-RPC error answer (invalid arguments, unknown tool): the server is there.
            raise ToolError(f"Le serveur MCP a refusé l'appel : {exc.message}") from None
        except Exception as exc:  # noqa: BLE001 - AD-16
            submitted.cancel()
            raise Unreachable(describe_error(exc, self.call_timeout)) from None
        if result.is_error:
            raise ToolError(result_text(result) or "Le serveur signale une erreur, sans détail.")
        return result_text(result)

    def close(self, wait: bool = True) -> None:
        """Close from another thread; `wait` bounds the wait (never on the loop's own thread)."""
        if self.loop.is_closed():
            return
        try:
            closing = asyncio.run_coroutine_threadsafe(self.aclose(), self.loop)
        except RuntimeError:  # the loop is shutting down
            return
        if not wait:
            return
        with suppress(Exception):
            closing.result(CLOSE_TIMEOUT_S + 1)
