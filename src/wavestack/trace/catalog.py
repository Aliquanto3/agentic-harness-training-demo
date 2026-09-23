"""Restricted event catalog for this story (AD-2).

Only the ``kind`` values actually emitted by story 1 are listed here. The
envelope itself (envelope.py) is already the full AD-2 shape; later stories
add their own ``kind``/payload pairs to this catalog without ever changing
the envelope.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Actor = Literal["model", "harness", "user"]
Trigger = Literal["model", "user", "harness", "hook"]


class DiagnosticCheckPayload(BaseModel):
    check: Literal["memory", "model", "network", "port"]
    status: Literal["ok", "warn", "fail"]
    message_fr: str
    action_fr: str | None = None
    blocking: bool


class OutboundRequestPayload(BaseModel):
    origin: Literal["brick", "diagnostic", "download"]
    method: str
    url: str


class HarnessErrorPayload(BaseModel):
    message_fr: str
    cause: str | None = None
    effect_fr: str | None = None


SessionState = Literal[
    "idle", "turn", "awaiting_human", "model_load", "download", "reset", "diagnostic"
]


class SessionStatePayload(BaseModel):
    state: SessionState
    reason_fr: str | None = None


# Maps each story-1 kind to its payload model, so `Envelope` can validate it.
PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "diagnostic_check": DiagnosticCheckPayload,
    "outbound_request": OutboundRequestPayload,
    "harness_error": HarnessErrorPayload,
    "session_state": SessionStatePayload,
}
