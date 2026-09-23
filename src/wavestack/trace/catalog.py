"""Restricted event catalog for this story (AD-2).

Only the ``kind`` values actually emitted by story 1 are listed here. The
envelope itself (envelope.py) is already the full AD-2 shape; later stories
add their own ``kind``/payload pairs to this catalog without ever changing
the envelope.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class ArchitectureNode(BaseModel):
    """A node of the architecture schema (AD-12).

    Only `core.harness` and `core.model` exist for this story; `kind` will
    grow (brick, tool, mcp_server, ...) once bricks are emitted (story 4+).
    """

    id: str
    kind: Literal["harness", "model"]
    hosting: Literal["local", "network"]
    label_fr: str
    wanted: bool
    available: bool
    reason_fr: str | None = None


class ArchitectureEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    crosses_boundary: bool

    model_config = {"populate_by_name": True}


class ArchitectureChangedPayload(BaseModel):
    nodes: list[ArchitectureNode]
    edges: list[ArchitectureEdge]


# Maps each story-1/2 kind to its payload model, so `Envelope` can validate it.
PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "diagnostic_check": DiagnosticCheckPayload,
    "outbound_request": OutboundRequestPayload,
    "harness_error": HarnessErrorPayload,
    "session_state": SessionStatePayload,
    "architecture_changed": ArchitectureChangedPayload,
}
