"""In-memory event journal: a locked list, `seq` never reset within a process.

A restart loses it (AD-2). SSE subscribers are notified synchronously here;
the web layer is responsible for waking its own event loop (AD-24).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from typing import Any

from wavestack.trace.envelope import Envelope, now_iso
from wavestack.trace.scope import TraceScope, current


class Journal:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[Envelope] = []
        self._seq = 0
        self._session_epoch = 0
        self._subscribers: list[Callable[[Envelope], None]] = []
        # This process's journal: a client holding a `seq` of another instance (WaveStack
        # relaunched while its tab stayed open) must resync from scratch, not resume.
        self.instance_id = uuid.uuid4().hex

    def subscribe(self, callback: Callable[[Envelope], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[Envelope], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def emit(
        self,
        kind: str,
        payload: dict[str, Any],
        *,
        scope: TraceScope | None = None,
        **scope_overrides: Any,
    ) -> Envelope:
        base_scope = scope if scope is not None else current()
        if scope_overrides:
            from dataclasses import replace

            base_scope = replace(base_scope, **scope_overrides)

        with self._lock:
            self._seq += 1
            envelope = Envelope(
                seq=self._seq,
                ts=now_iso(),
                session_epoch=self._session_epoch,
                turn_id=base_scope.turn_id,
                context_id=base_scope.context_id,
                call_id=base_scope.call_id,
                step_id=base_scope.step_id,
                parent_step=base_scope.parent_step,
                kind=kind,
                actor=base_scope.actor,
                trigger=base_scope.trigger,
                brick=base_scope.brick,
                component=base_scope.component,
                edge=base_scope.edge,
                payload=payload,
            )
            self._events.append(envelope)
            subscribers = list(self._subscribers)

        for callback in subscribers:
            callback(envelope)
        return envelope

    def events_since(self, seq: int) -> list[Envelope]:
        with self._lock:
            return [e for e in self._events if e.seq > seq]

    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def all_events(self) -> list[Envelope]:
        with self._lock:
            return list(self._events)


_journal = Journal()


def get_journal() -> Journal:
    return _journal
