"""Event catalog (AD-2).

Only the ``kind`` values actually emitted so far are listed here. The
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


# ---------- story 3: bare LLM turn, context, gauge (AD-2, AD-4, AD-9) ----------

TurnStatus = Literal["completed", "cancelled", "limit", "overflow", "error"]
StopReason = Literal["stop", "length", "cancelled", "error"]
Channel = Literal["reasoning", "text", "tool_call"]


class TurnStartedPayload(BaseModel):
    replay_of: str | None = None
    message: str


class TurnEndedPayload(BaseModel):
    status: TurnStatus
    duration_ms: int | None = None


class SegmentPayload(BaseModel):
    id: str
    kind: str
    label_fr: str
    brick: str | None = None
    component: str | None = None
    text: str
    tokens: int


class BreakdownItem(BaseModel):
    group: str
    label_fr: str
    tokens: int
    kinds: list[str]


class ContextWindowPayload(BaseModel):
    """Shared by `context_rendered` and `context_preview`: every figure comes from the session."""

    segments: list[SegmentPayload]
    window: int
    reserve: int
    usable: int
    used: int
    percent: float
    near_limit: bool
    near_limit_ratio: float
    overflow: bool
    breakdown: list[BreakdownItem]


class ContextOverflowPayload(BaseModel):
    used: int
    usable: int
    message_fr: str
    strategies_fr: list[str]


class OutputTruncatedPayload(BaseModel):
    channel: Channel
    output_tokens: int
    max_tokens: int


class ModelCallStartedPayload(BaseModel):
    phase_label: str


class ModelFirstTokenPayload(BaseModel):
    pass


class ModelDeltaPayload(BaseModel):
    channel: Channel
    text: str


class ModelCallEndedPayload(BaseModel):
    raw_output: str
    reasoning: str
    text: str
    tool_calls: list[dict[str, object]]
    prompt_tokens: int
    output_tokens: int
    prompt_ms: int
    gen_ms: int
    stop_reason: StopReason
    duration_ms: int


class SpecialTokenNeutralizedPayload(BaseModel):
    segment_kind: str
    tokens: list[str]
    message_fr: str


# Maps each kind to its payload model, so `Envelope` can validate it.
PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "diagnostic_check": DiagnosticCheckPayload,
    "outbound_request": OutboundRequestPayload,
    "harness_error": HarnessErrorPayload,
    "session_state": SessionStatePayload,
    "architecture_changed": ArchitectureChangedPayload,
    "turn_started": TurnStartedPayload,
    "turn_ended": TurnEndedPayload,
    "context_rendered": ContextWindowPayload,
    "context_preview": ContextWindowPayload,
    "context_overflow": ContextOverflowPayload,
    "output_truncated": OutputTruncatedPayload,
    "model_call_started": ModelCallStartedPayload,
    "model_first_token": ModelFirstTokenPayload,
    "model_delta": ModelDeltaPayload,
    "model_call_ended": ModelCallEndedPayload,
    "special_token_neutralized": SpecialTokenNeutralizedPayload,
}
