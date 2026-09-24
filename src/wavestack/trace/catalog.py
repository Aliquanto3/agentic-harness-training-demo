"""Event catalog (AD-2).

Only the ``kind`` values actually emitted so far are listed here. The
envelope itself (envelope.py) is already the full AD-2 shape; later stories
add their own ``kind``/payload pairs to this catalog without ever changing
the envelope.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

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
    body: str = ""


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
    """A node of the architecture schema (AD-12): a fixed `core.*` node or a brick component.

    `kind` will grow with later stories.
    """

    id: str
    kind: Literal["harness", "model", "brick", "tool", "file", "mcp_server"]
    hosting: Literal["local", "network"]
    label_fr: str
    wanted: bool
    available: bool
    reason_fr: str | None = None
    # Network tools: the state left by the last call actually sent. MCP servers: the
    # state of their connection (AD-12).
    contact: Literal["not_contacted", "available", "unavailable"] | None = None
    tools: list[str] = []  # MCP servers: the names of the tools they expose
    model: str | None = None  # `core.model`: file name (no extension) of the loaded model


class ArchitectureEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    crosses_boundary: bool

    model_config = {"populate_by_name": True}


class ArchitectureChangedPayload(BaseModel):
    nodes: list[ArchitectureNode]
    edges: list[ArchitectureEdge]

    @model_validator(mode="after")
    def _edges_join_listed_nodes(self) -> ArchitectureChangedPayload:
        ids = {node.id for node in self.nodes}
        for edge in self.edges:
            if edge.from_ not in ids or edge.to not in ids:
                raise ValueError(f"edge {edge.from_!r} -> {edge.to!r} targets an absent node")
        return self


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


# ---------- story 4: bricks, system prompt, conversation (AD-3, AD-12, AD-17) ----------


class BrickOption(BaseModel):
    """A sub-option of a brick card (story 5: one native tool)."""

    id: str
    label_fr: str
    enabled: bool
    hosting_fr: str
    network: bool


class BrickState(BaseModel):
    """One brick card: its content, and `available`/`pending` as computed by the session."""

    id: str
    label_fr: str
    category: Literal["prompt", "context", "harness"]
    category_fr: str
    hosting_fr: str
    explanation_fr: str
    wanted: bool
    available: bool
    reason_fr: str | None = None
    pending: bool
    options: list[BrickOption] = []
    limits_fr: str | None = None
    # Story 6b, `mcp` brick only: documentation complète or lazy loading (AD-25).
    mode: Literal["full", "lazy"] | None = None
    lazy_label_fr: str | None = None


class SystemPromptState(BaseModel):
    text: str
    is_default: bool


class BricksChangedPayload(BaseModel):
    bricks: list[BrickState]
    system_prompt: SystemPromptState


class ConversationClearedPayload(BaseModel):
    pass


# ---------- story 5: native tools, bounded turn loop (AD-4, AD-10, AD-14) ----------


class ToolStartedPayload(BaseModel):
    tool: str
    arguments: dict[str, object]
    phase_label: str
    source: Literal["native", "harness", "mcp_local", "mcp_public"] = "native"


class ToolEndedPayload(BaseModel):
    status: Literal["ok", "error", "blocked", "limit", "overflow"]
    result: str | None = None
    error_fr: str | None = None
    duration_ms: int


class ToolCallMalformedPayload(BaseModel):
    raw: str
    fragment: str
    detail_fr: str
    reaction: Literal["retry", "stop"]


class LimitReachedPayload(BaseModel):
    limit: Literal["calls", "retries", "sub_calls"]
    message_fr: str


class PrefixNotReusedPayload(BaseModel):
    common_tokens: int
    message_fr: str


# ---------- story 6: MCP servers (AD-12, AD-15) ----------


class McpConnectStartedPayload(BaseModel):
    server: str
    phase_label: str


class McpConnectEndedPayload(BaseModel):
    server: str
    status: Literal["ok", "error"]
    tools: list[str]
    error_fr: str | None = None
    duration_ms: int


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
    "bricks_changed": BricksChangedPayload,
    "conversation_cleared": ConversationClearedPayload,
    "tool_started": ToolStartedPayload,
    "tool_ended": ToolEndedPayload,
    "tool_call_malformed": ToolCallMalformedPayload,
    "limit_reached": LimitReachedPayload,
    "prefix_not_reused": PrefixNotReusedPayload,
    "mcp_connect_started": McpConnectStartedPayload,
    "mcp_connect_ended": McpConnectEndedPayload,
}
