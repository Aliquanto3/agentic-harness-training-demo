"""CAP-3: the security journal — every MCP tool call's authorization decision, and a
guardrail's verdict (story 5, through the same `record`), timestamped, never a secret,
downloadable as CSV. Read by a future « Journal » button (story 9) and the « Sécurité »
page (story 10); this story only exposes it (`GET /api/security_journal`, `.csv`).
"""

from __future__ import annotations

import csv
import io
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import islice

_KEPT = 500  # a demo's journal, not a production log (shortcut: in memory, lost on restart)

# Decisions that count as a refusal or a block, for the barre's red counter (story 9).
_DENIED = frozenset({"deny", "blocked"})


@dataclass(frozen=True)
class JournalEntry:
    ts: datetime
    source: str  # "mcp_tool" today; "guardrail" once story 5 calls `record`
    name: str  # the tool's or guardrail's name
    decision: str  # "allow" | "allow_once" | "cancelled" | "deny" | "blocked" | "masked" | ...
    reason_text: str


class SecurityJournal:
    """Accepts an entry from any source through `record` (CAP-3's "interface d'ajout
    simple"): a module never needs to import another's types to log into it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: deque[JournalEntry] = deque(maxlen=_KEPT)  # O(1) eviction
        # The session's refusals and blocks, counted as recorded (O(1)), never lowered when
        # an entry leaves the 500-entry window: the bar's count is the session's.
        self._denied = 0

    def record(self, source: str, name: str, decision: str, reason_text: str) -> JournalEntry:
        entry = JournalEntry(datetime.now(UTC), source, name, decision, reason_text)
        with self._lock:
            self._entries.append(entry)
            if decision in _DENIED:
                self._denied += 1
        return entry

    def entries(self) -> list[JournalEntry]:
        with self._lock:
            return list(self._entries)

    def denied_count(self) -> int:
        with self._lock:
            return self._denied

    def recent(self, n: int) -> list[JournalEntry]:
        """The `n` most recent entries, newest first (O(n), not a copy of the journal)."""
        with self._lock:
            return list(islice(reversed(self._entries), n))

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["horodatage", "source", "nom", "decision", "raison"])
        for e in self.entries():
            writer.writerow(
                [e.ts.isoformat(timespec="seconds"), e.source, e.name, e.decision, e.reason_text]
            )
        return buf.getvalue()
