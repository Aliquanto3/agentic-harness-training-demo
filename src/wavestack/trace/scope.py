"""`TraceScope`: the implicit context every emitter (tools, hooks, mcp, net) reads.

The session (or, in this story, the cli/diagnostic code) sets the current
scope; downstream modules emit without receiving an emitter parameter.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Literal

Origin = Literal["brick", "diagnostic", "download"]


@dataclass(frozen=True)
class TraceScope:
    turn_id: str | None = None
    context_id: str | None = None
    call_id: str | None = None
    step_id: str | None = None
    parent_step: str | None = None
    brick: str | None = None
    component: str | None = None
    edge: str | None = None
    actor: Literal["model", "harness", "user"] = "harness"
    trigger: Literal["model", "user", "harness", "hook"] = "harness"
    origin: Origin | None = None


_DEFAULT = TraceScope()
_current: ContextVar[TraceScope] = ContextVar("wavestack_trace_scope", default=_DEFAULT)


def current() -> TraceScope:
    return _current.get()


@contextmanager
def scoped(**changes: object) -> Iterator[TraceScope]:
    """Enter a scope derived from the current one, restored on exit."""
    new_scope = replace(current(), **changes)
    token = _current.set(new_scope)
    try:
        yield new_scope
    finally:
        _current.reset(token)


def copy_for_thread() -> TraceScope:
    """Return the current scope, to be re-applied explicitly on another thread/loop (AD-24)."""
    return current()
