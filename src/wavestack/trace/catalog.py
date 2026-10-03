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
# Story 33: a context segment's discipline, its brick's category (AD-9).
Discipline = Literal["prompt", "context", "harness", "neutral"]
Trigger = Literal["model", "user", "harness", "hook"]


class DiagnosticCheckPayload(BaseModel):
    # `cloud`: an invalid or unusable cloud declaration; `cloud_test`: « Tester » (story 11).
    check: Literal["memory", "model", "network", "port", "cloud", "cloud_test"]
    status: Literal["ok", "warn", "fail"]
    message_text: str
    action_text: str | None = None
    blocking: bool
    # Story 11, `cloud_test`: the model tested, its answer, the tool call received, the rate.
    model_id: str | None = None
    answer: str | None = None
    tool_call: dict[str, object] | None = None
    output_tps: int | None = None


class DiagnosticProgressPayload(BaseModel):
    """Story 3 (corrections): the model search's progress. `total` counts only the
    candidates that need a probe (cached ones cost nothing); `done` the probes finished."""

    done: int = Field(ge=0)
    total: int = Field(ge=0)


class OutboundHeader(BaseModel):
    """Story 23: one header as sent, in order and case. Outside the public allow-list its
    value is « [masqué] » and `masked` is true: the real value never reaches the journal."""

    name: str
    value: str
    masked: bool = False


class OutboundRequestPayload(BaseModel):
    origin: Literal["brick", "diagnostic", "download", "model"]
    method: str
    url: str
    # Story 23: the headers sent (AD-15); empty for events traced before them.
    headers: list[OutboundHeader] = []
    body: str = ""


class OutboundResponsePayload(BaseModel):
    """Recette du 02/10 (R2): an error response (status 400 or more) from a destination
    outside the loopback range, with its headers in the order received. Outside
    `PUBLIC_RESPONSE_HEADERS` and the quota prefixes, each value is « [masqué] »."""

    origin: Literal["brick", "diagnostic", "download", "model"]
    method: str
    url: str
    status: int
    headers: list[OutboundHeader] = []


class HarnessErrorPayload(BaseModel):
    message_text: str
    cause: str | None = None
    effect_text: str | None = None
    # AD-16, a cloud provider's outcome: what to try, and the figures built in Python.
    hints_text: list[str] = []
    http_status: int | None = None
    retry_after_s: float | None = None
    quota_scope: Literal["second", "minute", "day", "unknown"] | None = None


SessionState = Literal[
    "idle",
    "turn",
    "awaiting_human",
    "model_load",
    "download",
    "index_build",
    "reset",
    "diagnostic",
    "llm_lab",  # story 29: the « LLM nu » screen generates
    "rag_lab",  # story 30: the RAG workshop runs its chains
    "mcp_lab",  # story 6 (2026-09-30): the MCP workshop connects or calls
]


class ActiveModel(BaseModel):
    """AD-12: the model indicator's only source, built by the session."""

    id: str
    label: str
    hosting: Literal["local", "network"]
    provider: str | None = None
    disclosure: dict[str, object] | None = None
    warning_text: str | None = None  # the `cloud-warning`'s text, the indicator's tooltip
    banner_text: str | None = None  # Contexte LLM's banner (chat mode)
    # Story 17: which entry of the model lists is active: a file (`ref`: its path) or a
    # cloud model (`ref`: its `id`); story 18: a served model (`ref`: `ollama/{name}` or
    # `llama_server/{file}`), `provider` its server, `server_url` its loopback address.
    kind: Literal["file", "server", "cloud"] | None = None
    ref: str | None = None
    server_url: str | None = None


class SessionStatePayload(BaseModel):
    state: SessionState
    reason_text: str | None = None
    active_model: ActiveModel | None = None
    # Languages (1/5): the application session's language, and whether the conversation
    # locks it; absent from the diagnostic session's states.
    language: Literal["fr", "en", "de"] | None = None
    language_locked: bool | None = None


class ArchitectureNode(BaseModel):
    """A node of the architecture schema (AD-12): a fixed `core.*` node or a brick component.

    `kind` will grow with later stories.
    """

    id: str
    kind: Literal["harness", "model", "brick", "tool", "file", "mcp_server", "skill", "hook"]
    hosting: Literal["local", "network"]
    label_text: str
    wanted: bool
    available: bool
    reason_text: str | None = None
    # Network tools: the state left by the last call actually sent. MCP servers: the
    # state of their connection (AD-12).
    contact: Literal["not_contacted", "available", "unavailable"] | None = None
    tools: list[str] = []  # MCP servers: the names of the tools they expose
    model: str | None = None  # `core.model`: file name (no extension) of the loaded model
    provider: str | None = None  # `core.model` of a cloud model: its provider (story 11)
    # Story 18, `core.model` served by a local server: a process apart from the harness, on
    # this workstation, at `server_url`.
    process: Literal["external"] | None = None
    server_url: str | None = None
    # Skills (story 7): loaded in the conversation or not. Any node: what its tooltip adds
    # (a skill's or a hook's description, the audit log's path).
    loaded: bool | None = None
    detail_text: str | None = None
    # Story 34, network nodes (tools, public MCP servers): what the harness sends there, in
    # French, from `content/` (AD-19); the outbound summary under the schema quotes it.
    sends_text: str | None = None


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
    # FinOps: the sum of the costs of the turn's cloud calls (sub-agent included), in dollars,
    # when the turn cost something; `cost_source` is `estimate` when one of them was.
    cost_in_usd: float | None = None
    cost_out_usd: float | None = None
    cost_source: Literal["api", "estimate"] | None = None
    # GreenOps: the sums of the estimated footprints of the turn's calls (sub-agent
    # included), in Wh and g CO₂e (min and max), when one of them had a footprint.
    energy_wh_min: float | None = None
    energy_wh_max: float | None = None
    gco2e_min: float | None = None
    gco2e_max: float | None = None


class CompressedFromPayload(BaseModel):
    """Story 20: the tokens before; the text before is in the step `step_id`, rank `item`."""

    tokens_before: int
    estimated: bool = False
    step_id: str
    item: int


class SegmentPayload(BaseModel):
    id: str
    kind: str
    label_text: str
    brick: str | None = None
    component: str | None = None
    text: str
    tokens: int
    estimated: bool = False  # chat mode: an estimate, shown with « ≈ » (AD-4)
    # Story 20 (AD-22): a compressed tool result or RAG excerpt, with what it was before.
    compressed_from: CompressedFromPayload | None = None
    # Story 33: its brick's category, `neutral` without a brick (template, user message).
    discipline: Discipline = "neutral"


class BreakdownItem(BaseModel):
    group: str
    label_text: str
    tokens: int
    kinds: list[str]
    discipline: Discipline = "neutral"  # story 33: its first segment's


class BrickTokens(BaseModel):
    """Story 33: the tokens of one brick's segments, summed by the session (AD-1, AD-9)."""

    brick: str
    tokens: int
    estimated: bool = False  # chat mode: at least one of its segments is an estimate


class ContextSection(BaseModel):
    """Story 32: consecutive segments of one source (`kind`, `brick`), the template pieces
    between them absorbed (`template_tokens`); `start` and `end` index `segments`, `end`
    excluded. `seen`: read already by the previous call of the same context in the turn.
    Computed by the session (AD-1, AD-9): the interface adds nothing up."""

    start: int
    end: int
    kind: str
    label_text: str
    brick: str | None = None
    discipline: Discipline = "neutral"
    tokens: int
    template_tokens: int = 0
    estimated: bool = False
    seen: bool = False


# AD-9: where the effective window comes from.
WindowSource = Literal["configured", "native", "server", "tpm", "override"]


class ContextWindowPayload(BaseModel):
    """Shared by `context_rendered`, `context_preview` and `context_reconciled`: every figure
    comes from the session (AD-9)."""

    segments: list[SegmentPayload]
    window: int
    window_source: WindowSource = "configured"
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
    uncertain_text: str | None = None
    # Story 20: the total if the compressed segments were not, computed by the session.
    uncompressed_used: int | None = None
    # Story 33: tokens per brick, in order of first appearance, segments without a brick left
    # out; the brick cards read them (AD-1).
    by_brick: list[BrickTokens] = []
    # Story 32: the reading sections, and the prefix of segments the previous call of the same
    # context read already in this turn (0 at a turn's first call), with their tokens.
    sections: list[ContextSection] = []
    seen_segments: int = 0
    seen_tokens: int = 0


class ContextReconciledPayload(ContextWindowPayload):
    """AD-4, chat mode: after the call, `usage.prompt_tokens` is the total."""

    call_id: str


class WindowChoicePayload(BaseModel):
    """Story 26 (AD-9): one window the panel offers, with what it would cost the active
    model, every figure and text computed by the session (AD-1). `effective`: the window the
    model would get (bounded by `source`, `bound_text` says so); `kv_bytes`: its KV cache at
    `effective` (f16, an upper bound), `null` when unknown or not on this workstation;
    `read_s`: a full window's read at the measured rate (a lower bound), `null` when not
    measured; `fits`: within the memory budget (AD-8), else `refusal_text`; `current`: the
    window configured now."""

    window: int
    effective: int
    source: WindowSource
    bound_text: str | None = None
    kv_bytes: int | None = None
    kv_text: str
    read_s: float | None = None
    read_text: str
    fits: bool
    refusal_text: str | None = None
    current: bool


class ContextWindowStatePayload(BaseModel):
    """Story 26 (AD-2, AD-9): the context window as the session holds it and the choices the
    interface offers. `configured`: the window chosen (or read at launch); `window` and
    `window_source`: the active model's effective one; `hosting`: the active model's kind;
    `read_tps`: its measured read rate (local or served); `locked_text`: why no window can be
    applied (a cloud model's declared `window`)."""

    configured: int
    default: int
    window: int
    window_source: WindowSource
    bound_text: str | None = None
    model_label: str | None = None
    hosting: Literal["file", "server", "cloud"] | None = None
    read_tps: float | None = None
    read_note_text: str
    locked_text: str | None = None
    choices: list[WindowChoicePayload]


class ContextOverflowPayload(BaseModel):
    used: int
    usable: int
    message_text: str
    strategies_text: list[str]


class OutputTruncatedPayload(BaseModel):
    channel: Channel
    output_tokens: int
    max_tokens: int


class ReasoningCutPayload(BaseModel):
    """Lot C (N4), local mode: the reasoning reached `budget` tokens without closing; the
    harness closed it (`reasoning_tokens` generated) and relaunched the model with
    `answer_reserve` tokens left for the answer."""

    budget: int
    reasoning_tokens: int
    answer_reserve: int
    message_text: str


class SamplingTrace(BaseModel):
    """Story 29: the sampling a call sends, each value `None` when it is not sent; `source`:
    the harness's defaults (`harness`), the « LLM nu » screen's (`screen`), or the
    provider's own, nothing sent (`provider`); `note_text` what could not be set."""

    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    min_p: float | None = None
    source: Literal["harness", "screen", "provider"]
    note_text: str | None = None


class ModelCallStartedPayload(BaseModel):
    phase_label: str
    sampling: SamplingTrace | None = None  # story 29


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
    # Lot A (AD-4): the prompt tokens the engine really evaluated, the ones reused from its
    # cache excluded; `None` when the engine cannot say.
    evaluated_tokens: int | None = None
    # FinOps: a cloud call's estimated cost, in dollars, when its entry declares `pricing`;
    # `cost_source` follows `usage_source` (`estimate`: « ≈ »). Never for a local model.
    cost_in_usd: float | None = None
    cost_out_usd: float | None = None
    cost_source: Literal["api", "estimate"] | None = None
    # GreenOps: the call's estimated footprint, in Wh and g CO₂e, as a range (min = max for
    # a single value): EcoLogits for a cloud call whose entry declares `impacts`, CodeCarbon
    # for a local one. `impact_note_text`: the method and its limits, or why there is none.
    energy_wh_min: float | None = None
    energy_wh_max: float | None = None
    gco2e_min: float | None = None
    gco2e_max: float | None = None
    impact_method: Literal["ecologits", "codecarbon"] | None = None
    impact_note_text: str | None = None


class ConsumptionUpdatedPayload(BaseModel):
    """FinOps: the session's API spend after a paid call (turns, sub-agent, « Tester », « LLM
    nu »), in dollars; reset by a relaunch only. `approx`: one of its calls was estimated.
    `total_eur`: the total at `eur_per_usd` (`[finops]`), computed by the session. GreenOps:
    also after a call with a footprint (a local one included, which costs nothing), the sums
    of the footprints of `impact_calls` calls, in Wh and g CO₂e (min and max)."""

    total_in_usd: float
    total_out_usd: float
    total_usd: float
    calls: int
    approx: bool
    eur_per_usd: float
    total_eur: float
    energy_wh_min: float = 0.0
    energy_wh_max: float = 0.0
    gco2e_min: float = 0.0
    gco2e_max: float = 0.0
    impact_calls: int = 0


class SpecialTokenNeutralizedPayload(BaseModel):
    segment_kind: str
    tokens: list[str]
    message_text: str


# ---------- story 4: bricks, system prompt, conversation (AD-3, AD-12, AD-17) ----------


class ToolPresetState(BaseModel):
    """A preset of a forced tool call's arguments (story 9), from `content/tools.yaml`."""

    label_text: str
    args: dict[str, object]


class McpCallOption(BaseModel):
    """Lot K: the forced call of one MCP tool of a connected server: its parameters (name ->
    French description, from the server's schema) and the presets of `content/mcp.yaml`."""

    tool: str
    parameters: dict[str, str]
    presets: list[ToolPresetState] = []


class BrickOption(BaseModel):
    """A sub-option of a brick card (story 5: one native tool)."""

    id: str
    label_text: str
    enabled: bool
    hosting_text: str
    network: bool
    # Story 9, tools: the parameters of a forced call (name -> French description, in the
    # call's order) and the presets that fill its form.
    parameters: dict[str, str] | None = None
    presets: list[ToolPresetState] = []
    # Story 9, MCP servers: the tools whose documentation can be loaded by force.
    tools: list[str] = []
    # Lot K, MCP servers: the form of each tool's forced call (« Forcer l'appel »).
    calls: list[McpCallOption] = []
    # AD-9 (E089), public MCP servers: the live tools drift from the versioned snapshot
    # beyond `[mcp] snapshot_drift_threshold` (None: no snapshot, or within it).
    drift_text: str | None = None


class BrickForce(BaseModel):
    """Story 19: a forced action at the card's level (a brick without sub-option), with the
    form of its parameters (name -> French description) and the presets that fill it."""

    kind: Literal["delegate"]
    target: str
    label_text: str
    parameters: dict[str, str]
    presets: list[ToolPresetState] = []


class DownloadOffer(BaseModel):
    """Story 15: « Télécharger » on a brick card, its target and its label (size included)."""

    target: Literal["rag_embedding", "rag_reranker"]  # story 16: the reranking model
    label_text: str


class IndexBuildOffer(BaseModel):
    """Story 15: « Construire l'index » on the RAG card, once its model is there."""

    label_text: str


class RerankOption(BaseModel):
    """Story 16, `rag` brick: the reranking sub-option, its availability computed by the
    session, and « Télécharger » while its model's files are missing (AD-21)."""

    label_text: str
    enabled: bool
    available: bool
    reason_text: str | None = None
    hosting_text: str
    download: DownloadOffer | None = None


class BrickState(BaseModel):
    """One brick card: its content, and `available`/`pending` as computed by the session."""

    id: str
    label_text: str
    category: Literal["prompt", "context", "harness"]
    # Story 33: « Ce que le modèle lit » (`reads`) or « Ce que le harnais fait » (`acts`).
    group: Literal["reads", "acts"] | None = None
    category_text: str
    hosting_text: str
    explanation_text: list[str | list[str]]
    wanted: bool
    available: bool
    reason_text: str | None = None
    pending: bool
    options: list[BrickOption] = []
    limits_text: str | None = None
    # Story 6b, `mcp` brick only: documentation complète or lazy loading (AD-25).
    mode: Literal["full", "lazy"] | None = None
    lazy_label_text: str | None = None
    # Story 13, `reasoning` brick only: the model always reasons, whatever the switch says.
    always_text: str | None = None
    # Story 14, `global_memory` brick: what the card adds (e.g. no tool parser, AD-6).
    note_text: str | None = None
    # Story 14, `global_memory` brick: the empty drawer's text and the forced write's help
    # (AD-19), which depend on the model's tool parser.
    empty_text: str | None = None
    text_help_text: str | None = None
    # Story 19, `subagent` brick only: « Déléguer au sous-agent », on the card itself.
    force: BrickForce | None = None
    # Story 15, `rag` brick: offered when the embedding model's files are missing (AD-21).
    download: DownloadOffer | None = None
    build_index: IndexBuildOffer | None = None
    # Story 16, `rag` brick: the reranking sub-option (None: no RAG content).
    rerank: RerankOption | None = None
    # Story 23, `tools` and `mcp` bricks: what leaves the workstation and where to read it.
    outbound_text: str | None = None


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


class ToolResultTruncated(BaseModel):
    """Lot B (N3): the harness cut a network or MCP tool's result to `[tools]
    result_max_tokens`; `tokens` kept of `total_tokens`, estimated in chat mode (« ≈ »)."""

    tokens: int
    total_tokens: int
    estimated: bool = False


class ToolEndedPayload(BaseModel):
    status: Literal["ok", "error", "blocked", "limit", "overflow", "cancelled"]
    result: str | None = None
    error_text: str | None = None
    duration_ms: int
    truncated: ToolResultTruncated | None = None


class ToolCallMalformedPayload(BaseModel):
    raw: str
    fragment: str
    detail_text: str
    reaction: Literal["retry", "stop"]


class LimitReachedPayload(BaseModel):
    limit: Literal["calls", "retries", "sub_calls", "sub_retries"]
    message_text: str


# Lot A (AD-4): why the engine reads again. `in_turn`: call n+1 does not extend call n and
# its output. At a turn's first call, against the ids in the engine's cache: `reset` (the
# conversation cleared, a scenario or the reset), `replay`, `abandoned` (the previous turn
# not `completed`), `subagent` (a sub-agent's context in the cache), else by the segment
# of the first byte that differs: `system` (system message, memory, catalogs, skills),
# `history`, or `template`.
PrefixCause = Literal[
    "in_turn",
    "system",
    "history",
    "template",
    "reset",
    "replay",
    "abandoned",
    "subagent",
    "llm",  # story 29: the « LLM nu » screen took the engine's cache
]


class PrefixNotReusedPayload(BaseModel):
    common_tokens: int
    message_text: str
    cause: PrefixCause = "in_turn"


# ---------- story 4 of the deferred leftovers (E122): the first turn's context prefilled ----------


class ContextPrefillStartedPayload(BaseModel):
    """The engine starts reading, at a scenario's launch, the part of the first turn's
    context that does not depend on the message (`tokens` ids), while the instructions
    are read. Journal only, never the turn's rail."""

    tokens: int
    phase_label: str  # AD-2: every `*_started` names its phase
    message_text: str


class ContextPrefillEndedPayload(BaseModel):
    """`completed`: every id is in cache; `abandoned`: a turn, a load, a setting or another
    scenario came first (the ids evaluated stay useful); `error`: the engine failed."""

    status: Literal["completed", "abandoned", "error"]
    tokens: int
    evaluated_tokens: int
    duration_ms: int
    message_text: str


# ---------- story 6: MCP servers (AD-12, AD-15) ----------


class McpConnectStartedPayload(BaseModel):
    server: str
    phase_label: str


class McpConnectEndedPayload(BaseModel):
    server: str
    status: Literal["ok", "error"]
    tools: list[str]
    error_text: str | None = None
    duration_ms: int
    # AD-9 (E089): the same warning as the MCP card's, when the live tools drift.
    drift_text: str | None = None


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
    detail_text: str
    # French labels from content/hooks.yaml, so the front formats without a table (AD-1).
    hook_text: str
    point_text: str


class EffectAppliedPayload(BaseModel):
    # Story 15: `model_download` (each file and its sha256), `rag_index_write` (the index).
    effect: Literal[
        "audit_append",
        "setting_write",
        "api_key_set",
        "memory_write",
        "model_download",
        "rag_index_write",
    ]
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
    label_text: str


class ArmedActionsChangedPayload(BaseModel):
    actions: list[ArmedActionState]


class ActionDroppedPayload(BaseModel):
    armed_id: str
    reason_text: str


# ---------- story 10: scenarios, programme, reset (AD-19, FR-38, FR-39) ----------


class ScenarioEntry(BaseModel):
    id: str
    title_text: str
    description_text: str
    prompts: list[str]


class ProgramModule(BaseModel):
    title_text: str
    duration_min: int
    scenarios: list[ScenarioEntry]


class Program(BaseModel):
    modules: list[ProgramModule]
    transverse: list[ScenarioEntry]


class UnavailableBrick(BaseModel):
    """Lot E (E5): a brick the active scenario wants and the active model cannot offer."""

    brick: str
    label_text: str
    reason_text: str


class ScenarioChangedPayload(BaseModel):
    program: Program
    active: str | None  # the scenario launched, `None` at launch and after a reset
    # Lot E (E5): the scenario's bricks the active model cannot offer, with their reasons
    # (at the launch, and again after a model change); empty without a scenario.
    unavailable: list[UnavailableBrick] = []
    # Lot E (E5): the same scenario, `unavailable` read again after a model load (no launch).
    refresh: bool = False


class HarnessResetPayload(BaseModel):
    pass


# ---------- languages (1/5, AD-19) ----------


class LanguageChangedPayload(BaseModel):
    """The language saved in `settings.json`; the texts sent to the model follow it."""

    language: Literal["fr", "en", "de"]


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
    error_text: str | None = None
    # The limits the drawer and the forced write apply (AD-19: from the session).
    max_entries: int
    max_chars: int


# ---------- story 17: hot model switch (AD-2, AD-3, AD-8) ----------


class ServerCacheUsedPayload(BaseModel):
    """Story 18, information: Ollama read fewer prompt tokens than the harness counted, the
    start of the prompt coming from its cache (not a « transparence réduite »)."""

    prompt_tokens: int
    evaluated_tokens: int
    message_text: str


class ModelLoadStartedPayload(BaseModel):
    """A model load starts, out of any turn: at launch or on a switch. Its `ts` anchors the
    « Chargement du modèle… » stopwatch."""

    model: ActiveModel  # the model being loaded
    phase_label: str
    # Story 26: the window of a reload of the active model with another window, which the
    # top bar then names by `phase_label` (« Rechargement de … avec une fenêtre de … »).
    window: int | None = None


class ModelLoadEndedPayload(BaseModel):
    """`ok`: the model is active; `restored`: it failed and the previous one is active again;
    `cancelled` (lot E): « Arrêter » stopped it, the previous one is active again (or none,
    when there was none, `reason_text` says it); `error`: no model is active."""

    model: ActiveModel  # the model that was being loaded
    status: Literal["ok", "restored", "cancelled", "error"]
    duration_ms: int
    reason_text: str | None = None
    # Story 29: the memory the load took, on `ok` (the « LLM nu » screen shows it).
    memory: LoadMemory | None = None


class LoadMemory(BaseModel):
    """Story 29: WaveStack's RSS before the load and after it, the cost the budget counts
    (AD-8), and where the model lies, in French (formatted by the session)."""

    rss_before: int | None = None
    rss_after: int | None = None
    cost_bytes: int = 0
    where_text: str


class ModelLoadStepPayload(BaseModel):
    """Story 29: a step of a load passed, out of any turn: the previous model released, the
    probe, the budget's check, the engine created, ready. `elapsed_ms` since the load
    started, `duration_ms` the step's own, `rss_bytes` WaveStack's RSS then."""

    model: ActiveModel
    step: Literal["release", "probe", "check", "engine", "ready"]
    label_text: str
    elapsed_ms: int
    duration_ms: int = 0
    rss_bytes: int | None = None


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
    # Lot A (AD-11): the main context's state saved before the sub-agent (bytes of the
    # copy) and restored after it (ms); `None` when the engine cannot, or it failed.
    state_saved_bytes: int | None = None
    state_restore_ms: int | None = None


# ---------- story 15: simple RAG (AD-2, AD-22) ----------


class RagExcerpt(BaseModel):
    position: int  # rank, from 1
    chunk_id: int
    doc_id: str
    title_text: str
    text: str
    score: float  # 1 − cosine distance, 3 decimals


class RagSearchStartedPayload(BaseModel):
    query: str
    top_k: int
    phase_label: str


class RagSearchEndedPayload(BaseModel):
    status: Literal["ok", "error"]
    excerpts: list[RagExcerpt]
    placement_text: str  # where the excerpts go in the context
    error_text: str | None = None
    duration_ms: int
    # Story 16: the reranking enabled but not applied to this turn, and why.
    rerank_skipped_text: str | None = None


# ---------- story 16: reranking (AD-2, AD-22) ----------


class RerankedExcerpt(BaseModel):
    position: int  # rank after reranking, from 1
    before: int  # rank given by the embedding search, from 1
    chunk_id: int
    doc_id: str
    title_text: str  # the text is the search's, found by `chunk_id`
    score: float  # the reranker's, 0 to 1, 3 decimals
    retrieval_score: float  # the embedding search's
    truncated: bool = False  # cut to fit the reranker's pair (`[rag.reranker] max_tokens`)


class RagRerankStartedPayload(BaseModel):
    query: str
    candidates: int
    keep: int
    phase_label: str


class RagRerankProgressPayload(BaseModel):
    done: int  # candidates scored so far
    total: int


class RagRerankEndedPayload(BaseModel):
    status: Literal["ok", "error", "cancelled"]
    excerpts: list[RerankedExcerpt]  # every candidate, in the reranker's order
    keep: int  # the first `keep` go to the context
    placement_text: str
    error_text: str | None = None
    duration_ms: int


# ---------- story 20: context compression (AD-4, AD-22) ----------


class CompressionItem(BaseModel):
    """One candidate of a compression step: a tool result or a RAG excerpt."""

    source_text: str  # « Résultat de l'outil « read_file » », « Extrait RAG n° 2 »
    kind: Literal["tool_result", "rag_excerpt"]
    brick: str | None = None
    component: str | None = None
    tokens_before: int
    tokens_after: int
    text_before: str
    text_after: str | None = None  # only when `changed`: else the text before goes on
    changed: bool  # false: the compressor left it as it was (or did not shorten it)
    transforms: list[str] = []
    error_text: str | None = None


class CompressionStartedPayload(BaseModel):
    phase_label: str
    title_text: str  # the step's title, « Compression (Headroom) » (content/compression.yaml)
    items: int  # candidates given to the compressor
    compressor_text: str


class CompressionEndedPayload(BaseModel):
    status: Literal["ok", "error"]
    compressor_text: str
    items: list[CompressionItem]
    tokens_before: int
    tokens_after: int
    saved_tokens: int
    estimated: bool = False  # chat mode: tokens estimated (AD-4)
    unchanged_text: str  # why a candidate may come back as it was (content/compression.yaml)
    error_text: str | None = None
    duration_ms: int


# ---------- story 29: the « LLM nu » screen (context `llm`, no turn) ----------


class LlmToken(BaseModel):
    """One chip: the token's id, its text (its bytes « ⟨F0 9F⟩ » when they are only part of a
    character), and whether it is a special token of the vocabulary (a template marker)."""

    id: int
    text: str
    special: bool = False


class LlmDimensions(BaseModel):
    """The model's sizes (`None`: unknown), the embedding table's (vocabulary × dimension),
    their French figures and where they were read."""

    vocab_size: int | None = None
    embedding_length: int | None = None
    layer_count: int | None = None
    head_count: int | None = None
    context_length: int | None = None
    embedding_params: int | None = None
    figures_text: dict[str, str | None] = {}
    source_text: str


class LlmTokenizedPayload(BaseModel):
    """The text cut into tokens by the active model's tokenizer, without template (`exact`);
    a cloud model's tokenizer is at its provider: no token, the harness's estimate and why.
    `tokens`: the first 512, `more` the rest; `token_count` all of them."""

    request_id: str
    text: str
    char_count: int
    model_label: str
    hosting: Literal["local", "network"]
    exact: bool
    tokenizer_text: str
    tokens: list[LlmToken]
    token_count: int | None = None
    more: int = 0
    estimate: int | None = None
    chars_per_token: float | None = None  # the estimate's ratio (AD-4, chat mode)
    unavailable_text: str | None = None
    dimensions: LlmDimensions | None = None
    dimensions_text: str
    # The counts in French (« 1 004 »), written by the session: the page places them.
    figures_text: dict[str, str] = {}


class LlmGenerationStartedPayload(BaseModel):
    """The screen's prompt, rendered as one user message by the model's template (`rendered`:
    the text, or a cloud model's JSON body), its tokens (`exact`: counted by the model's
    tokenizer, else estimated), the sampling sent, the output reserve (AD-9)."""

    request_id: str
    prompt: str
    rendered: str
    prompt_tokens: int
    exact: bool
    sampling: SamplingTrace
    reserve: int
    # Story 5 of 2026-09-30: the window's share left to the prompt (window - reserve), for
    # the page's diagram of the window (values received, the page computes nothing).
    usable: int | None = None
    reasoning: bool = False
    phase_label: str
    # What one `llm_token` is: a token of the in-process engine, or a fragment of a server's
    # or a provider's stream (usually one token, not always).
    unit: Literal["token", "fragment"] = "token"
    figures_text: dict[str, str] = {}


class LlmTokenPart(BaseModel):
    """A token's decoded text in one channel, tags dropped (the reasoning's lanes)."""

    channel: Channel
    text: str


class LlmCandidate(BaseModel):
    """Story 29, increment 4: a candidate of a token (in-process engine only): the model's
    probability `p`, whether top-k, top-p and min-p `kept` it, its real chance to be drawn
    `p_sampled` (temperature applied among the kept), and whether it was the one drawn."""

    token_id: int
    text: str
    p: float
    kept: bool
    p_sampled: float
    chosen: bool = False


class LlmTokenPayload(BaseModel):
    """One token as it comes (a cloud model: one fragment the provider sent), its channel,
    and the ms since the generation started."""

    request_id: str
    index: int
    token_id: int | None = None
    text: str
    channel: Channel
    elapsed_ms: int
    candidates: list[LlmCandidate] | None = None
    parts: list[LlmTokenPart] = []


class LlmGenerationEndedPayload(BaseModel):
    """How the screen's generation ended; `read_tps` the prompt's read rate (`evaluated_tokens
    / prompt_ms`, `None` when the engine does not say), the tokens of each channel."""

    request_id: str
    status: Literal["completed", "cancelled", "limit", "error"]
    duration_ms: int
    read_tps: float | None = None
    reasoning_tokens: int = 0
    answer_tokens: int = 0
    message_text: str | None = None
    figures_text: dict[str, str] = {}


# ---------- story 30: the RAG workshop (AD-2, AD-22), context `rag_lab`, no turn ----------

RagLabLaneId = Literal["a", "b"]
RagLabStageStatus = Literal["ok", "error", "skipped", "cancelled", "not_run"]


class RagLabStageRef(BaseModel):
    """A stage of a lane as the run draws it: its kind, its option and their French names,
    its settings."""

    stage_id: str
    kind: str
    option: str
    label_text: str
    option_label_text: str
    params: dict[str, int] = {}


class RagLabLane(BaseModel):
    lane: RagLabLaneId
    label_text: str
    stages: list[RagLabStageRef]


class RagLabRunStartedPayload(BaseModel):
    run_id: str
    question: str
    lanes: list[RagLabLane]
    phase_label: str


class RagLabStageStartedPayload(BaseModel):
    run_id: str
    lane: RagLabLaneId
    stage_id: str
    kind: str
    option: str
    phase_label: str


class RagLabStageProgressPayload(BaseModel):
    run_id: str
    lane: RagLabLaneId
    stage_id: str
    kind: str
    option: str
    done: int
    total: int


class RagLabFact(BaseModel):
    label_text: str
    value_text: str


class RagLabSource(BaseModel):
    """Where an excerpt stood in a list an earlier stage made (a search, before a fusion or a
    reranking), and its score there."""

    kind: str
    label_text: str
    rank: int | None = None
    score: float | None = None


class RagLabItem(BaseModel):
    rank: int  # from 1, in the list this stage makes
    before: int | None = None  # its rank in the list the stage received
    chunk_id: int
    doc_id: str
    title_text: str
    text: str
    score: float | None = None  # this stage's, 3 decimals
    sources: list[RagLabSource] = []


class RagLabStageEndedPayload(BaseModel):
    """What a stage received and made, its figures and its excerpts, its duration and
    WaveStack's memory at its end (`None` for a stage that did not run)."""

    run_id: str
    lane: RagLabLaneId
    stage_id: str
    kind: str
    option: str
    status: RagLabStageStatus
    input_text: str = ""
    output_text: str = ""
    facts: list[RagLabFact] = []
    items: list[RagLabItem] = []
    borrowed: bool = False  # the model was the RAG brick's, lent and not closed
    error_text: str | None = None
    duration_ms: int
    rss_bytes: int | None = None
    memory_text: str | None = None


class RagLabCompared(BaseModel):
    key: str  # an excerpt (`doc_id#position`) or a document (`doc_id`)
    doc_id: str
    title_text: str
    rank_a: int | None = None
    rank_b: int | None = None


class RagLabComparison(BaseModel):
    """The two contexts compared, in Python (AD-1): excerpt by excerpt when both chains cut
    the corpus alike, else document by document."""

    basis: Literal["excerpt", "document"]
    common: list[RagLabCompared]
    only_a: list[RagLabCompared]
    only_b: list[RagLabCompared]
    rank_changes: list[RagLabCompared]
    summary_text: str


class RagLabRunEndedPayload(BaseModel):
    run_id: str
    status: Literal["ok", "error", "cancelled"]
    duration_ms: int
    comparison: RagLabComparison | None = None


# ---------- corrections of 2026-09-30, story 6: the MCP workshop, context `mcp_lab` ----------


class McpLabMessagePayload(BaseModel):
    """A JSON-RPC message as it passed the workshop's transport (captured, not rebuilt:
    `reconstructed` stays false). `elapsed_ms`: for a response, its round trip from its
    request; for a request or a notification, the time since the exchange started."""

    direction: Literal["to_server", "from_server"]
    method: str
    jsonrpc: str
    elapsed_ms: int
    reconstructed: bool = False


class McpLabTool(BaseModel):
    """A listed tool and what its documentation weighs in the context (AD-4, AD-25)."""

    name: str  # exposed: `{server}__{tool}`
    tool: str  # as the server names it (`mcp_lab_call`'s)
    description: str
    schema_: dict = Field(alias="schema")
    definition_text: str  # the definition `_tool_definitions` renders, as JSON
    doc_tokens: int
    line_text: str  # its line in `load_tool_doc`'s catalog (lazy loading)
    line_tokens: int

    model_config = {"populate_by_name": True, "serialize_by_alias": True}


class McpLabConnectEndedPayload(BaseModel):
    server: str
    status: Literal["ok", "error"]
    tools: list[McpLabTool] = []
    full_tokens: int | None = None
    lazy_tokens: int | None = None  # the lines, plus `load_tool_doc`'s definition
    load_tool_doc_tokens: int | None = None
    lazy_definition_text: str | None = None  # `load_tool_doc` with this server's lines
    estimated: bool = False  # no engine loaded: `_count_tokens`'s estimate
    error_text: str | None = None
    duration_ms: int = 0


class McpLabCallEndedPayload(BaseModel):
    server: str
    tool: str
    status: Literal["ok", "error"]
    raw: str | None = None  # the JSON-RPC answer, as received
    text: str | None = None  # what the harness would reinject (bounded)
    truncated: dict | None = None  # `{tokens, total_tokens, estimated}` when bounded
    error_text: str | None = None
    duration_ms: int


# Maps each kind to its payload model, so `Envelope` can validate it.
PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "diagnostic_check": DiagnosticCheckPayload,
    "diagnostic_progress": DiagnosticProgressPayload,
    "outbound_request": OutboundRequestPayload,
    "outbound_response": OutboundResponsePayload,
    "harness_error": HarnessErrorPayload,
    "server_cache_used": ServerCacheUsedPayload,
    "session_state": SessionStatePayload,
    "architecture_changed": ArchitectureChangedPayload,
    "turn_started": TurnStartedPayload,
    "turn_ended": TurnEndedPayload,
    "context_rendered": ContextWindowPayload,
    "context_preview": ContextWindowPayload,
    "context_reconciled": ContextReconciledPayload,
    "context_overflow": ContextOverflowPayload,
    "context_window_state": ContextWindowStatePayload,
    "output_truncated": OutputTruncatedPayload,
    "reasoning_cut": ReasoningCutPayload,
    "model_call_started": ModelCallStartedPayload,
    "model_first_token": ModelFirstTokenPayload,
    "model_delta": ModelDeltaPayload,
    "model_call_ended": ModelCallEndedPayload,
    "consumption_updated": ConsumptionUpdatedPayload,
    "special_token_neutralized": SpecialTokenNeutralizedPayload,
    "bricks_changed": BricksChangedPayload,
    "conversation_cleared": ConversationClearedPayload,
    "tool_started": ToolStartedPayload,
    "tool_ended": ToolEndedPayload,
    "tool_call_malformed": ToolCallMalformedPayload,
    "limit_reached": LimitReachedPayload,
    "prefix_not_reused": PrefixNotReusedPayload,
    "context_prefill_started": ContextPrefillStartedPayload,
    "context_prefill_ended": ContextPrefillEndedPayload,
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
    "language_changed": LanguageChangedPayload,
    "memory_changed": MemoryChangedPayload,
    "model_load_started": ModelLoadStartedPayload,
    "model_load_ended": ModelLoadEndedPayload,
    "subagent_started": SubagentStartedPayload,
    "subagent_ended": SubagentEndedPayload,
    "rag_search_started": RagSearchStartedPayload,
    "rag_search_ended": RagSearchEndedPayload,
    "rag_rerank_started": RagRerankStartedPayload,
    "rag_rerank_progress": RagRerankProgressPayload,
    "rag_rerank_ended": RagRerankEndedPayload,
    "compression_started": CompressionStartedPayload,
    "compression_ended": CompressionEndedPayload,
    "llm_tokenized": LlmTokenizedPayload,
    "model_load_step": ModelLoadStepPayload,
    "llm_generation_started": LlmGenerationStartedPayload,
    "llm_token": LlmTokenPayload,
    "llm_generation_ended": LlmGenerationEndedPayload,
    "rag_lab_run_started": RagLabRunStartedPayload,
    "rag_lab_stage_started": RagLabStageStartedPayload,
    "rag_lab_stage_progress": RagLabStageProgressPayload,
    "rag_lab_stage_ended": RagLabStageEndedPayload,
    "rag_lab_run_ended": RagLabRunEndedPayload,
    "mcp_lab_message": McpLabMessagePayload,
    "mcp_lab_connect_ended": McpLabConnectEndedPayload,
    "mcp_lab_call_ended": McpLabCallEndedPayload,
}
