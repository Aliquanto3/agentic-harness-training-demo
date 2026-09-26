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
    # `cloud`: an invalid or unusable cloud declaration; `cloud_test`: « Tester » (story 11).
    check: Literal["memory", "model", "network", "port", "cloud", "cloud_test"]
    status: Literal["ok", "warn", "fail"]
    message_fr: str
    action_fr: str | None = None
    blocking: bool
    # Story 11, `cloud_test`: the model tested, its answer, the tool call received, the rate.
    model_id: str | None = None
    answer: str | None = None
    tool_call: dict[str, object] | None = None
    output_tps: int | None = None


class OutboundRequestPayload(BaseModel):
    origin: Literal["brick", "diagnostic", "download", "model"]
    method: str
    url: str
    body: str = ""


class HarnessErrorPayload(BaseModel):
    message_fr: str
    cause: str | None = None
    effect_fr: str | None = None
    # AD-16, a cloud provider's outcome: what to try, and the figures built in Python.
    hints_fr: list[str] = []
    http_status: int | None = None
    retry_after_s: float | None = None
    quota_scope: Literal["second", "minute", "day", "unknown"] | None = None


SessionState = Literal[
    "idle", "turn", "awaiting_human", "model_load", "download", "reset", "diagnostic"
]


class ActiveModel(BaseModel):
    """AD-12: the model indicator's only source, built by the session."""

    id: str
    label: str
    hosting: Literal["local", "network"]
    provider: str | None = None
    disclosure: dict[str, object] | None = None
    warning_fr: str | None = None  # the `cloud-warning`'s text, the indicator's tooltip
    banner_fr: str | None = None  # Contexte LLM's banner (chat mode)
    # Story 17: which entry of the model lists is active: a file (`ref`: its path) or a
    # cloud model (`ref`: its `id`).
    kind: Literal["file", "cloud"] | None = None
    ref: str | None = None


class SessionStatePayload(BaseModel):
    state: SessionState
    reason_fr: str | None = None
    active_model: ActiveModel | None = None


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
    provider: str | None = None  # `core.model` of a cloud model: its provider (story 11)
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
    # Story 17: the model that plays this turn, for « Modèle : … » and « Comparer ».
    active_model: ActiveModel | None = None


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
    estimated: bool = False  # chat mode: an estimate, shown with « ≈ » (AD-4)


class BreakdownItem(BaseModel):
    group: str
    label_fr: str
    tokens: int
    kinds: list[str]


class ContextWindowPayload(BaseModel):
    """Shared by `context_rendered`, `context_preview` and `context_reconciled`: every figure
    comes from the session (AD-9)."""

    segments: list[SegmentPayload]
    window: int
    window_source: Literal["configured", "native", "server", "tpm", "override"] = "configured"
    reserve: int
    usable: int
    used: int
    percent: float
    near_limit: bool
    near_limit_ratio: float
    overflow: bool
    breakdown: list[BreakdownItem]
    # Chat mode (AD-4): the body sent, the source of `used`, and the warning of an estimate
    # that only exceeds `usable` once corrected.
    body: str | None = None
    usage_source: Literal["engine", "api", "estimate"] = "engine"
    uncertain_fr: str | None = None


class ContextReconciledPayload(ContextWindowPayload):
    """AD-4, chat mode: after the call, `usage.prompt_tokens` is the total."""

    call_id: str


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
    output_tps: int | None = None  # computed by the session (AD-2); `None` when `gen_ms` is 0
    usage_source: Literal["engine", "api", "estimate"] = "engine"


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


class BrickForce(BaseModel):
    """Story 19: a forced action at the card's level (a brick without sub-option), with the
    form of its parameters (name -> French description) and the presets that fill it."""

    kind: Literal["delegate"]
    target: str
    label_fr: str
    parameters: dict[str, str]
    presets: list[ToolPresetState] = []


class DownloadOffer(BaseModel):
    """Story 15: « Télécharger » on a brick card, its target and its label (size included)."""

    target: Literal["rag_embedding"]
    label_fr: str


class BrickState(BaseModel):
    """One brick card: its content, and `available`/`pending` as computed by the session."""

    id: str
    label_fr: str
    category: Literal["prompt", "context", "harness"]
    category_fr: str
    hosting_fr: str
    explanation_fr: list[str | list[str]]
    wanted: bool
    available: bool
    reason_fr: str | None = None
    pending: bool
    options: list[BrickOption] = []
    limits_fr: str | None = None
    # Story 6b, `mcp` brick only: documentation complète or lazy loading (AD-25).
    mode: Literal["full", "lazy"] | None = None
    lazy_label_fr: str | None = None
    # Story 13, `reasoning` brick only: the model always reasons, whatever the switch says.
    always_fr: str | None = None
    # Story 14, `global_memory` brick: what the card adds (e.g. no tool parser, AD-6).
    note_fr: str | None = None
    # Story 14, `global_memory` brick: the empty drawer's text and the forced write's help
    # (AD-19), which depend on the model's tool parser.
    empty_fr: str | None = None
    text_help_fr: str | None = None
    # Story 19, `subagent` brick only: « Déléguer au sous-agent », on the card itself.
    force: BrickForce | None = None
    # Story 15, `rag` brick: offered when the embedding model's files are missing (AD-21).
    download: DownloadOffer | None = None


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
    status: Literal["ok", "error", "blocked", "limit", "overflow", "cancelled"]
    result: str | None = None
    error_fr: str | None = None
    duration_ms: int


class ToolCallMalformedPayload(BaseModel):
    raw: str
    fragment: str
    detail_fr: str
    reaction: Literal["retry", "stop"]


class LimitReachedPayload(BaseModel):
    limit: Literal["calls", "retries", "sub_calls", "sub_retries"]
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
    effect: Literal["audit_append", "setting_write", "api_key_set", "memory_write"]
    lines: list[str] = []
    # `memory_write` (story 14, AD-23): the change applied to `memory.json`.
    op: Literal["add", "replace", "delete"] | None = None
    entry_id: str | None = None
    text: str | None = None
    key: str | None = None  # `setting_write`: the settings.json key, never a secret
    # `api_key_set` (AD-23): only the cloud model's id and whether a key is now set.
    id: str | None = None
    key_set: bool | None = None


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
    kind: Literal["tool", "skill", "tool_doc", "memory", "delegate"]
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


# ---------- story 14: global memory (AD-20, AD-23) ----------


class MemoryEntryState(BaseModel):
    id: str
    text: str
    created_at: str
    source: Literal["model", "user", "demo"]


class MemoryChangedPayload(BaseModel):
    """The whole memory after a change (AD-1): the drawer and the card project it."""

    entries: list[MemoryEntryState]
    path: str
    # Unreadable or invalid `memory.json`: why the brick is unavailable, until a reset.
    error_fr: str | None = None
    # The limits the drawer and the forced write apply (AD-19: from the session).
    max_entries: int
    max_chars: int


# ---------- story 17: hot model switch (AD-2, AD-3, AD-8) ----------


class ModelLoadStartedPayload(BaseModel):
    """A model load starts, out of any turn: at launch or on a switch. Its `ts` anchors the
    « Chargement du modèle… » stopwatch."""

    model: ActiveModel  # the model being loaded
    phase_label: str


class ModelLoadEndedPayload(BaseModel):
    """`ok`: the model is active; `restored`: it failed and the previous one is active again;
    `error`: no model is active."""

    model: ActiveModel  # the model that was being loaded
    status: Literal["ok", "restored", "error"]
    duration_ms: int
    reason_fr: str | None = None


# ---------- story 19: delegation to a sub-agent (AD-11, AD-25) ----------


class SubagentStartedPayload(BaseModel):
    """In the context `sub{n}`, `parent_step` the step of `delegate` (AD-11)."""

    task: str
    tools: list[str]  # the tools the sub-agent is offered
    phase_label: str


class SubagentEndedPayload(BaseModel):
    """The delegation's outcome and its saving, computed by the session (AD-1).

    `context_tokens`: the `used` of the sub-agent's last call (reconciled when it was);
    `kept_tokens`: its tool replies (results, errors, refusals), what the main context
    would have read without the delegation; `result`/`result_tokens`: what the main context
    reads, the result or the error reinjected in its place (`estimated` in chat mode);
    `saved_tokens`: `max(0, kept_tokens - result_tokens)`, 0 unless `completed`; `calls`:
    the sub-agent's model calls."""

    status: Literal["completed", "limit", "overflow", "error", "cancelled"]
    result: str
    context_tokens: int
    kept_tokens: int = 0  # the tool results that stayed in the sub-agent's context
    result_tokens: int
    saved_tokens: int
    estimated: bool = False
    # Chat mode: `context_tokens` and `kept_tokens` estimated, not reconciled by `usage`.
    context_estimated: bool = False
    calls: int


# ---------- story 15: simple RAG (AD-2, AD-22) ----------


class RagExcerpt(BaseModel):
    position: int  # rank, from 1
    chunk_id: int
    doc_id: str
    title_fr: str
    text: str
    score: float  # 1 − cosine distance, 3 decimals


class RagSearchStartedPayload(BaseModel):
    query: str
    top_k: int
    phase_label: str


class RagSearchEndedPayload(BaseModel):
    status: Literal["ok", "error"]
    excerpts: list[RagExcerpt]
    placement_fr: str  # where the excerpts go in the context
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
    "context_reconciled": ContextReconciledPayload,
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
    "memory_changed": MemoryChangedPayload,
    "model_load_started": ModelLoadStartedPayload,
    "model_load_ended": ModelLoadEndedPayload,
    "subagent_started": SubagentStartedPayload,
    "subagent_ended": SubagentEndedPayload,
    "rag_search_started": RagSearchStartedPayload,
    "rag_search_ended": RagSearchEndedPayload,
}
