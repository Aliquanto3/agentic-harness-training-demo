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
    kind: Literal["harness", "model", "brick", "tool", "file", "mcp_server", "skill", "hook"]
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
    # Skills (story 7): loaded in the conversation or not. Any node: what its tooltip adds
    # (a skill's or a hook's description, the audit log's path).
    loaded: bool | None = None
    detail_fr: str | None = None


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

TurnStatus = Literal["completed", "cancelled", "limit", "overflow", "error", "blocked"]
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


class ToolPresetState(BaseModel):
    """A preset of a forced tool call's arguments (story 9), from `content/tools.yaml`."""

    label_fr: str
    args: dict[str, object]


class BrickOption(BaseModel):
    """A sub-option of a brick card (story 5: one native tool)."""

    id: str
    label_fr: str
    enabled: bool
    hosting_fr: str
    network: bool
    # Story 9, tools: the parameters of a forced call (name -> French description, in the
    # call's order) and the presets that fill its form.
    parameters: dict[str, str] | None = None
    presets: list[ToolPresetState] = []
    # Story 9, MCP servers: the tools whose documentation can be loaded by force.
    tools: list[str] = []


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


# ---------- story 8: hooks (AD-13, AD-23) ----------


# AD-13: `assemble_context` and `transform_context` stay brick steps (RAG, compression).
HookPoint = Literal[
    "on_user_message", "before_model_call", "before_tool", "after_tool", "on_turn_end"
]
HookDecision = Literal["allow", "modify", "block", "ask_human"]  # ask_human: H5 (8b)


class HookDecidedPayload(BaseModel):
    hook: str
    point: HookPoint
    decision: HookDecision
    detail_fr: str
    # French labels from content/hooks.yaml, so the front formats without a table (AD-1).
    hook_fr: str
    point_fr: str


class EffectAppliedPayload(BaseModel):
    effect: Literal["audit_append"]
    lines: list[str]


# ---------- story 8b: human validation (AD-13, AD-14) ----------


class ApprovalPreview(BaseModel):
    """Exactly what would leave the workstation (the tool's `preview`)."""

    method: str
    url: str
    body: str


class ApprovalRequestedPayload(BaseModel):
    approval_id: str
    tool: str
    destination: str  # the URL's host
    preview: ApprovalPreview


class ApprovalResolvedPayload(BaseModel):
    approval_id: str
    decision: Literal["approved", "refused", "cancelled"]
    hook_disabled: bool


# ---------- story 9: forced actions (AD-3, AD-25) ----------


class ArmedActionState(BaseModel):
    """An armed action, as the session holds it (AD-3): the front projects its chips."""

    armed_id: str
    kind: Literal["tool", "skill", "tool_doc"]
    brick: str
    target: str
    args: dict[str, object] = {}
    label_fr: str


class ArmedActionsChangedPayload(BaseModel):
    actions: list[ArmedActionState]


class ActionDroppedPayload(BaseModel):
    armed_id: str
    reason_fr: str


# ---------- story 10: scenarios, programme, reset (AD-19, FR-38, FR-39) ----------


class ScenarioEntry(BaseModel):
    id: str
    title_fr: str
    description_fr: str
    prompts: list[str]
    expects_overflow: bool


class ProgramModule(BaseModel):
    title_fr: str
    duration_min: int
    scenarios: list[ScenarioEntry]


class Program(BaseModel):
    modules: list[ProgramModule]
    transverse: list[ScenarioEntry]


class ScenarioChangedPayload(BaseModel):
    program: Program
    active: str | None  # the scenario launched, `None` at launch and after a reset


class HarnessResetPayload(BaseModel):
    pass


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
    "hook_decided": HookDecidedPayload,
    "effect_applied": EffectAppliedPayload,
    "approval_requested": ApprovalRequestedPayload,
    "approval_resolved": ApprovalResolvedPayload,
    "armed_actions_changed": ArmedActionsChangedPayload,
    "action_dropped": ActionDroppedPayload,
    "scenario_changed": ScenarioChangedPayload,
    "harness_reset": HarnessResetPayload,
}
