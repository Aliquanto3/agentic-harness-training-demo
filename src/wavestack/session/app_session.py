"""Minimal application session, once the diagnostic has confirmed a model (AD-3).

State is fixed at `idle` for this story: no turn, no brick. `emit_initial()`
pushes the two events the 5-pane front needs to boot: `session_state` and
`architecture_changed` with the two reserved local nodes (AD-12). Later
stories add states and bricks; this module is not pre-built for them.
"""

from __future__ import annotations

from wavestack.trace.journal import get_journal

_CORE_HARNESS = {
    "id": "core.harness",
    "kind": "harness",
    "hosting": "local",
    "label_fr": "Harnais WaveStack",
    "wanted": True,
    "available": True,
    "reason_fr": None,
}
_CORE_MODEL = {
    "id": "core.model",
    "kind": "model",
    "hosting": "local",
    "label_fr": "Modèle",
    "wanted": True,
    "available": True,
    "reason_fr": None,
}


class AppSession:
    """The only session once WaveStack has a confirmed, usable model."""

    def __init__(self) -> None:
        self.state = "idle"

    def emit_initial(self) -> None:
        journal = get_journal()
        journal.emit("session_state", {"state": self.state, "reason_fr": None})
        journal.emit(
            "architecture_changed",
            {"nodes": [_CORE_HARNESS, _CORE_MODEL], "edges": []},
        )
