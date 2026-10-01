"""The application session: single writer of state, one worker thread (AD-3, AD-24).

It loads the model found by the diagnostic, then runs turns: freeze a
`TurnState` (AD-17), render the prompt through the model's own template with
the effective bricks' segments, attribute its tokens, refuse an overflowing
call, stream the completion, and emit the counter and gauge figures. It alone
holds the bricks' `wanted`, the system prompt and the history (AD-3), and
computes availability in one place (AD-12). Nothing crosses its boundary as an
exception (AD-16).
"""

from __future__ import annotations

import asyncio
import bisect
import importlib.util
import inspect
import json
import logging
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from itertools import accumulate
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

from mcp.shared.exceptions import MCPError
from mcp_types.jsonrpc import CONNECTION_CLOSED

from wavestack import config
from wavestack import memory as memory_file
from wavestack.bricks.contract import (
    BrickContent,
    BrickDeclaration,
    Component,
    load_brick_content,
    load_default_system_prompt,
)
from wavestack.bricks.registry import BRICKS, check_panel_groups, check_unique_ids
from wavestack.cloud import active_model, chat_fields, load_cloud_content
from wavestack.compression import headroom_adapter
from wavestack.compression.port import (
    CompressionContent,
    Compressor,
    load_compression_content,
)
from wavestack.config import (
    DEFAULT_WINDOW,
    MAX_RESERVE,
    MIN_REASONING_BUDGET,
    WINDOW_CHOICES,
    CloudModel,
    EmbeddingModel,
    ModelFile,
    RerankerModel,
    output_reserve,
)
from wavestack.context.render import (
    RenderedChat,
    RenderedContext,
    reasoning_wrap,
    render_chat_body,
    render_context,
    with_total,
)
from wavestack.context.segments import (
    CompressedFrom,
    Joined,
    Part,
    Segment,
    SegmentKind,
    SegmentLabels,
    load_labels,
)
from wavestack.context.window import (
    bound_fr,
    gauge,
    kv_fr,
    read_seconds,
    read_time_fr,
    seen_prefix,
    window_for,
)
from wavestack.greenops import Impact, LocalMeter, Measure
from wavestack.hooks import (
    ALLOWED,
    AUDIT,
    DEMO_HOOKS,
    Hook,
    HookContext,
    HookPoint,
    HookResult,
    HooksContent,
    host,
    load_hooks_content,
)
from wavestack.mcp import lab as mcp_lab
from wavestack.mcp.connection import (
    CLOSE_TIMEOUT_S,
    McpConnection,
    describe_error,
    result_text,
)
from wavestack.mcp.servers import McpContent, load_mcp_content, mcp_servers
from wavestack.messages import (
    KeyedError,
    Lazy,
    Message,
    in_language,
    join,
    load_messages,
    msg,
    number,
    render,
    said,
)
from wavestack.models import download as download_module
from wavestack.models import embedding as embedding_module
from wavestack.models import gguf_meta
from wavestack.models import probe as probe_module
from wavestack.models import reranker as reranker_module
from wavestack.models.capabilities import (
    NO_TOOL_PARSER_FR,
    TOOL_CALL_TAGS,
    Capabilities,
    ChannelSplitter,
    capabilities_for,
    cloud_capabilities,
    reasoning_mode,
    reasoning_window_fr,
)
from wavestack.models.embedding import Embedder
from wavestack.models.engine import (
    DEFAULT_SAMPLING,
    SAMPLING_BOUNDS,
    CancelToken,
    Engine,
    EngineMetadata,
    EngineSnapshot,
    Fragment,
    LlamaCppEngine,
    Sampling,
)
from wavestack.models.load_registry import (
    COMPRESSOR,
    EMBEDDING,
    GREENOPS_CODECARBON,
    RAG_LAB_EMBEDDING,
    RAG_LAB_FAISS,
    RAG_LAB_FASTEMBED,
    RAG_LAB_LANCEDB,
    RERANKER,
    LoadRegistry,
    ModelChoice,
    process_rss,
)
from wavestack.models.openai_chat import (
    CallCost,
    ChatBody,
    OpenAIChatEngine,
    ProviderError,
    output_tps,
    record_spend,
    run_call,
    session_spend,
)
from wavestack.models.reranker import RerankCancelled, Reranker
from wavestack.models.servers import (
    ServerError,
    TokenizerRefused,
    ollama_load_bytes,
    open_engine,
)
from wavestack.rag import index as rag_index
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import Chunk, RagContent, chunk_corpus, load_rag_content
from wavestack.rag.retriever import Excerpt, SqliteVecRetriever
from wavestack.scenarios import EMPTY_PROGRAM, ScenariosContent, load_scenarios
from wavestack.session import llm_lab
from wavestack.session.effects import (
    ArmConsumed,
    AuditAppend,
    Effect,
    MemoryWrite,
    SettingWrite,
    SkillLoaded,
    ToolDocLoaded,
    ToolReply,
    apply_setting,
)
from wavestack.skills import SkillsContent, SkillText, load_skills_content
from wavestack.subagent import SubagentContent, load_subagent_content
from wavestack.tools.executor import ToolExecutor
from wavestack.tools.native import NATIVE_TOOLS, get_datetime, read_file
from wavestack.tools.network import network_tools
from wavestack.tools.parser import (
    Malformed,
    ToolCall,
    convert_value,
    parse_tool_calls,
    tool_call_id,
)
from wavestack.tools.registry import (
    DelegationFailed,
    ToolError,
    ToolRegistry,
    ToolsContent,
    ToolSpec,
    load_tools_content,
)
from wavestack.trace.catalog import (
    PAYLOAD_MODELS,
    LlmGenerationEndedPayload,
    LlmGenerationStartedPayload,
    LlmTokenizedPayload,
    LlmTokenPayload,
)
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import TraceScope, current, scoped
from wavestack.ui_texts import UiTexts, load_ui_texts

DELTA_INTERVAL_S = 0.05  # AD-2: model_delta grouped every 50 ms at most
LOAD_TOOL_DOC = "load_tool_doc"  # the harness meta-tool of the lazy loading mode (AD-25)
DOC_LINE_MAX = 120  # characters of a tool's first description line in `load_tool_doc`
LOAD_SKILL = "load_skill"  # the harness meta-tool of the skills brick (AD-25)
REMEMBER = "remember"  # the harness meta-tool of the global memory brick (AD-25)
MEMORY = "file.memory"  # the schema node of `memory.json` (AD-12, AD-23)
DELEGATE = "delegate"  # the harness meta-tool of the subagent brick (AD-11, AD-25)
RAG_INDEX = "file.rag_index"  # the schema node of the RAG index (story 15, AD-12)
# Lot G: the card's reason when another program keeps the index open (Windows).
INDEX_HELD_FR = Message("session.rag.index_held")
RAG_TARGET = "rag_embedding"  # a `download_model` target: the embedding model (story 15)
RERANK_TARGET = "rag_reranker"  # the other one: the reranking model (story 16)
RAG_RERANKER = "rag.reranker"  # the reranker's schema node (story 16, AD-12)

_CORE_HARNESS = {
    "id": "core.harness",
    "kind": "harness",
    "hosting": "local",
    "label_text": Message("session.architecture.harness"),
    "wanted": True,
    "available": True,
    "reason_text": None,
}
_CORE_MODEL = {
    "id": "core.model",
    "kind": "model",
    "hosting": "local",
    "label_text": Message("session.architecture.model"),
    "wanted": True,
    "available": True,
    "reason_text": None,
}

_TURN_FR = Message("session.state.turn")
# Languages (1/5): why the language cannot change, in French, then in the current language
# (the buttons keep their French names until the interface is translated).
_LANGUAGE_LOCKED = {
    "fr": (
        "La langue ne se change que sur une conversation vide : cliquez d'abord sur « Vider "
        "la conversation » ou sur « Réinitialiser »."
    ),
    "en": (
        "The language can only change on an empty conversation: first click « Vider la "
        "conversation » (clear the conversation) or « Réinitialiser » (reset)."
    ),
    "de": (
        "Die Sprache lässt sich nur bei leerer Unterhaltung ändern: Klicken Sie zuerst auf "
        "« Vider la conversation » (Unterhaltung leeren) oder « Réinitialiser » "
        "(Zurücksetzen)."
    ),
}


class ValueRefused(KeyedError, ValueError):
    """Languages (5/5): a refusal raised as a `ValueError`, its text keyed."""

    shown_name = "ValueError"  # the name a trace gives it, as before the keys


class RuntimeRefused(KeyedError, RuntimeError):
    """Languages (5/5): a failure raised as a `RuntimeError`, its text keyed."""

    shown_name = "RuntimeError"


class _RenderingJournal:
    """The journal, seen from the session: `emit` writes the payload's `Message`s in the
    session's language (languages 5/5); anything else is the journal's own."""

    def __init__(self, journal: Any, lang: str) -> None:
        self._journal, self._lang = journal, lang

    def emit(self, kind: str, payload: dict[str, Any], **kw: Any) -> Any:
        return self._journal.emit(kind, in_language(payload, self._lang), **kw)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._journal, name)


def _takes_lang(load: Callable[..., Any]) -> bool:
    """Whether a content loader takes `lang` (every loader of `wavestack` does)."""
    try:
        return "lang" in inspect.signature(load).parameters
    except (TypeError, ValueError):
        return False


def _language_locked_reason(language: str) -> str:
    french = _LANGUAGE_LOCKED["fr"]
    return french if language == "fr" else f"{french} / {_LANGUAGE_LOCKED[language]}"


# Lot A (AD-4): why a turn's first call does not extend what the engine holds in cache: the
# causes of `messages.yaml` (`session.prefix.causes`), `{why}` filled for a sub-agent.
_PREFIX_CAUSES = (
    "system",
    "history",
    "template",
    "reset",
    "replay",
    "abandoned",
    "subagent",
    "llm",
)
_LAB_FR = Message("session.state.llm_lab")
RAG_LAB_CATALOG_TTL_S = 5.0  # story 30: the validation's catalog, read again after this
_RAG_LAB_FR = Message("session.state.rag_lab")
_MCP_LAB_FR = Message("session.state.mcp_lab")  # story 6 of 2026-09-30
# Story 6 of 2026-09-30: past the connection's own delay, what its closing may take.
MCP_LAB_CLOSE_WAIT_S = CLOSE_TIMEOUT_S + 1
CANDIDATES = 5  # story 29: the candidates read with each token, the one drawn added if apart
# Lot A (AD-4): the segment kinds of the system message, for the `system` cause, and those
# of the conversation, for `history`.
_CONVERSATION_KINDS = {
    SegmentKind.HISTORY,
    SegmentKind.USER_MESSAGE,
    SegmentKind.RAG_EXCERPT,
    SegmentKind.HOOK_INJECTION,
}
_SYSTEM_KINDS = {
    SegmentKind.SYSTEM_PROMPT,
    SegmentKind.GLOBAL_MEMORY,
    SegmentKind.TOOL_CATALOG,
    SegmentKind.SKILL_CATALOG,
    SegmentKind.SKILL_BODY,
}
_AWAITING_FR = Message("session.state.awaiting")
_NO_MODEL_FR = Message("session.state.no_model")
_LOAD_FAILED_FR = Message("session.state.load_failed")
_CLOUD_FAILED_FR = Message("session.state.cloud_failed")
_NO_TURN_FR = Message("session.state.no_turn")
# Lot E (E4): a load stopped with no previous model to come back to.
_LOAD_STOPPED_FR = Message("session.state.load_stopped")
# Story 26: the read rate is measured on a call that evaluated at least this many tokens, not
# on a cache hit (lot A).
READ_MIN_TOKENS = 64
# Story 26 (AD-9): what the window panel says of a model's context cache and read time when
# they are not WaveStack's to measure.
_KV_CLOUD_FR = Message("session.window.kv_cloud")
_KV_NO_MODEL_FR = Message("session.window.kv_no_model")
_READ_CLOUD_FR = Message("session.window.read_cloud")
_READ_NO_MODEL_FR = Message("session.window.read_no_model")

# Lot B: the heaviest kind of segment names the cause (message first on ties), every kind
# but the template counted, some with another (`_OVERFLOW_GROUP`); the causes are
# `session.overflow.causes.{kind}` of `messages.yaml`.
_OVERFLOW_CAUSES = (
    SegmentKind.USER_MESSAGE,
    SegmentKind.RAG_EXCERPT,  # story 15: after the message, which wins the ties
    SegmentKind.HISTORY,
    SegmentKind.SYSTEM_PROMPT,
    SegmentKind.TOOL_CATALOG,  # in lazy loading; see `tool_catalog_full`
    SegmentKind.TOOL_RESULT,  # lot B: `_compression_hint_fr` fills `{compression}`
    SegmentKind.HOOK_INJECTION,
    SegmentKind.SUBAGENT_RESULT,
    SegmentKind.GLOBAL_MEMORY,
    SegmentKind.SKILL_BODY,  # with the catalog (`_OVERFLOW_GROUP`)
)
# Lot B: the kinds counted with another's cause.
_OVERFLOW_GROUP = {
    SegmentKind.SKILL_CATALOG: SegmentKind.SKILL_BODY,
    SegmentKind.ASSISTANT_TURN: SegmentKind.HISTORY,  # the turn's calls, its exchanges
}
# AD-6: the name of a model capability a brick requires (`session.capabilities`).
_CAPABILITIES = ("tool_call_parser",)
_OVERFLOW_STRATEGIES = ("sliding_window", "compaction", "old_tool_results", "lazy_loading")


class Exchange(NamedTuple):
    """One `completed` turn of the active branch, as stored for the history (AD-4, AD-17).

    `steps` are the turn's intermediate messages, before the final answer:
    `{role: assistant, content, reasoning, tool_calls: [{name, arguments}]}` and
    `{role: tool, name, content, component}`. `injection`: H3's text placed before the
    message, kept with it in the history (story 8).
    """

    turn_id: str
    user: str
    text: str
    reasoning: str
    steps: tuple[dict[str, Any], ...] = ()
    injection: str = ""


class _TokenTap:
    """Story 29: a cloud engine whose streamed items also reach `on_item(channel, text)`:
    the « LLM nu » screen shows each fragment the provider sends, as it comes. `run_call`
    reads the engine's `entry` (its declared spacing) through it."""

    def __init__(self, engine: Any, on_item: Callable[[str, str], None]) -> None:
        self._engine, self._on_item = engine, on_item
        self.entry = getattr(engine, "entry", None)

    def complete(self, body: Any, cancel: CancelToken) -> Any:
        for item in self._engine.complete(body, cancel):
            if isinstance(item, tuple) and len(item) == 2 and item[1]:
                self._on_item(item[0], item[1])
            yield item


# The tags a `think_tags` reasoning goes back in when the entry declares none (AD-4).
THINK_TAGS = ("<think>", "</think>")


@dataclass
class _ModelOutput:
    status: str  # completed | cancelled | limit
    raw: str = ""
    # The output without its reasoning (local: the separator's `outside`, AD-6): what a
    # malformed call's step re-renders, its reasoning passed apart (AD-10).
    answer: str = ""
    text: str = ""
    reasoning: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    malformed: Malformed | None = None
    # The session's `tool_call_id` of each call (AD-4), and, in chat mode, each call's
    # `arguments` as the provider emitted them.
    ids: list[str] = field(default_factory=list)
    arguments: list[str] = field(default_factory=list)
    # Chat mode: each call's `extra_content` as the provider sent it (`None`: none), and the
    # `id` of the entry that sent them; only that entry ever gets them back (Gemini 3.x).
    extras: list[dict[str, Any] | None] = field(default_factory=list)
    extra_for: str | None = None
    # Chat mode: the call's `context_reconciled` payload once `usage` came back (AD-4); a
    # provider's refusal: its French message (for a failed delegation, AD-11).
    reconciled: dict[str, Any] | None = None
    message_text: str = ""


@dataclass(frozen=True)
class ArmedAction:
    """An action the user armed for the next turn (AD-3, AD-25): the session alone holds
    them. `kind`: a native tool call with its `args`, a skill, an MCP documentation, or a
    memory write with its `text` (story 14)."""

    armed_id: str
    kind: str  # tool | skill | tool_doc | memory | delegate
    brick: str
    target: str
    args: dict[str, Any]
    label_text: str

    def payload(self) -> dict[str, Any]:
        return {
            "armed_id": self.armed_id,
            "kind": self.kind,
            "brick": self.brick,
            "target": self.target,
            "args": self.args,
            "label_text": self.label_text,
        }


class ArmRefused(Exception):
    """An arming the session refuses: unknown target (`not_found`) or invalid arguments."""

    def __init__(self, reason_text: str, *, not_found: bool = False) -> None:
        super().__init__(reason_text)
        self.reason_text = reason_text
        self.not_found = not_found


@dataclass(frozen=True)
class TurnState:
    """What a turn reads for all its calls, frozen at its start (AD-17)."""

    history: tuple[Exchange, ...]
    system_prompt: str
    effective: frozenset[str]  # brick ids, `wanted` and `available`
    tools: tuple[str, ...] = ()  # enabled tools of the effective tools and mcp bricks
    # Lazy loading (AD-25): the available MCP tools whose documentation is not loaded yet.
    loadable: tuple[str, ...] = ()
    # Skills (AD-25), in the registry's order: loaded and enabled, then enabled not loaded.
    skills: tuple[str, ...] = ()
    skill_catalog: tuple[str, ...] = ()
    # Hooks (AD-13): the active ones, in call order; H3's text, set by `on_user_message`.
    hooks: tuple[str, ...] = ()
    injection: str = ""
    # Story 9: the armed actions taken when the turn is sent, consumed in arming order.
    armed: tuple[ArmedAction, ...] = ()
    # Story 14 (AD-4): the global memory's texts, read at the turn's start; empty when the
    # brick is not effective. A write during the turn waits for the next one.
    memory: tuple[str, ...] = ()
    # Story 15 (AD-4): the RAG's intro then its excerpts, formatted, found by this turn's
    # search; never kept in the history.
    rag_excerpts: tuple[str, ...] = ()
    # Story 16: the RAG's search is reranked (sub-option enabled, reranker loaded at start).
    rag_rerank: bool = False
    # Story 16: the sub-option enabled, but no reranker at the turn's start: why (the RAG
    # step says it), else `None`.
    rag_rerank_skipped_text: str | None = None
    # Story 20 (AD-22): what each of `rag_excerpts` was before the compressor (same order).
    rag_compressed: tuple[CompressedFrom | None, ...] = ()
    # Story 19 (AD-11): the sub-agent's tools, `[subagent] tools` among the enabled ones.
    subagent_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SubContext:
    """A sub-agent's context (AD-11): its own system prompt, the task and its tools, nothing
    else of the main context."""

    context_id: str  # sub{n}
    task: str
    prompt: str
    tools: tuple[str, ...]


@dataclass
class _SubOutcome:
    """How a sub-agent's loop ended; `message_text` is the error reinjected on a failure."""

    status: str  # completed | limit | overflow | error | cancelled
    result: str = ""
    message_text: str = ""


def _with_loaded(state: TurnState, loaded_in_turn: list[str]) -> TurnState:
    """Chat mode (AD-25): the documentations loaded in this turn join `tools` at once, by
    `build_turn_state`'s rule: out of `loadable`, and `load_tool_doc` gone once nothing is
    left to load."""
    added = [n for n in state.loadable if n in loaded_in_turn and n not in state.tools]
    if not added:
        return state
    loadable = tuple(n for n in state.loadable if n not in added)
    tools = list(state.tools)
    at = tools.index(LOAD_TOOL_DOC) if LOAD_TOOL_DOC in tools else len(tools)
    tools[at:at] = added
    if not loadable and LOAD_TOOL_DOC in tools:
        tools.remove(LOAD_TOOL_DOC)
    return replace(state, tools=tuple(tools), loadable=loadable)


@dataclass
class _Approval:
    """H5's pending (then answered) human validation (AD-13): the HTTP thread answers, the
    turn's thread waits on `answered`, without delay."""

    id: str
    decision: str | None = None  # approved | refused | cancelled
    disable_hook: bool = False
    answered: threading.Event = field(default_factory=threading.Event)


class SendRefused(Exception):
    def __init__(self, reason_text: str) -> None:
        super().__init__(reason_text)
        self.reason_text = reason_text


# AD-7, story 24: a hot switch's probe of a GGUF (`DiagnosticSession.probe_path`): `None`
# when it loads or when « Arrêter » (the load's token) killed it, else why, in French.
ProbeFn = Callable[[str, CancelToken | None], str | None]


class _LoadCancelled(Exception):
    """Lot E (E4): « Arrêter » during a load, seen at one of `_load`'s checkpoints."""


class _LoadFailed(Exception):
    """A load refused for a known reason (probe, incompatible template): `message_text` for
    `harness_error`, `reason_text` its cause, `idle_text` the reason left in `idle` when no
    model is active afterwards."""

    def __init__(
        self,
        message_text: str,
        reason_text: str,
        idle_text: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(reason_text)
        self.message_text, self.reason_text, self.idle_text = message_text, reason_text, idle_text
        self.detail = detail  # lot E (E6): the loader's own message, `harness_error.cause`


def _checkpoint(cancel: CancelToken | None) -> None:
    """Lot E (E4): a point of `_load` where « Arrêter » takes effect."""
    if cancel is not None and cancel.cancelled:
        raise _LoadCancelled


def _kind_tokens(payload: dict[str, Any], kind: SegmentKind) -> int:
    """The tokens of a context's segments of `kind` (AD-1: the session's own figures)."""
    return sum(s["tokens"] for s in payload["segments"] if s["kind"] == kind)


def _common_prefix(a: list[int], b: list[int]) -> int:
    """How many ids `a` and `b` share from their start."""
    pairs = enumerate(zip(a, b, strict=False))
    return next((i for i, (x, y) in pairs if x != y), min(len(a), len(b)))


def _engine_cached_ids(engine: Any) -> list[int] | None:
    """Lot A (AD-4): the ids an engine holds in its cache, `None` when it cannot say (an
    engine without `cached_ids`, or one that fails)."""
    try:
        cached = getattr(engine, "cached_ids", None)
        return None if cached is None else cached()
    except Exception:  # noqa: BLE001 - AD-16: unknown, the ids sent are kept instead
        return None


def _evaluated(engine: Any) -> int | None:
    """Lot A (AD-4): the prompt tokens the engine says its last call evaluated."""
    try:
        value = getattr(engine, "last_evaluated", None)
    except Exception:  # noqa: BLE001 - AD-16: unknown
        return None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _fr(n: int) -> str:
    return f"{n:,}".replace(",", "\u202f")  # narrow no-break space, French style


def _mo(n: int) -> str:
    """Bytes in decimal Mo, rounded, French style (story 15: one unit for file sizes)."""
    return _fr(round(n / 1_000_000))


def _stamp(path: Path) -> tuple[int, int] | None:
    """A file's modification time and size, to notice it was replaced; `None` if absent."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _missing_model_fr(noun: str, label_text: str, missing: list[ModelFile], tail: str = "") -> str:
    """Stories 15 and 16: « modèle absent » (or another file there) for the embedding or the
    reranking model (`noun`: `embedding` or `reranking`), with what to download or copy by
    hand, and where: a `Message`, rendered where it is shown. Reads the disk: called when
    the files are read again, never at each emission."""
    names = ", ".join(PurePosixPath(f.path).name for f in missing)
    folder = config.models_dir() / PurePosixPath(missing[0].path).parent
    total = sum(f.size for f in missing)
    size = Lazy(lambda lang: number(round(total / 1_000_000), lang))
    kind = Message(f"session.rag.model_noun.{noun}")
    if any((config.models_dir() / f.path).is_file() for f in missing):
        key = "session.rag.model_mismatch"
    else:
        key = "session.rag.model_absent"
    return Message(
        key, names=names, folder=folder, noun=kind, label=label_text, size=size, tail=tail
    )


_log = logging.getLogger(__name__)


def _join_fr(items: list[str]) -> str:
    """« a, b et c »: a French enumeration (`messages.join` in another language)."""
    return join(items, config.DEFAULT_LANGUAGE)


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


class AppSession:
    """The only session once WaveStack has a confirmed model."""

    def __init__(
        self,
        cfg: config.Config | None = None,
        engine_factory: Callable[..., Engine] = LlamaCppEngine,
        bricks: list[BrickDeclaration] | None = None,
        hooks: tuple[Hook, ...] = DEMO_HOOKS,
        cloud_factory: Callable[..., Any] | None = None,
        rss_fn: Callable[[], int] | None = None,
        server_factory: Callable[..., Engine] | None = None,
        embedder_factory: Callable[[EmbeddingModel], Embedder] | None = None,
        reranker_factory: Callable[[RerankerModel], Reranker] | None = None,
        download_transport: Any = None,
        compressor_factory: Callable[[], Compressor] | None = None,
    ) -> None:
        self.cfg = cfg or config.load_config()
        # Languages (1/5): the language of the content sent to the model, `fr` by default;
        # changed only on an empty conversation (`set_language`).
        self._language = self.cfg.language
        # Languages (2/5): the interface's texts, read at the first `ui_texts()` in the
        # session's language, again after a change of language.
        self._ui_texts: UiTexts | None = None
        self._engine_factory = engine_factory
        # Story 18: the adapter of a model an already-running local server serves
        # (`llama_server`, `ollama_raw`), a fake one in tests.
        self._server_factory = server_factory or (
            lambda candidate, n_ctx: open_engine(candidate, n_ctx, self.cfg)
        )
        # Story 11: the cloud model's adapter (`openai_chat`), a fake one in tests.
        self._cloud_factory = cloud_factory or (
            lambda entry, key: OpenAIChatEngine(
                entry,
                key,
                connect_timeout_s=self.cfg.cloud_connect_timeout_s,
                read_timeout_s=self.cfg.cloud_read_timeout_s,
            )
        )
        self._cloud: CloudModel | None = None  # the active cloud model: chat mode (AD-4)
        self._window_source = "configured"
        # AD-4: the last real `usage.prompt_tokens / Σ estimates` of the main context, by
        # cloud model `id` (`_ratio` reads the active one's).
        self._ratios: dict[str, float] = {}
        # AD-8: every model load goes through the registry, one generative slot.
        self._load_registry = LoadRegistry(
            self.cfg.memory_budget, self.cfg.load_margin_bytes, rss_fn or process_rss
        )
        self._active: ModelChoice | None = None  # the model loaded now (AD-3)
        self._call_ids: set[str] = set()  # the running turn's `tool_call_id`s (AD-4)
        self._cloud_content = None  # `content/cloud.yaml`, read when a cloud model boots
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wavestack-worker")
        self._lock = threading.Lock()
        self.state = "diagnostic"
        self.reason_text: str | None = Message("session.state.diagnostic")
        self._engine: Engine | None = None
        self._model_name: str | None = None  # file stem of the loaded GGUF, shown in the schema
        self._caps: Capabilities | None = None
        # Story 26 (AD-9): the window chosen in the interface, else read at launch
        # (`[context] window`, `settings.json` over `wavestack.toml`); every load reads it
        # (`configured_window`), and the active model's effective one is `_window`.
        self._configured_window = self.cfg.context_window
        self._window = self._configured_window
        # The active model's metadata (its native and server contexts), for the window
        # panel's choices; `None` for a cloud model or none.
        self._meta: EngineMetadata | None = None
        # Story 26: the prompt read rate measured by model label (tokens a second), on a local
        # or served call that evaluated at least `READ_MIN_TOKENS` tokens.
        self._read_tps: dict[str, float] = {}
        self._read_warm = False  # a call was made since the last load: the next one measures
        self._labels: SegmentLabels | None = None
        self._turns = 0
        self._cancel: CancelToken | None = None
        # Bricks: in memory only, every launch starts as the bare LLM (no persistence).
        declared = BRICKS if bricks is None else bricks
        check_panel_groups(declared)
        self._bricks = check_unique_ids(declared)
        self._wanted: set[str]  # launch values: `_apply_launch_config`
        self._history: list[Exchange] = []
        self._custom_prompt: str | None  # None: the default from content/
        self._content: dict[str, BrickContent] = {}
        self._content_errors: dict[str, str] = {}
        self._default_prompt = ""
        self._tools_content: ToolsContent | None = None
        self._mcp_content: McpContent | None = None
        self._skills_content: SkillsContent | None = None
        self._hooks = hooks  # tests replace them to reach every point (CAP-27)
        self._hooks_content: HooksContent | None = None
        # Story 14 (AD-20, AD-23): the global memory, the mirror of `memory.json` the session
        # alone writes; `_memory_error` while the file is unreadable (brick unavailable).
        self._memory_content: memory_file.MemoryContent | None = None
        self._memory: list[memory_file.MemoryEntry] = []
        self._memory_error: str | None = None
        # One write at a time, whichever thread; a drawer write or a reset holds it from its
        # `idle` check to its end, and a turn takes it to start: no drawer write in a turn.
        # Always taken before `_lock`.
        self._memory_lock = threading.RLock()
        self._subagent_content: SubagentContent | None = None
        # Story 19 (AD-11): sub-agents numbered over the session's life, never reset; the
        # running turn's frozen state and stop token, for `delegate`.
        self._subs = 0
        self._turn_ctx: tuple[TurnState, CancelToken] | None = None
        self._hook_steps = 0  # hook steps of the running turn, for their step ids
        self._turn_seq = 0  # seq of the running turn's `turn_started`: its events follow it
        # Story 15 (AD-8, AD-22): the RAG's texts and model, what was read of its index and
        # model files (at launch and after a download), and the embedding model loaded.
        self._embedder_factory = embedder_factory or embedding_module.open_embedder
        self._download_transport = download_transport  # tests: an `httpx.MockTransport`
        self._rag_content: RagContent | None = None
        self._rag_model: EmbeddingModel | None = None
        # The index's state: `vec` (sqlite-vec), `absent`, `unreadable`, `other_model`,
        # `stale`, or `None` (usable), with its French reason.
        self._rag_index_kind: str | None = None
        self._rag_index_error: str | None = None
        self._rag_stamp: tuple[int, int] | None = None  # the index file read: mtime, size
        self._rag_chunks = 0
        self._rag_missing: list[ModelFile] = []
        self._rag_missing_text: str | None = None  # its reason, read with the files
        self._rag_longest: list[Chunk] = []  # the preview's excerpts (AD-9)
        self._embedder: Embedder | None = None
        self._rag_retriever: SqliteVecRetriever | None = None  # its index connection
        self._rag_loading = False
        self._rag_load_error: str | None = None  # the budget's refusal, or the load's failure
        self._download_cancel: CancelToken | None = None  # « Arrêter » a download or a build
        # Lot E (E4): « Arrêter » a model load, read by `_load` at its checkpoints.
        self._load_cancel: CancelToken | None = None
        # Story 16 (AD-8): the reranking sub-option, its model (`[rag.reranker]`, or why it is
        # invalid), the files missing, and the reranker loaded.
        self._reranker_factory = reranker_factory or reranker_module.open_reranker
        self._rerank_model: RerankerModel | None = None
        self._rerank_config_error: str | None = None
        self._rerank_missing: list[ModelFile] = []
        self._rerank_missing_text: str | None = None  # its reason, read with the files
        self._reranker: Reranker | None = None
        self._rerank_loading = False
        self._rerank_load_error: str | None = None
        self._rag_rerank = False  # launch value: `_apply_launch_config`
        self._sent_rerank = False  # what the last `send` froze, for `pending`
        # Story 20 (AD-8, AD-22): Headroom, an optional dependency, loaded while the brick is
        # wanted; why it cannot be (not installed) is read once, for the default adapter only.
        self._compressor_factory: Callable[[], Compressor] = (
            compressor_factory or headroom_adapter.HeadroomCompressor
        )
        self._compression_missing = (
            headroom_adapter.missing_fr() if compressor_factory is None else None
        )
        self._compression_content: CompressionContent | None = None
        self._compressor: Compressor | None = None
        self._compression_loading = False
        self._compression_load_error: str | None = None
        self._compressor_imported = False  # AD-8: its memory stays counted by the RSS once in
        # Story 29 (« LLM nu »): the screen's requests, numbered over the session's life
        # (`llm{n}`), and the content error already traced (once per message).
        self._labs = 0
        self._lab_error_traced: str | None = None
        # Story 30 (the RAG workshop): its runs, numbered over the session's life (`lab{n}`),
        # and its content error already traced (once per message).
        self._rag_labs = 0
        self._rag_lab_error_traced: str | None = None
        # Increment 3: FAISS and LanceDB imported (what each import added to the RSS), and
        # the ones whose import failed (a DLL blocked), then unavailable with the reason.
        self._rag_lab_imported: dict[str, int | None] = {}
        self._rag_lab_import_errors: dict[str, str] = {}
        # The catalog the validation of an edited chain reads (`_rag_lab_recent_catalog`).
        self._rag_lab_catalog_kept: tuple[float, Any, rag_lab.Catalog] | None = None
        # Story 6 of 2026-09-30 (the MCP workshop): its exchanges, numbered (`mcp{n}`), the
        # first of its last connection, its own connection (never the brick's) and the tools
        # it listed, and its content error already traced.
        self._mcp_labs = 0
        self._mcp_lab_first = 0
        self._mcp_lab_conn: mcp_lab.LabConnection | None = None
        self._mcp_lab_tools: dict[str, Any] = {}
        self._mcp_lab_error_traced: str | None = None
        self._load_content()
        self._registry = ToolRegistry(
            self._native_tools()
            + network_tools(self.cfg, lambda: self._language)
            + self._harness_tools(),
            self._tools_content,
            lambda: self._language,
        )
        # Languages (5/5): what the executor writes, in the session's language at each call.
        self._tool_executor = ToolExecutor(self._registry, lambda: self._language)
        self._check_subagent_tools()
        self._tools_enabled: set[str]  # sub-options: see `_apply_launch_config`
        # MCP servers (story 6): the local one starts enabled, the public ones disabled. A
        # server is contacted only while enabled with the brick wanted (AD-15).
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mcp_servers = mcp_servers(self.cfg)
        self._mcp_enabled: set[str]
        self._mcp_conns: dict[str, McpConnection] = {}
        self._mcp_state: dict[str, tuple[str, str | None]] = {}  # contact, reason_text
        # Story 6b: documentation complète by default; the documentations loaded belong to
        # the conversation (AD-17), and wait while their server is off.
        self._mcp_lazy: bool
        self._loaded_docs: set[str] = set()
        # Skills (story 7): the skills loaded belong to the conversation (AD-17), and wait
        # while their skill is disabled.
        self._skills_enabled: set[str]
        self._loaded_skills: set[str] = set()
        self._hooks_enabled: set[str]
        # H5 (8b): the last validation asked, and the hooks switched off for the rest of the
        # running turn (« Autoriser et ne plus demander »), since its state is frozen.
        self._approval: _Approval | None = None
        self._approvals = 0
        self._hooks_off: set[str] = set()
        # Story 9 (AD-3): the armed actions, in arming order, and their counter for ids.
        self._armed: list[ArmedAction] = []
        self._arms = 0
        # Story 9b (AD-17): the last turn started and the conversational state it started
        # from (turn id, message, history, skills and documentations loaded), for the replay.
        # Lot A (N1): with the global memory it read, frozen for the conversation.
        self._last: (
            tuple[
                str,
                str,
                tuple[Exchange, ...],
                frozenset[str],
                frozenset[str],
                tuple[tuple[str, str], ...] | None,
            ]
            | None
        ) = None
        # Lot A (N1, AD-17): the global memory the conversation reads, taken at its first
        # turn; `None` until then (the preview reads the file's current entries).
        # `(id, text)` pairs: an entry deleted or edited since leaves it at once.
        self._memory_snapshot: tuple[tuple[str, str], ...] | None = None
        # Lot A (AD-4, AD-11): the ids the engine holds for the main context after its last
        # call (`None`: nothing known, no check); why the next turn's first call may not
        # extend them (`reset`, `replay`); a sub-agent's context left in the engine's cache
        # (`stateless` or `failed`); and the last turn's status (`abandoned`).
        self._main_cache: list[int] | None = None
        self._cache_cause: str | None = None
        self._cache_evicted: str | None = None
        self._last_status: str | None = None
        self._turn_called = False  # the running turn made a main call (`abandoned`)
        # FinOps: the running turn's cloud calls' costs (main and sub-agent), for `turn_ended`.
        self._turn_costs: list[CallCost] = []
        # GreenOps: the running turn's estimated footprints (cloud and local, sub-agent
        # included), for `turn_ended`; CodeCarbon around each local call, counted by the
        # memory budget at its first use.
        self._turn_impacts: list[Impact] = []
        self._greenops_warm_up: threading.Thread | None = None  # the last warm-up (tests)
        self._local_meter = LocalMeter(
            self.cfg.local_gco2e_per_kwh,
            check=lambda: self._load_registry.check_component(
                "CodeCarbon", self.cfg.greenops_codecarbon_cost_bytes, GREENOPS_CODECARBON
            ),
            grant=lambda: self._load_registry.grant(
                "CodeCarbon", self.cfg.greenops_codecarbon_cost_bytes, GREENOPS_CODECARBON
            ),
        )
        self._save_failed = False  # the last `_save_main_state` failed (not unavailable)
        # Configuration frozen by the last `send`: `pending` is measured against it.
        self._sent: tuple[
            frozenset[str],
            str,
            frozenset[str],
            frozenset[str],
            bool,
            frozenset[str],
            frozenset[str],
        ]
        self._apply_launch_config()
        # Story 10 (AD-19): the programme, and the scenario launched last (`None` at launch
        # and after a reset).
        self._scenarios: ScenariosContent | None = None
        self._active_scenario: str | None = None
        self._load_scenarios()
        self._emit_memory()

    def _apply_launch_config(self) -> None:
        """The launch configuration, applied again by a reset or before a scenario: no
        brick, default sub-options and system prompt, nothing sent yet."""
        self._wanted = set()
        self._custom_prompt = None
        # Offline tools start enabled; network tools start disabled (story 5b). Harness and
        # MCP tools are no sub-option: the session alone decides when they are offered.
        self._tools_enabled = {
            n
            for n in self._registry.names
            if not (spec := self._registry.get(n)).network
            and spec.source != "harness"
            and not spec.is_mcp
        }
        # MCP servers (story 6): the local one starts enabled, the public ones disabled.
        self._mcp_enabled = {"local"} & set(self._mcp_servers)
        self._mcp_lazy = False  # story 6b: documentation complète by default
        self._rag_rerank = self._sent_rerank = False  # story 16: no reranking at launch
        self._skills_enabled = set(self._skill_ids())  # story 7: all enabled
        self._hooks_enabled = set(self._hook_ids()) - {"h5"}  # story 8: H5 disabled (8b, Q1)
        self._sent = (
            frozenset(),
            self._default_prompt,
            frozenset(),
            frozenset(),
            False,
            frozenset(self._skills_enabled),
            frozenset(self._hooks_enabled),
        )

    # ---------- state ----------

    def _set_state(self, state: str, reason_text: str | None = None) -> None:
        with self._lock:
            self.state, self.reason_text = state, reason_text
        self._emit_state()

    def active_model(self) -> dict[str, Any] | None:
        """AD-12: the model indicator's only source, from the file or the cloud entry."""
        if self._cloud is not None:
            return active_model(self._cloud, self._language)
        if self._model_name is None:
            return None
        active = self._active
        if active is not None and active.kind == "server":
            return self._model_payload(active)
        return {
            "id": self._model_name,
            "label": self._model_name,
            "hosting": "local",
            "kind": "file",
            "ref": active.ref if active is not None else None,
        }

    def _emit_state(self) -> None:
        with self._lock:
            state, reason_text = self.state, self.reason_text
            language, locked = self._language, self._conversation_started()
        self._journal().emit(
            "session_state",
            {
                "state": state,
                "reason_text": reason_text,
                "active_model": self.active_model(),
                "language": language,
                "language_locked": locked,
            },
        )

    def emit_initial(self) -> None:
        self._emit_state()
        self._emit_architecture()
        self._emit_bricks()
        self._emit_window_state()  # story 26: the window panel, before any model

    def _drawn_components(self, brick: BrickDeclaration) -> list[Component]:
        """A tool or an MCP server is drawn only while its sub-option is enabled."""
        with self._lock:
            if brick.id == "tools":
                enabled = {f"tools.{name}" for name in self._tools_enabled}
            elif brick.id == "mcp":
                enabled = {f"mcp.{server}" for server in self._mcp_enabled}
            elif brick.id == "skills":
                enabled = {f"skills.{skill}" for skill in self._skills_enabled}
            elif brick.id == "hooks":
                enabled = {f"hooks.{hook}" for hook in self._hooks_enabled}
            elif brick.id == "rag":  # story 16: the reranker while its sub-option is enabled
                enabled = {c.id for c in brick.components if c.id != RAG_RERANKER}
                enabled |= {RAG_RERANKER} if self._rag_rerank else set()
            else:
                return list(brick.components)
        return [c for c in brick.components if c.id in enabled]

    def _mcp_label(self, server_id: str) -> str:
        text = self._mcp_content.servers.get(server_id) if self._mcp_content else None
        return text.label_text if text else server_id

    def _hook_ids(self) -> list[str]:
        """The declared hooks, in the registry's order, which is their call order."""
        brick = self._bricks.get("hooks")
        return [c.id.removeprefix("hooks.") for c in brick.components] if brick else []

    def _hook_label(self, hook_id: str) -> str:
        text = self._hooks_content.hooks.get(hook_id) if self._hooks_content else None
        return text.label_text if text else hook_id

    def _skill_ids(self) -> list[str]:
        """The declared skills, in the registry's order."""
        brick = self._bricks.get("skills")
        return [c.id.removeprefix("skills.") for c in brick.components] if brick else []

    def _skill_text(self, skill_id: str) -> SkillText | None:
        return self._skills_content.skills.get(skill_id) if self._skills_content else None

    def _skill_label(self, skill_id: str) -> str:
        text = self._skill_text(skill_id)
        return text.label_text if text else skill_id

    def _mcp_tools(self, server_id: str) -> list[str]:
        """The names the registry exposes for `server_id`'s tools."""
        return [n for n in self._registry.names if n.startswith(f"{server_id}__")]

    def _mcp_node(self, node: dict[str, Any], server_id: str) -> None:
        """AD-12: an MCP server node carries its connection state and its tools."""
        with self._lock:
            contact, why = self._mcp_state.get(server_id, ("not_contacted", None))
        text = self._mcp_content.servers.get(server_id) if self._mcp_content else None
        node.update(
            kind="mcp_server",
            label_text=self._mcp_label(server_id),
            contact=contact,
            tools=self._mcp_tools(server_id) if contact == "available" else [],
        )
        if node["hosting"] == "network" and text is not None:  # story 34, AD-19
            node["sends_text"] = text.sends_text
        if node["available"] and contact == "unavailable":
            node["available"], node["reason_text"] = False, self._text(why)

    def _emit_architecture(self) -> None:
        """AD-12: a component is drawn as soon as its brick is `wanted`, even unavailable."""
        always = self._caps is not None and self._caps.reasoning_always
        with self._lock:
            # A model that always reasons draws the reasoning brick, as its card shows it on.
            wanted = [
                b
                for b in self._bricks.values()
                if b.id in self._wanted or (always and b.id == "reasoning")
            ]
        model = {**_CORE_MODEL, "model": self._model_name}
        edges: list[dict[str, Any]] = []
        active = self._active
        if self._cloud is not None:  # AD-12: drawn in the network zone, with its provider
            model |= {"hosting": "network", "provider": self._cloud.provider}
            edges.append({"from": "core.harness", "to": "core.model", "crosses_boundary": True})
        elif active is not None and active.kind == "server":
            # Story 18: a process of this workstation apart from the harness; the call stays
            # on the loopback, it never crosses the workstation's boundary.
            model |= {
                "process": "external",
                "provider": active.provider,
                "server_url": getattr(active.server, "server_url", None),
            }
            edges.append({"from": "core.harness", "to": "core.model", "crosses_boundary": False})
        nodes: list[dict[str, Any]] = [_CORE_HARNESS, model]
        if any(b.id == "subagent" for b in wanted):  # AD-11: the same model, a second context
            available, reason_text = self._availability("subagent")
            sub_model = {
                **model,
                "id": "core.model_sub",
                "label_text": self._t("session.architecture.model_sub"),
                "available": available,
                "reason_text": reason_text,
            }
            nodes.append(sub_model)
            if self._cloud is not None:  # as `core.model`: an edge only across the boundary
                edges.append(
                    {"from": "core.harness", "to": "core.model_sub", "crosses_boundary": True}
                )
        components = {b.id: self._drawn_components(b) for b in wanted}
        # A file node is drawn once a drawn component points to it: its brick, its label
        # and what its tooltip adds.
        targets = {t for cs in components.values() for c in cs for t in c.edges_to}
        files = {
            "file.demo_dir": (
                "tools",
                self._tools_content.demo_dir_label_text if self._tools_content else "demo_files",
                None,
            ),
            AUDIT: (
                "hooks",
                self._hooks_content.audit_label_text if self._hooks_content else "audit.log",
                str(config.audit_path()),
            ),
            MEMORY: (
                "global_memory",
                self._memory_content.file_label_text if self._memory_content else "memory.json",
                str(config.memory_path()),
            ),
            RAG_INDEX: (
                "rag",
                self._rag_content.index_label_text if self._rag_content else "rag_index.sqlite",
                self._rag_index_detail(),
            ),
        }
        for file_id, (brick_id, label, detail_text) in files.items():
            if file_id not in targets or brick_id not in self._bricks:
                continue
            available, reason_text = self._availability(brick_id)
            nodes.append(
                {
                    "id": file_id,
                    "kind": "file",
                    "hosting": "local",
                    "label_text": label,
                    "wanted": True,
                    "available": available,
                    "reason_text": reason_text,
                    "detail_text": detail_text,
                }
            )
        drawn = {n["id"] for n in nodes} | {c.id for cs in components.values() for c in cs}
        for brick in wanted:
            available, reason_text = self._availability(brick.id)
            for component in components[brick.id]:
                hosting = "network" if component.hosting == "network_service" else "local"
                is_tool = component.kind == "tool"
                is_skill = component.kind == "skill"
                is_hook = component.kind == "hook"
                node = {
                    "id": component.id,
                    "kind": component.kind if is_tool or is_skill or is_hook else "brick",
                    "hosting": hosting,
                    "label_text": (
                        self._registry.label(component.id.removeprefix("tools."))
                        if is_tool
                        else self._skill_label(component.id.removeprefix("skills."))
                        if is_skill
                        else self._hook_label(component.id.removeprefix("hooks."))
                        if is_hook
                        else self._label(brick.id)
                    ),
                    "wanted": True,
                    "available": available,
                    "reason_text": reason_text,
                }
                if is_tool and hosting == "network":
                    name = component.id.removeprefix("tools.")
                    contact, why = self._tool_executor.contact.get(name, ("not_contacted", None))
                    node["contact"] = contact
                    node["sends_text"] = self._registry.sends(name)  # story 34, AD-19
                    if available and contact == "unavailable":
                        node["available"], node["reason_text"] = False, self._text(why)
                if component.kind == "mcp_server":
                    self._mcp_node(node, component.id.removeprefix("mcp."))
                if is_skill:  # its tooltip gives its description and state (FR-3)
                    skill_id = component.id.removeprefix("skills.")
                    text = self._skill_text(skill_id)
                    with self._lock:
                        node["loaded"] = skill_id in self._loaded_skills
                    node["detail_text"] = text.description if text else None
                if is_hook and self._hooks_content:  # its tooltip says when it acts
                    hook = self._hooks_content.hooks.get(component.id.removeprefix("hooks."))
                    node["detail_text"] = hook.description_text if hook else None
                if component.id == "rag.retriever" and self._rag_model is not None:
                    node["detail_text"] = self._t(
                        "session.architecture.embedding", model=self._rag_model.id
                    )
                if component.id == RAG_RERANKER:  # story 16: its label, model and own reason
                    if self._rag_content is not None:
                        node["label_text"] = self._rag_content.rerank_label_text
                    if self._rerank_model is not None:
                        node["detail_text"] = self._t(
                            "session.architecture.reranking", model=self._rerank_model.id
                        )
                    ok, why = self._rerank_availability()
                    if node["available"] and not ok:
                        node["available"], node["reason_text"] = False, self._text(why)
                if component.id == "compression.compressor":
                    node["detail_text"] = self._t(
                        "session.architecture.compressor", label=self._compressor_label()
                    )
                nodes.append(node)
                edges += [
                    {"from": component.id, "to": target, "crosses_boundary": hosting == "network"}
                    for target in component.edges_to
                    if target in drawn  # e.g. a `file.*` node not emitted yet
                ]
        self._journal().emit("architecture_changed", {"nodes": nodes, "edges": edges})

    def _pending_ids(self) -> set[str]:
        """Bricks whose effect on the next turn differs from what the last `send` froze."""
        mcp_tools = frozenset(self._mcp_tool_names())
        with self._lock:
            (
                sent_wanted,
                sent_prompt,
                sent_tools,
                sent_mcp,
                sent_lazy,
                sent_skills,
                sent_hooks,
            ) = self._sent
            pending = set(self._wanted) ^ sent_wanted
            prompt = self._custom_prompt or self._default_prompt
            if "system_prompt" in self._wanted and prompt != sent_prompt:
                pending.add("system_prompt")
            if "tools" in self._wanted and self._tools_enabled != sent_tools:
                pending.add("tools")
            mcp_changed = mcp_tools != sent_mcp or self._mcp_lazy != sent_lazy
            if "mcp" in self._wanted and mcp_changed:
                pending.add("mcp")
            if "skills" in self._wanted and self._skills_enabled != sent_skills:
                pending.add("skills")
            if "hooks" in self._wanted and self._hooks_enabled != sent_hooks:
                pending.add("hooks")
            if "rag" in self._wanted and self._rag_rerank != self._sent_rerank:  # story 16
                pending.add("rag")
        return pending

    def _mcp_options(self) -> list[dict[str, Any]]:
        with self._lock:
            enabled = set(self._mcp_enabled)
        available = self._mcp_tool_names()
        tools = {s: [n for n in available if n.startswith(f"{s}__")] for s in self._mcp_servers}
        return [
            {
                "id": server.id,
                "label_text": self._mcp_label(server.id),
                "enabled": server.id in enabled,
                "hosting_text": self._t(
                    "session.hosting.network" if server.network else "session.hosting.local"
                ),
                "network": server.network,
                # Story 9: the tools whose documentation « Charger la documentation » loads.
                "tools": tools.get(server.id, []),
                # Lot K: « Forcer l'appel » of each of them, its form and its presets.
                "calls": [self._mcp_call_option(n) for n in tools.get(server.id, [])],
            }
            for server in self._mcp_servers.values()
        ]

    def _mcp_call_option(self, name: str) -> dict[str, Any]:
        """Lot K: the form of an MCP tool's forced call: one field per parameter of its
        schema, described by the server (« facultatif » when not required), and the presets
        of `content/mcp.yaml` restricted to those parameters."""
        spec = self._registry.get(name)
        params = dict(spec.params) if spec else {}
        properties = ((spec.schema if spec else None) or {}).get("properties") or {}
        required = set(params) if spec is None or spec.required is None else set(spec.required)
        parameters = {}
        for arg in params:
            described = properties.get(arg, {}) if isinstance(properties, dict) else {}
            text = described.get("description") if isinstance(described, dict) else None
            text = str(text).strip() if text else f"Argument {arg}."
            parameters[arg] = text if arg in required else f"{text} (facultatif)"
        content = self._mcp_content.call_presets.get(name, []) if self._mcp_content else []
        presets = [
            {"label_text": p.label_text, "args": {k: v for k, v in p.args.items() if k in params}}
            for p in content
        ]
        return {"tool": name, "parameters": parameters, "presets": presets}

    def _skill_options(self) -> list[dict[str, Any]]:
        with self._lock:
            enabled = set(self._skills_enabled)
        return [
            {
                "id": skill_id,
                "label_text": self._skill_label(skill_id),
                "enabled": skill_id in enabled,
                "hosting_text": "Local",
                "network": False,
            }
            for skill_id in self._skill_ids()
        ]

    def _hook_options(self) -> list[dict[str, Any]]:
        with self._lock:
            enabled = set(self._hooks_enabled)
        return [
            {
                "id": hook_id,
                "label_text": self._hook_label(hook_id),
                "enabled": hook_id in enabled,
                "hosting_text": "Local",
                "network": False,
            }
            for hook_id in self._hook_ids()
        ]

    def _tool_options(self) -> list[dict[str, Any]]:
        with self._lock:
            enabled = set(self._tools_enabled)
        options = []
        for name in self._registry.names:
            spec = self._registry.get(name)
            # MCP tools are the mcp brick's servers; harness tools are no sub-option.
            if spec is None or spec.is_mcp or spec.source == "harness":
                continue
            text = self._tools_content.tools.get(name) if self._tools_content else None
            options.append(
                {
                    "id": name,
                    "label_text": self._registry.label(name),
                    "enabled": name in enabled,
                    "hosting_text": self._t(
                        "session.hosting.network" if spec.network else "session.hosting.local"
                    ),
                    "network": spec.network,
                    # Story 9: the form of a forced call, one field per parameter.
                    "parameters": {
                        arg: text.parameters.get(arg, arg) if text else arg for arg in spec.params
                    },
                    "presets": [p.model_dump() for p in text.presets] if text else [],
                }
            )
        return options

    def _limits_fr(self) -> str:
        return self._t(
            "session.bricks.limits",
            calls=self.cfg.tool_max_calls,
            retries=self.cfg.tool_max_retries,
        )

    def _subagent_card(self, text: SubagentContent) -> dict[str, Any]:
        """Story 19: « Déléguer au sous-agent » on the card (no sub-option), and the bounds."""
        tools = ", ".join(self._registry.label(n) for n in self.cfg.subagent_tools) or self._t(
            "tools.check.none"
        )
        n = self.cfg.subagent_max_calls
        return {
            "force": {
                "kind": "delegate",
                "target": DELEGATE,
                "label_text": text.force_label_text,
                "parameters": {"task": text.task_label_text},
                "presets": [p.model_dump() for p in text.presets],
            },
            "limits_text": self._t("session.bricks.subagent_limits", count=n, tools=tools),
        }

    def _outbound_fr(self, brick_id: str, content: BrickContent | None) -> str | None:
        """Story 23: the card's « what leaves the workstation, and where to read it », built
        from `content/bricks/*.yaml` (AD-19): the network tools, in the registry's order, and
        the public MCP servers. None for a brick with nothing that can leave."""
        if content is None or content.outbound_text is None or brick_id not in ("tools", "mcp"):
            return None
        servers = [self._mcp_label(s.id) for s in self._mcp_servers.values() if s.network]
        tools: list[str] = []
        if brick_id == "tools":
            tools = [o["label_text"] for o in self._tool_options() if o["network"]]
            if not tools and not servers:
                return None
        elif not servers:
            return None
        try:
            lang = self._language
            return content.outbound_text.format(
                tools=join(tools, lang) or msg("session.outbound.no_tool", lang),
                servers=join(servers, lang) or msg("tools.check.none", lang),
            )
        except (KeyError, IndexError, ValueError, AttributeError, TypeError) as exc:
            # A placeholder the session does not fill (`{x}`, `{tools.x}`, `{0}`): no line,
            # but the cards still go out.
            _log.warning("outbound_text of %s ignored: %s: %s", brick_id, type(exc).__name__, exc)
            return None

    def _emit_bricks(self) -> None:
        pending = self._pending_ids()
        with self._lock:
            wanted = set(self._wanted)
            custom = self._custom_prompt
            lazy = self._mcp_lazy
        bricks = []
        for brick in self._bricks.values():
            available, reason_text = self._availability(brick.id)
            content = self._content.get(brick.id)
            bricks.append(
                {
                    "id": brick.id,
                    "label_text": self._label(brick.id),
                    "category": brick.category,
                    "group": brick.group,
                    "category_text": content.category_text if content else brick.category,
                    "hosting_text": content.hosting_text if content else "",
                    "explanation_text": self._explanation(content),
                    "wanted": brick.id in wanted,
                    "available": available,
                    "reason_text": reason_text,
                    "pending": brick.id in pending,
                    "options": (
                        self._tool_options()
                        if brick.id == "tools"
                        else self._mcp_options()
                        if brick.id == "mcp"
                        else self._skill_options()
                        if brick.id == "skills"
                        else self._hook_options()
                        if brick.id == "hooks"
                        else []
                    ),
                    "limits_text": self._limits_fr() if brick.id == "tools" else None,
                    "outbound_text": self._outbound_fr(brick.id, content),
                }
            )
            if brick.id == "reasoning":
                bricks[-1]["always_text"] = self._always_fr()
                bricks[-1]["limits_text"] = self._reasoning_budget_fr()
            if brick.id == "global_memory":
                bricks[-1] |= self._memory_card()
            if brick.id == "subagent" and self._subagent_content is not None:
                bricks[-1] |= self._subagent_card(self._subagent_content)
            if brick.id == "rag":
                bricks[-1] |= self._rag_offers() | {"rerank": self._rerank_card()}
            if brick.id == "compression" and self._compression_content is not None:
                bricks[-1]["limits_text"] = self._compression_content.limits_text.format(
                    min_chars=self.cfg.compression_min_chars
                )
            if brick.id == "mcp":
                bricks[-1] |= {
                    "mode": "lazy" if lazy else "full",
                    "lazy_label_text": (
                        self._mcp_content.lazy_label_text if self._mcp_content else "Lazy loading"
                    ),
                }
        text = custom if custom is not None else self._default_prompt
        self._journal().emit(
            "bricks_changed",
            {
                "bricks": bricks,
                "system_prompt": {"text": text, "is_default": text == self._default_prompt},
            },
        )

    def _journal(self) -> _RenderingJournal:
        """Languages (5/5): the journal, every `Message` of a payload written in the
        session's language as it is emitted (the texts built far from the session)."""
        return _RenderingJournal(get_journal(), self._language)

    @staticmethod
    def _mo_lazy(n: int) -> Lazy:
        """Bytes in decimal Mo, rounded (story 15), in the language rendered in."""
        return Lazy(lambda lang: number(round(n / 1_000_000), lang))

    @staticmethod
    def _num_lazy(n: int) -> Lazy:
        """A count of tokens, in the language its message is rendered in (« 8 192 »)."""
        return Lazy(lambda lang: number(n, lang))

    @staticmethod
    def _size_lazy(n: int) -> Lazy:
        """A size (« 448 Mo », « 1,8 Go »), in the language its message is rendered in."""
        return Lazy(lambda lang: config.size_fr(n, lang))

    @staticmethod
    def _bound_lazy(source: str, window: int, provider: str | None = None) -> Lazy:
        """Story 26: « (bornée à … par …) » after a window, or nothing, in the language its
        message is rendered in."""

        def bound(lang: str) -> str:
            text = bound_fr(source, window, provider, lang)
            return f" ({text})" if text else ""

        return Lazy(bound)

    def _decimal(self, text: str) -> str:
        """A decimal written with `.`, in the session's language (« 12,5 » but in English)."""
        return text if self._language == "en" else text.replace(".", ",")

    def _n(self, n: float) -> str:
        """A count in the session's language: « 8 192 », « 8,192 », « 8.192 »."""
        return number(n, self._language)

    def _t(self, key: str, /, **kw: Any) -> str:
        """Languages (5/5): the message `key` of `messages.yaml` in the session's language."""
        return msg(key, self._language, **kw)

    def _text(self, value: Any) -> Any:
        """Languages (5/5): a `Message` or a `KeyedError` written in the session's language
        where it is placed (an event, the state, the context), as a `Said` (a `str` that
        keeps its `Message`, for the terminal); anything else as it is."""
        return said(value, self._language)

    def _error(self, message_text: str, exc: BaseException | str, effect_text: str) -> None:
        """A `harness_error`: its texts (`Message`s, or a keyed exception as the cause) in
        the session's language; a third party's exception text stays as it is."""
        if isinstance(exc, str):
            cause = self._text(exc)
        elif isinstance(exc, KeyedError):
            kind = getattr(exc, "shown_name", type(exc).__name__)
            cause = self._text(Message("session.cause", kind=kind, text=exc.message))
        else:
            cause = f"{type(exc).__name__}: {exc}"
        self._journal().emit(
            "harness_error",
            {
                "message_text": self._text(message_text),
                "cause": cause,
                "effect_text": self._text(effect_text),
            },
        )

    def _localized(self, load: Callable[..., Any], *args: Any) -> Any:
        """Languages (1/5, AD-19): `load(*args)` in the session's language. A translation
        that fails is traced (`harness_error`), then the French file answers; the French
        file's own failure is raised, for the caller to trace as before."""
        lang = self._language
        if lang == config.DEFAULT_LANGUAGE:
            # Always the session's language, never `settings.json`'s; a loader a test replaces
            # without `lang` is called as it is.
            return load(*args, lang=lang) if _takes_lang(load) else load(*args)
        try:
            return load(*args, lang=lang)
        except Exception as exc:  # noqa: BLE001 - AD-19: traced, then French
            content = load(*args, lang=config.DEFAULT_LANGUAGE)
            self._error(
                msg("session.translation_invalid.message", lang, lang=lang),
                exc,
                msg("session.translation_invalid.effect", lang),
            )
            return content

    def join(self) -> None:
        """Wait until the worker has run everything submitted so far."""
        self._executor.submit(lambda: None).result()

    def close(self) -> None:
        self.stop()
        with self._lock:
            conns = list(self._mcp_conns.values())
            self._mcp_conns.clear()
        for conn in conns:  # AD-21: no local server outlives WaveStack
            conn.close(wait=not self._on_loop())
        self._mcp_lab_drop(wait=not self._on_loop())  # story 6 of 2026-09-30: its own too
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._release_embedder()  # story 15 (AD-8)
        self._release_reranker()  # story 16
        self._release_compressor()  # story 20 (AD-8)
        if self._engine is not None:
            self._engine.close()
            self._engine = None

    def _on_loop(self) -> bool:
        try:
            return asyncio.get_running_loop() is self._loop
        except RuntimeError:
            return False

    # ---------- model load (AD-3, AD-7, AD-8) ----------

    @property
    def model_loaded(self) -> bool:
        return self._engine is not None

    def active_choice(self) -> ModelChoice | None:
        """The model loaded now, which the model lists mark « actif »; `None` while none is."""
        with self._lock:
            return self._active

    @property
    def _ratio(self) -> float:
        """AD-4: the active cloud model's last `usage.prompt_tokens / Σ estimates`, kept by
        model `id`: a round trip through another model finds it again. The sub-agents'
        contexts keep one of their own, under `{id}#sub` (AD-11)."""
        return self._ratios.get(self._ratio_id(), self.cfg.estimate_ratio)

    @_ratio.setter
    def _ratio(self, value: float) -> None:
        self._ratios[self._ratio_id()] = value

    def _ratio_id(self) -> str:
        model = self._cloud.id if self._cloud is not None else ""
        return f"{model}#sub" if self._ratio_key() == "sub" else model

    @property
    def configured_window(self) -> int:
        """Story 26 (AD-9): the window every load reads, chosen in the interface or read at
        launch (`[context] window`); the model's effective one may be smaller (`_window`).
        An attribute read, atomic: safe with or without the lock."""
        return self._configured_window

    def _cost(self, choice: ModelChoice, window: int | None = None) -> int:
        """AD-8: a file's estimated cost at the configured window, or at `window` (an upper
        bound of the effective one); a cloud model costs nothing. Story 26: a file whose
        probe did not read its KV cache adds it, read in its header, for the tokens beyond
        the probe's own window (the same rule for the check and the grant)."""
        if window is None:
            window = self.configured_window
        if choice.kind == "cloud":
            return 0
        if choice.kind == "server":  # AD-8: the served model's memory, outside WaveStack
            served = choice.server
            if served.resident or not served.gguf_path:
                return served.served_bytes or 0  # already in memory: what it takes there
            # Ollama will load it in its own process: its file, its KV cache (f16) at the
            # window, and the margin, which also covers its tokenizer opened `vocab_only` in
            # WaveStack. Story 24: never the probe's RSS of the blob, which measured
            # llama-cpp-python in WaveStack's child (buffers, KV), not Ollama.
            # The diagnostic's figure (`servers.served_bytes` at the window, with its fallback
            # to the size Ollama reports), read again only for a candidate without one.
            # Story 26: at another window than the launch's, read again at this one.
            memory = served.served_bytes if window == self.cfg.context_window else None
            if memory is None:
                memory = ollama_load_bytes(served.gguf_path, window)
            return (memory or 0) + self._load_registry.margin_bytes
        cost = self._load_registry.file_cost(choice.ref, window)
        entry = probe_module.probed_entry(choice.ref) or {}
        if not entry.get("kv_bytes_per_token"):
            probed = int(entry.get("probe_window") or 0) if entry.get("rss_bytes") else 0
            kv = probe_module.gguf_kv_bytes_per_token(choice.ref) or 0
            cost += kv * max(window - probed, 0)
        return cost

    def _reload_cost(self, choice: ModelChoice, window: int) -> int | None:
        """Story 26 (AD-8): what reloading the active model with `window` costs. Ollama loads
        it again at its new `num_ctx`: a model it holds costs what one it does not would
        (its file, its KV at `window`, the margin); `None` when that cannot be read (no
        readable blob, KV unknown). Any other model: `_cost` at `window`."""
        served = choice.server if choice.kind == "server" else None
        if served is None or served.engine != "ollama":
            return self._cost(choice, window)
        memory = ollama_load_bytes(served.gguf_path, window)
        if memory is None:
            kv = probe_module.gguf_kv_bytes_per_token(served.gguf_path)
            if not kv or not served.size_bytes:
                return None
            memory = served.size_bytes + kv * window
        return memory + self._load_registry.margin_bytes

    @property
    def memory_budget_bytes(self) -> int:
        """Story 24: the budget the refusals use (`/api/diagnostic`, the E2E run)."""
        return self._load_registry.budget_bytes

    @staticmethod
    def _checked(choice: ModelChoice) -> bool:
        """AD-8: a served model already in memory (llama-server's, a model Ollama holds)
        takes nothing more once chosen: it is counted, never refused."""
        return not (choice.kind == "server" and choice.server.resident)

    @staticmethod
    def _load_reason(choice: ModelChoice) -> str:
        if choice.entry is not None:
            return Message(
                "session.load.cloud", model=choice.entry.model, provider=choice.entry.provider
            )
        if choice.kind == "server":
            return Message("session.load.server", provider=choice.provider)
        return Message("session.load.file", file=choice.file_name)

    def _model_payload(self, choice: ModelChoice) -> dict[str, Any]:
        """The `ActiveModel` of a model not loaded yet: `model_load_*`."""
        if choice.entry is not None:
            return active_model(choice.entry, self._language)
        label = choice.label
        if choice.kind == "server":  # AD-12, story 18: a local process apart from WaveStack
            return {
                "id": choice.ref,
                "label": label,
                "hosting": "local",
                "provider": choice.provider,
                "server_url": getattr(choice.server, "server_url", None),
                "disclosure": None,
                "kind": "server",
                "ref": choice.ref,
            }
        return {"id": label, "label": label, "hosting": "local", "kind": "file", "ref": choice.ref}

    def boot(self, model_path: str | None, name: str | None = None) -> Future[str]:
        """The launch's model (AD-21) on the worker thread: `model_load` → `idle`, then
        `context_preview`. `None`: a local server only, no file to load. `name`: the
        candidate's readable name (an Ollama `model:tag`)."""
        choice = ModelChoice("file", model_path, name=name) if model_path else None
        return self._executor.submit(self._boot, choice)

    def boot_cloud(self, entry: CloudModel) -> Future[str]:
        """The launch's cloud model, prepared without any request (AD-21)."""
        return self._executor.submit(self._boot, ModelChoice("cloud", entry.id, entry))

    def boot_server(self, candidate: Any) -> Future[str]:
        """The launch's served model (story 18): `candidate` is its discovery candidate
        (`source = server`). Nothing is launched; no model loads in-process."""
        return self._executor.submit(self._boot, ModelChoice.served(candidate))

    def _boot(self, choice: ModelChoice | None) -> str:
        if choice is None:
            self._set_state("idle", _NO_MODEL_FR)
            self._emit_architecture()
            self._emit_bricks()
            return "error"
        with self._lock:
            previous = self._active
            self.state, self.reason_text = "model_load", self._load_reason(choice)
            self._load_cancel = CancelToken()
        self._emit_state()
        return self._load(choice, previous, None, save=False)

    def switch_model(
        self, choice: ModelChoice, probe: ProbeFn | None = None
    ) -> tuple[str, Future[str] | None]:
        """Intention `select_model` once past the diagnostic (class b, AD-3): accepted in
        `idle`, even with a reason; refused otherwise (`SendRefused`). The budget is checked
        before anything is released (AD-8): its refusal, in figures, leaves the active model.
        `probe(path, cancel)` probes a GGUF never probed, after the release: `None` if it
        loads (or « Arrêter » killed it: story 24, `cancel` is the load's token), else why.
        Returns the French answer and the load's future (`None`: already active)."""
        cost = self._cost(choice)
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            previous = self._active
            if choice.same_as(previous):
                return Message("session.load.already_active", label=choice.label), None
            refusal = (
                self._load_registry.check(choice.label, cost) if self._checked(choice) else None
            )
            if refusal is None:  # switched under the lock: a second choice racing it is refused
                self.state, self.reason_text = "model_load", self._load_reason(choice)
                self._load_cancel = CancelToken()  # lot E (E4): « Arrêter » from now on
        if refusal is not None:
            self._error(
                refusal,
                Message("session.load.budget_cause"),
                Message("session.load.nothing_released"),
            )
            raise SendRefused(refusal)
        self._emit_state()
        future = self._executor.submit(self._load, choice, previous, probe, True)
        return Message("session.load.loading", label=choice.label), future

    def _load(
        self,
        choice: ModelChoice,
        previous: ModelChoice | None,
        probe: ProbeFn | None,
        save: bool,
        window: int | None = None,
    ) -> str:
        """The single load path, on the worker, in `model_load` (AD-3, AD-8): release the
        active model, probe a GGUF never measured (AD-7) and check the budget again with the
        measure, load; on failure, reload `previous`. Lot E (E4): « Arrêter » is seen after
        the release, after the probe and after the load (llama.cpp cannot interrupt a load;
        story 24: the probe's child is killed at once): what was loaded is released and
        `previous` reloaded (`cancelled`). Then
        `model_load_ended`, `idle`, and the bricks, schema and preview again. The choice is
        saved (`save`) after a success only. Story 26, `window`: the active model reloaded
        with this window (`previous` is the same model): on success the window is the one
        configured and saved, on failure or « Arrêter » the model comes back with the window
        it had. Returns `ok`, `restored`, `cancelled` or `error`."""
        started = time.monotonic()
        model = self._model_payload(choice)
        journal = self._journal()
        off_turn = {"turn_id": None, "step_id": None, "call_id": None, "context_id": None}
        phase_label = (
            self._reload_reason(choice, window) if window is not None else self._load_reason(choice)
        )
        with scoped(**off_turn):
            journal.emit(
                "model_load_started",
                {"model": model, "phase_label": phase_label}
                | ({"window": window} if window is not None else {}),
            )
        status, reason_text, idle_text = "error", None, _LOAD_FAILED_FR
        with self._lock:
            cancel = self._load_cancel
        # Story 29: each step passed, with WaveStack's RSS, for the « LLM nu » screen.
        rss_before = self._rss_now()
        last_step = started

        def step(name: str, label_text: str) -> None:
            nonlocal last_step
            now = time.monotonic()
            with scoped(**off_turn):
                journal.emit(
                    "model_load_step",
                    {
                        "model": model,
                        "step": name,
                        "label_text": label_text,
                        "elapsed_ms": _ms(now - started),
                        "duration_ms": _ms(now - last_step),
                        "rss_bytes": self._rss_now(),
                    },
                )
            last_step = now

        try:
            try:
                self._release()
                self._emit_architecture()  # the schema no longer shows the released model
                step("release", self._release_fr(previous))
                _checkpoint(cancel)
                if (
                    choice.kind == "file"
                    and probe is not None
                    and not probe_module.measured(choice.ref)
                ):
                    why = probe(choice.ref, cancel)  # story 24: « Arrêter » kills it
                    _checkpoint(cancel)
                    step(
                        "probe",
                        Message(
                            "session.load.steps.probe",
                            outcome=Message(
                                "session.load.steps.probe_ok"
                                if why is None
                                else "session.load.steps.probe_incompatible"
                            ),
                        ),
                    )
                    if why is not None:
                        raise _LoadFailed(
                            Message("session.load.incompatible", file=choice.file_name), why
                        )
                    # AD-8: the probe's measure replaces the file size of the first check.
                    refusal = self._load_registry.check(choice.label, self._cost(choice))
                    if refusal is not None:
                        over_text = Message("session.load.over_budget")
                        raise _LoadFailed(over_text, refusal)
                step("check", self._check_fr(choice, window))
                self._install(choice, window)
                step("engine", self._engine_fr(choice))
                self._last_checkpoint(cancel)
                step("ready", Message("session.load.steps.ready", label=choice.label))
                status, idle_text = "ok", None
            except _LoadCancelled:
                self._last_checkpoint(None)
                reason_text, idle_text, status = self._load_cancelled(previous, window is not None)
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._last_checkpoint(None)  # « Arrêter » cannot stop the way back
                reason_text, idle_text, status = self._load_failed(choice, previous, exc, window)
            if status == "ok" and save:
                reason_text = self._save_choice(choice)
            if status == "ok" and window is not None:  # story 26: applied, then saved
                with self._lock:
                    self._configured_window = window
                reason_text = self._save_window(window) or Message(
                    "session.load.window_applied", window=self._num_lazy(window)
                )
        except Exception as exc:  # noqa: BLE001 - AD-16: never let the worker die silently
            self._error(Message("session.load.interrupted"), exc, _NO_TURN_FR)
            status, reason_text, idle_text = "error", self._text(exc), _LOAD_FAILED_FR
        finally:
            with self._lock:  # « Arrêter » acts on this load no longer
                self._load_cancel = None
                scenario = self._active_scenario
            if scenario is not None:  # lot E (E5): the bricks the new model cannot offer
                try:
                    self._emit_scenario(refresh=True)
                except Exception as exc:  # noqa: BLE001 - AD-16: the load still ends
                    self._error(
                        Message("session.load.scenario_bricks.message"),
                        exc,
                        Message("session.load.scenario_bricks.effect"),
                    )
            memory = self._loaded_memory(choice, rss_before, window) if status == "ok" else None
            with scoped(**off_turn):
                journal.emit(
                    "model_load_ended",
                    {
                        "model": model,
                        "status": status,
                        "duration_ms": _ms(time.monotonic() - started),
                        "reason_text": reason_text,
                    }
                    | ({"memory": memory} if memory is not None else {}),
                )
            self._set_state("idle", idle_text)
            # AD-6, AD-9, AD-12: capabilities, window and model changed with the load.
            self._emit_architecture()
            self._emit_bricks()
            self._emit_preview()
            self._emit_window_state()  # story 26: the choices' costs for the model now active
            # Story 15 (AD-8): memory changed with the model; an embedding model the budget
            # refused gets another chance.
            with self._lock:
                retry = "rag" in self._wanted and (
                    self._rag_load_error is not None or self._rerank_load_error is not None
                )
            if retry:
                self._request_rag_sync()
            with self._lock:  # story 20: the same second chance for Headroom
                retry = "compression" in self._wanted and self._compression_load_error is not None
            if retry:
                self._request_compression_sync()
        return status

    # ---------- story 29: the steps and memory of a load, for the « LLM nu » screen ----------

    def _rss_now(self) -> int | None:
        """WaveStack's RSS (the registry's measure); `None` when it cannot be read."""
        try:
            return int(self._load_registry.baseline())
        except Exception:  # noqa: BLE001 - a figure shown, never a failure
            return None

    def _release_fr(self, previous: ModelChoice | None) -> str:
        rss = self._rss_now()
        after = Message("session.load.steps.occupies", size=self._size_lazy(rss)) if rss else ""
        if previous is None:
            return Message("session.load.steps.nothing_to_release", after=after)
        return Message("session.load.steps.released", label=previous.label, after=after)

    def _check_fr(self, choice: ModelChoice, window: int | None) -> str:
        """The step « check »: the budget was checked before anything was released (AD-3,
        and again after a probe); this says it is confirmed. A label only: never a failure."""
        try:
            return self._check_label_fr(choice, window)
        except Exception:  # noqa: BLE001 - a figure shown, never a load's failure
            return Message("session.load.steps.budget_checked")

    def _check_label_fr(self, choice: ModelChoice, window: int | None) -> str:
        if choice.kind == "cloud":
            return Message("session.load.steps.budget_cloud")
        cost = self._size_lazy(self._cost(choice, window))
        budget = self._size_lazy(self._load_registry.budget_bytes)
        if choice.kind == "server" and not self._checked(choice):
            return Message(
                "session.load.steps.budget_server",
                cost=cost,
                provider=choice.provider,
                budget=budget,
            )
        return Message("session.load.steps.budget_file", cost=cost, budget=budget)

    @staticmethod
    def _engine_fr(choice: ModelChoice) -> str:
        if choice.kind == "cloud":
            return Message("session.load.steps.engine_cloud")
        if choice.kind == "server":
            return Message("session.load.steps.engine_server", provider=choice.provider)
        return Message("session.load.steps.engine_file")

    def _loaded_memory(
        self, choice: ModelChoice, rss_before: int | None, window: int | None
    ) -> dict[str, Any] | None:
        """`model_load_ended.memory` (story 29): the RSS before and after, the cost the budget
        counts, and where the model lies."""
        try:
            cost = self._cost(choice, window)
        except Exception:  # noqa: BLE001 - a figure shown, never a failure
            cost = 0
        rss_after = self._rss_now()
        if choice.kind == "cloud":
            provider = (
                choice.entry.provider
                if choice.entry is not None
                else Message("session.load.memory.the_provider")
            )
            where_text = Message("session.load.memory.cloud", provider=provider)
        elif choice.kind == "server":
            where_text = Message(
                "session.load.memory.server", provider=choice.provider, cost=self._size_lazy(cost)
            )
        else:
            before = self._size_lazy(rss_before) if rss_before else "?"
            after = self._size_lazy(rss_after) if rss_after else "?"
            where_text = Message(
                "session.load.memory.file", before=before, after=after, cost=self._size_lazy(cost)
            )
        return {
            "rss_before": rss_before,
            "rss_after": rss_after,
            "cost_bytes": cost,
            "where_text": where_text,
        }

    def _load_failed(
        self,
        choice: ModelChoice,
        previous: ModelChoice | None,
        exc: Exception,
        window: int | None = None,
    ) -> tuple[str, str | None, str]:
        """AD-3: back to `previous` when there was one. Returns the `model_load_ended`
        reason, the reason left in `idle` and the status. Story 26, `window`: the window
        that could not be applied, `previous` coming back with the one it had."""
        cause: BaseException | str = exc
        reason: str | None = None  # lot E (E6): the French reason, when the cause is not
        if isinstance(exc, _LoadFailed):
            message_text, reason, idle_text = exc.message_text, exc.reason_text, exc.idle_text
            cause = exc.detail or exc.reason_text  # lot E (E6): the raw message, a detail
        elif choice.entry is not None:
            message_text = Message("session.load.failed.cloud", label=choice.label)
            idle_text = _CLOUD_FAILED_FR
        elif choice.kind == "server":
            message_text = Message(
                "session.load.failed.server", label=choice.label, provider=choice.provider
            )
            idle_text = None
            if isinstance(exc, ServerError):
                cause = getattr(exc, "message", None) or exc.message_text
            elif isinstance(exc, TokenizerRefused):  # the loader's message, a detail
                cause, reason = exc.detail, exc.reason_text
        else:
            message_text, idle_text = Message("session.load.failed.file"), None
        if reason:
            cause_text = reason
        elif isinstance(cause, KeyedError):
            cause_text = cause.message
        else:
            cause_text = cause if isinstance(cause, str) else str(cause)
        self._release()  # whatever the failed load left
        if previous is None:
            self._error(message_text, cause, _NO_TURN_FR)
            return cause_text, idle_text or _LOAD_FAILED_FR, "error"
        self._error(message_text, cause, Message("session.load.back", label=previous.label))
        try:
            self._install(previous)
        except Exception as back:  # noqa: BLE001 - AD-16
            self._release()
            self._error(
                Message("session.load.previous_failed", label=previous.label), back, _NO_TURN_FR
            )
            return (
                Message(
                    "session.load.failed.and_previous", message=message_text, label=previous.label
                ),
                _LOAD_FAILED_FR,
                "error",
            )
        if window is not None:
            return (
                Message(
                    "session.load.failed.window",
                    window=self._num_lazy(window),
                    cause=cause_text,
                    label=previous.label,
                    current=self._num_lazy(self._window),
                ),
                None,
                "restored",
            )
        return (
            Message(
                "session.load.failed.restored",
                label=choice.label,
                cause=cause_text,
                previous=previous.label,
            ),
            None,
            "restored",
        )

    def _last_checkpoint(self, cancel: CancelToken | None) -> None:
        """Lot E (E4): past this point « Arrêter » acts on this load no longer (`stop()`
        answers `False`): under the lock, a stop is either seen here or refused."""
        with self._lock:
            self._load_cancel = None
            _checkpoint(cancel)

    def _load_cancelled(
        self, previous: ModelChoice | None, reload: bool = False
    ) -> tuple[str, str | None, str]:
        """Lot E (E4): « Arrêter » during a load. What was loaded is released and `previous`
        reloaded (none: no model is active). Returns the `model_load_ended` reason, the
        reason left in `idle` and the status (`cancelled`; `error` when `previous` fails to
        come back). Story 26, `reload`: a window change, `previous` back with its window."""
        self._release()
        if previous is None:
            return Message("session.load.stopped.none"), _LOAD_STOPPED_FR, "cancelled"
        try:
            self._install(previous)
        except Exception as back:  # noqa: BLE001 - AD-16
            self._release()
            self._error(
                Message("session.load.previous_failed", label=previous.label), back, _NO_TURN_FR
            )
            return (
                Message("session.load.stopped.previous_failed", label=previous.label),
                _LOAD_FAILED_FR,
                "error",
            )
        if reload:
            return (
                Message(
                    "session.load.stopped.reload",
                    label=previous.label,
                    window=self._num_lazy(self._window),
                ),
                None,
                "cancelled",
            )
        return (
            Message("session.load.stopped.restored", label=previous.label),
            None,
            "cancelled",
        )

    def _release(self) -> None:
        """AD-8: the active model is closed and leaves the registry before anything loads;
        the registry forgets it even when `close()` fails (raised afterwards)."""
        with self._lock:
            engine = self._engine
            self._engine, self._caps, self._cloud, self._active = None, None, None, None
            self._model_name, self._meta = None, None
            # Lot A: the next engine starts with an empty cache, nothing to check against.
            self._main_cache = self._cache_evicted = None
        try:
            if engine is not None:
                engine.close()
        finally:
            self._load_registry.release()

    def _install(self, choice: ModelChoice, window: int | None = None) -> None:
        """Load `choice` as the active model, nothing being loaded: raises on failure, the
        engine it opened closed first (AD-8: never two models). Story 26, `window`: the
        window to load it with, else the configured one."""
        base: int | None = None
        configured = self.configured_window if window is None else window
        if choice.entry is not None:
            self._install_cloud(choice.entry, configured)
        else:
            if choice.kind == "server":  # story 18: its adapter; nothing loads in-process
                engine = self._server_factory(choice.server, n_ctx=configured)
            else:
                # Story 24: WaveStack without the model, measured after the release and
                # before the engine: the floor of any later refusal's remainder.
                base = self._load_registry.baseline()
                try:
                    engine = self._engine_factory(choice.ref, n_ctx=configured)
                except Exception as exc:  # lot E (E6): llama.cpp's message is the detail
                    raise _LoadFailed(
                        Message("session.load.failed.file"),
                        probe_module.incompatible_fr(),
                        detail=str(exc) or type(exc).__name__,
                    ) from exc
            try:
                meta = engine.metadata()
                caps = capabilities_for(meta)
                if caps.incompatible_reason:
                    raise _LoadFailed(
                        Message("session.load.incompatible_model"),
                        caps.incompatible_reason,
                        caps.incompatible_reason,
                    )
                # AD-9: min(configured, native, the server's own context).
                effective, source = window_for(meta, configured)
                if hasattr(engine, "use_window"):  # `ollama_raw`: num_ctx = this window
                    engine.use_window(effective)
                labels = self._load_labels()
            except BaseException:
                engine.close()
                raise
            with self._lock:
                self._engine, self._caps, self._cloud = engine, caps, None
                if hasattr(engine, "language"):  # a served engine traces its own texts
                    engine.language = self._language
                self._model_name, self._meta = choice.label, meta
                self._read_warm = False  # story 26: its first call warms it up
                self._window = effective
                self._window_source = source
                self._labels = labels
                self._active = choice
        # A cloud model is granted too (cost 0): the registry names the active model. Lot E
        # (E3): only a file's cost is in WaveStack's RSS, never a served model's.
        in_process = choice.kind == "file"
        share = self._load_registry.file_share(choice.ref) if in_process else None
        # Story 26: a window reload is granted the cost it was checked with.
        cost = self._reload_cost(choice, configured) if window is not None else None
        self._load_registry.grant(
            choice.label,
            self._cost(choice, configured) if cost is None else cost,
            in_process=in_process,
            share=share,
            base=base,
        )
        # GreenOps: CodeCarbon imported (within the budget) and the CPU detected in the
        # background, so that the first local call does not wait seconds for them (a call
        # that starts meanwhile waits); nothing without the extra, nor for a cloud model.
        if choice.entry is None:
            self._greenops_warm_up = threading.Thread(
                target=self._local_meter.warm_up,
                args=(choice.kind == "server",),
                name="greenops-warm-up",
                daemon=True,
            )
            self._greenops_warm_up.start()

    def _install_cloud(self, entry: CloudModel, configured: int | None = None) -> None:
        key = config.cloud_key(entry)
        if key is None:
            raise ValueRefused("session.load.no_key")
        unavailable = config.cloud_unavailable_fr(entry)
        if unavailable:
            raise ValueRefused(unavailable)
        self._cloud_content = self._localized(load_cloud_content)
        engine = self._cloud_factory(entry, key)
        try:
            # AD-6: declared capabilities; the API's structured format parses the tool calls.
            caps = cloud_capabilities(entry)
            window, source = config.cloud_window(
                entry, self.configured_window if configured is None else configured
            )
            labels = self._load_labels()
        except BaseException:
            engine.close()
            raise
        with self._lock:
            self._engine, self._caps, self._cloud = engine, caps, entry
            self._model_name, self._meta = entry.model, None
            self._window, self._window_source = window, source
            self._labels = labels
            self._active = ModelChoice("cloud", entry.id, entry)

    def _save_choice(self, choice: ModelChoice) -> str | None:
        """AD-20: `selected_model`, by the single applier (AD-23), after a success only.
        Returns the French notice when it could not be written; whatever the failure, the
        model loaded stays active."""
        value = {"kind": choice.kind, "ref": choice.ref}
        try:
            apply_setting(SettingWrite(key="selected_model", value=value))
        except Exception as exc:  # noqa: BLE001 - AD-16: a success is never undone by this
            notice = Message("session.settings.choice_not_saved", label=choice.label)
            self._error(Message("session.settings.unwritable"), exc, notice)
            return notice
        return None

    # ---------- context window (story 26, AD-9) ----------

    @staticmethod
    def _reload_reason(choice: ModelChoice, window: int) -> str:
        return Message(
            "session.window.reloading", label=choice.label, window=AppSession._num_lazy(window)
        )

    @staticmethod
    def _locked_fr(entry: CloudModel | None) -> str | None:
        """AD-9: a cloud model that declares its `window` takes no other: why, in French."""
        if entry is None or not entry.window:
            return None
        return Message(
            "session.window.locked", model=entry.model, window=AppSession._num_lazy(entry.window)
        )

    def set_context_window(self, window: int) -> tuple[str, Future[str] | None]:
        """Intention `context_window` (class b, AD-3): accepted in `idle` only, else
        `SendRefused` with the reason. No model active: the window is saved for the next
        load. A cloud model: the window takes effect at the next turn, nothing reloads
        (refused when its declaration fixes `window`). A local or served model: the budget
        is checked before anything is released (AD-8; never for llama-server, whose memory
        its `-c` fixes), then the model reloads by `_load` with the new window, the
        conversation kept; a refusal, in figures, releases, writes and reloads nothing.
        Returns the French answer and the reload's future (`None`: nothing reloads)."""
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            if window == self._configured_window:
                return Message("session.window.already", window=self._num_lazy(window)), None
            active, cloud = self._active, self._cloud
            if cloud is not None:
                locked = self._locked_fr(cloud)
                if locked:
                    raise SendRefused(locked)
                self._window, self._window_source = config.cloud_window(cloud, window)
            if active is None or cloud is not None:
                self._configured_window = window
            effective, source = self._window, self._window_source
        if active is None or cloud is not None:
            notice = self._save_window(window)
            if cloud is not None:  # AD-9: the gauge and the reasoning card follow at once
                self._executor.submit(self._after_window_change)
                message = Message(
                    "session.window.cloud_next_turn",
                    window=self._num_lazy(window),
                    bound=self._bound_lazy(source, effective),
                )
            else:
                self._executor.submit(self._emit_window_state)
                message = Message("session.window.saved_for_next", window=self._num_lazy(window))
            return notice or message, None
        with self._lock:
            meta, current = self._meta, self._window
        effective, source = window_for(meta, window) if meta else (window, "configured")
        if effective == current:  # the model's window does not change: nothing to reload
            with self._lock:
                if self.state != "idle" or self._active is not active:
                    raise SendRefused(self._refusal_reason())
                self._configured_window = window
                self._window_source = source
            notice = self._save_window(window)
            self._executor.submit(self._after_window_change)
            return notice or Message(
                "session.window.unchanged",
                window=self._num_lazy(window),
                label=active.label,
                effective=self._num_lazy(effective),
                bound=self._bound_lazy(source, effective, active.provider),
            ), None
        refusal = self._window_refusal(active, window, current)
        with self._lock:
            if self.state != "idle" or self._active is not active:
                raise SendRefused(self._refusal_reason())
            if refusal is None:  # switched under the lock: a second intention is refused
                self.state, self.reason_text = "model_load", self._reload_reason(active, window)
                self._load_cancel = CancelToken()  # « Arrêter » from now on
        if refusal is not None:
            self._error(
                refusal,
                Message("session.load.budget_cause"),
                Message("session.window.nothing_reloaded"),
            )
            raise SendRefused(refusal)
        self._emit_state()
        future = self._executor.submit(self._load, active, active, None, False, window)
        return self._reload_reason(active, window), future

    def _window_refusal(self, active: ModelChoice, window: int, current: int) -> str | None:
        """Story 26 (AD-8): why reloading the local or served `active` model with `window`
        is refused, else `None`. Never for llama-server (its `-c` fixes its memory) nor for a
        window smaller than the effective one `current` (shrinking only frees memory)."""
        if active.kind == "server" and active.provider == "llama-server":
            return None
        if window < current:
            return None
        cost = self._reload_cost(active, window)
        if cost is None:
            return Message(
                "session.window.cost_unknown",
                window=self._num_lazy(window),
                label=active.label,
                current=self._num_lazy(current),
            )
        return self._load_registry.check_window(active.label, window, current, cost)

    def _after_window_change(self) -> None:
        """A cloud model's new window (AD-9): the preview, the bricks (the reasoning card
        needs room for its reserve) and the window panel, on the worker."""
        self._emit_bricks()
        self._emit_preview()
        self._emit_window_state()

    def _save_window(self, window: int) -> str | None:
        """Story 26 (AD-20): `context.window` in `settings.json`, by the single applier
        (AD-23), keeping the other keys of `context`; read back at the next launch by
        `load_config`. Returns the French notice when it could not be written."""
        try:
            saved = config.read_settings().get("context")
            value = {**(saved if isinstance(saved, dict) else {}), "window": window}
            apply_setting(SettingWrite(key="context", value=value))
        except Exception as exc:  # noqa: BLE001 - AD-16: the window applied stays applied
            notice = Message("session.settings.window_not_saved", window=self._num_lazy(window))
            self._error(Message("session.settings.unwritable"), exc, notice)
            return notice
        return None

    def _note_read_rate(self, evaluated: int | None, prompt_ms: int) -> None:
        """Story 26: the active local or served model's read rate, from a call that
        evaluated at least `READ_MIN_TOKENS` tokens (not a cache hit, lot A). Never the
        first call after a load (warm-up, or Ollama loading at its new `num_ctx`), nor a
        call whose engine does not say what it evaluated (the cached prefix is no read)."""
        first, self._read_warm = not self._read_warm, True
        if first or evaluated is None:
            return
        if evaluated < READ_MIN_TOKENS or prompt_ms <= 0 or self._model_name is None:
            return
        self._read_tps[self._model_name] = evaluated / (prompt_ms / 1000)

    def _kv_per_token(self, active: ModelChoice) -> int | None:
        """The KV cache's bytes per token of the active local model: the probe's reading,
        else its GGUF header (f16); a served model's blob (Ollama); `None` for llama-server
        (its `-c` reserved it) or when unreadable."""
        if active.kind == "file":
            probed = (probe_module.probed_entry(active.ref) or {}).get("kv_bytes_per_token")
            return int(probed) if probed else probe_module.gguf_kv_bytes_per_token(active.ref)
        if active.kind == "server" and active.provider != "llama-server":
            return probe_module.gguf_kv_bytes_per_token(active.server.gguf_path)
        return None

    def _window_choice(
        self,
        window: int,
        active: ModelChoice | None,
        meta: EngineMetadata | None,
        configured: int,
        tps: float | None,
        kv_per_token: int | None,
        now: int,
    ) -> dict[str, Any]:
        """One choice of the window panel (AD-1: every figure and text from here); `now`:
        the active model's effective window."""
        current = window == configured
        row: dict[str, Any] = {
            "window": window,
            "current": current,
            "bound_text": None,
            "kv_bytes": None,
            "read_s": None,
            "fits": True,
            "refusal_text": None,
        }
        if active is None:
            return row | {
                "effective": window,
                "source": "configured",
                "kv_text": _KV_NO_MODEL_FR,
                "read_text": _READ_NO_MODEL_FR,
            }
        if active.entry is not None:
            effective, source = config.cloud_window(active.entry, window)
            return row | {
                "effective": effective,
                "source": source,
                "bound_text": bound_fr(source, effective, lang=self._language),
                "kv_text": _KV_CLOUD_FR,
                "read_text": _READ_CLOUD_FR,
            }
        effective, source = window_for(meta, window) if meta else (window, "configured")
        llama = active.kind == "server" and active.provider == "llama-server"
        if llama:
            slot = (meta.server_context if meta else None) or active.server.n_ctx
            kv_text = (
                self._t("session.window.kv_llama_slot", slot=self._num_lazy(slot))
                if slot
                else self._t("session.window.kv_llama")
            )
            kv_bytes = None
        else:
            kv_bytes = kv_per_token * effective if kv_per_token else None
            kv_text = self._t("session.window.kv", size=kv_fr(kv_bytes, self._language))
        read_s = read_seconds(effective, tps)
        refusal = None if current else self._window_refusal(active, window, now)
        return row | {
            "effective": effective,
            "source": source,
            "bound_text": bound_fr(source, effective, active.provider, self._language),
            "kv_bytes": kv_bytes,
            "kv_text": kv_text,
            "read_s": round(read_s, 1) if read_s is not None else None,
            "read_text": self._t(
                "session.window.read", time=read_time_fr(effective, tps, self._language)
            ),
            "fits": refusal is None,
            "refusal_text": refusal,
        }

    def _window_state(self) -> dict[str, Any]:
        """The `context_window_state` payload (AD-2, AD-9): the window configured, the
        active model's effective one, and each choice's cost (AD-1)."""
        with self._lock:
            active, meta = self._active, self._meta
            configured = self._configured_window
            effective, source = self._window, self._window_source
        if active is None:
            effective, source = configured, "configured"
        local = active is not None and active.entry is None
        tps = self._read_tps.get(active.label) if local else None
        kv_per_token = self._kv_per_token(active) if local else None
        if active is None:
            note = self._t("session.window.note.no_model")
        elif not local:
            note = self._t("session.window.note.cloud")
        elif tps is None:
            note = self._t("session.window.note.not_measured", label=active.label)
        else:
            note = self._t(
                "session.window.note.measured",
                label=active.label,
                tps=self._num_lazy(round(tps)),
                min=READ_MIN_TOKENS,
            )
        return {
            "configured": configured,
            "default": DEFAULT_WINDOW,
            "window": effective,
            "window_source": source,
            "bound_text": bound_fr(
                source, effective, active.provider if active else None, self._language
            ),
            "model_label": active.label if active else None,
            "hosting": active.kind if active else None,
            "read_tps": round(tps, 1) if tps else None,
            "read_note_text": note,
            "locked_text": self._locked_fr(active.entry if active else None),
            "choices": [
                self._window_choice(n, active, meta, configured, tps, kv_per_token, effective)
                for n in WINDOW_CHOICES
            ],
        }

    def _emit_window_state(self) -> None:
        """Story 26: `context_window_state`, out of any turn; a failure is contained."""
        try:
            payload = self._window_state()
        except Exception as exc:  # noqa: BLE001 - AD-16
            self._error(
                Message("session.window.error.message"),
                exc,
                Message("session.window.error.effect"),
            )
            return
        with scoped(turn_id=None, step_id=None, call_id=None, context_id=None):
            self._journal().emit("context_window_state", payload)

    def hold(self, state: str, reason_text: str, run: Callable[[], Any]) -> Any:
        """AD-3: runs `run` holding the operation lock in `state` (`test_cloud_model`:
        `model_load`), then gives the previous state back. Refused (`SendRefused`) outside
        `idle` and `diagnostic`."""
        with self._lock:
            if self.state not in ("idle", "diagnostic"):
                raise SendRefused(self._refusal_reason())
            previous = (self.state, self.reason_text)
            self.state, self.reason_text = state, reason_text
        self._emit_state()
        try:
            return run()
        finally:
            with self._lock:  # a boot may have moved the session meanwhile: leave it there
                mine = (self.state, self.reason_text) == (state, reason_text)
            if mine:
                self._set_state(*previous)

    def _load_messages(self) -> None:
        """Languages (5/5): the backend's messages in the session's language, read once at
        launch and at each change of language, so that an invalid translation is traced
        once (`msg` then answers in French, silently)."""
        try:
            self._localized(load_messages)
        except Exception as exc:  # noqa: BLE001 - the French catalogue itself: no text to use
            # The French catalogue itself cannot be read: no key to render, French literals.
            self._error(
                "Le fichier content/messages.yaml est absent ou invalide.",
                exc,
                "Les messages de WaveStack ne peuvent pas s'afficher ; corrigez le fichier, "
                "puis relancez WaveStack.",
            )

    def _load_labels(self) -> SegmentLabels:
        try:
            return self._localized(load_labels)
        except Exception as exc:  # noqa: BLE001 - AD-19: invalid content is traced, not fatal
            self._error(
                Message("session.content.labels.message"),
                exc,
                Message("session.content.labels.effect"),
            )
            return SegmentLabels(kinds={k: k.value for k in SegmentKind}, groups={})

    def _load_content(self) -> None:
        """AD-19: an invalid file makes its brick unavailable with the reason, never a crash."""
        self._load_messages()
        for brick_id in self._bricks:
            try:
                self._content[brick_id] = self._localized(load_brick_content, brick_id)
            except Exception as exc:  # noqa: BLE001
                self._content_errors[brick_id] = Message(
                    "session.content.file_invalid", file=f"content/bricks/{brick_id}.yaml"
                )
                self._error(
                    Message("session.content.explanation_invalid", brick=brick_id),
                    exc,
                    Message("session.content.brick_unavailable"),
                )
        if "tools" in self._bricks:
            try:
                self._tools_content = self._localized(load_tools_content)
            except Exception as exc:  # noqa: BLE001
                self._content_errors["tools"] = Message(
                    "session.content.file_invalid", file="content/tools.yaml"
                )
                self._error(
                    Message("session.content.invalid.tools"),
                    exc,
                    Message("session.content.unavailable.tools"),
                )
        if "mcp" in self._bricks:
            try:
                self._mcp_content = self._localized(load_mcp_content)
            except Exception as exc:  # noqa: BLE001
                self._content_errors["mcp"] = Message(
                    "session.content.file_invalid", file="content/mcp.yaml"
                )
                self._error(
                    Message("session.content.invalid.mcp"),
                    exc,
                    Message("session.content.unavailable.mcp"),
                )
        if "skills" in self._bricks:
            try:
                self._skills_content = self._localized(load_skills_content, self._skill_ids())
            except Exception as exc:  # noqa: BLE001
                self._content_errors["skills"] = Message("session.content.skills_file_invalid")
                self._error(
                    Message("session.content.invalid.skills"),
                    exc,
                    Message("session.content.unavailable.skills"),
                )
        if "hooks" in self._bricks:
            try:
                self._hooks_content = self._localized(load_hooks_content, self._hook_ids())
            except Exception as exc:  # noqa: BLE001
                self._content_errors["hooks"] = Message(
                    "session.content.file_invalid", file="content/hooks.yaml"
                )
                self._error(
                    Message("session.content.invalid.hooks"),
                    exc,
                    Message("session.content.unavailable.hooks"),
                )
        if "global_memory" in self._bricks:
            self._load_memory()
        if "subagent" in self._bricks:
            try:
                self._subagent_content = self._localized(load_subagent_content)
            except Exception as exc:  # noqa: BLE001
                self._content_errors["subagent"] = Message("session.content.subagent_file_invalid")
                self._error(
                    Message("session.content.invalid.subagent"),
                    exc,
                    Message("session.content.unavailable.subagent"),
                )
        if "rag" in self._bricks:
            self._load_rag()
        if "compression" in self._bricks:
            try:
                self._compression_content = self._localized(load_compression_content)
            except Exception as exc:  # noqa: BLE001
                self._content_errors["compression"] = Message(
                    "session.content.file_invalid", file="content/compression.yaml"
                )
                self._error(
                    Message("session.content.invalid.compression"),
                    exc,
                    Message("session.content.unavailable.compression"),
                )
        if "system_prompt" not in self._bricks:
            return
        try:
            self._default_prompt = self._localized(load_default_system_prompt)
        except Exception as exc:  # noqa: BLE001
            self._content_errors["system_prompt"] = Message(
                "session.content.system_prompt_file_invalid"
            )
            self._error(
                Message("session.content.invalid.system_prompt"),
                exc,
                Message("session.content.unavailable.system_prompt"),
            )

    def _load_memory(self) -> None:
        """Story 14 (AD-19, AD-20): its texts, then `memory.json`. An absent file gives the
        demonstration memory, in memory only; an unreadable one makes the brick unavailable,
        and is never written again but by a reset."""
        try:
            self._memory_content = self._localized(memory_file.load_memory_content)
        except Exception as exc:  # noqa: BLE001
            self._content_errors["global_memory"] = Message(
                "session.content.file_invalid", file="content/memory/memory.yaml"
            )
            self._error(
                Message("session.content.invalid.global_memory"),
                exc,
                Message("session.content.unavailable.global_memory"),
            )
            return
        path = config.memory_path()
        try:
            entries = memory_file.read_memory(path)
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            self._memory_error = Message("session.memory.file_unreadable", path=path)
            self._error(
                Message("session.memory.unreadable"),
                exc,
                Message("session.memory.unreadable_effect"),
            )
            return
        if entries is None:  # H5: the demonstration, not written until a change
            entries = memory_file.demo_entries(self._memory_content.demo, memory_file.now())
        self._memory = entries

    def _load_rag(self) -> None:
        """Story 15 (AD-19): its texts, then `[rag.embedding]`, then the index and the model's
        files. Invalid: the brick is unavailable with the reason, never a crash. Story 16:
        `[rag.reranker]` first, whose error makes only the sub-option unavailable."""
        self._rerank_model, self._rerank_config_error = self.cfg.rag_reranker
        self._rerank_refresh()  # before any early return: the sub-option says why
        try:
            self._rag_content = self._localized(load_rag_content)
        except Exception as exc:  # noqa: BLE001
            self._content_errors["rag"] = Message(
                "session.content.file_invalid", file="content/rag.yaml"
            )
            self._error(
                Message("session.content.invalid.rag"),
                exc,
                Message("session.content.unavailable.rag"),
            )
            return
        model, error_text = self.cfg.rag_embedding
        if model is None:
            self._content_errors["rag"] = error_text or Message("session.rag.section_invalid")
            if self.cfg.get("rag", "embedding") is not None:  # absent: said by the card only
                self._error(
                    Message("session.rag.declaration_invalid"),
                    error_text or "",
                    Message("session.content.unavailable.rag"),
                )
            return
        self._rag_model = model
        self._rag_refresh()

    def _rag_index_path(self) -> Path:
        """Languages (4/5): the index of the session's language (`[rag] index_path` in
        French, `rag_index.{lang}.sqlite` otherwise)."""
        return self.cfg.rag_index_path(self._language)

    def _rag_refresh(self) -> None:
        """Story 15: what the availability reads of the index (`meta`, the preview's
        excerpts) and of the model's files, at launch, before loading the model (the brick
        switched on), after a download or a build, and when a search finds the index
        replaced. Never at each emission. Story 16: the reranker's files too."""
        self._rerank_refresh()
        model = self._rag_model
        content = self._rag_content
        if model is None or content is None:
            return
        path = self._rag_index_path()
        kind, reason, chunks, longest, missing, missing_text = self._rag_index_state(model, content)
        with self._lock:
            self._rag_index_kind, self._rag_index_error = kind, reason
            self._rag_chunks = chunks
            self._rag_stamp = _stamp(path)
            self._rag_longest, self._rag_missing = longest, missing
            self._rag_missing_text = missing_text

    def _rag_index_state(
        self, model: EmbeddingModel, content: RagContent
    ) -> tuple[str | None, str | None, int, list[Chunk], list[ModelFile], str | None]:
        """What the index and the model's files are now, read without storing anything
        (story 30: the RAG workshop reads it too, and never changes the brick's state): the
        index's kind and reason, its excerpts, the preview's excerpts, the files missing and
        their reason. Languages (4/5): the index and the corpus of the session's language."""
        lang = self._language
        path = self.cfg.rag_index_path(lang)
        kind, reason, chunks, longest = None, None, 0, []
        missing = download_module.missing_files(model.files, config.models_dir())
        build = Message("session.rag.build")
        if missing:
            build = Message("session.rag.download_then_build")
        why = rag_index.vec_unavailable()
        if why is not None:
            kind, reason = ("vec", Message("session.rag.vec_unavailable", why=why))
        elif not path.is_file():
            script = "scripts/build_rag_index.py"
            if lang != config.DEFAULT_LANGUAGE:  # languages (4/5): the script's option
                script += f" --lang {lang}"
            kind, reason = (
                "absent",
                Message("session.rag.index_absent", path=path, build=build, script=script),
            )
        else:
            try:
                meta = rag_index.read_meta(path)
                longest = rag_index.longest_chunks(path, self.cfg.rag_top_k)
            except Exception as exc:  # noqa: BLE001 - a state, never a crash
                kind, reason = (
                    "unreadable",
                    Message(
                        "session.rag.index_unreadable",
                        path=path,
                        kind=type(exc).__name__,
                        build=build,
                    ),
                )
            else:
                chunks = meta.chunks
                kind, reason = self._rag_index_mismatch(meta, model, content, build, lang)
        missing_text = (
            _missing_model_fr("embedding", model.label_text, missing) if missing else None
        )
        return kind, reason, chunks, longest, missing, missing_text

    def _rerank_refresh(self) -> None:
        """Story 16: the reranker's files read again, and the reason they give."""
        model = self._rerank_model
        missing = download_module.missing_files(model.files, config.models_dir()) if model else []
        missing_text = None
        if model is not None and missing:
            tail = Message("session.rag.works_without_reranking")
            missing_text = _missing_model_fr("reranking", model.label_text, missing, tail)
        with self._lock:
            self._rerank_missing, self._rerank_missing_text = missing, missing_text

    def _rag_index_mismatch(
        self,
        meta: rag_index.IndexMeta,
        model: EmbeddingModel,
        content: RagContent,
        build: str,
        lang: str = config.DEFAULT_LANGUAGE,
    ) -> tuple[str | None, str | None]:
        """An index built by another model (id, dimensions, file), or from another corpus or
        another `chunk_max_chars`: its kind and French reason, else `(None, None)`.
        Languages (4/5): the corpus is `lang`'s, so another language's index is stale."""
        declared = model.load_file
        other_file = (meta.model_size and meta.model_size != declared.size) or (
            meta.model_sha256
            and declared.sha256
            and meta.model_sha256.lower() != declared.sha256.lower()
        )
        if meta.embedding_model_id != model.id or meta.dims != model.dims or other_file:
            built_size = meta.model_size
            built_file = (
                Message(
                    "session.rag.built_file",
                    size=Lazy(lambda lang: number(round(built_size / 1_000_000), lang)),
                )
                if built_size
                else ""
            )
            declared_size = declared.size
            return "other_model", Message(
                "session.rag.other_model",
                built_id=meta.embedding_model_id,
                built_dims=meta.dims,
                built_file=built_file,
                model=model.id,
                dims=model.dims,
                size=Lazy(lambda lang: number(round(declared_size / 1_000_000), lang)),
                build=build,
            )
        chunks = chunk_corpus(content, self.cfg.rag_chunk_max_chars, lang)
        stale = meta.chunk_max_chars != self.cfg.rag_chunk_max_chars or (
            meta.corpus_sha256 and meta.corpus_sha256 != rag_index.corpus_digest(chunks)
        )
        if stale or not meta.corpus_sha256:
            return "stale", Message("session.rag.stale", built_at=meta.built_at, build=build)
        return None, None

    def _rag_unavailable(self) -> str | None:
        """Story 15, AD-12: the RAG's reasons after its content (1), in order: sqlite-vec,
        index absent, unreadable, of another model or stale (2-4), model's files missing (5),
        then, once wanted, loading (6) and a refused or failed load (7)."""
        model = self._rag_model
        with self._lock:
            index_error, missing_text = self._rag_index_error, self._rag_missing_text
            wanted = "rag" in self._wanted
            loading, load_error, loaded = (
                self._rag_loading,
                self._rag_load_error,
                self._embedder is not None,
            )
        if index_error is not None:
            return index_error
        if missing_text is not None:
            return missing_text
        if not wanted or loaded:
            return None
        if loading:
            return Message("session.rag.loading", label=model.label_text if model else "")
        return load_error or Message("session.rag.not_loaded")

    def _rag_offers(self) -> dict[str, dict[str, str] | None]:
        """AD-21, the card's actions: « Télécharger » while the model's files are missing,
        « Construire l'index » once they are there and the index is absent, unreadable, of
        another model or stale. None when sqlite-vec cannot load or the content is invalid."""
        model, content = self._rag_model, self._rag_content
        none: dict[str, dict[str, str] | None] = {"download": None, "build_index": None}
        if model is None or content is None or "rag" in self._content_errors:
            return none
        with self._lock:
            kind, missing = self._rag_index_kind, list(self._rag_missing)
        if kind == "vec":
            return none
        if missing:
            size_mb = max(1, round(sum(f.size for f in missing) / 1_000_000))
            label = content.download_label_text.format(size_mb=size_mb)
            return none | {"download": {"target": RAG_TARGET, "label_text": label}}
        if kind is not None:
            return none | {"build_index": {"label_text": content.build_label_text}}
        return none

    def _rag_index_detail(self) -> str:
        """The index node's tooltip: its path, its excerpts and its embedding model."""
        path = self._rag_index_path()
        with self._lock:
            chunks, error = self._rag_chunks, self._rag_index_error
        if not chunks:
            return self._t("session.rag.detail_absent", path=path)
        model = self._rag_model.id if self._rag_model else "?"
        detail = self._t("session.rag.detail", path=path, chunks=chunks, model=model)
        return f"{detail} · {self._text(error)}" if error else detail

    def _request_rag_sync(self) -> None:
        """Story 15 (AD-8): the embedding model follows the brick's `wanted`, loaded or
        released on the worker. « Chargement en cours » from now on, so no turn takes the
        brick before its model is there; a turn already queued runs without it."""
        if "rag" not in self._bricks:
            return
        static, rerank_static = self._rag_static_reason(), self._rerank_static_reason()
        with self._lock:
            wanted, loaded = "rag" in self._wanted, self._embedder is not None
            if not wanted:
                self._rag_load_error, self._rag_loading = None, False
            # Story 16: the reranker follows the sub-option, with the embedder loaded or
            # loading now (as `_sync_reranker` decides): no « Chargement » for nothing.
            embedder_on = loaded or (wanted and static is None)
            rerank_need = (
                wanted and self._rag_rerank and embedder_on and static is None and not rerank_static
            )
            rerank_loaded = self._reranker is not None
            if not rerank_need:
                self._rerank_load_error, self._rerank_loading = None, False
        embedder_idle = wanted == loaded or (wanted and static is not None)
        if embedder_idle and rerank_need == rerank_loaded:
            return  # nothing to load nor to release: no event (one per reconfiguration)
        with self._lock:
            if wanted and not loaded and static is None:
                self._rag_loading, self._rag_load_error = True, None
            if rerank_need and not rerank_loaded:
                self._rerank_loading, self._rerank_load_error = True, None
        self._executor.submit(self._sync_rag)

    def _rag_static_reason(self) -> str | None:
        """Reasons 1 to 5: what prevents loading the model at all."""
        if "rag" in self._content_errors or self._rag_model is None:
            return self._content_errors.get("rag") or Message("session.rag.not_configured")
        with self._lock:
            index_error, missing = self._rag_index_error, bool(self._rag_missing)
        return index_error or (Message("session.rag.model_missing") if missing else None)

    def _sync_rag(self) -> None:
        """On the worker: load the embedding model through the registry (AD-8) when the brick
        is wanted and could be available, release it (`close()`) otherwise. Then the card, the
        schema and the preview again."""
        model = self._rag_model
        with self._lock:
            wanted, embedder = "rag" in self._wanted, self._embedder
        changed = False
        if wanted and embedder is None:
            self._rag_refresh()  # a file deleted or copied since: read again, no relaunch
        if not wanted or model is None or self._rag_static_reason() is not None:
            changed = embedder is not None
            self._release_embedder()
        elif embedder is None:
            loaded, retriever, error = self._load_embedder(model)
            with self._lock:
                still = "rag" in self._wanted  # switched off while it loaded?
                if still:
                    self._embedder, self._rag_retriever = loaded, retriever
                    self._rag_load_error = error
            if not still:
                self._close_embedder(loaded, retriever)
            changed = True
        with self._lock:
            changed = changed or self._rag_loading
            self._rag_loading = False
        changed = self._sync_reranker() or changed  # story 16, once the embedder is there
        if changed:
            self._emit_bricks()
            self._emit_architecture()
            self._emit_preview()

    def _load_embedder(
        self, model: EmbeddingModel
    ) -> tuple[Embedder | None, SqliteVecRetriever | None, str | None]:
        """The budget first (a refusal in figures, nothing loaded), then the file's identity
        (its declared sha256), then the load and the index's connection."""
        label = Message("session.rag.embedding_label", label=model.label_text)
        cost = self._load_registry.component_cost(
            model.measured_rss_mb, [f.size for f in model.files]
        )
        refusal = self._load_registry.check_component(label, cost, EMBEDDING)
        if refusal is not None:
            with scoped(brick="rag", component="rag.retriever"):
                self._error(
                    refusal,
                    Message("session.load.budget_cause"),
                    Message("session.rag.refused_effect"),
                )
            return None, None, Message("session.unavailable", reason=refusal)
        path = embedding_module.model_path(model)
        embedder: Embedder | None = None
        try:
            declared = model.load_file.sha256
            if declared and rag_index.file_sha256(path) != declared.lower():
                raise ValueRefused("session.rag.sha256", path=path, section="rag.embedding")
            embedder = self._embedder_factory(model)
            retriever = SqliteVecRetriever(self._rag_index_path(), embedder, self.cfg.rag_top_k)
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            self._close_embedder(embedder, None)
            with scoped(brick="rag", component="rag.retriever"):
                self._error(
                    Message("session.rag.load_failed"),
                    exc,
                    Message("session.content.unavailable.rag"),
                )
            return (
                None,
                None,
                Message(
                    "session.rag.load_failed_reason",
                    kind=type(exc).__name__,
                    cause=exc,
                    path=path,
                ),
            )
        self._load_registry.grant(model.label_text, cost, EMBEDDING)
        return embedder, retriever, None

    def _close_embedder(
        self, embedder: Embedder | None, retriever: SqliteVecRetriever | None
    ) -> None:
        if retriever is not None:
            retriever.close()
        if embedder is not None:
            try:
                embedder.close()
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(Message("session.rag.close_failed"), exc, Message("session.forgotten"))
        self._load_registry.release(EMBEDDING)

    def _release_embedder(self) -> None:
        with self._lock:
            embedder, self._embedder = self._embedder, None
            retriever, self._rag_retriever = self._rag_retriever, None
        self._close_embedder(embedder, retriever)

    # ---------- story 16: the reranking sub-option (AD-8, AD-12, AD-21) ----------

    def _rerank_static_reason(self) -> str | None:
        """What prevents loading the reranker at all: its declaration, then its files."""
        if self._rerank_model is None:
            return self._rerank_config_error or Message("session.rerank.not_configured")
        with self._lock:
            return self._rerank_missing_text

    def _rerank_availability(self) -> tuple[bool, str | None]:
        """The sub-option's own availability, in order: its declaration, its files, then,
        once it should load, loading and a refused or failed load, and the embedding model it
        waits for. The RAG brick stays available without it."""
        static = self._rerank_static_reason()
        if static is not None:
            return False, static
        model = self._rerank_model
        with self._lock:
            wanted = "rag" in self._wanted and self._rag_rerank
            loading, error = self._rerank_loading, self._rerank_load_error
            loaded = self._reranker is not None
            embedder = self._embedder is not None
        if not wanted or loaded:
            return True, None
        if loading:
            return False, Message("session.rerank.loading", label=model.label_text if model else "")
        if error is not None:
            return False, error
        if not embedder:  # the reranker loads after the embedding model, never alone
            rag = self._rag_unavailable()
            prefix = self._t("session.unavailable", reason="")
            why = f" ({self._text(rag).removeprefix(prefix)})" if rag else ""
            return False, self._t("session.rerank.waits_for_rag", why=why)
        return True, None

    def _rerank_skipped_fr(self) -> str | None:
        """Why a turn with the sub-option enabled runs without reranking (said by its RAG
        step), or `None`."""
        ok, why = self._rerank_availability()
        if not ok:
            return self._t("session.rerank.skipped", why=why)
        return self._t("session.rerank.skipped_not_loaded")

    def _rerank_card(self) -> dict[str, Any] | None:
        """The RAG card's « Reranking » switch, its reason and « Télécharger » (AD-21)."""
        content, model = self._rag_content, self._rerank_model
        if content is None:
            return None
        with self._lock:
            enabled, missing = self._rag_rerank, list(self._rerank_missing)
        available, reason_text = self._rerank_availability()
        download = None
        if model is not None and missing:
            size_mb = max(1, round(sum(f.size for f in missing) / 1_000_000))
            download = {
                "target": RERANK_TARGET,
                "label_text": content.rerank_download_label_text.format(size_mb=size_mb),
            }
        return {
            "label_text": content.rerank_label_text,
            "enabled": enabled,
            "available": available,
            "reason_text": reason_text,
            "hosting_text": self._t("session.hosting.local"),
            "download": download,
        }

    def set_rag_rerank(self, enabled: bool) -> None:
        """Class (a), story 16: the RAG brick's reranking sub-option, effective from the next
        turn; its model loads or leaves on the worker. `KeyError` without a RAG brick."""
        if "rag" not in self._bricks:
            raise KeyError("rag")
        with self._lock:
            if self._rag_rerank == enabled:
                return
            self._rag_rerank = enabled
        self._request_rag_sync()
        self._emit_bricks()
        self._emit_architecture()

    def _sync_reranker(self) -> bool:
        """On the worker, after the embedder: load the reranker through the registry (AD-8)
        when the brick and its sub-option want it and the embedder is loaded; release it
        otherwise. Returns whether something changed."""
        model = self._rerank_model
        static, rerank_static = self._rag_static_reason(), self._rerank_static_reason()
        with self._lock:
            need = (
                "rag" in self._wanted
                and self._rag_rerank
                and self._embedder is not None
                and static is None
                and rerank_static is None
                and model is not None
            )
            reranker, error = self._reranker, self._rerank_load_error
        changed = False
        if not need:
            changed = reranker is not None
            self._release_reranker()
        elif reranker is None and error is None:  # a refusal waits for a new request
            loaded, error = self._load_reranker(model)
            with self._lock:
                still = "rag" in self._wanted and self._rag_rerank  # switched off meanwhile?
                if still:
                    self._reranker, self._rerank_load_error = loaded, error
            if not still:
                self._close_reranker(loaded)
            changed = True
        with self._lock:
            changed = changed or self._rerank_loading
            self._rerank_loading = False
        return changed

    def _load_reranker(self, model: RerankerModel) -> tuple[Reranker | None, str | None]:
        """The budget first (a refusal in figures, nothing loaded), then the file's declared
        sha256, then the load."""
        label = Message("session.rerank.label", label=model.label_text)
        cost = self._load_registry.component_cost(
            model.measured_rss_mb, [f.size for f in model.files]
        )
        refusal = self._load_registry.check_component(label, cost, RERANKER)
        if refusal is not None:
            with scoped(brick="rag", component=RAG_RERANKER):
                self._error(
                    refusal,
                    Message("session.load.budget_cause"),
                    Message("session.rerank.refused_effect"),
                )
            return None, Message("session.unavailable", reason=refusal)
        path = reranker_module.model_path(model)
        reranker: Reranker | None = None
        try:
            declared = model.load_file.sha256
            if declared and rag_index.file_sha256(path) != declared.lower():
                raise ValueRefused("session.rag.sha256", path=path, section="rag.reranker")
            reranker = self._reranker_factory(model)
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            self._close_reranker(reranker)
            with scoped(brick="rag", component=RAG_RERANKER):
                self._error(
                    Message("session.rerank.load_failed"),
                    exc,
                    Message("session.rerank.unavailable_effect"),
                )
            return None, Message(
                "session.rerank.load_failed_reason", kind=type(exc).__name__, cause=exc, path=path
            )
        self._load_registry.grant(model.label_text, cost, RERANKER)
        return reranker, None

    def _close_reranker(self, reranker: Reranker | None) -> None:
        if reranker is not None:
            try:
                reranker.close()
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(
                    Message("session.rerank.close_failed"), exc, Message("session.forgotten")
                )
        self._load_registry.release(RERANKER)

    def _release_reranker(self) -> None:
        with self._lock:
            reranker, self._reranker = self._reranker, None
        if reranker is not None:
            self._close_reranker(reranker)

    def _compressor_label(self) -> str:
        """The loaded compressor's own label; before it loads, its factory's (Headroom's)."""
        with self._lock:
            compressor = self._compressor
        if compressor is not None:
            return compressor.label_text
        named = getattr(self._compressor_factory, "label_text", None)
        return str(named) if named else self._t("session.compression.the_compressor")

    def _compression_unavailable(self) -> str | None:
        """Story 20: Headroom not installed (or another version), then, once wanted, loading
        and a refused or failed load."""
        if self._compression_missing is not None:
            return self._compression_missing
        with self._lock:
            wanted = "compression" in self._wanted
            loading, error = self._compression_loading, self._compression_load_error
            loaded = self._compressor is not None
        if not wanted or loaded:
            return None
        if loading:
            named = getattr(self._compressor_factory, "label_text", None)
            if named:
                return Message("session.load.loading", label=named)
            return Message("session.compression.loading")
        return error or Message("session.compression.not_loaded")

    def _request_compression_sync(self) -> None:
        """As the RAG's model (story 15): Headroom follows the brick's `wanted`, loaded or
        released on the worker; « Chargement » from now on, so no turn takes the brick first."""
        if "compression" not in self._bricks:
            return
        with self._lock:
            wanted, loaded = "compression" in self._wanted, self._compressor is not None
            if not wanted:
                self._compression_load_error, self._compression_loading = None, False
        static = self._compression_missing or self._content_errors.get("compression")
        if wanted == loaded or (wanted and static is not None):
            return
        if wanted:
            with self._lock:
                self._compression_loading, self._compression_load_error = True, None
        self._executor.submit(self._sync_compression)

    def _sync_compression(self) -> None:
        """On the worker: load through the registry when wanted, release otherwise; then the
        card and the schema again. Switched off while it loaded: closed and released."""
        with self._lock:
            wanted, compressor = "compression" in self._wanted, self._compressor
        static = self._compression_missing or self._content_errors.get("compression")
        changed = False
        if not wanted or static is not None:
            changed = compressor is not None
            self._release_compressor()
        elif compressor is None:
            loaded, error = self._load_compressor()
            with self._lock:
                still = "compression" in self._wanted
                if still:
                    self._compressor, self._compression_load_error = loaded, error
            if not still:
                self._close_compressor(loaded)
            changed = True
        with self._lock:
            changed = changed or self._compression_loading
            self._compression_loading = False
        if changed:
            self._emit_bricks()
            self._emit_architecture()

    def _load_compressor(self) -> tuple[Compressor | None, str | None]:
        """The budget first (a refusal in figures, nothing imported), then the import and the
        warm-up call. Once imported, the library stays in memory until WaveStack stops: a
        later load costs nothing more, its memory being in the RSS measured (AD-8)."""
        label = self._compressor_label()
        cost = 0 if self._compressor_imported else self.cfg.compression_cost_bytes
        refusal = self._load_registry.check_component(label, cost, COMPRESSOR) if cost else None
        if refusal is not None:
            with scoped(brick="compression", component="compression.compressor"):
                self._error(
                    refusal,
                    Message("session.load.budget_cause"),
                    Message("session.compression.refused_effect"),
                )
            return None, Message("session.unavailable", reason=refusal)
        try:
            compressor = self._compressor_factory()
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            with scoped(brick="compression", component="compression.compressor"):
                self._error(
                    Message("session.compression.load_failed"),
                    exc,
                    Message("session.compression.unavailable_effect"),
                )
            return None, Message(
                "session.compression.load_failed_reason", kind=type(exc).__name__, cause=exc
            )
        self._compressor_imported = True
        self._load_registry.grant(compressor.label_text, cost, COMPRESSOR)
        return compressor, None

    def _close_compressor(self, compressor: Compressor | None) -> None:
        if compressor is not None:
            try:
                compressor.close()
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(
                    Message("session.compression.close_failed"), exc, Message("session.forgotten")
                )
        self._load_registry.release(COMPRESSOR)

    def _release_compressor(self) -> None:
        with self._lock:
            compressor, self._compressor = self._compressor, None
        self._close_compressor(compressor)

    def _emit_memory(self) -> None:
        """AD-1: the drawer and the card project the last `memory_changed`."""
        if "global_memory" not in self._bricks:
            return
        error_text = self._memory_unavailable_fr()
        with self._lock:
            entries = [e.model_dump() for e in self._memory] if error_text is None else []
        self._journal().emit(
            "memory_changed",
            {
                "entries": entries,
                "path": str(config.memory_path()),
                "error_text": error_text,
                "max_entries": memory_file.MAX_ENTRIES,
                "max_chars": memory_file.MAX_CHARS,
            },
        )

    # ---------- bricks (AD-12) ----------

    def _label(self, brick_id: str) -> str:
        content = self._content.get(brick_id)
        return content.label_text if content else brick_id

    def _availability(self, brick_id: str) -> tuple[bool, str | None]:
        """The single point computing `available` and its French reason (AD-12)."""
        brick = self._bricks.get(brick_id)
        if brick is None:
            return False, Message("session.availability.unknown_brick", brick=brick_id)
        with self._lock:
            wanted = set(self._wanted)
        for dep in brick.requires:
            if dep not in wanted or not self._availability(dep)[0]:
                return False, Message("session.availability.requires", brick=self._label(dep))
        if (reason := self._capability_reason(brick_id)) is not None:
            return False, reason
        if brick_id in self._content_errors:
            return False, self._content_errors[brick_id]
        if brick_id == "global_memory":
            with self._lock:
                error_text = self._memory_error
            if error_text is not None:
                return False, error_text
        if brick_id == "rag" and (reason := self._rag_unavailable()) is not None:
            return False, reason
        if brick_id == "compression" and (reason := self._compression_unavailable()) is not None:
            return False, reason
        return True, None

    def _capability_reason(self, brick_id: str) -> str | None:
        """AD-6: why the active model cannot offer `brick_id` (a capability it lacks, or a
        window too small for the reasoning), else `None`. Part of `_availability`; lot E
        (E5): the scenario's warning."""
        brick = self._bricks.get(brick_id)
        if brick is None:
            return None
        missing = [c for c in brick.capabilities if not getattr(self._caps, c, None)]
        if "reasoning" in missing:
            return self._no_reasoning_fr()
        if brick_id == "reasoning" and (too_small := reasoning_window_fr(self._window)):
            return too_small  # AD-9, as the cloud `tpm` guard
        if missing and self._cloud is not None:  # AD-6: a capability not declared is absent
            return Message("session.availability.cloud_no_tools", model=self._cloud.id)
        if missing:
            needs = ", ".join(
                self._t(f"session.capabilities.{c}", parser=NO_TOOL_PARSER_FR)
                if c in _CAPABILITIES
                else c
                for c in missing
            )
            return self._t("session.availability.lacks", needs=needs)
        return None

    def _no_reasoning_fr(self) -> str:
        """EXPERIENCE.md's reason, then its cause: no model, the template, or the cloud
        declaration."""
        if self._caps is None:
            return Message("session.availability.no_model")
        if self._cloud is not None:
            return Message("session.availability.cloud_no_reasoning", model=self._cloud.id)
        return Message("session.availability.no_reasoning")

    def _memory_card(self) -> dict[str, Any]:
        """What the memory card and its drawer say (AD-19): the note without a tool parser
        (H4), the empty drawer's text, the forced write's field help."""
        note_text = self._memory_note_fr()
        content = self._memory_content
        if content is None:
            return {"note_text": note_text}
        drawer = content.drawer
        return {
            "note_text": note_text,
            "empty_text": drawer.empty_no_parser_text if note_text else drawer.empty_text,
            "text_help_text": drawer.text_help_text.replace(
                "{max_chars}", str(memory_file.MAX_CHARS)
            ),
        }

    def _memory_note_fr(self) -> str | None:
        """H4: without a tool parser, the memory is injected and edited, not written by the
        model."""
        if self._caps is None or self._caps.tool_call_parser:
            return None
        return self._t("session.memory.no_parser")

    def _always_fr(self) -> str | None:
        """AD-6: a cloud model that always reasons shows it on the reasoning card."""
        entry = self._cloud
        if entry is None or not entry.always_reasons:
            return None
        return self._t(
            "session.reasoning.always", model=entry.model, reserve=self._num_lazy(MAX_RESERVE)
        )

    def _reasoning_budget_fr(self) -> str | None:
        """Lot C (N4): the reasoning budget, local mode only (a cloud provider manages its
        own reasoning effort)."""
        caps = self._caps
        if self._cloud is not None or caps is None or not (caps.reasoning_tags and caps.reasoning):
            return None
        budget = self.cfg.reasoning_budget_tokens
        return self._t(
            "session.reasoning.budget",
            budget=self._num_lazy(budget),
            left=self._num_lazy(MAX_RESERVE - budget),
        )

    def _reasoning_on(self, state: TurnState) -> bool:
        """AD-6, AD-9: the model reasons in this turn: brick effective, or a cloud model
        that always reasons. In a sub-agent's context (AD-11), the brick counts only if it
        contributes to it (`contributes_to`): the reasoning brick does not, so the sub-agent
        keeps the 512-token reserve and the room for its document."""
        always = self._caps is not None and self._caps.reasoning_always
        brick_on = "reasoning" in state.effective
        if self._ratio_key() == "sub":
            brick_on = brick_on and self._contributes("reasoning", "sub")
        return always or brick_on

    def _contributes(self, brick_id: str, context: str) -> bool:
        """AD-11, AD-12: the brick declares it contributes to `context` (`main` or `sub`)."""
        brick = self._bricks.get(brick_id)
        return brick is not None and context in brick.contributes_to

    def _reserve_of(self, state: TurnState) -> int:
        """AD-9: the output reserve of a turn (or of the preview), from its frozen state."""
        return output_reserve(self._reasoning_on(state))

    def _resend(self) -> str | None:
        """AD-4, chat mode: the `format` the reasoning goes back in, when `resend` is set."""
        reasoning = self._cloud.reasoning if self._cloud is not None else None
        return reasoning.format if reasoning is not None and reasoning.resend else None

    def _resend_tags(self) -> tuple[str, str]:
        """The tags a `think_tags` reasoning goes back in: the active entry's."""
        reasoning = self._cloud.reasoning if self._cloud is not None else None
        return tuple(reasoning.tags) if reasoning is not None else THINK_TAGS

    def _effective(self) -> frozenset[str]:
        with self._lock:
            wanted = set(self._wanted)
        return frozenset(b for b in wanted if self._availability(b)[0])

    def _mcp_tool_names(self) -> list[str]:
        """The tools of the enabled servers that are `available` (in documentation complète)."""
        with self._lock:
            ready = {
                s for s in self._mcp_enabled if self._mcp_state.get(s, ("",))[0] == "available"
            }
        return [n for s in self._mcp_servers if s in ready for n in self._mcp_tools(s)]

    def build_turn_state(self) -> TurnState:
        """AD-17: the conversational snapshot (branch history, skills and documentations
        loaded) plus the current configuration. A replay restores the snapshot first."""
        with self._lock:
            history = list(self._history)
            prompt = self._custom_prompt
        effective = self._effective()
        with self._lock:
            enabled = set(self._tools_enabled)
            lazy, loaded = self._mcp_lazy, set(self._loaded_docs)
            skills_enabled, skills_loaded = set(self._skills_enabled), set(self._loaded_skills)
            hooks_enabled = set(self._hooks_enabled)
        tools = [n for n in self._registry.names if n in enabled] if "tools" in effective else []
        loadable: list[str] = []
        if "mcp" in effective:
            mcp = self._mcp_tool_names()
            if lazy:  # AD-25: loaded documentations only, the others through `load_tool_doc`
                loadable = [n for n in mcp if n not in loaded]
                tools += [n for n in mcp if n in loaded] + ([LOAD_TOOL_DOC] if loadable else [])
            else:
                tools += mcp
        skills: list[str] = []
        catalog: list[str] = []
        if "skills" in effective:  # AD-25: bodies loaded, the others in the catalog
            enabled_skills = [s for s in self._skill_ids() if s in skills_enabled]
            skills = [s for s in enabled_skills if s in skills_loaded]
            catalog = [s for s in enabled_skills if s not in skills_loaded]
            tools += [LOAD_SKILL] if catalog else []
        memory: tuple[str, ...] = ()
        if "global_memory" in effective:  # AD-4: frozen for the turn's calls
            with self._lock:  # N1: the conversation's snapshot, else the file's entries
                snapshot, entries = self._memory_snapshot, list(self._memory)
            if snapshot is None:
                memory = tuple(e.text for e in entries)
            else:  # an addition waits for the next conversation; a deletion or an edit
                current = {e.id: e.text for e in entries}  # applies at once
                memory = tuple(text for id_, text in snapshot if current.get(id_) == text)
            if self._caps is not None and self._caps.tool_call_parser:  # H4, AD-25
                tools.append(REMEMBER)
        sub_tools: list[str] = []
        if "subagent" in effective:  # AD-11: `[subagent] tools` among the tools retained
            wanted = self.cfg.subagent_tools  # of the bricks contributing to `sub`
            sub_tools = [
                n
                for n in tools
                if n in wanted
                and (spec := self._registry.get(n)) is not None
                and spec.source != "harness"  # no meta-tool, no nested delegation
                and self._contributes(spec.brick or spec.component.split(".")[0], "sub")
            ]
            tools.append(DELEGATE)
        hooks = [h for h in self._hook_ids() if h in hooks_enabled] if "hooks" in effective else []
        with self._lock:  # story 16: reranked only with its model loaded at the turn's start
            asked = "rag" in effective and self._rag_rerank
            rerank = asked and self._reranker is not None
        skipped = self._rerank_skipped_fr() if asked and not rerank else None
        return TurnState(
            history=tuple(history),
            system_prompt=prompt if prompt is not None else self._default_prompt,
            effective=effective,
            tools=tuple(tools),
            loadable=tuple(loadable),
            skills=tuple(skills),
            skill_catalog=tuple(catalog),
            hooks=tuple(hooks),
            memory=memory,
            subagent_tools=tuple(sub_tools),
            rag_rerank=rerank,
            rag_rerank_skipped_text=skipped,
        )

    # ---------- rendering ----------

    @staticmethod
    def _step_messages(
        steps: tuple[dict[str, Any], ...] | list[dict[str, Any]],
        *,
        history: bool,
        group: str,
        chat: bool = False,
        resend: str | None = None,
        wrap: tuple[str, str] | None = None,
        cloud_id: str | None = None,
        tags: tuple[str, str] = THINK_TAGS,
    ) -> list[dict[str, Any]]:
        """Intermediate messages of a turn: `assistant_turn`/`tool_result` in the turn itself
        (or the step's own `kind`), `history` afterwards, where a step's `stub` replaces its
        content. Each call's name and arguments form one group (AD-4). Calls carry their
        session `id`, replies its `tool_call_id`. Chat mode (AD-4): the reasoning sent back
        only with `resend` (its `format`), an empty `content` omitted, `arguments` as the
        string emitted, a reply without `name`, and a malformed call's error sent as a `user`
        message. `wrap` (lot A, local mode): a past step rendered as it was produced
        (`_as_produced`). A call's `extra` fields (Gemini's thought signature, under
        `extra_content`) go back in chat mode only to the entry they are for: `extra_for`
        equal to `cloud_id`; they never replace `id`, `type` nor `function`."""
        memory = (SegmentKind.HISTORY, "short_memory", "short_memory.history")
        messages: list[dict[str, Any]] = []
        for i, step in enumerate(steps):
            if step["role"] == "tool":
                kind, brick, component = (
                    memory
                    if history
                    else (
                        step.get("kind", SegmentKind.TOOL_RESULT),
                        step.get("brick", "tools"),
                        step["component"],
                    )
                )
                text = step.get("stub", step["content"]) if history else step["content"]
                # Story 20: in the turn, a compressed reply carries what it was (AD-22).
                was = None if history else step.get("compressed_from")
                content = [Part(kind, text, brick, component, compressed_from=was)]
                if chat and step.get("id") is None:  # a malformed call's error (AD-10)
                    messages.append({"role": "user", "content": content})
                    continue
                reply: dict[str, Any] = {"role": "tool"}
                if step.get("id") is not None:
                    reply["tool_call_id"] = step["id"]
                messages.append(reply | {"content": content})
                continue
            # A forced action's call is attributed to its brick (AD-25), the model's to it.
            kind, brick, component = (
                memory
                if history
                else (
                    SegmentKind.ASSISTANT_TURN,
                    step.get("brick"),
                    step.get("component", "core.model"),
                )
            )
            if history and wrap is not None:
                answer = AppSession._as_produced(
                    Part(kind, step["content"], brick, component), step.get("reasoning", ""), wrap
                )
            else:
                answer = AppSession._assistant_message(
                    Part(kind, step["content"], brick, component),
                    step.get("reasoning", ""),
                    chat=chat,
                    resend=resend,
                    omit_empty=chat,
                    tags=tags,
                )
            if step["tool_calls"]:
                answer["tool_calls"] = []
                for j, call in enumerate(step["tool_calls"]):
                    in_call = (brick, component, f"{group}.{i}.{j}")
                    if chat:  # the string emitted, or serialized once by the session
                        arguments: Any = Part(kind, call["arguments_json"], *in_call)
                    else:
                        # ponytail: only string values are wrapped; a number or an object
                        # stays plain (template), since a template may `tojson` them.
                        arguments = {
                            arg: Part(kind, value, *in_call) if isinstance(value, str) else value
                            for arg, value in call["arguments"].items()
                        }
                    name = Part(kind, call["name"], *in_call)
                    function = {"name": name, "arguments": arguments}
                    sent = {"id": call.get("id"), "type": "function", "function": function}
                    if chat and call.get("extra") and call.get("extra_for") == cloud_id:
                        sent |= {k: v for k, v in call["extra"].items() if k not in sent}
                    answer["tool_calls"].append(sent)
            messages.append(answer)
        return messages

    @staticmethod
    def _assistant_message(
        content: Part,
        reasoning: str,
        *,
        chat: bool,
        resend: str | None,
        omit_empty: bool,
        tags: tuple[str, str] = THINK_TAGS,
    ) -> dict[str, Any]:
        """An assistant message with its reasoning, attributed like its text (AD-4): locally
        the `reasoning_content` variable, the template deciding whether it keeps it; in chat
        mode, only with `resend`, in the form of the entry's `format`."""
        answer: dict[str, Any] = {"role": "assistant"}
        text = [content] if content.text or not omit_empty else []
        thought = content._replace(text=reasoning) if reasoning else None
        if thought is not None and chat and resend == "content_blocks":
            blocks = [{"type": "thinking", "thinking": [{"type": "text", "text": thought}]}]
            # No empty `text` block: a past answer of reasoning only keeps its thinking alone.
            answer["content"] = blocks + [
                {"type": "text", "text": part} for part in text if part.text
            ]
        elif thought is not None and chat and resend == "think_tags":
            # As received: the closing tag right before the text, no separator added.
            tagged = thought._replace(text=f"{tags[0]}{reasoning}{tags[1]}")
            answer["content"] = [Joined((tagged, *(p for p in text if p.text)), sep="")]
        elif text:
            answer["content"] = text
        if thought is not None and not chat:
            answer["reasoning_content"] = thought
        elif thought is not None and chat and resend == "field":
            answer["reasoning"] = thought
        return answer

    @staticmethod
    def _as_produced(content: Part, reasoning: str, wrap: tuple[str, str]) -> dict[str, Any]:
        """Lot A (AD-4, append only over the conversation): a past assistant message, locally,
        as the model produced it, since its tokens are in the engine's cache. The template
        omits the reasoning block of a past message; the harness writes it itself, with the
        template's own texts (`reasoning_wrap`, `template` parts, its literals), the
        reasoning (empty or not) and the text attributed like the text, and an empty
        `reasoning_content` so that the template keeps the content as it is. As any
        content, its outer blanks go (the template trims it)."""
        texts = [wrap[0], reasoning.strip(), wrap[1], content.text.strip()]
        for ends in (range(4), range(3, -1, -1)):  # from the start, then from the end
            for i in ends:
                texts[i] = texts[i].lstrip() if ends.step > 0 else texts[i].rstrip()
                if texts[i]:
                    break
        template = SegmentKind.TEMPLATE
        parts = (
            Part(template, texts[0]),
            content._replace(text=reasoning),
            Part(template, texts[2]),
            content,
        )
        return {"role": "assistant", "content": [Joined(parts, sep="")], "reasoning_content": ""}

    def _system_parts(self, state: TurnState) -> list[Part | Joined]:
        """AD-4: the system prompt, then the global memory (its intro and one line per
        entry), then the skills catalog (its intro and one line per skill), then the bodies
        of the skills loaded (AD-25)."""
        parts: list[Part | Joined] = []
        if "system_prompt" in state.effective:
            parts.append(
                Part(
                    SegmentKind.SYSTEM_PROMPT,
                    state.system_prompt,
                    "system_prompt",
                    "system_prompt.prompt",
                )
            )
        if state.memory and self._memory_content is not None:
            memory = (SegmentKind.GLOBAL_MEMORY, "global_memory", MEMORY)
            intro = Part(memory[0], self._memory_content.intro, *memory[1:])
            lines = [Part(memory[0], f"- {text}", *memory[1:]) for text in state.memory]
            parts.append(Joined((intro, *lines), sep="\n"))
        content = self._skills_content
        if content is None:  # invalid content: the skills brick is unavailable anyway
            return parts
        if state.skill_catalog:
            intro = Part(SegmentKind.SKILL_CATALOG, content.catalog_intro, "skills", "core.harness")
            lines = [
                Part(
                    SegmentKind.SKILL_CATALOG,
                    f"- {s} : {content.skills[s].description}",
                    "skills",
                    f"skills.{s}",
                )
                for s in state.skill_catalog
            ]
            parts.append(Joined((intro, *lines), sep="\n"))
        for s in state.skills:  # each body named by a header line, so they stay apart
            text = content.skills[s]
            header = self._t("session.skills.body_header", label=text.label_text, skill=s)
            body = f"{header}\n{text.body}"
            parts.append(Part(SegmentKind.SKILL_BODY, body, "skills", f"skills.{s}"))
        return parts

    def _messages(
        self,
        state: TurnState,
        message: str,
        steps: list[dict[str, Any]] | None = None,
        *,
        chat: bool = False,
    ) -> list[dict[str, Any]]:
        """AD-4 slots: system message, history, the turn's user message, then the turn's steps.

        Every brick off gives the bare LLM's single user message, byte for byte.
        """
        messages: list[dict[str, Any]] = []
        resend = self._resend() if chat else None
        cloud_id = self._cloud.id if chat and self._cloud is not None else None
        tags = self._resend_tags()
        wrap = None
        if not chat and self._caps is not None and self._caps.chat_template:
            wrap = reasoning_wrap(self._caps.chat_template)  # lot A: None for most templates
        if system := self._system_parts(state):
            messages.append({"role": "system", "content": system})
        if "short_memory" in state.effective:
            for ex in state.history:
                memory = ("short_memory", "short_memory.history")
                user = [Part(SegmentKind.HISTORY, ex.user, *memory)]
                if ex.injection:  # H3's text stays before its message
                    user.insert(0, Part(SegmentKind.HISTORY, ex.injection, *memory))
                messages.append({"role": "user", "content": user})
                messages += self._step_messages(
                    ex.steps,
                    history=True,
                    group=ex.turn_id,
                    chat=chat,
                    resend=resend,
                    wrap=wrap,
                    cloud_id=cloud_id,
                    tags=tags,
                )
                text = Part(SegmentKind.HISTORY, ex.text, *memory)
                messages.append(
                    self._as_produced(text, ex.reasoning, wrap)
                    if wrap is not None
                    else self._assistant_message(
                        text,
                        ex.reasoning,
                        chat=chat,
                        resend=resend,
                        omit_empty=False,  # a past answer keeps its `content`, even empty
                        tags=tags,
                    )
                )
        # Story 15 (AD-4): the RAG's intro and excerpts, each its own part, before the message.
        # Story 20: an excerpt the compressor replaced carries what it was.
        was = state.rag_compressed + (None,) * (len(state.rag_excerpts) - len(state.rag_compressed))
        rag = [
            Part(SegmentKind.RAG_EXCERPT, t, "rag", "rag.retriever", compressed_from=w)
            for t, w in zip(state.rag_excerpts, was, strict=True)
        ]
        user = [*rag, Part(SegmentKind.USER_MESSAGE, message)]
        if state.injection:  # AD-13: added before the message, never rewriting it
            user.insert(0, Part(SegmentKind.HOOK_INJECTION, state.injection, "hooks", "hooks.h3"))
        messages.append({"role": "user", "content": user})
        messages += self._step_messages(
            steps or [],
            history=False,
            group="turn",
            chat=chat,
            resend=resend,
            cloud_id=cloud_id,
            tags=tags,
        )
        return messages

    def _tool_definitions(self, state: TurnState) -> list[dict[str, Any]] | None:
        """AD-4: the `tools` variable, one `tool_catalog` group per tool; `None` when off."""
        if not state.tools:
            return None

        def wrap(value: Any, name: str, spec: ToolSpec, key: str | None = None) -> Any:
            if isinstance(value, dict):
                return {k: wrap(v, name, spec, k) for k, v in value.items()}
            if isinstance(value, list):
                return [wrap(v, name, spec) for v in value]
            if isinstance(value, str) and key in ("name", "description"):
                brick = spec.brick or spec.component.split(".")[0]  # `tools` or `mcp` (AD-4)
                return Part(SegmentKind.TOOL_CATALOG, value, brick, spec.component, name)
            return value

        definitions = []
        for name in state.tools:
            spec = self._registry.get(name)
            if spec is None:  # a server closed since the turn started: nothing to describe
                continue
            definition = wrap(self._registry.definition(name), name, spec)
            if name == LOAD_TOOL_DOC:
                definition["function"]["description"] = self._doc_catalog(spec, state.loadable)
            definitions.append(definition)
        return definitions or None

    def _doc_catalog(self, spec: ToolSpec, loadable: tuple[str, ...]) -> Joined:
        """AD-25: `load_tool_doc`'s description, its intro then one line per loadable tool,
        each line a `tool_catalog` segment of its own server's component."""
        lines = []
        for name in loadable:
            tool = self._registry.get(name)
            if tool is None:
                continue
            text = mcp_lab.catalog_line(name, tool.description, DOC_LINE_MAX)
            lines.append(Part(SegmentKind.TOOL_CATALOG, text, "mcp", tool.component, name))
        intro = Part(
            SegmentKind.TOOL_CATALOG, spec.description or "", "mcp", spec.component, LOAD_TOOL_DOC
        )
        return Joined((intro, *lines), sep="\n")

    def _sub_messages(
        self, sub: _SubContext, steps: list[dict[str, Any]], *, chat: bool = False
    ) -> list[dict[str, Any]]:
        """AD-11: the sub-agent's context, its prompt then the task, then its own steps;
        nothing of the main context (history, main prompt, skills, H3)."""
        own = ("subagent", "subagent.agent")
        return [
            {"role": "system", "content": [Part(SegmentKind.SYSTEM_PROMPT, sub.prompt, *own)]},
            {"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, sub.task, *own)]},
            *self._step_messages(
                steps,
                history=False,
                group="sub",
                chat=chat,
                resend=self._resend() if chat else None,
                cloud_id=self._cloud.id if chat and self._cloud is not None else None,
                tags=self._resend_tags(),
            ),
        ]

    def _render(
        self,
        state: TurnState,
        message: str,
        call_id: str | None,
        steps: list[dict[str, Any]] | None = None,
        sub: _SubContext | None = None,
        read_before: list[Segment] | None = None,
    ) -> tuple[RenderedContext | RenderedChat, dict[str, Any]]:
        """`sub`: a sub-agent's call (AD-11), rendered the same way from its own messages and
        tools (`_tool_definitions` reads only `tools` and `loadable`). `read_before` (story
        32): the segments of the previous call of the same context in the turn, whose common
        prefix is « déjà lu »."""
        assert self._engine is not None and self._caps is not None and self._labels is not None
        if self._cloud is not None:
            return self._render_chat(state, message, call_id, steps, sub, read_before)
        meta = self._engine.metadata()
        template_vars: dict[str, Any] = {}
        if self._caps.reasoning_variable:  # AD-6: the brick sets the template's variable
            template_vars[self._caps.reasoning_variable] = self._reasoning_on(state)
        rendered = render_context(
            self._engine,
            self._caps.chat_template or "",
            self._sub_messages(sub, steps or []) if sub else self._messages(state, message, steps),
            call_id=call_id,
            special_tokens=meta.special_tokens,
            tools=self._tool_definitions(
                replace(state, tools=sub.tools, loadable=()) if sub else state
            ),
            bos_token=meta.bos_token,
            eos_token=meta.eos_token,
            add_generation_prompt=True,
            **template_vars,
            lang=self._language,
        )
        rendered.seen = seen_prefix(read_before, rendered.segments)
        payload = gauge(
            rendered.segments,
            window=self._window,
            reserve=self._reserve_of(state),
            near_limit_ratio=self.cfg.near_limit_ratio,
            labels=self._labels,
            window_source=self._window_source,
            categories=self._categories(),
            seen=rendered.seen,
        )
        return rendered, payload

    def _render_chat(
        self,
        state: TurnState,
        message: str,
        call_id: str | None,
        steps: list[dict[str, Any]] | None,
        sub: _SubContext | None = None,
        read_before: list[Segment] | None = None,
    ) -> tuple[RenderedChat, dict[str, Any]]:
        """AD-4, chat mode: `context` writes the body; before the call, the total is the
        estimates × `ratio` (the main one, or the sub-agents'), and only their raw sum can
        block the call."""
        entry, content = self._cloud, self._cloud_content
        assert entry is not None and content is not None
        reserve = self._reserve_of(state)
        messages = (
            self._sub_messages(sub, steps or [], chat=True)
            if sub
            else self._messages(state, message, steps, chat=True)
        )
        rendered = render_chat_body(
            messages,
            self._tool_definitions(replace(state, tools=sub.tools, loadable=()) if sub else state),
            call_id=call_id,
            fields=chat_fields(entry, reserve, reasoning=self._reasoning_on(state)),
            markers=self.cfg.cloud_markers,
            estimate=lambda text: config.estimate_tokens(text, self.cfg.chars_per_token),
            provider_label_text=content.provider_segment_text,
            lang=self._language,
        )
        rendered.seen = seen_prefix(read_before, rendered.segments)
        payload = self._chat_gauge(
            rendered,
            round(rendered.raw_total * self._ratio),
            "estimate",
            reserve,
        )
        if not payload["overflow"] and payload["used"] > payload["usable"]:
            payload["uncertain_text"] = content.uncertain_text
        return rendered, payload

    @staticmethod
    def _ratio_key() -> str:
        """AD-4: `main`, or `sub` for any sub-agent context (they share one ratio)."""
        return "sub" if (current().context_id or "").startswith("sub") else "main"

    def _categories(self) -> dict[str, str]:
        """Story 33: brick id → category, for the gauge's disciplines (AD-9)."""
        return {brick.id: brick.category for brick in self._bricks.values()}

    def _chat_gauge(
        self, rendered: RenderedChat, total: int, source: str, reserve: int
    ) -> dict[str, Any]:
        """The gauge fields of a chat call for `total`: before the call (`estimate`) or once
        `usage` came back (`api`); one function for both (AD-9)."""
        assert self._labels is not None
        payload = gauge(
            with_total(rendered, total),
            window=self._window,
            reserve=reserve,
            near_limit_ratio=self.cfg.near_limit_ratio,
            labels=self._labels,
            window_source=self._window_source,
            raw_used=rendered.raw_total,
            categories=self._categories(),
            seen=rendered.seen,  # story 32: the same « déjà lu » before and after the call
        )
        return payload | {"body": rendered.body, "usage_source": source}

    def _emit_preview(self) -> None:
        """AD-9: the next-turn gauge, rendered without any message. Runs on the worker."""
        if self._engine is None:
            return  # no model: nothing to preview
        state = self.build_turn_state()
        state = replace(state, injection=self._preview_injection(state))
        if "rag" in state.effective:  # AD-9: the excerpts at their declared maximum
            with self._lock:
                longest = list(self._rag_longest)
            state = replace(
                state,
                rag_excerpts=self._rag_texts(
                    [(i, c.title_text, c.text) for i, c in enumerate(longest, start=1)]
                ),
            )
        try:
            _, payload = self._render(state, "", None)
        except Exception as exc:  # noqa: BLE001 - AD-16
            self._error(
                Message("session.preview.error.message"),
                exc,
                Message("session.preview.error.effect"),
            )
            return
        self._journal().emit("context_preview", payload)

    def _rag_texts(self, excerpts: list[tuple[int, str, str]]) -> tuple[str, ...]:
        """The intro, then each `(position, title_text, text)` in `excerpt_format_text`."""
        content = self._rag_content
        if content is None or not excerpts:
            return ()
        return (content.intro_text, *(content.excerpt(*excerpt) for excerpt in excerpts))

    def _preview_injection(self, state: TurnState) -> str:
        """What the active `on_user_message` hooks would add, for the gauge only: no
        decision emitted, a failing hook left out."""
        texts = []
        for hook in self._hooks:
            if hook.id not in state.hooks or "on_user_message" not in hook.points:
                continue
            try:
                result = hook.fn(
                    HookContext(
                        "on_user_message",
                        "",
                        content=self._hooks_content,
                        language=self._language,
                    )
                )
            except Exception:  # noqa: BLE001, S112 - the turn traces it, not the preview
                continue
            if result is not None and result.decision == "modify" and result.injection:
                texts.append(result.injection)
        return texts[-1] if texts else ""  # as in a turn: the last hook that modified

    # ---------- intentions ----------

    def send(self, message: str) -> str:
        """Intention class (b): refused outside `idle`, with the reason."""
        return self._start(message)

    def replay(self) -> str:
        """Intention class (b), story 9b: the last turn's message again, from the
        conversational state that preceded that turn (AD-17), with the current configuration."""
        return self._start(None)

    def _start(self, message: str | None) -> str:
        """Starts a turn: `message`, or the replay of the last turn when `None`."""
        replay_of = None
        with self._memory_lock, self._lock:  # never while a drawer write or a reset runs
            if self.state != "idle" or self._engine is None or self.reason_text:
                raise SendRefused(self._refusal_reason())
            if message is None:
                if self._last is None:
                    raise SendRefused(Message("session.refused.nothing_to_replay"))
                replay_of, message, history, skills, docs, memory = self._last
                self._history[:] = history
                self._loaded_skills, self._loaded_docs = set(skills), set(docs)
                self._memory_snapshot = memory  # N1: the memory of its conversation
                self._cache_cause = self._cache_cause or "replay"
            self._turns += 1
            turn_id = f"t{self._turns}"
            cancel = self._cancel = CancelToken()
            # Switched under the lock, so a second `send` racing this one is refused.
            self.state, self.reason_text = "turn", _TURN_FR
            # AD-3: the armed actions this turn takes; one armed from now waits for the next.
            armed = tuple(self._armed)
            self._last = (
                turn_id,
                message,
                tuple(self._history),
                frozenset(self._loaded_skills),
                frozenset(self._loaded_docs),
                self._memory_snapshot,
            )
        self._emit_state()
        # N1: the conversation's memory, taken at its first turn with the brick effective
        # (no write can run meanwhile: the state is `turn`).
        if "global_memory" in self._effective():
            with self._lock:
                if self._memory_snapshot is None:
                    self._memory_snapshot = tuple((e.id, e.text) for e in self._memory)
                self._last = (*self._last[:5], self._memory_snapshot)  # type: ignore[index]
        # Frozen now: a later toggle waits for the next turn.
        state = replace(self.build_turn_state(), armed=armed)
        had_pending = bool(self._pending_ids())
        mcp_tools = frozenset(self._mcp_tool_names())
        with self._lock:
            self._sent = (
                frozenset(self._wanted),
                self._custom_prompt or self._default_prompt,
                frozenset(self._tools_enabled),
                mcp_tools,
                self._mcp_lazy,
                frozenset(self._skills_enabled),
                frozenset(self._hooks_enabled),
            )
            # Story 16, apart from `_sent`: what this turn really runs; enabled while its
            # model still loads, it stays « Prend effet au prochain tour ».
            self._sent_rerank = state.rag_rerank or (self._rag_rerank and not self._rerank_loading)
        if had_pending:  # « Prend effet au prochain tour » is over for what this turn reads
            self._emit_bricks()
        if replay_of is not None:  # the schema shows the skills loaded in the replayed branch
            self._emit_architecture()
        self._executor.submit(self._run_turn, turn_id, message, cancel, state, replay_of)
        return turn_id

    def set_brick(self, brick_id: str, wanted: bool) -> None:
        """Class (a): accepted at any time, effective from the next turn. `KeyError` if unknown."""
        if brick_id not in self._bricks:
            raise KeyError(brick_id)
        with self._lock:
            if (brick_id in self._wanted) == wanted:
                return
            if wanted:
                self._wanted.add(brick_id)
            else:
                self._wanted.discard(brick_id)
            servers = sorted(self._mcp_enabled) if brick_id == "mcp" else []
        for server_id in servers:  # AD-15: servers are contacted only once the brick is wanted
            if wanted:
                self._mcp_connect(server_id)
            else:
                self._mcp_disconnect(server_id)
        if brick_id == "rag":  # story 15: its embedding model loads or leaves on the worker
            self._request_rag_sync()
        if brick_id == "compression":  # story 20: Headroom loads or leaves on the worker
            self._request_compression_sync()
        self._emit_bricks()
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    def set_tool(self, name: str, enabled: bool) -> None:
        """Class (a): a tool sub-option, effective from the next turn. `KeyError` if unknown."""
        spec = self._registry.get(name)
        if spec is None or spec.is_mcp or spec.source == "harness":
            raise KeyError(name)
        with self._lock:
            if (name in self._tools_enabled) == enabled:
                return
            if enabled:
                self._tools_enabled.add(name)
            else:
                self._tools_enabled.discard(name)
        self._emit_bricks()
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    def set_skill(self, skill_id: str, enabled: bool) -> None:
        """Class (a): a skill sub-option, effective from the next turn. `KeyError` if unknown.
        A loaded skill disabled leaves the context, and comes back once enabled again."""
        if skill_id not in self._skill_ids():
            raise KeyError(skill_id)
        with self._lock:
            if (skill_id in self._skills_enabled) == enabled:
                return
            if enabled:
                self._skills_enabled.add(skill_id)
            else:
                self._skills_enabled.discard(skill_id)
        self._emit_bricks()
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    def set_hook(self, hook_id: str, enabled: bool) -> None:
        """Class (a): a hook sub-option, effective from the next turn. `KeyError` if unknown."""
        if hook_id not in self._hook_ids():
            raise KeyError(hook_id)
        with self._lock:
            if (hook_id in self._hooks_enabled) == enabled:
                return
            if enabled:
                self._hooks_enabled.add(hook_id)
            else:
                self._hooks_enabled.discard(hook_id)
        self._emit_bricks()
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    # ---------- forced actions (story 9, AD-3, AD-25) ----------

    def arm(self, kind: str, target: str, args: dict[str, Any] | None = None) -> str:
        """Class (a): arms an action for the next turn; returns its `armed_id`. Raises
        `ArmRefused` for an unknown target (`not_found`) or invalid arguments: nothing is
        armed then. Whether the target is still available is checked at consumption."""
        args = dict(args or {})
        if kind == "tool":  # a tool of the tools brick, or an MCP server's (lot K, 2026-09-29)
            spec = self._registry.get(target)
            if (
                spec is None
                or spec.source == "harness"  # a meta-tool has its own action
                or (spec.is_mcp and self._mcp_content is None)
            ):
                raise ArmRefused(Message("session.arm.unknown_tool", target=target), not_found=True)
            # The form's fields are text: converted per the tool's schema, as a model's call;
            # an optional argument left empty is not sent (an MCP tool's optional ones).
            optional = set(spec.params) - set(spec.required) if spec.required is not None else set()
            args = {
                arg: convert_value(value, spec.params.get(arg)) if isinstance(value, str) else value
                for arg, value in args.items()
                if not (arg in optional and isinstance(value, str) and not value.strip())
            }
            detail = self._tool_executor.check(ToolCall(target, args), [target])
            if detail is not None:
                raise ArmRefused(Message("session.arm.nothing_armed", why=detail))
            brick = spec.brick or spec.component.split(".")[0]
            shown = ", ".join(str(value) for value in args.values())
            label = self._registry.label(target)
            label_text = f"{label} ({shown})" if shown else label
        elif kind == "skill":
            if self._skills_content is None or target not in self._skill_ids():
                raise ArmRefused(
                    Message("session.arm.unknown_skill", target=target), not_found=True
                )
            args, brick, label_text = {}, "skills", self._skill_label(target)
        elif kind == "tool_doc":
            spec = self._registry.get(target)
            if self._mcp_content is None or spec is None or not spec.is_mcp:
                raise ArmRefused(
                    Message("session.arm.unknown_mcp_tool", target=target), not_found=True
                )
            args, brick, label_text = {}, "mcp", Message("session.arm.doc_label", target=target)
        elif kind == "memory":
            if self._memory_content is None or target != REMEMBER:
                raise ArmRefused(
                    Message("session.arm.unknown_memory_action", target=target), not_found=True
                )
            try:
                text = memory_file.check_text(args.get("text"))
            except ValueError as exc:
                raise ArmRefused(Message("session.arm.nothing_armed", why=exc)) from None
            shown = text if len(text) <= 40 else f"{text[:40].rstrip()}…"
            args, brick, label_text = (
                {"text": text},
                "global_memory",
                Message("session.arm.memory_label", text=shown),
            )
        elif kind == "delegate":  # story 19: the card's action, its target fixed
            if self._subagent_content is None or target != DELEGATE:
                raise ArmRefused(
                    Message("session.arm.not_delegation", target=target), not_found=True
                )
            extra = sorted(set(args) - {"task"})
            if extra:
                raise ArmRefused(Message("session.arm.delegation_argument", args=", ".join(extra)))
            task = args.get("task", "")
            if not isinstance(task, str):
                raise ArmRefused(Message("session.arm.task_not_text"))
            task = task.strip()
            if not task:
                raise ArmRefused(Message("session.arm.task_empty"))
            shown = task if len(task) <= 40 else f"{task[:40].rstrip()}…"
            args, brick, label_text = (
                {"task": task},
                "subagent",
                Message("session.arm.delegation_label", task=shown),
            )
        else:
            raise ArmRefused(Message("session.arm.unknown_action", kind=kind), not_found=True)
        with self._lock:
            self._arms += 1
            action = ArmedAction(f"arm{self._arms}", kind, brick, target, args, label_text)
            self._armed.append(action)
        self._emit_armed()
        return action.armed_id

    def disarm(self, armed_id: str) -> None:
        """Class (a): removes an armed action. A turn that already took it still runs it.
        Raises `ArmRefused` (`not_found`) when it is not armed."""
        with self._lock:
            kept = [a for a in self._armed if a.armed_id != armed_id]
            found = len(kept) != len(self._armed)
            self._armed = kept
        if not found:
            raise ArmRefused(
                Message("session.arm.not_armed", armed_id=armed_id),
                not_found=True,
            )
        self._emit_armed()

    def _emit_armed(self) -> None:
        """AD-1: the front projects the chips from this event, replayed on reload."""
        with self._lock:
            actions = [a.payload() for a in self._armed]
        self._journal().emit("armed_actions_changed", {"actions": actions})

    def _apply_arm_consumed(self, effects: list[ArmConsumed]) -> None:
        """`ArmConsumed`: the actions a turn took leave the list at its end, whatever its
        status (AD-3); an action armed during the turn stays for the next one."""
        ids = {e.armed_id for e in effects}
        with self._lock:
            kept = [a for a in self._armed if a.armed_id not in ids]
            changed = len(kept) != len(self._armed)
            self._armed = kept
        if changed:
            self._emit_armed()

    # ---------- MCP servers (story 6, AD-15, AD-24) ----------

    def set_mcp_mode(self, lazy: bool) -> None:
        """Class (a): documentation complète or lazy loading, for every MCP server (AD-25).
        Effective from the next turn; the preview shows the difference now. No server is
        contacted again."""
        with self._lock:
            if self._mcp_lazy == lazy:
                return
            self._mcp_lazy = lazy
        self._emit_bricks()
        self._executor.submit(self._emit_preview)

    def _native_tools(self) -> list[ToolSpec]:
        """The native tools, `read_file` bound to the session's language (languages 3/5): it
        reads the demonstration file of the language current at each call."""
        bound = {"read_file": self._read_file, "get_datetime": self._get_datetime}
        return [replace(s, run=bound[s.name]) if s.name in bound else s for s in NATIVE_TOOLS]

    def _read_file(self, path: str) -> str:
        return read_file(path, self._language)

    def _get_datetime(self) -> str:
        return get_datetime(self._language)  # languages (5/5): the day in the session's

    def _harness_tools(self) -> list[ToolSpec]:
        """`load_tool_doc`, `load_skill` and `remember`, registered once; the turn state
        decides when they are offered. Invalid content: their brick is unavailable anyway."""
        specs = []
        if self._mcp_content is not None:
            specs.append(self._load_tool_doc_spec())
        if self._skills_content is not None:
            text = self._skills_content.load_skill
            specs.append(
                ToolSpec(
                    name=LOAD_SKILL,
                    run=self._load_skill,
                    params={"skill": "string"},
                    component="core.harness",
                    source="harness",
                    brick="skills",
                    label_text=text.label_text,
                    description=text.description,  # the catalog is in the system message
                    schema={
                        "type": "object",
                        "properties": {"skill": {"type": "string", "description": text.skill}},
                        "required": ["skill"],
                    },
                    required=("skill",),
                )
            )
        if self._memory_content is not None:
            text = self._memory_content.remember
            specs.append(
                ToolSpec(
                    name=REMEMBER,
                    run=self._remember,
                    params={"text": "string"},
                    component="core.harness",
                    source="harness",
                    brick="global_memory",
                    label_text=text.label_text,
                    description=text.description,
                    schema={
                        "type": "object",
                        "properties": {"text": {"type": "string", "description": text.text}},
                        "required": ["text"],
                    },
                    required=("text",),
                )
            )
        if self._subagent_content is not None:
            text = self._subagent_content
            specs.append(
                ToolSpec(
                    name=DELEGATE,
                    run=self._delegate,
                    params={"task": "string"},
                    component="subagent.agent",
                    source="harness",
                    brick="subagent",
                    label_text=text.phase_label_text,  # the working indicator's phase (EXPERIENCE)
                    description=text.delegate.description,
                    schema={
                        "type": "object",
                        "properties": {
                            "task": {"type": "string", "description": text.delegate.task}
                        },
                        "required": ["task"],
                    },
                    required=("task",),
                )
            )
        return specs

    # ---------- sub-agent (story 19, AD-10, AD-11) ----------

    def _delegate(self, task: str) -> str:
        """`delegate` (AD-25): runs the sub-agent in `sub{n}`, on the same engine, and returns
        only its result. Always emits `subagent_started` then `subagent_ended`, with
        `parent_step` the step of `delegate`; a failure raises `DelegationFailed` with its
        status, and the main turn goes on."""
        ctx, text = self._turn_ctx, self._subagent_content
        if ctx is None or text is None:
            raise DelegationFailed("delegation.outside_turn", "error")
        task = task.strip()
        if not task:
            raise DelegationFailed("delegation.empty_task", "error")
        state, cancel = ctx
        self._subs += 1
        sub = _SubContext(f"sub{self._subs}", task, text.prompt, state.subagent_tools)
        journal = self._journal()
        started = time.monotonic()
        # `estimated`: chat mode, the context's figures not reconciled by `usage` (AD-4).
        figures = {"calls": 0, "context_tokens": 0, "kept_tokens": 0, "estimated": 0}
        outcome = _SubOutcome("error", message_text=Message("delegation.interrupted"))
        saved = self._save_main_state()  # AD-11 (N2): the main context's cache, kept
        # AD-11: every event of the sub-agent hangs on the step of `delegate`; the trigger
        # (model or user) is inherited.
        with scoped(
            context_id=sub.context_id,
            parent_step=current().step_id,
            call_id=None,
            step_id=None,
            brick="subagent",
            component="core.model_sub",
        ):
            journal.emit(
                "subagent_started",
                {"task": task, "tools": list(sub.tools), "phase_label": text.phase_label_text},
            )
            try:
                outcome = self._run_subagent(sub, state, cancel, figures)
            except Exception as exc:  # noqa: BLE001 - AD-16: the delegation fails, not the turn
                self._error(
                    Message("delegation.error.message"), exc, Message("delegation.error.effect")
                )
            finally:
                restore_ms = self._restore_main_state(saved, figures["calls"])
                done = outcome.status == "completed"
                failure = None if done else self._delegation_failure(outcome)
                # What the main context reads: the result, or the error the executor
                # reinjects in its place (« Erreur : … »).
                result = (
                    outcome.result if done else self._t("tools.error", text=self._text(failure))
                )
                result_tokens, estimated = self._count_tokens(result)
                # The saving: what the main context would have read (every tool reply that
                # stayed in the sub-agent, errors and refusals included) against the result it
                # reads instead; none when the delegation failed.
                kept = figures["kept_tokens"]
                journal.emit(
                    "subagent_ended",
                    {
                        "status": outcome.status,
                        "result": result,
                        "context_tokens": figures["context_tokens"],
                        "kept_tokens": kept,
                        "result_tokens": result_tokens,
                        "saved_tokens": max(0, kept - result_tokens) if done else 0,
                        "estimated": estimated,
                        "context_estimated": bool(figures["estimated"]),
                        "calls": figures["calls"],
                        "duration_ms": _ms(time.monotonic() - started),
                        "state_saved_bytes": saved.size_bytes if saved else None,
                        "state_restore_ms": restore_ms,
                    },
                )
        if failure is not None:
            raise failure
        return outcome.result

    def _save_main_state(self) -> EngineSnapshot | None:
        """AD-11 (N2), local mode: a copy of the engine's state before a sub-agent takes its
        cache; `None` when the engine cannot (a server) or the copy failed, then the main
        context is read again after the delegation (`_restore_main_state` says why)."""
        self._save_failed = False
        if self._cloud is not None:
            return None  # chat mode: the whole context is sent at every call anyway
        save = getattr(self._engine, "snapshot", None)
        try:
            return save() if save is not None else None
        except Exception:  # noqa: BLE001 - AD-16: the turn goes on, the reading is traced
            self._save_failed = True
            return None

    def _restore_main_state(self, saved: EngineSnapshot | None, calls: int) -> int | None:
        """AD-11 (N2): the main context's state put back once the sub-agent made calls;
        returns the restore's ms. Never raises: without a copy, or when the restore fails,
        the sub-agent's context stays in the cache and the next main call traces it
        (`prefix_not_reused`, cause `subagent`)."""
        if self._cloud is not None or not calls:
            return None  # chat mode, or the engine's cache untouched
        if saved is None:
            self._cache_evicted = "failed" if self._save_failed else "stateless"
            return None
        started = time.monotonic()
        try:
            restored = bool(self._engine.restore(saved))  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - AD-16: the main context is read again
            restored = False
        if not restored:
            self._cache_evicted = "failed"
            return None
        return _ms(time.monotonic() - started)

    @staticmethod
    def _delegation_failure(outcome: _SubOutcome) -> DelegationFailed:
        """The error a failed delegation reinjects (AD-11), with `delegate`'s status."""
        if outcome.status == "cancelled":
            return DelegationFailed("delegation.cancelled", "cancelled")
        status = outcome.status if outcome.status in ("limit", "overflow") else "error"
        return DelegationFailed("delegation.failed", status, reason=outcome.message_text)

    def _check_subagent_tools(self) -> None:
        """AD-19: a name of `[subagent] tools` that no tool of the tools brick bears is
        traced at load, not silently ignored."""
        if "subagent" not in self._bricks:
            return
        known = {
            n
            for n in self._registry.names
            if (spec := self._registry.get(n)).source != "harness" and not spec.is_mcp
        }
        unknown = [n for n in self.cfg.subagent_tools if n not in known]
        if unknown:
            self._error(
                Message("session.subagent.unknown_tools", tools=", ".join(unknown)),
                Message("session.subagent.known_tools", tools=", ".join(sorted(known))),
                Message("session.subagent.ignored"),
            )

    def _count_tokens(self, text: str, *, uncapped: bool = False) -> tuple[int, bool]:
        """AD-1: the tokens `text` takes in the main context: by the model's tokenizer
        locally; in chat mode (then `True`), the estimate scaled as `distribute` scales the
        main context's segments (AD-4): shrunk by a ratio below 1, never grown (a ratio above
        1 goes to the provider's segment), unless `uncapped` (lot B: a bound the provider's
        count must respect). Never raises: an estimate then."""
        estimate = config.estimate_tokens(text, self.cfg.chars_per_token)
        if self._cloud is not None or self._engine is None:
            ratio = self._ratios.get(self._cloud.id if self._cloud else "", self.cfg.estimate_ratio)
            return round(estimate * (ratio if uncapped else min(1.0, ratio))), True
        try:
            return len(self._engine.tokenize(text)), False
        except Exception:  # noqa: BLE001 - AD-16: `subagent_ended` is always emitted
            return estimate, True

    def _run_subagent(
        self,
        sub: _SubContext,
        state: TurnState,
        cancel: CancelToken,
        figures: dict[str, int],
    ) -> _SubOutcome:
        """AD-10, AD-11: the sub-agent's bounded loop, as the turn's (`_turn`) but in its own
        context: its calls on a counter of their own, the new attempts among them; the hooks
        `before_model_call`, `before_tool` and `after_tool`; no armed action, no loading.
        Fills `figures` (`calls`, `context_tokens`) as it goes."""
        journal = self._journal()
        turn_id, cid = current().turn_id or "", sub.context_id
        max_calls, max_retries = self.cfg.subagent_max_calls, self.cfg.tool_max_retries
        retries = step = 0
        steps: list[dict[str, Any]] = []
        previous: tuple[list[int], str] | None = None
        read_before: list[Segment] | None = None  # story 32: its previous call's segments
        stopped = _SubOutcome("cancelled", message_text=Message("delegation.stopped"))
        for n in range(1, max_calls + 1):
            call_id = f"{turn_id}.{cid}.c{n}"
            with scoped(call_id=call_id):
                decided = self._hook("before_model_call", state)
            if decided is not None and decided[1].decision == "block":
                label = self._hook_label(decided[0])
                return _SubOutcome(
                    "error", message_text=Message("delegation.hook_blocked", label=label)
                )
            step += 1
            with scoped(call_id=call_id, step_id=f"{turn_id}.{cid}.s{step}"):
                rendered, payload = self._render(state, "", call_id, steps, sub, read_before)
                read_before = rendered.segments
                journal.emit("context_rendered", payload)
                figures["context_tokens"] = payload["used"]
                figures["kept_tokens"] = _kind_tokens(payload, SegmentKind.TOOL_RESULT)
                figures["estimated"] = int(payload.get("usage_source") == "estimate")
                if previous is not None:
                    self._check_prefix(*previous, rendered.ids)
                if payload["overflow"]:
                    self._emit_overflow(payload, getattr(rendered, "raw_total", None))
                    return _SubOutcome(
                        "overflow",
                        message_text=Message(
                            "delegation.overflow",
                            used=self._num_lazy(payload["used"]),
                            usable=self._num_lazy(payload["usable"]),
                        ),
                    )
                figures["calls"] += 1
                out = self._call_model(
                    rendered, cancel, sub.tools, payload["reserve"], self._reasoning_on(state)
                )
            if out.reconciled is not None:  # chat mode: `usage` reconciled the figures (AD-4)
                figures["context_tokens"] = out.reconciled["used"]
                figures["kept_tokens"] = _kind_tokens(out.reconciled, SegmentKind.TOOL_RESULT)
                figures["estimated"] = 0
            if out.status == "cancelled":
                return stopped
            if out.status == "limit":  # `output_truncated` emitted in `sub{n}` (AD-9)
                return _SubOutcome(
                    "limit",
                    message_text=Message(
                        "delegation.cut", reserve=self._num_lazy(payload["reserve"])
                    ),
                )
            if out.status != "completed":  # a provider's refusal, traced in `sub{n}` (AD-16)
                return _SubOutcome(
                    "error", message_text=out.message_text or Message("delegation.refused")
                )
            if not out.calls and out.malformed is None:
                no_text = self._t("delegation.no_text")
                return _SubOutcome("completed", result=out.text.strip() or no_text)
            if isinstance(rendered, RenderedContext):
                previous = (rendered.ids, out.raw)

            reaction = "retry" if retries < max_retries and n < max_calls else "stop"
            failed = False
            with scoped(call_id=call_id, component="core.harness"):
                if out.malformed is not None:
                    failed = True
                    step += 1
                    with scoped(step_id=f"{turn_id}.{cid}.s{step}"):
                        error = self._tool_executor.reject(
                            out.raw, out.malformed.fragment, out.malformed.detail_text, reaction
                        )
                    steps.append(
                        {
                            "role": "assistant",
                            "content": out.answer or out.raw,
                            "tool_calls": [],
                            "component": "core.model_sub",
                        }
                        | ({"reasoning": out.reasoning} if out.reasoning and out.answer else {})
                    )
                    steps.append(
                        {
                            "role": "tool",
                            "name": None,
                            "content": error,
                            "component": "core.harness",
                            "brick": "subagent",
                        }
                    )
                else:
                    steps.append(self._assistant_step(out) | {"component": "core.model_sub"})
                    for call, call_ref in zip(out.calls, out.ids, strict=True):
                        step += 1
                        step_id = f"{turn_id}.{cid}.s{step}"
                        detail = self._tool_executor.check(call, sub.tools)
                        named = self._registry.get(call.name)
                        spec = named if detail is None else None
                        component = spec.component if spec else "core.harness"
                        brick = (
                            (named.brick or named.component.split(".")[0]) if named else "subagent"
                        )
                        blocker = None
                        if spec is None:
                            failed = True
                            with scoped(step_id=step_id, brick=brick, component=component):
                                result = self._tool_executor.reject(
                                    out.raw, call.source, detail or "", reaction
                                )
                        else:
                            ran = self._run_tool(call, spec, state, cancel, [], step_id, brick)
                            if ran is None:
                                return stopped
                            result, blocker = ran
                        steps.append(
                            self._reply_step(call_ref, call.name, result, component, brick, blocker)
                        )
            if failed:
                retries += 1
                if retries > max_retries:
                    self._emit_limit("sub_retries", retries)
                    return _SubOutcome(
                        "limit", message_text=Message("delegation.retries", retries=retries)
                    )
            if cancel.cancelled:
                return stopped
        self._emit_limit("sub_calls", max_calls)
        return _SubOutcome("limit", message_text=Message("delegation.calls", max=max_calls))

    @staticmethod
    def _assistant_step(out: _ModelOutput) -> dict[str, Any]:
        """The assistant step of an output with tool calls: each call with its session id,
        its arguments and their JSON, as emitted in chat mode, else serialized once (AD-4);
        in chat mode, a call's `extra_content` (`extra`) and the entry it goes back to
        (`extra_for`)."""
        calls = []
        for j, (c, call_ref) in enumerate(zip(out.calls, out.ids, strict=True)):
            call: dict[str, Any] = {
                "id": call_ref,
                "name": c.name,
                "arguments": c.arguments,
                "arguments_json": (
                    out.arguments[j]
                    if out.arguments
                    else json.dumps(c.arguments, ensure_ascii=False)
                ),
            }
            extra = out.extras[j] if j < len(out.extras) else None
            if extra:
                call |= {"extra": {"extra_content": extra}, "extra_for": out.extra_for}
            calls.append(call)
        return {"role": "assistant", "content": out.text, "tool_calls": calls} | (
            {"reasoning": out.reasoning} if out.reasoning else {}
        )

    @staticmethod
    def _reply_step(
        call_ref: str | None,
        name: str,
        result: str,
        component: str,
        brick: str,
        blocker: str | None,
        spec: ToolSpec | None = None,
    ) -> dict[str, Any]:
        """A tool's reply step (AD-4): a hook's refusal is the hook's text; `delegate`'s reply
        is the sub-agent's result (`subagent_result`), even a failure (AD-11). `spec`: the tool
        that ran; its own output (native, network, MCP, never a meta-tool's) is marked
        `tool_output`, what the compression may take (story 20, AD-22), decided here once."""
        step = {
            "role": "tool",
            "id": call_ref,
            "name": name,
            "content": result,
            "component": component,
            "brick": brick,
        }
        if blocker is None and spec is not None and spec.source != "harness":
            step["tool_output"] = True
        if blocker is not None:
            return step | {"component": f"hooks.{blocker}", "brick": "hooks"}
        if name == DELEGATE and component == "subagent.agent":  # it ran (not refused)
            kind = SegmentKind.SUBAGENT_RESULT
            return step | {"kind": kind, "brick": "subagent", "component": "subagent.agent"}
        return step

    def _load_tool_doc_spec(self) -> ToolSpec:
        assert self._mcp_content is not None
        text = self._mcp_content.load_tool_doc
        return ToolSpec(
            name=LOAD_TOOL_DOC,
            run=self._load_tool_doc,
            params={"tool": "string"},
            component="core.harness",
            source="harness",
            brick="mcp",
            label_text=text.label_text,
            description=text.intro,  # the lines of the loadable tools follow, per turn
            schema={
                "type": "object",
                "properties": {"tool": {"type": "string", "description": text.tool}},
                "required": ["tool"],
            },
            required=("tool",),
        )

    def _load_tool_doc(self, tool: str) -> ToolReply | str:
        """AD-25: reads the registry, writes nothing; the session applies the effect (AD-23)."""
        available = self._mcp_tool_names()
        with self._lock:
            loaded = set(self._loaded_docs)
        if tool in available and tool in loaded:
            return self._t("mcp.doc.already_loaded", tool=tool)
        if tool not in available:
            loadable = ", ".join(n for n in available if n not in loaded)
            raise ToolError(
                "mcp.doc.unknown", tool=tool, loadable=loadable or Message("tools.check.none")
            )
        definition = json.dumps(self._registry.definition(tool), ensure_ascii=False)
        return ToolReply(definition, (ToolDocLoaded(tool=tool),))

    def _load_skill(self, skill: str) -> ToolReply | str:
        """AD-25: reads the skills, writes nothing; the session applies the effect (AD-23)."""
        with self._lock:
            enabled, loaded = set(self._skills_enabled), set(self._loaded_skills)
        if skill in enabled and skill in loaded:
            return self._t("skills.already_loaded", skill=skill)
        text = self._skill_text(skill)
        if skill not in enabled or text is None:
            loadable = [s for s in self._skill_ids() if s in enabled and s not in loaded]
            raise ToolError(
                "skills.unknown",
                skill=skill,
                loadable=", ".join(loadable) or Message("tools.check.none"),
            )
        return ToolReply(text.body, (SkillLoaded(skill_id=skill),))

    def _memory_unavailable_fr(self) -> str | None:
        """Why the memory can be neither read nor edited: its texts in `content/` are invalid,
        or `memory.json` is unreadable (the card's reason, the drawer's refusal)."""
        with self._lock:
            return self._content_errors.get("global_memory") or self._memory_error

    def _remember(self, text: str) -> ToolReply | str:
        """AD-25: reads the memory, writes nothing; the session applies the effect (AD-23).
        A refusal (empty, too long, full) is reinjected; a duplicate adds nothing."""
        try:
            text = memory_file.check_text(text)
        except memory_file.TextRefused as exc:
            raise ToolError(exc.message) from None
        if self._memory_unavailable_fr() is not None:  # the brick is unavailable then
            raise ToolError("memory.unreadable")
        with self._lock:
            entries = list(self._memory)
        if any(memory_file.same_text(e.text, text) for e in entries):
            return self._t("memory.duplicate", text=text)
        if len(entries) >= memory_file.MAX_ENTRIES:
            raise ToolError("memory.full", max=memory_file.MAX_ENTRIES)
        write = MemoryWrite(op="add", entry_id=memory_file.new_entry_id(), text=text)
        return ToolReply(self._t("memory.remembered", text=text), (write,))

    def _apply_now(self, effects: tuple[Effect, ...]) -> tuple[tuple[Effect, ...], str | None]:
        """The effects the executor applies before `tool_ended` (AD-23), so the trace never
        shows a success the file did not get: the memory writes of `remember`, by the model
        or forced (`trigger`). Returns the other effects, and the failure in French."""
        writes = [e for e in effects if isinstance(e, MemoryWrite)]
        others = tuple(e for e in effects if not isinstance(e, MemoryWrite))
        if not writes:
            return others, None
        source = "user" if current().trigger == "user" else "model"
        return others, self._apply_memory(writes, source)

    def _apply_memory(self, writes: list[MemoryWrite], source: memory_file.Source) -> str | None:
        """AD-23, the single applier of `MemoryWrite`: applied in order on a copy, the file
        written once, then one `effect_applied` per effect and one `memory_changed`, all
        under `_memory_lock` so no snapshot is emitted out of order. Returns the French
        failure (memory unchanged)."""
        with self._memory_lock:
            with self._lock:
                entries = list(self._memory)
            try:
                updated = memory_file.apply_writes(entries, writes, source, memory_file.now())
            except (KeyError, ValueError) as exc:  # changed meanwhile, or beyond its limits
                self._error(
                    Message("memory.error.not_modified"), exc, Message("memory.error.unchanged")
                )
                return self._t("memory.not_modified")
            try:
                memory_file.write_memory(config.memory_path(), updated)
            except OSError as exc:
                self._error(
                    Message("memory.error.not_written"), exc, Message("memory.error.unchanged")
                )
                return self._t("memory.not_written")
            with self._lock:
                self._memory = updated
                self._memory_error = None  # written: readable again (reset, H5)
            with scoped(brick="global_memory", component=MEMORY):
                for write in writes:
                    self._journal().emit(
                        "effect_applied",
                        {
                            "effect": "memory_write",
                            "op": write.op,
                            "entry_id": write.entry_id,
                            "text": write.text,
                        },
                    )
            self._emit_memory()
        return None

    def edit_memory(self, op: str, entry_id: str | None = None, text: str | None = None) -> None:
        """Class (b), the edit drawer (AD-23), `trigger = user`: `replace` or `delete` one
        entry, or `clear` them all (one `delete` each). Raises `SendRefused` outside `idle`
        (held until the write ends) or while the memory is unavailable, `KeyError` for an
        unknown entry, `ValueError` for an invalid or duplicate text, and `OSError` when the
        file could not be written. A replace by the same text writes nothing."""
        with self._memory_lock:
            with self._lock:
                if self.state != "idle":
                    raise SendRefused(self._refusal_reason())
                entries = list(self._memory)
            unavailable = self._memory_unavailable_fr()
            if unavailable is not None:
                raise SendRefused(unavailable)
            if op == "clear":
                writes = [MemoryWrite(op="delete", entry_id=e.id, text=e.text) for e in entries]
            else:
                entry = next((e for e in entries if e.id == entry_id), None)
                if entry is None:
                    raise KeyError(entry_id)
                if op == "replace":
                    text = memory_file.check_text(text)
                    if text == entry.text:
                        return  # nothing changed: nothing written
                    if any(memory_file.same_text(e.text, text) for e in entries if e != entry):
                        raise ValueRefused("session.memory.duplicate", text=text)
                    writes = [MemoryWrite(op="replace", entry_id=entry.id, text=text)]
                elif op == "delete":
                    writes = [MemoryWrite(op="delete", entry_id=entry.id, text=entry.text)]
                else:
                    raise ValueRefused("session.memory.unknown_op", op=op)
            if not writes:
                return
            with scoped(trigger="user"):
                if self._apply_memory(writes, "user") is not None:
                    raise OSError(self._t("session.memory.not_written"))
        self._executor.submit(self._emit_preview)

    def _restore_memory(self) -> None:
        """FR-39 (CAP-41, H6): one `delete` per entry, then one `add` per demonstration
        entry, by the single applier (`trigger = user`: the reset is the user's); nothing
        when the memory already is the demonstration. An unreadable memory becomes available
        once written."""
        if self._memory_content is None:
            return
        demo = self._memory_content.demo
        with self._memory_lock:
            with self._lock:
                entries, error_text = list(self._memory), self._memory_error
            if error_text is None and memory_file.is_demo(entries, demo):
                return
            writes = [MemoryWrite(op="delete", entry_id=e.id, text=e.text) for e in entries]
            writes += [
                MemoryWrite(op="add", entry_id=f"demo{i}", text=text)
                for i, text in enumerate(demo, start=1)
            ]
            with scoped(trigger="user"):
                self._apply_memory(writes, "demo")

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """The asyncio loop MCP clients live on (FastAPI's); set once, before any intention."""
        self._loop = loop

    def set_mcp_server(self, server_id: str, enabled: bool) -> None:
        """Class (a): an MCP server sub-option. Enabled with the brick wanted, the server is
        contacted now; disabled, its connection closes. `KeyError` if unknown."""
        if server_id not in self._mcp_servers:
            raise KeyError(server_id)
        with self._lock:
            if (server_id in self._mcp_enabled) == enabled:
                return
            if enabled:
                self._mcp_enabled.add(server_id)
            else:
                self._mcp_enabled.discard(server_id)
            brick_wanted = "mcp" in self._wanted
        if brick_wanted:
            if enabled:
                self._mcp_connect(server_id)
            else:
                self._mcp_disconnect(server_id)
        self._emit_bricks()
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    def _mcp_connect(self, server_id: str) -> None:
        """Start contacting `server_id` on the loop; `_mcp_connected` applies the outcome."""
        server = self._mcp_servers[server_id]
        with self._lock:
            if server_id in self._mcp_conns:
                return
            self._mcp_state[server_id] = ("not_contacted", None)
            loop = self._loop
            conn = (
                McpConnection(
                    server,
                    loop,
                    connect_timeout=self.cfg.mcp_connect_timeout_s,
                    call_timeout=self.cfg.mcp_call_timeout_s,
                    language=self._language,
                )
                if loop is not None
                else None
            )
            if conn is not None:
                self._mcp_conns[server_id] = conn
        journal = self._journal()
        with scoped(brick="mcp", component=server.component):
            journal.emit(
                "mcp_connect_started",
                {
                    "server": server_id,
                    "phase_label": Message(
                        "session.mcp.connecting", server=self._mcp_label(server_id)
                    ),
                },
            )
        started = time.monotonic()
        if conn is None:
            reason = Message("session.mcp.no_loop")
            self._executor.submit(
                self._mcp_apply, server_id, None, started, started, None, RuntimeError(reason)
            )
            return
        future = asyncio.run_coroutine_threadsafe(conn.start(), conn.loop)

        def done(_: Any) -> None:
            ended = time.monotonic()  # not counting any wait behind a turn on the worker
            try:
                self._executor.submit(self._mcp_connected, server_id, conn, started, ended, future)
            except RuntimeError:  # the session is closing
                pass

        future.add_done_callback(done)

    def _mcp_connected(self, server_id, conn, started, ended, future) -> None:  # noqa: ANN001
        """On the worker: the connection's outcome becomes a state, tools and events."""
        try:
            tools, error = future.result(), None
        except BaseException as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            tools, error = None, exc
        self._mcp_apply(server_id, conn, started, ended, tools, error)

    def _mcp_apply(self, server_id, conn, started, ended, tools, error) -> None:  # noqa: ANN001
        server = self._mcp_servers[server_id]
        with self._lock:
            current_conn = self._mcp_conns.get(server_id)
        names: list[str] = []
        error_text = None
        if error is not None:
            error_text = (
                (error.args[0] if error.args and isinstance(error.args[0], Message) else str(error))
                if conn is None
                else describe_error(error, self.cfg.mcp_connect_timeout_s)
            )
        if conn is not current_conn:  # disabled or closed meanwhile: nothing to apply
            error_text = Message("session.mcp.abandoned")
        elif error_text is not None:
            with self._lock:
                self._mcp_conns.pop(server_id, None)
                self._mcp_state[server_id] = ("unavailable", error_text)
        else:
            specs = [self._mcp_spec(server, conn, tool) for tool in tools]
            self._registry.remove(f"{server_id}__")
            names = self._registry.add(specs)
            with self._lock:
                self._mcp_state[server_id] = ("available", None)
        with scoped(brick="mcp", component=server.component):
            self._journal().emit(
                "mcp_connect_ended",
                {
                    "server": server_id,
                    "status": "ok" if error_text is None else "error",
                    "tools": names,
                    "error_text": error_text,
                    "duration_ms": _ms(ended - started),
                },
            )
        self._emit_architecture()
        self._emit_bricks()
        self._emit_preview()

    def _mcp_spec(self, server, conn: McpConnection, tool) -> ToolSpec:  # noqa: ANN001
        """A listed MCP tool as a registry entry, in documentation complète (AD-14)."""
        schema = dict(tool.input_schema or {})
        properties = schema.get("properties") or {}
        params = {  # a boolean schema (`true`) or an untyped one: any value
            arg: kind
            if isinstance(prop, dict) and isinstance(kind := prop.get("type"), str)
            else ""
            for arg, prop in properties.items()
        }
        name = tool.name

        def preview(**arguments: Any) -> dict[str, str]:
            """What the client posts, but the JSON-RPC `id` it assigns when sending (the
            client adds an empty `_meta`, so it is shown too)."""
            params = {"name": name, "arguments": arguments, "_meta": {}}
            body = {"jsonrpc": "2.0", "method": "tools/call", "params": params}
            body_text = json.dumps(body, ensure_ascii=False)
            return {"method": "POST", "url": server.url, "body": body_text}

        return ToolSpec(
            name=name,
            run=lambda **arguments: conn.call(name, arguments, self._language),
            preview=preview if server.network else None,
            params=params,
            component=server.component,
            source=server.source,
            hosting="network_service" if server.network else "local_process",
            network=server.network,
            description=tool.description or "",
            schema=schema,
            required=tuple(schema.get("required") or ()),
        )

    def _mcp_disconnect(self, server_id: str) -> None:
        """Close the connection (the local process stops); tools leave from the next turn."""
        with self._lock:
            conn = self._mcp_conns.pop(server_id, None)
            self._mcp_state.pop(server_id, None)  # drawn again as « non contacté »
        if conn is not None:
            conn.close(wait=False)
        self._executor.submit(self._registry.remove, f"{server_id}__")

    def _mcp_failed(self, server_id: str, reason_text: str | None) -> None:
        """On the worker: a call could not reach its server, which becomes `unavailable`."""
        with self._lock:
            conn = self._mcp_conns.pop(server_id, None)
            if conn is None:  # disabled during the call: it stays « non contacté »
                return
            self._mcp_state[server_id] = ("unavailable", reason_text)
        conn.close(wait=False)
        self._registry.remove(f"{server_id}__")

    async def aclose_mcp(self) -> None:
        """On the loop, at shutdown: close every connection before `close` (AD-21)."""
        with self._lock:
            conns = list(self._mcp_conns.values())
            self._mcp_conns.clear()
            lab, self._mcp_lab_conn = self._mcp_lab_conn, None  # the MCP workshop's (story 6)
        conns += [lab] if lab is not None else []
        await asyncio.gather(*(conn.aclose() for conn in conns), return_exceptions=True)

    def save_system_prompt(self, text: str | None) -> dict[str, Any]:
        """Class (a): `None` (or a blank text) restores the default. Returns the saved state."""
        text = (text or "").strip() or None
        with self._lock:
            self._custom_prompt = text
        self._emit_bricks()
        self._executor.submit(self._emit_preview)
        saved = text if text is not None else self._default_prompt
        return {"text": saved, "is_default": saved == self._default_prompt}

    def clear_conversation(self) -> None:
        """Class (b): empties the active branch; bricks and system prompt are untouched."""
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            self._history.clear()
            self._loaded_docs.clear()  # AD-25: the documentations leave with the conversation
            self._loaded_skills.clear()  # and so do the skills
            self._last = None  # nothing left to replay (story 9b)
            self._memory_snapshot = None  # N1: the next conversation reads the memory again
            self._cache_cause = "reset"
        self._journal().emit("conversation_cleared", {})
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    # ---------- languages (1/5, AD-19) ----------

    def _conversation_started(self) -> bool:
        """Under `_lock`: something of the conversation is in the context (its exchanges,
        a documentation or a skill loaded, the global memory it read): no change of language."""
        return bool(
            self._history
            or self._loaded_docs
            or self._loaded_skills
            or self._memory_snapshot is not None
        )

    @property
    def language(self) -> str:
        """The session's language (languages 3/5): what every content loader is given."""
        return self._language

    def language_state(self) -> dict[str, Any]:
        """`/api/state`: the language, the languages offered (each written in itself), and
        whether the conversation locks the choice."""
        with self._lock:
            language, locked = self._language, self._conversation_started()
        return {
            "language": language,
            "languages": [
                {"id": lang, "label": config.LANGUAGE_LABELS[lang]} for lang in config.LANGUAGES
            ],
            "language_locked": locked,
        }

    def ui_texts(self) -> dict[str, Any]:
        """`GET /api/ui_texts` (languages 2/5): the interface's texts in the session's
        language, each key a translation lacks in French; an invalid translation is traced
        (`harness_error`), then French answers. A French file that cannot be read gives no
        texts, traced: the page stays in the French of its HTML."""
        with self._lock:
            language, texts = self._language, self._ui_texts
        if texts is None:
            try:
                texts = self._localized(load_ui_texts)
            except Exception as exc:  # noqa: BLE001 - AD-19: traced, never fatal
                self._error(
                    Message("session.content.ui_invalid.message"),
                    exc,
                    Message("session.content.ui_invalid.effect"),
                )
                return {"language": language, "texts": {}}
            with self._lock:
                if self._language == language:
                    self._ui_texts = texts
        return {"language": language, "texts": texts}

    def set_language(self, language: str) -> None:
        """Class (b): saves `language` in `settings.json`, then reads again every text sent
        to the model in it. `SendRefused` outside `idle` or once the conversation is not
        empty, with the reason in French (and in the current language)."""
        language = config.as_language(language)
        with self._memory_lock:  # no turn starts before the texts are read again
            with self._lock:
                if self.state != "idle":
                    raise SendRefused(self._refusal_reason())
                if self._conversation_started():
                    raise SendRefused(_language_locked_reason(self._language))
                if language == self._language:
                    return
                old_default = self._default_prompt
                old_demo = list(self._memory_content.demo) if self._memory_content else None
            try:
                config.save_setting("language", language)
            except OSError as exc:
                raise SendRefused(
                    Message(
                        "session.language.not_saved",
                        path=config.settings_path(),
                        cause=exc.strerror or exc,
                    )
                ) from None
            with self._lock:
                self._language = language
                self._ui_texts = None  # never the former language's under the new code
                if hasattr(self._engine, "language"):  # a served engine's own traces
                    self._engine.language = language
            config.clear_content_caches()
            self._load_messages()  # languages (5/5): traced once, in the new language
            self._reload_texts()
            if "rag" in self._bricks:  # languages (4/5): the new language's index and corpus
                self._rag_refresh()
            with self._lock:  # what the last `send` froze: the new default is no change
                if self._sent[1] == old_default:
                    self._sent = (self._sent[0], self._default_prompt, *self._sent[2:])
                restart = [s for s in self._mcp_conns if self._mcp_servers[s].url is None]
            self._demo_memory_in(old_demo)
        self._journal().emit("language_changed", {"language": language})
        self._emit_state()  # `language` in the session's state
        self._mcp_lab_drop(wait=False)  # story 6 of 2026-09-30: reconnected in the language
        for server_id in restart:  # the local server describes its tools in the language
            self._mcp_disconnect(server_id)
            self._mcp_connect(server_id)
        self._emit_bricks()
        self._load_scenarios()  # `scenario_changed`
        self._emit_memory()
        self._emit_architecture()
        if "rag" in self._bricks:
            self._executor.submit(self._rag_follow_language)
        self._executor.submit(self._emit_preview)

    def _rag_follow_language(self) -> None:
        """Languages (4/5), on the worker (after a load in progress, before any turn): the
        embedding model and its connection to the former language's index are released,
        then loaded again on the new language's index when the brick is wanted and its
        index is there (else the card says why, and offers « Construire l'index »)."""
        with self._lock:
            loaded = self._embedder is not None
        if loaded:
            self._release_embedder()
        self._request_rag_sync()
        self._emit_bricks()
        self._emit_architecture()

    def _reload_texts(self) -> None:
        """Every text read from `content/` at launch, read again in the new language. A
        file that cannot be read in any language keeps the text read before (its error was
        traced at launch)."""

        def again(load: Callable[..., Any], *args: Any) -> Any:
            try:
                return self._localized(load, *args)
            except Exception as exc:  # noqa: BLE001 - AD-19: traced, the text read before stays
                self._error(
                    Message("session.language.both_invalid.message", lang=self._language),
                    exc,
                    Message("session.language.both_invalid.effect"),
                )
                return None

        for brick_id in self._bricks:
            if (brick := again(load_brick_content, brick_id)) is not None:
                self._content[brick_id] = brick
        loaders: dict[str, tuple[str, Callable[..., Any], tuple[Any, ...]]] = {
            "tools": ("_tools_content", load_tools_content, ()),
            "mcp": ("_mcp_content", load_mcp_content, ()),
            "skills": ("_skills_content", load_skills_content, (self._skill_ids(),)),
            "hooks": ("_hooks_content", load_hooks_content, (self._hook_ids(),)),
            "subagent": ("_subagent_content", load_subagent_content, ()),
            "compression": ("_compression_content", load_compression_content, ()),
            "global_memory": ("_memory_content", memory_file.load_memory_content, ()),
            "rag": ("_rag_content", load_rag_content, ()),
            "system_prompt": ("_default_prompt", load_default_system_prompt, ()),
        }
        for brick_id, (attribute, load, args) in loaders.items():
            if brick_id in self._bricks and (text := again(load, *args)) is not None:
                setattr(self, attribute, text)
        # Languages (2/5): the interface's texts, in the new language for the reloaded page
        # (`None`, read again at its request, when neither file can be read).
        self._ui_texts = again(load_ui_texts)
        # Languages (3/5): what the session keeps of a loaded model, in the new language (the
        # programme is read again by `set_language`, `read_file` reads `_language` at each call).
        if self._cloud_content is not None and (cloud := again(load_cloud_content)) is not None:
            self._cloud_content = cloud
        if self._labels is not None and (labels := again(load_labels)) is not None:
            self._labels = labels

        # The same tools, described again: only values change, never the registry's names.
        self._registry.content = self._tools_content
        self._registry.replace(self._harness_tools())

    def _demo_memory_in(self, old_demo: list[str] | None) -> None:
        """Under `_memory_lock`: a global memory that is the demonstration in the former
        language becomes the new language's; one the user or the model wrote stays as is."""
        content = self._memory_content
        if old_demo is None or content is None or content.demo == old_demo:
            return
        with self._lock:
            entries, error_text = list(self._memory), self._memory_error
        if error_text is not None or not memory_file.is_demo(entries, old_demo):
            return
        if config.memory_path().exists():
            self._restore_memory()  # the file is written again, as by « Réinitialiser »
            return
        with self._lock:  # H5: the demonstration, still not written until a change
            self._memory = memory_file.demo_entries(content.demo, memory_file.now())

    # ---------- scenarios and reset (story 10, AD-19, FR-38, FR-39) ----------

    def _load_scenarios(self) -> None:
        """AD-19: an invalid file gives `harness_error` and an empty programme, never a crash."""
        known = {
            "bricks": set(self._bricks),
            "tools": {
                n
                for n in self._registry.names
                if (spec := self._registry.get(n)).source != "harness" and not spec.is_mcp
            },
            "mcp_servers": set(self._mcp_servers),
            "skills": set(self._skill_ids()),
            "hooks": set(self._hook_ids()),
        }
        try:
            self._scenarios = self._localized(load_scenarios, known)
        except Exception as exc:  # noqa: BLE001
            self._error(
                Message("session.content.scenarios_invalid.message"),
                exc,
                Message("session.content.scenarios_invalid.effect"),
            )
        self._emit_scenario()

    def _fill(self, text: str) -> str:
        """Story 16: a French text with the reranking's figures, `{candidates}` and `{keep}`
        (`[rag] rerank_candidates`, `[rag] top_k`), never written in hard in `content/`."""
        return text.replace("{candidates}", str(self.cfg.rag_rerank_candidates)).replace(
            "{keep}", str(self.cfg.rag_top_k)
        )

    def _explanation(self, content: BrickContent | None) -> list[str | list[str]]:
        if content is None:
            return []
        return [
            [self._fill(t) for t in block] if isinstance(block, list) else self._fill(block)
            for block in content.explanation_text
        ]

    def _emit_scenario(self, *, refresh: bool = False) -> None:
        """`refresh` (lot E, E5): the same scenario, its unavailable bricks read again after a
        model load; not a launch."""
        program = self._scenarios.payload(self._fill) if self._scenarios else EMPTY_PROGRAM
        with self._lock:
            active = self._active_scenario
        self._journal().emit(
            "scenario_changed",
            {
                "program": program,
                "active": active,
                "unavailable": self._scenario_unavailable(),
                "refresh": refresh,
            },
        )

    def _scenario_unavailable(self) -> list[dict[str, str]]:
        """Lot E (E5): the active scenario's bricks the active model cannot offer (a
        capability it lacks), each with its reason: said at the launch, and again after a
        model change. Empty with no scenario, or no model active (the composer says why)."""
        with self._lock:
            active = self._active_scenario
        scenario = self._scenarios.scenarios.get(active) if self._scenarios and active else None
        if scenario is None or self._caps is None:
            return []
        unavailable = []
        for brick_id in scenario.bricks:
            reason = self._capability_reason(brick_id)
            if reason is not None:
                unavailable.append(
                    {"brick": brick_id, "label_text": self._label(brick_id), "reason_text": reason}
                )
        return unavailable

    def launch_scenario(self, scenario_id: str) -> None:
        """Class (b): empties the conversation, applies the launch configuration, then the
        scenario's. `KeyError` if unknown, `SendRefused` outside `idle`."""
        scenario = self._scenarios.scenarios.get(scenario_id) if self._scenarios else None
        if scenario is None:
            raise KeyError(scenario_id)

        def apply() -> None:
            self._wanted = set(scenario.bricks)
            if scenario.tools is not None:
                self._tools_enabled = set(scenario.tools)
            if scenario.mcp_servers is not None:
                self._mcp_enabled = set(scenario.mcp_servers)
            if scenario.skills is not None:
                self._skills_enabled = set(scenario.skills)
            if scenario.hooks is not None:
                self._hooks_enabled = set(scenario.hooks)
            self._mcp_lazy = scenario.mcp_lazy
            self._rag_rerank = scenario.rag_rerank  # story 16

        self._reconfigure(scenario_id, apply, restore_memory=scenario.restore_memory)

    def reset(self) -> None:
        """Class (b): back to the launch state: bare LLM, no turn, no scenario."""
        self._reconfigure(None, lambda: None)

    def _reconfigure(
        self, scenario_id: str | None, apply: Callable[[], None], *, restore_memory: bool = False
    ) -> None:
        """One `bricks_changed`, one `architecture_changed`, one preview; MCP servers
        connect or close on the difference only (AD-15). The reset, and a scenario that
        declares `restore_memory` (story 21), restore the demonstration memory."""
        with self._memory_lock:  # no turn starts before the memory is restored
            with self._lock:
                if self.state != "idle":
                    raise SendRefused(self._refusal_reason())
                before = set(self._mcp_enabled) if "mcp" in self._wanted else set()
                self._history.clear()
                self._loaded_docs.clear()
                self._loaded_skills.clear()
                self._last = None  # nothing left to replay (story 9b)
                self._memory_snapshot = None  # N1: the next conversation reads it again
                self._cache_cause = "reset"
                self._armed.clear()
                self._apply_launch_config()
                apply()
                after = set(self._mcp_enabled) if "mcp" in self._wanted else set()
                self._active_scenario = scenario_id
            journal = self._journal()
            journal.emit("conversation_cleared" if scenario_id else "harness_reset", {})
            if scenario_id is None or restore_memory:  # FR-39; story 21, a module's start
                self._restore_memory()
        self._emit_armed()
        self._emit_scenario()
        for server_id in sorted(before - after):
            self._mcp_disconnect(server_id)
        for server_id in sorted(after - before):
            self._mcp_connect(server_id)
        self._request_rag_sync()  # story 15: loaded or released as the brick is now wanted
        self._request_compression_sync()  # story 20: the same for Headroom
        self._emit_bricks()
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    def _refusal_reason(self) -> str:
        if self.state == "turn":
            return Message("session.refused.turn")
        if self.reason_text:
            return self.reason_text
        return Message("session.refused.no_model")

    def stop(self) -> bool:
        """Intention class (c): arms the turn's `CancelToken`; no effect outside a turn. A
        pending human validation is resolved as `cancelled`. Story 15: stops a download or an
        index build. Lot E (E4): stops a model load at its next checkpoint."""
        if self._mcp_lab_stop():  # story 6 of 2026-09-30: the MCP workshop's exchange
            return True
        with self._lock:
            if self.state in ("download", "index_build") and self._download_cancel is not None:
                self._download_cancel.cancel()
                return True
            if self.state == "model_load" and self._load_cancel is not None:
                self._load_cancel.cancel()
                return True
            if (
                self.state not in ("turn", "awaiting_human", "llm_lab", "rag_lab")
                or self._cancel is None
            ):
                return False
            self._cancel.cancel()
            approval = self._approval
            if approval is None or approval.decision is not None:
                return True
            approval.decision = "cancelled"
        approval.answered.set()
        return True

    # ---------- model download and index build (story 15, AD-15, AD-21) ----------

    def download_model(self, target: str) -> str:
        """Class (b): downloads the embedding model's missing files, on a thread of its own,
        in the `download` state (« Arrêter » stops it). `KeyError` for an unknown target,
        `SendRefused` outside `idle`, or when there is nothing to download (the files being
        there, the index and the files are read again)."""
        if target not in (RAG_TARGET, RERANK_TARGET) or "rag" not in self._bricks:
            raise KeyError(target)
        rerank = target == RERANK_TARGET  # story 16: the reranking model
        model = self._rerank_model if rerank else self._rag_model
        noun = Message(
            "session.rag.model_noun.reranking" if rerank else "session.rag.model_noun.embedding"
        )
        if model is None:
            raise SendRefused(
                (self._rerank_config_error if rerank else self._content_errors.get("rag"))
                or Message("session.download.no_model", noun=noun)
            )
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
        dest = config.models_dir()
        missing = download_module.missing_files(model.files, dest)
        if not missing:  # e.g. copied by hand meanwhile: the card catches up now
            self._rag_caught_up()
            raise SendRefused(Message("session.download.nothing", noun=noun, dest=dest))
        total = sum(f.size for f in missing)
        cancel = download_module.StopToken()
        previous = self._enter_rag_job("download", self._download_fr(0, total, noun), cancel)
        threading.Thread(
            target=self._run_download,
            args=(missing, dest, cancel, previous),
            kwargs={"noun": noun, "component": RAG_RERANKER if rerank else "rag.retriever"},
            name="wavestack-download",
            daemon=True,
        ).start()
        return self._download_fr(0, total, noun)

    def _enter_rag_job(self, state: str, reason_text: str, cancel: CancelToken) -> str | None:
        """`download` or `index_build`, switched under the lock from `idle` (class b). Returns
        the reason `idle` had (e.g. no model loaded), given back afterwards."""
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            previous = self.reason_text
            self.state, self.reason_text = state, reason_text
            self._download_cancel = cancel
        self._emit_state()
        return previous

    def _rag_caught_up(self) -> None:
        """The index and the files read again, the card, the schema and the preview."""
        self._rag_refresh()
        self._request_rag_sync()
        self._emit_bricks()
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

    @staticmethod
    def _download_fr(done: int, total: int, noun: str | None = None) -> str:
        percent = int(done * 100 / total) if total else 100
        return Message(
            "session.download.progress",
            noun=noun or Message("session.rag.model_noun.embedding"),
            percent=percent,
            done=Lazy(lambda lang: number(round(done / 1_000_000), lang)),
            total=Lazy(lambda lang: number(round(total / 1_000_000), lang)),
        )

    def _throttled(self, state: str, text: Callable[[int, int], str]) -> Callable[[int, int], None]:
        """A progress callback: `session_state.reason_text` at most once a second."""
        last = time.monotonic()

        def progress(done: int, total: int) -> None:
            nonlocal last
            if time.monotonic() - last < 1.0:
                return
            last = time.monotonic()
            with self._lock:
                if self.state != state:
                    return
                self.reason_text = text(done, total)
            self._emit_state()

        return progress

    def _run_download(
        self,
        files: list[ModelFile],
        dest: Path,
        cancel: CancelToken,
        previous: str | None,
        *,
        noun: str | None = None,
        component: str = "rag.retriever",
    ) -> None:
        """The download thread, then back to `idle`; the index and the files are read again,
        and the model loads if wanted. Each file's sha256 is traced (to pin it in
        [rag.embedding])."""
        failed: str | None = None
        stopped = False
        digests: dict[str, str] = {}
        try:
            with scoped(brick="rag", component=component, origin="download"):
                digests = download_module.download_files(
                    files,
                    dest,
                    cancel,
                    self._throttled("download", lambda d, t: self._download_fr(d, t, noun)),
                    transport=self._download_transport,
                )
        except download_module.DownloadError as exc:
            failed, stopped = exc.reason_text, exc.cancelled
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            failed = f"{type(exc).__name__}: {exc}"
        noun = noun or Message("session.rag.model_noun.embedding")
        with self._lock:
            self._download_cancel = None
        with scoped(brick="rag", component=component):  # the card shows it (AD-1)
            if failed is not None:
                names = ", ".join(PurePosixPath(f.path).name for f in files)
                folder = dest / PurePosixPath(files[0].path).parent
                self._error(
                    Message(
                        "session.download.stopped" if stopped else "session.download.failed",
                        noun=noun,
                    ),
                    failed,
                    Message("session.download.by_hand", folder=folder, names=names),
                )
            else:
                self._journal().emit(
                    "effect_applied",
                    {
                        "effect": "model_download",
                        "lines": [f"{dest / path} · sha256 {sha}" for path, sha in digests.items()],
                    },
                )
        self._set_state("idle", previous)
        try:
            self._rag_caught_up()
        except RuntimeError:  # the session is closing: nothing left to show
            pass

    def build_rag_index(self) -> str:
        """Class (b): builds the RAG index from the corpus shipped, with the embedding model
        on the workstation (the code of scripts/build_rag_index.py), on a thread of its own,
        in the `index_build` state (« Arrêter » stops it). `SendRefused` outside `idle`, or
        when the card offers no build (model missing, sqlite-vec, index up to date)."""
        if "rag" not in self._bricks:
            raise KeyError("rag")
        model, content = self._rag_model, self._rag_content
        if model is None or content is None:
            raise SendRefused(self._content_errors.get("rag") or Message("session.build.no_model"))
        self._rag_refresh()  # the files may have been copied, the corpus edited
        if self._rag_offers()["build_index"] is None:
            with self._lock:
                kind, missing = self._rag_index_kind, bool(self._rag_missing)
            self._rag_caught_up()
            if missing:
                raise SendRefused(Message("session.build.model_missing"))
            if kind == "vec":
                raise SendRefused(self._rag_index_error or Message("session.build.vec"))
            raise SendRefused(Message("session.build.up_to_date"))
        cancel = CancelToken()
        previous = self._enter_rag_job("index_build", self._build_fr(0, 0), cancel)
        threading.Thread(
            target=self._run_build,
            args=(model, content, cancel, previous, self._language),
            name="wavestack-index-build",
            daemon=True,
        ).start()
        return self._build_fr(0, 0)

    @staticmethod
    def _build_fr(done: int, total: int) -> str:
        if not total:
            return Message("session.build.loading")
        return Message("session.build.progress", done=done, total=total)

    def _run_build(
        self,
        model: EmbeddingModel,
        content: RagContent,
        cancel: CancelToken,
        previous: str | None,
        lang: str = config.DEFAULT_LANGUAGE,
    ) -> None:
        """The build thread: its own embedding model, through the registry (AD-8), closed
        afterwards; the index written then read again; the brick loads if wanted.
        Languages (4/5): the index and the corpus of `lang`, the session's (no change of
        language outside `idle`)."""
        path = self.cfg.rag_index_path(lang)
        self._release_embedder()  # its connection to the old index closes first (Windows)
        failed: BaseException | str | None = None
        stopped = False
        embedder, refusal = self._build_embedder(model)
        meta = None
        if refusal is not None:
            failed = refusal
        else:
            try:
                meta = rag_index.build_index(
                    content,
                    embedder,
                    path,
                    self.cfg.rag_chunk_max_chars,
                    self._throttled("index_build", self._build_fr),
                    model_file=embedding_module.model_path(model),
                    cancelled=lambda: cancel.cancelled,
                    lang=lang,
                )
            except rag_index.BuildCancelled as exc:
                failed, stopped = exc.message, True
            except rag_index.IndexInUse:  # lot G: another program holds it open (Windows)
                failed = INDEX_HELD_FR
            except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
                failed = exc
            finally:
                self._close_embedder(embedder, None)
        with self._lock:
            self._download_cancel = None
        with scoped(brick="rag", component=RAG_INDEX):  # the card shows a failure (AD-1)
            if failed is not None:
                self._error(
                    Message("session.build.stopped" if stopped else "session.build.failed"),
                    failed,
                    Message("session.build.unchanged", path=path),
                )
            elif meta is not None:
                self._journal().emit(
                    "effect_applied",
                    {
                        "effect": "rag_index_write",
                        "lines": [
                            Message(
                                "session.build.written",
                                path=path,
                                chunks=meta.chunks,
                                model=meta.embedding_model_id,
                                dims=meta.dims,
                            )
                        ],
                    },
                )
        self._set_state("idle", previous)
        try:
            self._rag_caught_up()
        except RuntimeError:  # the session is closing
            pass

    def _build_embedder(self, model: EmbeddingModel) -> tuple[Embedder | None, str | None]:
        """The build's embedding model, loaded as the brick's is (budget, then load)."""
        label = Message("session.rag.embedding_label", label=model.label_text)
        cost = self._load_registry.component_cost(
            model.measured_rss_mb, [f.size for f in model.files]
        )
        refusal = self._load_registry.check_component(label, cost, EMBEDDING)
        if refusal is not None:
            return None, refusal
        try:
            embedder = self._embedder_factory(model)
        except Exception as exc:  # noqa: BLE001 - AD-16
            return None, Message(
                "session.build.embedder_failed", kind=type(exc).__name__, cause=exc
            )
        self._load_registry.grant(model.label_text, cost, EMBEDDING)
        return embedder, None

    def answer_approval(self, approval_id: str, approved: bool, disable_hook: bool) -> None:
        """Intention class (c): answers the pending validation; the first answer wins.
        `disable_hook` only counts with `approved`. Raises `SendRefused` otherwise."""
        with self._lock:
            approval = self._approval
            if approval is None or approval.id != approval_id:
                raise SendRefused(Message("session.approval.unknown", approval_id=approval_id))
            if approval.decision is not None:
                raise SendRefused(Message("session.approval.answered"))
            approval.decision = "approved" if approved else "refused"
            approval.disable_hook = approved and disable_hook
        approval.answered.set()

    # ---------- turn ----------

    def _run_turn(
        self,
        turn_id: str,
        message: str,
        cancel: CancelToken,
        state: TurnState,
        replay_of: str | None = None,
    ) -> None:
        started = time.monotonic()
        status = "error"
        journal = self._journal()
        self._hook_steps = 0
        self._approvals = 0
        self._turn_called = False  # lot A: set by `_keep_cache`
        self._turn_costs = []
        self._turn_impacts = []
        self._hooks_off.clear()
        self._call_ids.clear()
        steps: list[dict[str, Any]] = []
        text = reasoning = ""
        with scoped(turn_id=turn_id, context_id="main", trigger="user"):
            try:
                self._turn_seq = journal.emit(
                    "turn_started",
                    {
                        "replay_of": replay_of,
                        "message": message,
                        "active_model": self.active_model(),
                    },
                    actor="user",
                ).seq
                decided = self._hook("on_user_message", state)
                if decided is not None and decided[1].injection:  # computed once for the turn
                    state = replace(state, injection=decided[1].injection)
                self._turn_ctx = (state, cancel)  # what `delegate` reads (AD-11)
                status, text, reasoning = self._turn(turn_id, message, cancel, state, steps)
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(
                    # Story 18: a local server stopped while the prompt was tokenized.
                    (getattr(exc, "message", None) or exc.message_text)
                    if isinstance(exc, ServerError)
                    else Message("session.turn.interrupted"),
                    exc,
                    Message("session.turn.over"),
                )
            finally:
                self._turn_ctx = None
                try:
                    ended = self._hook("on_turn_end", state, status=status)
                except Exception as exc:  # noqa: BLE001 - AD-16: the turn still ends
                    ended = None
                    self._error(
                        Message("session.turn.end_hooks.message"),
                        exc,
                        Message("session.turn.end_hooks.effect"),
                    )
                if status == "completed" and ended is not None and ended[1].decision == "block":
                    status = "blocked"  # the answer stays out of the history
                if status == "completed":  # AD-17: recorded even with short memory off
                    exchange = Exchange(
                        turn_id, message, text, reasoning, tuple(steps), state.injection
                    )
                    with self._lock:
                        self._history.append(exchange)
                self._apply_arm_consumed([ArmConsumed(armed_id=a.armed_id) for a in state.armed])
                journal.emit(
                    "turn_ended",
                    {"status": status, "duration_ms": _ms(time.monotonic() - started)}
                    | self._turn_cost()
                    | self._turn_impact(),
                )
                with self._lock:
                    self._cancel = None
                    if self._turn_called:  # lot A: `abandoned` only for a turn that
                        self._last_status = status  # left its output in the engine's cache
                self._set_state("idle")
                self._emit_window_state()  # story 26: the read rate this turn measured

    def _turn(
        self,
        turn_id: str,
        message: str,
        cancel: CancelToken,
        state: TurnState,
        steps: list[dict[str, Any]],
    ) -> tuple[str, str, str]:
        """The bounded loop of AD-10. Returns `(status, text, reasoning)`; fills `steps`."""
        journal = self._journal()
        max_calls, max_retries = self.cfg.tool_max_calls, self.cfg.tool_max_retries
        retries = 0
        previous: tuple[list[int], str] | None = None  # last call's ids and raw output
        # Story 32: the last call's segments, whose common prefix the next call read already.
        read_before: list[Segment] | None = None
        # AD-25: documentations loaded in this turn are callable at once. Locally, they enter
        # `tools` only from the next turn (the prefix stays append only); in chat mode, from
        # the next call, since a provider refuses a call to a tool its `tools` lacks.
        loaded_in_turn: list[str] = []
        # AD-3: the armed actions, after `on_user_message` and before the first call, outside
        # the call budget (AD-10). Lot K: the MCP tools they called join `tools` at once.
        defined: list[str] = []
        stopped, step = self._consume_armed(turn_id, state, cancel, steps, loaded_in_turn, defined)
        state = _with_loaded(state, defined)
        if stopped:
            return "cancelled", "", ""
        if "rag" in state.effective:  # story 15: once per turn, main context, before any call
            step += 1
            excerpts = self._rag_search(
                turn_id, step, message, state.rag_rerank, state.rag_rerank_skipped_text
            )
            if state.rag_rerank and excerpts and not cancel.cancelled:  # story 16: its own step
                step += 1
                excerpts = self._rag_rerank_step(turn_id, step, message, excerpts, cancel)
            texts = [(e.position, e.title_text, e.text) for e in excerpts[: self.cfg.rag_top_k]]
            state = replace(state, rag_excerpts=self._rag_texts(texts))
            if cancel.cancelled:
                return "cancelled", "", ""
        sent = 0  # story 20: the steps the model has read already, never rewritten (AD-4)
        for n in range(1, max_calls + 1):
            call_id = f"{turn_id}.main.c{n}"
            if "compression" in state.effective:  # AD-4 `transform_context`, AD-22
                step, state = self._transform_context(
                    turn_id, step, state, steps, sent, n == 1, cancel
                )
                if cancel.cancelled:
                    return "cancelled", "", ""
            with scoped(call_id=call_id):
                decided = self._hook("before_model_call", state)
            if decided is not None and decided[1].decision == "block":
                return "blocked", "", ""
            step += 1
            with scoped(call_id=call_id, step_id=f"{turn_id}.main.s{step}", component="core.model"):
                shown = state if self._cloud is None else _with_loaded(state, loaded_in_turn)
                rendered, payload = self._render(
                    shown, message, call_id, steps, read_before=read_before
                )
                read_before = rendered.segments
                sent = len(steps)
                journal.emit("context_rendered", payload)
                if payload["overflow"]:
                    self._emit_overflow(payload, getattr(rendered, "raw_total", None))
                    return "overflow", "", ""
                if isinstance(rendered, RenderedContext):  # chat mode has no ids (AD-4)
                    self._check_reuse(rendered, previous)
                done: _ModelOutput | None = None
                try:
                    done = out = self._call_model(
                        rendered,
                        cancel,
                        state.tools + tuple(loaded_in_turn),
                        payload["reserve"],
                        self._reasoning_on(state),
                    )
                finally:  # lot A: what the engine holds now, even after a failed call
                    if isinstance(rendered, RenderedContext):
                        self._keep_cache(rendered.ids, done)
            if out.status != "completed":
                return out.status, "", ""
            if not out.calls and out.malformed is None:
                return "completed", out.text, out.reasoning
            if isinstance(rendered, RenderedContext):
                previous = (rendered.ids, out.raw)

            # A failed call earns a new attempt while retries and calls remain (AD-10, AD-14).
            reaction = "retry" if retries < max_retries and n < max_calls else "stop"
            failed = False
            harness_brick = next(
                (
                    b
                    for b in ("tools", "mcp", "skills", "global_memory", "subagent")
                    if b in state.effective
                ),
                "tools",
            )
            # AD-25: what the model decided carries `trigger = model`, a forced action `user`.
            with scoped(
                call_id=call_id, brick=harness_brick, component="core.harness", trigger="model"
            ):
                if out.malformed is not None:
                    failed = True
                    step += 1
                    with scoped(step_id=f"{turn_id}.main.s{step}"):
                        error = self._tool_executor.reject(
                            out.raw, out.malformed.fragment, out.malformed.detail_text, reaction
                        )
                    # The output without its reasoning, the reasoning apart (AD-4); in chat
                    # mode, the raw output AD-10 reinjects.
                    steps.append(
                        {"role": "assistant", "content": out.answer or out.raw, "tool_calls": []}
                        | ({"reasoning": out.reasoning} if out.reasoning and out.answer else {})
                    )
                    steps.append(
                        {
                            "role": "tool",
                            "name": None,
                            "content": error,
                            "component": "core.harness",
                            "brick": harness_brick,
                        }
                    )
                else:
                    steps.append(self._assistant_step(out))
                    for call, call_ref in zip(out.calls, out.ids, strict=True):
                        step += 1
                        detail = self._tool_executor.check(
                            call, state.tools + tuple(loaded_in_turn), state.loadable
                        )
                        named = self._registry.get(call.name)
                        spec = named if detail is None else None
                        if detail is not None:
                            failed = True
                        # AD-4: the step and its result belong to the named tool's own brick,
                        # even refused; an unknown name to the harness brick.
                        component = spec.component if spec else "core.harness"
                        brick = (
                            (named.brick or named.component.split(".")[0])
                            if named
                            else harness_brick
                        )
                        effects: list[Effect] = []
                        step_id = f"{turn_id}.main.s{step}"
                        blocker = None
                        if spec is None:
                            with scoped(step_id=step_id, brick=brick, component=component):
                                result = self._tool_executor.reject(
                                    out.raw, call.source, detail, reaction
                                )
                        else:
                            ran = self._run_tool(call, spec, state, cancel, effects, step_id, brick)
                            if ran is None:
                                return "cancelled", "", ""
                            result, blocker = ran
                        tool_step = self._reply_step(
                            call_ref, call.name, result, component, brick, blocker, spec
                        )
                        steps.append(self._apply_effects(effects, tool_step, loaded_in_turn))
            if failed:
                retries += 1
                if retries > max_retries:
                    self._emit_limit("retries", retries)
                    return "limit", "", ""
            if cancel.cancelled:
                return "cancelled", "", ""
        self._emit_limit("calls", max_calls)
        return "limit", "", ""

    def _compressible(self, reply: dict[str, Any]) -> bool:
        """Story 20 (AD-22): a tool's own output (`tool_output`, set by `_reply_step`), long
        enough. Never a meta-tool's reply (`delegate`, `load_skill`…), a hook's refusal, a
        call the harness refused, nor a malformed call's error."""
        if reply.get("role") != "tool" or not reply.get("tool_output"):
            return False
        if reply.get("kind", SegmentKind.TOOL_RESULT) != SegmentKind.TOOL_RESULT:
            return False
        return len(reply["content"].strip()) >= self.cfg.compression_min_chars

    def _transform_context(
        self,
        turn_id: str,
        step: int,
        state: TurnState,
        steps: list[dict[str, Any]],
        sent: int,
        first: bool,
        cancel: CancelToken,
    ) -> tuple[int, TurnState]:
        """Story 20, AD-4's `transform_context` (AD-22), as a step of the harness with its pair
        of events: before a call, the tool outputs no call has read yet (`steps[sent:]`) and,
        before the first call, the RAG excerpts, each compressed once. It works on the turn's
        parts before they are assembled (the same place in the turn), and offers no hook point
        (AD-13). What a call has read is never rewritten (append only). Returns the steps
        numbered and the state with the excerpts replaced; the outputs are replaced in
        `steps`. A stop between two texts leaves the others as they are."""
        with self._lock:
            compressor = self._compressor
        content = self._compression_content
        if compressor is None or content is None:
            return step, state  # unloaded meanwhile: the turn goes on uncompressed
        minimum = self.cfg.compression_min_chars
        # (source_text, kind, brick, component, text, where: ("step" | "rag", index))
        candidates: list[tuple[str, SegmentKind, str | None, str | None, str, tuple]] = []
        if first:
            for i, text in enumerate(state.rag_excerpts):
                if i > 0 and len(text.strip()) >= minimum:  # 0: the excerpts' intro
                    source = content.rag_source_text.format(n=i)
                    candidates.append(
                        (source, SegmentKind.RAG_EXCERPT, "rag", "rag.retriever", text, ("rag", i))
                    )
        for i in range(sent, len(steps)):
            reply = steps[i]
            if self._compressible(reply):
                source = content.tool_source_text.format(tool=reply.get("name"))
                candidates.append(
                    (
                        source,
                        SegmentKind.TOOL_RESULT,
                        reply.get("brick"),
                        reply.get("component"),
                        reply["content"],
                        ("step", i),
                    )
                )
        if not candidates:
            return step, state
        step += 1
        step_id = f"{turn_id}.main.s{step}"
        journal = self._journal()
        scope = {
            "step_id": step_id,
            "brick": "compression",
            "component": "compression.compressor",
            "actor": "harness",
            "trigger": "harness",
        }
        excerpts = list(state.rag_excerpts)
        was = list(state.rag_compressed) + [None] * (len(excerpts) - len(state.rag_compressed))
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        estimated = False
        with scoped(**scope):
            journal.emit(
                "compression_started",
                {
                    "phase_label": content.phase_label_text,
                    "title_text": content.step_title_text,
                    "items": len(candidates),
                    "compressor_text": compressor.label_text,
                },
            )
            started = time.monotonic()
            try:
                for source, kind, brick, component, text, (where, i) in candidates:
                    if cancel.cancelled:
                        break  # the turn stops right after: the others stay as they were
                    item = self._compress_one(compressor, source, kind, text, errors)
                    item |= {"brick": brick, "component": component}
                    estimated = estimated or item.pop("estimated")
                    items.append(item)
                    if not item["changed"]:
                        continue
                    origin = CompressedFrom(
                        tokens_before=item["tokens_before"],
                        estimated=estimated,
                        step_id=step_id,
                        item=len(items) - 1,
                    )
                    if where == "rag":
                        excerpts[i], was[i] = item["text_after"], origin
                    else:
                        steps[i] = steps[i] | {
                            "content": item["text_after"],
                            "compressed_from": origin,
                        }
            finally:  # AD-2: the pair is always complete
                total_before = sum(item["tokens_before"] for item in items)
                total_after = sum(item["tokens_after"] for item in items)
                journal.emit(
                    "compression_ended",
                    {
                        "status": "error" if errors else "ok",
                        "compressor_text": compressor.label_text,
                        "items": items,
                        "tokens_before": total_before,
                        "tokens_after": total_after,
                        "saved_tokens": max(0, total_before - total_after),
                        "estimated": estimated,
                        "unchanged_text": content.unchanged_text,
                        "error_text": " ".join(errors) or None,
                        "duration_ms": _ms(time.monotonic() - started),
                    },
                )
        if first and state.rag_excerpts:
            state = replace(state, rag_excerpts=tuple(excerpts), rag_compressed=tuple(was))
        return step, state

    def _compress_one(
        self,
        compressor: Compressor,
        source: str,
        kind: SegmentKind,
        text: str,
        errors: list[str],
    ) -> dict[str, Any]:
        """One candidate: its tokens before and after, counted by WaveStack (AD-1). An empty
        result, one not shorter in tokens, or a failure keeps the original (`changed` false);
        `text_after` is then left out of the trace (the original is already there)."""
        original = text.strip()
        before, estimated = self._count_tokens(original)
        after_text, transforms, error_text = original, (), None
        try:
            result = compressor.compress(text)
            after_text = (result.text or "").strip()
            transforms = tuple(str(t) for t in (result.transforms or ()))
        except Exception as exc:  # noqa: BLE001 - AD-16: the original goes on
            error_text = Message(
                "session.compression.text_failed", source=source, kind=type(exc).__name__, cause=exc
            )
            errors.append(error_text)
            self._error(
                Message("session.compression.failed.message"),
                exc,
                Message("session.compression.failed.effect"),
            )
        after, estimate_after = self._count_tokens(after_text) if after_text else (0, False)
        changed = error_text is None and bool(after_text) and after_text != original
        changed = changed and after < before
        return {
            "source_text": source,
            "kind": kind.value,
            "tokens_before": before,
            "tokens_after": after if changed else before,
            "text_before": original,
            "text_after": after_text if changed else None,
            "changed": changed,
            "transforms": list(transforms),
            "error_text": error_text,
            "estimated": estimated or estimate_after,
        }

    def _rag_current_retriever(self) -> SqliteVecRetriever:
        """The loaded retriever, on the index as it is now. An index replaced since it was
        read (rebuilt by the script) is read again; one that no longer fits the model makes
        the brick unavailable, and this search fails with the reason."""
        with self._lock:
            embedder, retriever, stamp = self._embedder, self._rag_retriever, self._rag_stamp
        if embedder is None or retriever is None:
            raise RuntimeRefused("session.rag.embedder_not_loaded")
        path = self._rag_index_path()
        if _stamp(path) == stamp:
            return retriever
        retriever.close()
        self._rag_refresh()
        with self._lock:
            reason = self._rag_index_error
        if reason is not None:
            self._release_embedder()
            self._release_reranker()  # story 16: no RAG, no reranking to keep in memory
            self._emit_bricks()
            self._emit_architecture()
            raise RuntimeRefused("session.rag.index_replaced", reason=reason)
        fresh = SqliteVecRetriever(path, embedder, self.cfg.rag_top_k)
        with self._lock:
            self._rag_retriever = fresh
        self._emit_architecture()  # its tooltip gives the new index's figures
        return fresh

    def _rag_search(
        self,
        turn_id: str,
        step: int,
        message: str,
        rerank: bool = False,
        rerank_skipped_text: str | None = None,
    ) -> list[Excerpt]:
        """Story 15 (AD-2, AD-22): the search, a step of the harness with its pair of events.
        Returns the excerpts found; a failure is traced and the turn goes on without excerpts
        (as a failing hook lets the turn through). Story 16: with `rerank`, the reranker's
        candidates, none of which goes to the context directly; `rerank_skipped_text`: why the
        reranking enabled does not apply to this turn, said by the step."""
        content = self._rag_content
        assert content is not None  # the brick is unavailable without it
        top_k = self.cfg.rag_top_k
        placement_text = content.placement_text
        if rerank:
            placement_text = content.rerank_search_placement_text.format(
                candidates=self.cfg.rag_rerank_candidates, keep=top_k
            )
            top_k = self.cfg.rag_rerank_candidates
        journal = self._journal()
        scope = {
            "step_id": f"{turn_id}.main.s{step}",
            "brick": "rag",
            "component": "rag.retriever",
            "actor": "harness",
            "trigger": "harness",
        }
        with scoped(**scope):
            journal.emit(
                "rag_search_started",
                {"query": message, "top_k": top_k, "phase_label": content.phase_label_text},
            )
            started = time.monotonic()
            try:
                excerpts = self._rag_current_retriever().search(message, top_k)
            except Exception as exc:  # noqa: BLE001 - AD-16: the turn goes on
                self._error(
                    Message("session.rag.search_failed.message"),
                    exc,
                    Message("session.rag.search_failed.effect"),
                )
                journal.emit(
                    "rag_search_ended",
                    {
                        "status": "error",
                        "excerpts": [],
                        "placement_text": placement_text,
                        "error_text": Message(
                            "session.rag.search_failed.text",
                            kind=type(exc).__name__,
                            cause=Lazy(lambda lang, e=exc: rag_index.exception_text(e, lang)),
                        ),
                        "duration_ms": _ms(time.monotonic() - started),
                        "rerank_skipped_text": rerank_skipped_text,
                    },
                )
                return []
            journal.emit(
                "rag_search_ended",
                {
                    "status": "ok",
                    "excerpts": [e.payload() for e in excerpts],
                    "placement_text": placement_text,
                    "error_text": None,
                    "duration_ms": _ms(time.monotonic() - started),
                    "rerank_skipped_text": rerank_skipped_text,
                },
            )
        return excerpts

    def _rag_rerank_step(
        self,
        turn_id: str,
        step: int,
        message: str,
        candidates: list[Excerpt],
        cancel: CancelToken,
    ) -> list[Excerpt]:
        """Story 16 (AD-2, AD-22): the reranking, a step of the harness with its pair of
        events and its progress after each candidate. Each candidate is scored with the query;
        the order before and after is traced (by `chunk_id`: the texts are the search's), and
        the first `top_k` after reranking are returned, numbered again from 1. A failure,
        scores that are not figures included, is traced and the turn goes on with the
        embedding's first `top_k`; « Arrêter » ends the step as `cancelled`."""
        content = self._rag_content
        assert content is not None  # the brick is unavailable without it
        keep = min(self.cfg.rag_top_k, len(candidates))
        placement_text = content.rerank_placement_text.format(candidates=len(candidates), keep=keep)
        journal = self._journal()
        scope = {
            "step_id": f"{turn_id}.main.s{step}",
            "brick": "rag",
            "component": RAG_RERANKER,
            "actor": "harness",
            "trigger": "harness",
        }

        def progress(done: int, total: int) -> None:
            with scoped(**scope):
                journal.emit("rag_rerank_progress", {"done": done, "total": total})

        with scoped(**scope):
            journal.emit(
                "rag_rerank_started",
                {
                    "query": message,
                    "candidates": len(candidates),
                    "keep": keep,
                    "phase_label": content.rerank_phase_label_text,
                },
            )
            started = time.monotonic()
            try:
                with self._lock:
                    reranker = self._reranker
                if reranker is None:
                    raise RuntimeRefused("session.rerank.not_loaded")
                # As the index embeds them: each excerpt with its document's title.
                passages = [f"{c.title_text}\n{c.text}" for c in candidates]
                raw = reranker.score(message, passages, lambda: cancel.cancelled, progress)
                if len(raw) != len(candidates):
                    raise ValueRefused(
                        "session.rerank.scores", scores=len(raw), excerpts=len(candidates)
                    )
                scores, truncated = [], []
                for item in raw:
                    value = float(item.score)  # raises on what is not a figure
                    if not math.isfinite(value):
                        raise ValueRefused("session.rerank.not_finite", score=repr(item.score))
                    scores.append(round(min(1.0, max(0.0, value)), 3))
                    truncated.append(bool(item.truncated))
            except Exception as exc:  # noqa: BLE001 - AD-16: the turn goes on
                stopped = isinstance(exc, RerankCancelled)
                if not stopped:
                    self._error(
                        Message("session.rerank.failed.message"),
                        exc,
                        Message("session.rerank.failed.effect", keep=keep),
                    )
                journal.emit(
                    "rag_rerank_ended",
                    {
                        "status": "cancelled" if stopped else "error",
                        "excerpts": [],
                        "keep": keep,
                        "placement_text": placement_text,
                        "error_text": (
                            Message("session.rerank.stopped")
                            if stopped
                            else Message(
                                "session.rerank.failed.text",
                                kind=type(exc).__name__,
                                cause=exc.message if isinstance(exc, KeyedError) else exc,
                                keep=keep,
                            )
                        ),
                        "duration_ms": _ms(time.monotonic() - started),
                    },
                )
                return candidates[:keep]
            # Stable: the reranker's score, then the embedding's rank.
            order = sorted(
                range(len(candidates)), key=lambda i: (-scores[i], candidates[i].position)
            )
            reranked = [
                {
                    "position": rank,
                    "before": candidates[i].position,
                    "chunk_id": candidates[i].chunk_id,
                    "doc_id": candidates[i].doc_id,
                    "title_text": candidates[i].title_text,
                    "score": scores[i],
                    "retrieval_score": candidates[i].score,
                    "truncated": truncated[i],
                }
                for rank, i in enumerate(order, start=1)
            ]
            journal.emit(
                "rag_rerank_ended",
                {
                    "status": "ok",
                    "excerpts": reranked,
                    "keep": keep,
                    "placement_text": placement_text,
                    "error_text": None,
                    "duration_ms": _ms(time.monotonic() - started),
                },
            )
        return [
            replace(candidates[i], position=rank) for rank, i in enumerate(order[:keep], start=1)
        ]

    def _run_tool(
        self,
        call: ToolCall,
        spec: ToolSpec,
        state: TurnState,
        cancel: CancelToken,
        effects: list[Effect],
        step_id: str,
        brick: str,
    ) -> tuple[str, str | None] | None:
        """AD-14: the single path of a checked call, `before_tool`, execution, `after_tool`.
        Returns the text reinjected and the id of the hook that blocked the call (then the tool
        never runs, and has no step), or `None` when the turn is stopped. H5's `ask_human`
        (story 8b) waits here; the forced action and the sub-agent (story 9) go through here."""
        decided = self._hook("before_tool", state, call=call, spec=spec)
        if decided is not None:
            hook_id, result = decided
            if result.decision == "block":  # not a new attempt (AD-10)
                return result.detail_text, hook_id
            if result.arguments is not None:
                call = replace(call, arguments=result.arguments)
            if result.decision == "ask_human" and result.preview is not None:
                answer = self._await_human(hook_id, call, result.preview)
                if answer == "cancelled":
                    return None
                if answer == "refused":  # nothing sent; not a new attempt either
                    return (
                        self._t(
                            "hooks.h5.refused", name=call.name, host=host(result.preview["url"])
                        ),
                        hook_id,
                    )
        bounded = (spec.network or spec.is_mcp) and spec.name != DELEGATE
        with scoped(step_id=step_id, brick=brick, component=spec.component):
            text = self._tool_executor.run(
                call,
                cancel,
                effects,
                apply=self._apply_now,
                bound=self._bound_result if bounded else None,
            )
        if spec.is_mcp and text is not None:
            self._after_mcp_call(call.name, spec)
        if spec.network or spec.is_mcp:
            self._emit_architecture()  # its contact state may have changed
        if text is None or (spec.name == DELEGATE and cancel.cancelled):
            return None  # AD-11: a delegation stopped ends the turn, no other call
        self._hook("after_tool", state, call=call, spec=spec, result=text)
        return text, None

    def _bound_result(self, text: str) -> tuple[str, dict[str, Any] | None]:
        """Lot B (N3): a network or MCP tool's result cut to `[tools] result_max_tokens`,
        before the compression. The longest prefix that fits with the mention (a bisection on
        the characters), back to its last line break when that is in its second half; the
        mention says what was kept, for the model. Returns the text and, when it cut,
        `{tokens, total_tokens, estimated}` for `tool_ended`. In chat mode, counted with the
        provider's ratio even above 1: what it will count. Never raises (`_count_tokens`)."""
        limit = self.cfg.tool_result_max_tokens

        def count(piece: str) -> tuple[int, bool]:
            return self._count_tokens(piece, uncapped=True)

        total, estimated = count(text)
        if total <= limit:
            return text, None

        # Lot B (N3): the mention appended to the cut result, seen by the model, in the
        # session's language (languages 5/5): its length counts in the bound.
        def mention(kept: int) -> str:
            return "\n\n" + self._t("tools.truncated", kept=kept, total=total)

        def cut(prefix: str) -> tuple[str, int, bool]:
            kept, rough = count(prefix)
            return prefix + mention(kept), kept, rough

        # The mention at its widest (as many digits kept as in total): one count per step.
        widest = mention(total)
        low, high = 0, len(text) - 1  # the longest fitting prefix is in [low, high]
        while low < high:
            middle = (low + high + 1) // 2
            if count(text[:middle] + widest)[0] <= limit:
                low = middle
            else:
                high = middle - 1
        end = low
        line = text.rfind("\n", 0, end + 1)  # `text[end]` a break: the prefix ends a line
        if line >= end / 2 and line > 0:
            end = line
        prefix = text[:end].rstrip()
        bounded, kept, rough = cut(prefix)
        while prefix and count(bounded)[0] > limit:  # a tokenizer's quirk
            prefix = prefix[: len(prefix) * 9 // 10]
            bounded, kept, rough = cut(prefix)
        return bounded, {"tokens": kept, "total_tokens": total, "estimated": estimated or rough}

    def _apply_effects(
        self, effects: list[Effect], tool_step: dict[str, Any], loaded_in_turn: list[str]
    ) -> dict[str, Any]:
        """AD-23: the session applies a tool's effects; returns its reply step, which a
        loading meta-tool turns into what it loaded (AD-4, AD-25)."""
        for effect in effects:
            if isinstance(effect, ToolDocLoaded):
                tool_step |= self._apply_doc_loaded(effect.tool, loaded_in_turn)
            elif isinstance(effect, SkillLoaded):
                tool_step |= self._apply_skill_loaded(effect.skill_id)
        return tool_step

    def _consume_armed(
        self,
        turn_id: str,
        state: TurnState,
        cancel: CancelToken,
        steps: list[dict[str, Any]],
        loaded_in_turn: list[str],
        defined: list[str],
    ) -> tuple[bool, int]:
        """AD-3, AD-25: runs the actions the turn took, in arming order, each through the
        single executor, hooks included, with `trigger = user`. Each is rendered as an
        assistant call attributed to its brick, then its reply. A failure (H1's block, a tool
        error) is reinjected, never a new attempt; an unavailable target is dropped with its
        reason. Returns whether the turn was stopped, and the steps numbered so far.

        Lot K: a forced call of an MCP tool whose documentation is not loaded (lazy loading)
        adds its definition to `tools` (AD-25), for the conversation: its name joins
        `defined`, and the caller moves it out of `loadable` for this turn's calls."""
        step = 0
        for action in state.armed:
            if cancel.cancelled:
                return True, step
            call = self._armed_call(action)
            spec = self._registry.get(call.name)
            reason = self._armed_unavailable(action, state, loaded_in_turn)
            if reason is None and spec is None:
                reason = Message("session.forced.undeclared", name=call.name)
            if reason is None:
                reason = self._tool_executor.check(call, [call.name])
            if reason is not None or spec is None:
                with scoped(brick=action.brick, trigger="user"):
                    self._journal().emit(
                        "action_dropped",
                        {
                            "armed_id": action.armed_id,
                            "reason_text": Message(
                                "session.forced.dropped",
                                label=action.label_text,
                                reason=Lazy(lambda lang, r=reason: render(r, lang).rstrip(".")),
                            ),
                        },
                    )
                continue
            if action.kind == "tool" and spec.is_mcp and call.name in state.loadable:
                with self._lock:
                    self._loaded_docs.add(call.name)
                if call.name not in defined:
                    defined.append(call.name)
            step += 1
            step_id = f"{turn_id}.main.s{step}"
            call_ref = self._new_call_id(step_id, 0)  # AD-4: index 0, its own step
            target = self._registry.get(action.target) if action.kind == "tool_doc" else spec
            component = (
                f"skills.{action.target}" if action.kind == "skill" else (target or spec).component
            )
            effects: list[Effect] = []
            with scoped(trigger="user"):
                ran = self._run_tool(call, spec, state, cancel, effects, step_id, action.brick)
            if ran is None:
                return True, step
            result, blocker = ran
            made: dict[str, Any] = {
                "id": call_ref,
                "name": call.name,
                "arguments": call.arguments,
                "arguments_json": json.dumps(call.arguments, ensure_ascii=False),
            }
            cloud = self._cloud
            if cloud is not None and cloud.tool_call_extra:  # chat mode (Gemini 3.x)
                made |= {"extra": dict(cloud.tool_call_extra), "extra_for": cloud.id}
            steps.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [made],
                    "brick": action.brick,
                    "component": component,
                }
            )
            tool_step = self._reply_step(
                call_ref, call.name, result, component, action.brick, blocker, spec
            )
            steps.append(self._apply_effects(effects, tool_step, loaded_in_turn))
        return False, step

    @staticmethod
    def _armed_call(action: ArmedAction) -> ToolCall:
        """The call a forced action makes: the tool itself, or its brick's meta-tool."""
        if action.kind == "skill":
            return ToolCall(LOAD_SKILL, {"skill": action.target})
        if action.kind == "tool_doc":
            return ToolCall(LOAD_TOOL_DOC, {"tool": action.target})
        if action.kind == "memory":
            return ToolCall(REMEMBER, {"text": action.args.get("text", "")})
        if action.kind == "delegate":
            return ToolCall(DELEGATE, {"task": action.args.get("task", "")})
        return ToolCall(action.target, dict(action.args))

    def _armed_unavailable(
        self, action: ArmedAction, state: TurnState, loaded_in_turn: list[str]
    ) -> str | None:
        """Why a forced action's target is not available to this turn, in French; `None`
        when it is. Read from the frozen `TurnState`, plus what this turn loaded."""
        target = action.target

        def why(key: str, **kw: Any) -> Message:
            return Message(f"session.forced.{key}", **kw)

        if action.kind == "tool" and action.brick == "mcp":  # lot K: an MCP tool's call
            if "mcp" not in state.effective:
                return why("inactive.mcp")
            if target not in state.tools and target not in state.loadable:
                return why("server_off", target=target)
            return None
        if action.kind == "tool":
            if "tools" not in state.effective:
                return why("inactive.tools")
            if target not in state.tools:
                return why("tool_unchecked", tool=self._registry.label(target))
            return None
        if action.kind == "skill":
            if "skills" not in state.effective:
                return why("inactive.skills")
            with self._lock:
                loaded = target in self._loaded_skills
            if target in state.skills or loaded:
                return why("skill_loaded", skill=self._skill_label(target))
            if target not in state.skill_catalog:
                return why("skill_unchecked", skill=self._skill_label(target))
            return None
        if action.kind == "memory":
            if "global_memory" not in state.effective:
                return why("inactive.global_memory")
            if REMEMBER not in state.tools:  # H4: no tool parser
                return why("no_parser")
            return None
        if action.kind == "delegate":
            if "subagent" not in state.effective:
                return why("inactive.subagent")
            return None
        if "mcp" not in state.effective:
            return why("inactive.mcp")
        with self._lock:
            lazy = self._sent[4]  # the mode frozen for this turn by `send`
        if not lazy and target in state.tools:
            return why("doc_in_context", target=target)
        if target in loaded_in_turn or target in state.tools:
            return why("doc_loaded", target=target)
        if target not in state.loadable:
            return why("server_off", target=target)
        return None

    def _await_human(self, hook_id: str, call: ToolCall, preview: dict[str, str]) -> str:
        """H5 (AD-13): `awaiting_human` until the user answers or stops the turn, without
        delay; on the hook's own step. Returns `approved`, `refused` or `cancelled`."""
        journal = self._journal()
        turn_id = current().turn_id or ""
        self._approvals += 1
        approval = _Approval(f"{turn_id}.a{self._approvals}")
        context_id = current().context_id or "main"  # `main` or `sub{n}` (AD-11)
        step = f"{turn_id}.{context_id}.h{self._hook_steps}"  # the step of H5's `hook_decided`
        with scoped(step_id=step, brick="hooks", component=f"hooks.{hook_id}"):
            # Answerable before its id is published, so no answer to it is ever refused.
            with self._lock:
                self._approval = approval
                waiting = self._cancel is None or not self._cancel.cancelled
                if waiting:
                    self.state, self.reason_text = "awaiting_human", _AWAITING_FR
                else:  # stopped just before
                    approval.decision = "cancelled"
            journal.emit(
                "approval_requested",
                {
                    "approval_id": approval.id,
                    "tool": call.name,
                    "destination": host(preview["url"]),
                    "preview": preview,
                },
            )
            if waiting:
                self._emit_state()
                approval.answered.wait()  # AD-13: no delay; `answer_approval` or `stop` wakes it
            with self._lock:
                decision, disable = approval.decision or "cancelled", approval.disable_hook
            journal.emit(
                "approval_resolved",
                {"approval_id": approval.id, "decision": decision, "hook_disabled": disable},
                actor="user",
            )
        if decision != "cancelled":  # stopped: the turn ends, no flash back to `turn`
            self._set_state("turn", _TURN_FR)
        if disable:  # off now, and for the rest of this turn despite its frozen state
            self._hooks_off.add(hook_id)
            with self._lock:
                self._hooks_enabled.discard(hook_id)
                self._sent = (*self._sent[:6], self._sent[6] - {hook_id})  # nothing pending
            self._emit_bricks()
            self._emit_architecture()
        return decision

    def _hook(
        self, point: HookPoint, state: TurnState, **ctx: Any
    ) -> tuple[str, HookResult] | None:
        """AD-13: calls the turn's active hooks of `point` in order, each decision emitted on
        a step of its own and its effects applied; the first `block` or `ask_human` stops
        there. Returns the deciding hook and its result: the blocking or asking one, else the
        last that modified. A failing hook or a decision not allowed at `point` is traced and
        counts as `allow`."""
        hooks = [
            h
            for h in self._hooks
            if h.id in state.hooks and h.id not in self._hooks_off and point in h.points
        ]
        if not hooks:
            return None
        journal = self._journal()
        turn_id = current().turn_id or ""
        texts = self._hooks_content
        decided: tuple[str, HookResult] | None = None
        for hook in hooks:
            # From this turn's start: another session's turn may share its id (AD-2).
            since = journal.events_since(self._turn_seq - 1)
            events = tuple(e for e in since if e.turn_id == turn_id)
            view = HookContext(
                point,
                turn_id,
                events=events,
                content=texts,
                context_id=current().context_id or "main",
                language=self._language,
                **ctx,
            )
            self._hook_steps += 1
            step_id = f"{turn_id}.{current().context_id or 'main'}.h{self._hook_steps}"
            label = self._hook_label(hook.id)
            with scoped(step_id=step_id, brick="hooks", component=f"hooks.{hook.id}"):
                try:
                    result = hook.fn(view)
                except Exception as exc:  # noqa: BLE001 - AD-16
                    self._error(
                        Message("session.hooks.failed.message", label=label),
                        exc,
                        Message("session.hooks.failed.effect"),
                    )
                    continue
                if result is None:  # not concerned: nothing is emitted
                    continue
                if result.decision not in ALLOWED[point]:
                    self._error(
                        Message(
                            "session.hooks.not_allowed.message",
                            label=label,
                            decision=result.decision,
                            point=point,
                        ),
                        Message("session.hooks.not_allowed.cause"),
                        Message("session.hooks.not_allowed.effect"),
                    )
                    result = replace(result, decision="allow")
                journal.emit(
                    "hook_decided",
                    {
                        "hook": hook.id,
                        "point": point,
                        "decision": result.decision,
                        "detail_text": result.detail_text,
                        "hook_text": label,
                        "point_text": texts.points[point] if texts else point,
                    },
                )
                for effect in result.effects:  # AD-23: the session alone writes
                    if isinstance(effect, AuditAppend):
                        self._apply_audit(effect.lines)
            if result.decision == "block":
                return hook.id, result
            if result.decision == "ask_human":  # with the arguments modified before it
                call = ctx.get("call")
                return hook.id, replace(result, arguments=call.arguments if call else None)
            if result.decision == "modify":
                decided = (hook.id, result)
                if result.arguments is not None and ctx.get("call") is not None:
                    ctx["call"] = replace(ctx["call"], arguments=result.arguments)
        return decided

    def _apply_audit(self, lines: list[str]) -> None:
        """`AuditAppend`: appended to `audit.log` in the data folder (AD-20, AD-23)."""
        path = config.audit_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as file:
                file.write("".join(f"{line}\n" for line in lines))
        except OSError as exc:
            self._error(
                Message("session.hooks.audit_unwritable.message"),
                exc,
                Message("session.hooks.audit_unwritable.effect"),
            )
            return
        with scoped(component=AUDIT):
            self._journal().emit("effect_applied", {"effect": "audit_append", "lines": lines})

    def _apply_doc_loaded(self, tool: str, loaded_in_turn: list[str]) -> dict[str, Any]:
        """`ToolDocLoaded`: the documentation is loaded for the conversation and callable now.
        Returns what its reply step becomes: documentation of its server's tool (AD-4), and a
        stub in the history of the next turns."""
        with self._lock:
            self._loaded_docs.add(tool)
        if tool not in loaded_in_turn:
            loaded_in_turn.append(tool)
        spec = self._registry.get(tool)
        return {
            "kind": SegmentKind.TOOL_CATALOG,
            "brick": "mcp",
            "component": spec.component if spec else "core.harness",
            "stub": self._t("session.stubs.doc", tool=tool),
        }

    def _apply_skill_loaded(self, skill_id: str) -> dict[str, Any]:
        """`SkillLoaded`: the skill is loaded for the conversation. Its body answers the call
        in this turn and joins the system message from the next one, the history keeping a
        stub in its place (AD-25)."""
        with self._lock:
            self._loaded_skills.add(skill_id)
        self._emit_architecture()  # the node shows « chargé »
        return {
            "kind": SegmentKind.SKILL_BODY,
            "brick": "skills",
            "component": f"skills.{skill_id}",
            "stub": self._t("session.stubs.skill", skill=self._skill_label(skill_id)),
        }

    def _after_mcp_call(self, name: str, spec: ToolSpec) -> None:
        """A call that could not reach its server (transport, delay) makes it unavailable."""
        contact, why = self._tool_executor.contact.get(name, ("available", None))
        if contact == "unavailable":
            self._mcp_failed(spec.component.removeprefix("mcp."), why)

    def _new_call_id(self, step_id: str, index: int) -> str:
        """AD-4: the session's `tool_call_id`, checked unique within the turn."""
        call_ref = tool_call_id(step_id, index)
        if call_ref in self._call_ids:
            self._error(
                Message("session.call_id.message"),
                Message("session.call_id.cause", ref=f"{step_id}#{index}", call_ref=call_ref),
                Message("session.call_id.effect"),
            )
        self._call_ids.add(call_ref)
        return call_ref

    def _emit_limit(self, limit: str, n: int) -> None:
        self._journal().emit(
            "limit_reached",
            {"limit": limit, "message_text": self._t(f"session.limits.{limit}", n=n)},
        )

    def _check_prefix(self, previous_ids: list[int], raw: str, ids: list[int]) -> None:
        """AD-4: within a turn, call n+1 should extend call n and its output (append only)."""
        assert self._engine is not None
        expected = previous_ids + self._engine.tokenize(raw)
        common = _common_prefix(expected, ids)
        if common < len(expected):
            self._journal().emit(
                "prefix_not_reused",
                {
                    "common_tokens": common,
                    "cause": "in_turn",
                    "message_text": (
                        self._t(
                            "session.prefix.in_turn",
                            common=self._n(common),
                            expected=self._n(len(expected)),
                        )
                    ),
                },
            )

    def _keep_cache(self, ids: list[int], out: _ModelOutput | None) -> None:
        """Lot A (AD-4): after a call of the main context, the ids its engine holds: its own
        word when it gives it, else the ids sent followed by the output (the ids sent alone
        when the call failed)."""
        cached = _engine_cached_ids(self._engine)
        if cached is None:
            cached = list(ids)
            if out is not None and out.raw and self._engine is not None:
                try:
                    cached += self._engine.tokenize(out.raw)
                except Exception:  # noqa: BLE001 - a server gone: the ids sent alone
                    pass
        self._main_cache = cached
        self._cache_evicted = None  # the main context is back in the engine's cache
        self._turn_called = True

    def _check_reuse(
        self, rendered: RenderedContext, previous: tuple[list[int], str] | None
    ) -> None:
        """Lot A (AD-4, append only over the conversation): within a turn, `_check_prefix`;
        at a turn's first call, the ids the engine holds for the main context must be a
        prefix of the new ones, else `prefix_not_reused` with its cause; after a sub-agent
        whose context stayed in the engine's cache, `subagent` at the next call."""
        ids, evicted = rendered.ids, self._cache_evicted
        if previous is not None and evicted is None:
            self._check_prefix(*previous, ids)
            return
        cause = None
        if previous is None:  # the turn's first call: what happened since the last one
            cause, self._cache_cause = self._cache_cause, None
            if cause is None and self._last_status not in (None, "completed"):
                cause = "abandoned"
        if evicted is not None:  # the engine holds the sub-agent's context, not the main one
            cached = _engine_cached_ids(self._engine) or []
            cause = cause or "subagent"
        else:
            cached = self._main_cache
            if cached is None or ids[: len(cached)] == cached:
                return
        common = _common_prefix(cached, ids)
        cause = cause or self._diverging_cause(rendered, common)
        evicted_why = Message(f"session.prefix.evicted.{evicted}") if evicted else ""
        why = self._t(f"session.prefix.causes.{cause}", why=evicted_why)
        again = len(ids) - common
        hybrid = self._t("session.prefix.hybrid", tokens=self._n(len(ids)))
        if not again:  # the new ids end inside the cache: nothing new, but a cut
            tail = self._t(
                "session.prefix.in_cache",
                tokens=self._n(len(ids)),
                cached=self._n(len(cached)),
                hybrid=hybrid,
            )
        elif cached:
            tail = self._t(
                "session.prefix.partly",
                common=self._n(common),
                cached=self._n(len(cached)),
                again=self._n(again),
                end=hybrid if common else ".",
            )
        else:
            tail = self._t("session.prefix.all", again=self._n(again))
        self._journal().emit(
            "prefix_not_reused",
            {"common_tokens": common, "cause": cause, "message_text": why + tail},
        )

    def _diverging_cause(self, rendered: RenderedContext, common: int) -> str:
        """The cause named by the segment holding the first byte that differs: the system
        message (its texts and the template between them) `system`, `history`, or
        `template`."""
        assert self._engine is not None
        segments = rendered.segments
        if not segments:
            return "template"
        try:
            offset = len(b"".join(self._engine.token_pieces(rendered.ids[:common])))
        except Exception:  # noqa: BLE001 - AD-16: the cause stays unnamed
            return "template"
        ends = list(accumulate(len(s.text.encode("utf-8")) for s in segments))
        index = min(bisect.bisect_right(ends, offset), len(segments) - 1)
        # The system message: the leading run of its texts and of the template around them
        # (a skill or a documentation loaded in the turn comes later, after the history).
        system_end = None
        for i, segment in enumerate(segments):
            if segment.kind in _SYSTEM_KINDS:
                system_end = ends[i]
            elif segment.kind != SegmentKind.TEMPLATE:
                break
        if system_end is not None and offset <= system_end:
            return "system"
        return "history" if segments[index].kind in _CONVERSATION_KINDS else "template"

    def _emit_overflow(self, payload: dict[str, Any], raw_used: int | None = None) -> None:
        """`raw_used` (chat mode): the raw sum of the estimates, which decided the block
        (AD-4), cited « ≈ »."""
        used, usable = payload["used"], payload["usable"]
        shown = f"≈ {self._n(raw_used)}" if raw_used is not None else self._n(used)
        tokens = dict.fromkeys(_OVERFLOW_CAUSES, 0)
        for segment in payload["segments"]:
            kind = _OVERFLOW_GROUP.get(segment["kind"], segment["kind"])
            if kind in tokens:  # every kind but the template
                tokens[kind] += segment["tokens"]
        heaviest = max(tokens, key=tokens.__getitem__)  # ties: the message
        with self._lock:
            lazy = self._sent[4]  # the mode frozen for this turn by `send`
        full = heaviest == SegmentKind.TOOL_CATALOG and not lazy
        if full:
            cause = self._t("session.overflow.tool_catalog_full")
        elif heaviest == SegmentKind.TOOL_RESULT:
            cause = self._t(
                "session.overflow.causes.tool_result", compression=self._compression_hint_fr()
            )
        else:
            cause = self._t(f"session.overflow.causes.{heaviest.value}")
        if self._ratio_key() == "sub" and self._subagent_content is not None:
            cause = self._subagent_content.overflow_cause_text  # AD-11: the sub-agent's context
        self._journal().emit(
            "context_overflow",
            {
                "used": used if raw_used is None else raw_used,
                "usable": usable,
                "message_text": self._t(
                    "session.overflow.message",
                    shown=shown,
                    usable=self._n(usable),
                    window=self._n(payload["window"]),
                    reserve=self._n(payload["reserve"]),
                    cause=cause,
                ),
                "strategies_text": [
                    self._t(f"session.overflow.strategies.{s}") for s in _OVERFLOW_STRATEGIES
                ],
            },
        )

    def _compression_hint_fr(self) -> str:
        """Lot B: « allumez la compression » only when the brick is available and off."""
        if "compression" not in self._bricks or not self._availability("compression")[0]:
            return ""
        with self._lock:
            off = "compression" not in self._wanted
        return self._t("session.overflow.compression") if off else ""

    def _call_model(
        self,
        rendered: RenderedContext | RenderedChat,
        cancel: CancelToken,
        tools: tuple[str, ...],
        reserve: int,
        reasons: bool = False,
        sampling: Sampling | None = None,
        on_token: Callable[[Fragment, str, list[tuple[str, str]]], None] | None = None,
        candidates: int = 0,
    ) -> _ModelOutput:
        """One streamed call of at most `reserve` output tokens (AD-9); with tools on, its
        `<tool_call>` blocks are parsed, outside the reasoning (AD-6). `reasons`: the model
        reasons in this call (`_reasoning_on`), which the reasoning budget requires (lot C).
        Story 29, the « LLM nu » screen: `sampling` is passed to the engine only when given
        (an engine with four arguments stays valid), and `on_token(fragment, channel)` is
        called for each fragment that carries a token, with the splitter's parts of its text;
        the trace says which sampling."""
        assert self._engine is not None and self._caps is not None
        if isinstance(rendered, RenderedChat):
            return self._call_model_chat(rendered, cancel, reserve)
        # GreenOps: CodeCarbon started before the call, so that neither `prompt_ms` nor the
        # read rate counts its start; the whole machine for a served model (another process).
        # Stopped whatever happens (`stop` is idempotent: `end` stops it first).
        active = self._active  # read once, the model loaded now (a swap waits for idle)
        measure = self._local_meter.start(machine=active is not None and active.kind == "server")
        try:
            return self._call_model_local(
                rendered, cancel, tools, reserve, reasons, sampling, on_token, candidates, measure
            )
        finally:
            measure.stop()

    def _call_model_local(
        self,
        rendered: RenderedContext,
        cancel: CancelToken,
        tools: tuple[str, ...],
        reserve: int,
        reasons: bool,
        sampling: Sampling | None,
        on_token: Callable[[Fragment, str, list[tuple[str, str]]], None] | None,
        candidates: int,
        measure: Measure,
    ) -> _ModelOutput:
        """`_call_model` on a local engine, under its CodeCarbon `measure`."""
        assert self._engine is not None and self._caps is not None
        step_id = current().step_id or ""
        journal = self._journal()
        started = time.monotonic()
        journal.emit(
            "model_call_started",
            {
                "phase_label": self._t(
                    "session.reading_context", tokens=self._n(len(rendered.ids))
                ),
                "sampling": self._sampling_trace(sampling),
            },
        )
        extra: dict[str, Any] = {"sampling": sampling} if sampling is not None else {}
        if candidates:  # story 29, increment 4: the in-process engine only
            extra["candidates"] = candidates
        tags = self._caps.reasoning_tags
        splitter = ChannelSplitter(
            tags,
            in_reasoning=bool(tags) and rendered.prompt.rstrip().endswith(tags[0]),
            tool_tags=TOOL_CALL_TAGS if tools else None,
        )
        # Lot C (N4): a reasoning longer than the budget is closed by the harness, the rest
        # of the reserve going to the answer; only when the call reasons and the reserve
        # leaves the answer at least the floor.
        budget = self.cfg.reasoning_budget_tokens
        budget = budget if tags and reasons and reserve - budget >= MIN_REASONING_BUDGET else None
        # The last generation: its output tokens could reach `limit`, after `before` (AD-9).
        limit, before = reserve, 0
        raw: list[str] = []
        channels: dict[str, list[str]] = {"reasoning": [], "text": [], "tool_call": []}
        pending: list[tuple[str, str]] = []
        first_at: float | None = None
        last_flush = started
        output_tokens = 0
        reasoning_tokens = 0
        # The prompt tokens each generation evaluated, as its engine says (AD-4).
        evaluations: list[int | None] = []
        stop_reason = "stop"

        def flush() -> None:
            nonlocal last_flush
            while pending:
                channel = pending[0][0]
                text = ""
                while pending and pending[0][0] == channel:
                    text += pending.pop(0)[1]
                journal.emit("model_delta", {"channel": channel, "text": text}, actor="model")
            last_flush = time.monotonic()

        def take(parts: list[tuple[str, str]]) -> None:
            for channel, text in parts:
                channels[channel].append(text)
                pending.append((channel, text))

        def end(reason: str, tool_calls: list[ToolCall] = ()) -> None:
            ended = time.monotonic()
            first = first_at or ended
            gen_ms = _ms(ended - first)
            if not evaluations:  # the engine failed before any generation was read
                evaluations.append(_evaluated(self._engine))
            # A server's count comes in its last chunk, never read after a cut: the known ones.
            known = [n for n in evaluations if n is not None]
            evaluated = sum(known) if known else None
            if first_at is not None:  # story 26: the read of the first generation's prompt
                self._note_read_rate(evaluations[0], _ms(first - started))
            impact = measure.stop()  # GreenOps: its footprint, or why it has none...
            if reason == "error" and first_at is None:  # ...none for a call without output,
                impact = Impact(impact.method)  # as a cloud call refused before any
            journal.emit(
                "model_call_ended",
                {
                    "raw_output": "".join(raw),
                    "reasoning": "".join(channels["reasoning"]),
                    "text": "".join(channels["text"]),
                    "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in tool_calls],
                    "prompt_tokens": len(rendered.ids),
                    "output_tokens": output_tokens,
                    "prompt_ms": _ms(first - started),
                    "gen_ms": gen_ms,
                    "stop_reason": reason,
                    "duration_ms": _ms(ended - started),
                    "output_tps": output_tps(output_tokens, gen_ms),
                    "usage_source": "engine",
                    "evaluated_tokens": evaluated,
                }
                | impact.fields(),
                actor="model",
            )
            self._count_impact(impact)

        def generate(ids: list[int], max_tokens: int, cut_at: int | None) -> str:
            """One generation of the engine, its tokens counted after the ones before it;
            `cut`: the reasoning reached `cut_at` tokens without closing, the generation is
            stopped there (lot C)."""
            nonlocal first_at, output_tokens, reasoning_tokens
            assert self._engine is not None and self._caps is not None
            base, reason = output_tokens, "stop"
            pieces = False  # the engine gives each token's bytes (story 29)
            fragments = self._engine.complete(
                ids, self._caps.stop_sequences, max_tokens, cancel, **extra
            )
            try:
                for fragment in fragments:
                    produced = base + fragment.output_tokens
                    new, output_tokens = produced - output_tokens, produced
                    if first_at is None and output_tokens:
                        first_at = time.monotonic()
                        journal.emit("model_first_token", {}, actor="model")
                    raw.append(fragment.text)
                    before = splitter.channel
                    parts = splitter.feed(fragment.text)
                    take(parts)
                    # Story 29: one call per token. An engine that gives pieces ends with a
                    # fragment of held-back text only: not a token of its own.
                    pieces = pieces or fragment.piece is not None
                    carries = fragment.piece is not None if pieces else bool(fragment.text)
                    if on_token is not None and carries:
                        # The token's channel: its first part's, else where it started.
                        on_token(fragment, parts[0][0] if parts else before, parts)
                    if splitter.channel == "reasoning":
                        reasoning_tokens += new
                    if fragment.stop_reason:
                        reason = fragment.stop_reason
                    elif (
                        cut_at is not None
                        and reasoning_tokens >= cut_at
                        and fragment.text  # else the engine holds bytes back
                        and fragment.output_tokens < max_tokens  # else `length` follows
                        and splitter.channel == "reasoning"
                        and (
                            # never inside a closing tag, nor after a blank, which the
                            # history's render trims (AD-4)...
                            not splitter.holding
                            and not "".join(channels["reasoning"][-1:])[-1:].isspace()
                            # ...unless waiting would eat the answer's floor
                            or max_tokens - fragment.output_tokens <= MIN_REASONING_BUDGET
                        )
                    ):
                        reason = "cut"
                        break
                    if pending and time.monotonic() - last_flush >= DELTA_INTERVAL_S:
                        flush()
            finally:
                fragments.close()  # stops the engine's generation when cut (lot C)
                evaluations.append(_evaluated(self._engine))
            return reason

        try:
            stop_reason = generate(rendered.ids, reserve, budget)
            if stop_reason == "cut" and cancel.cancelled:
                stop_reason = "cancelled"
            elif stop_reason == "cut":
                assert budget is not None and tags  # a cut needs both
                closure = self._reasoning_closure(tags[1])
                ids = self._relaunch_ids(rendered.ids, "".join(raw), closure)
                # AD-9: the room left after the prompt, the output and the closure.
                limit = left = len(rendered.ids) + reserve - len(ids)
                before = output_tokens
                journal.emit(
                    "reasoning_cut",
                    {
                        "budget": budget,
                        "reasoning_tokens": reasoning_tokens,
                        "answer_reserve": left,
                        "message_text": self._t(
                            "session.reasoning.cut",
                            tokens=self._n(reasoning_tokens),
                            budget=self._n(budget),
                            tag=tags[1],
                            left=self._n(left),
                        ),
                    },
                )
                raw.append(closure)  # the closure, as if the model had written it (AD-4)
                take(splitter.feed(closure))
                flush()
                stop_reason = generate(ids, left, None)
            take(splitter.flush())
            flush()
        except ServerError as error:  # story 18: the local server stopped or refused
            flush()
            end("error")
            self._error(
                getattr(error, "message", None) or error.message_text,
                error.cause,
                Message("session.turn.over"),
            )
            return _ModelOutput("error")
        except Exception:
            flush()
            end("error")
            raise
        out = _ModelOutput(
            status="cancelled" if stop_reason == "cancelled" else "completed",
            raw="".join(raw),
            text="".join(channels["text"]),
            reasoning="".join(channels["reasoning"]),
            answer=splitter.outside,
        )
        if tools and out.status == "completed":
            assert self._caps.tool_call_parser is not None  # the brick requires it (AD-6)
            schemas = {name: spec.params for name in tools if (spec := self._registry.get(name))}
            out.calls, out.malformed = parse_tool_calls(
                out.answer,  # a `<tool_call>` inside the reasoning never counts (AD-6)
                self._caps.tool_call_parser,
                schemas,
            )
        if stop_reason != "length":
            out.ids = [self._new_call_id(step_id, j) for j in range(len(out.calls))]
        end(stop_reason, out.calls)

        if stop_reason == "length":
            journal.emit(
                "output_truncated",
                {
                    "channel": splitter.channel,
                    "output_tokens": output_tokens - before,
                    "max_tokens": limit,
                },
            )
            if splitter.channel != "tool_call":
                return _ModelOutput("limit")
            # AD-9: cut inside a tool call, the output follows the malformed-call path.
            fragment = out.malformed.fragment if out.malformed else out.raw
            out.calls, out.ids, out.malformed = (
                [],
                [],
                Malformed(fragment, Message("tools.parser.cut", limit=self._num_lazy(limit))),
            )
        return out

    def _reasoning_closure(self, closing_tag: str) -> str:
        """Lot C (N4): what the harness writes to close a reasoning cut at the budget, the
        text the template writes between reasoning and answer (`reasoning_wrap`, Qwen3.5:
        `"\\n</think>\\n\\n"`), so that the answer goes on as the template renders it (AD-4);
        else the closing tag followed by a blank line."""
        template = self._caps.chat_template if self._caps is not None else None
        wrap = reasoning_wrap(template) if template else None
        if wrap is not None and closing_tag in wrap[1]:
            return wrap[1]
        return closing_tag + "\n\n"

    def _relaunch_ids(self, prompt_ids: list[int], produced: str, closure: str) -> list[int]:
        """Lot C (AD-4): the ids of the relaunch after a cut reasoning. The engine's cached
        ids when they extend the prompt with bytes of what was produced, followed by the rest
        and the closure: nothing already evaluated is tokenized again, which a hybrid model
        would read again in full. Else the prompt followed by the output and the closure."""
        assert self._engine is not None
        cached = _engine_cached_ids(self._engine)
        if cached is not None and cached[: len(prompt_ids)] == prompt_ids:
            try:
                done = b"".join(self._engine.token_pieces(cached[len(prompt_ids) :]))
                data = produced.encode("utf-8")
                if data.startswith(done):
                    rest = data[len(done) :].decode("utf-8")  # a cut character: the fallback
                    return cached + self._engine.tokenize(rest + closure)
            except Exception:  # noqa: BLE001 - AD-16: the ids of the output instead
                pass
        return list(prompt_ids) + self._engine.tokenize(produced + closure)

    def _turn_cost(self) -> dict[str, Any]:
        """FinOps: `turn_ended`'s cost fields, the sums of the turn's cloud calls (sub-agent
        included); none when no call of the turn had a price."""
        costs = self._turn_costs
        if not costs:
            return {}
        return {
            "cost_in_usd": sum(c.input_usd for c in costs),
            "cost_out_usd": sum(c.output_usd for c in costs),
            "cost_source": "estimate" if any(c.source == "estimate" for c in costs) else "api",
        }

    def _turn_impact(self) -> dict[str, Any]:
        """GreenOps: `turn_ended`'s footprint fields, the sums of the turn's estimated
        footprints (min and max, sub-agent included); none when no call of the turn had one."""
        impacts = [i for i in self._turn_impacts if i.estimated]
        if not impacts:
            return {}
        return {
            "energy_wh_min": sum(i.energy_wh_min for i in impacts),
            "energy_wh_max": sum(i.energy_wh_max for i in impacts),
            "gco2e_min": sum(i.gco2e_min for i in impacts),
            "gco2e_max": sum(i.gco2e_max for i in impacts),
        }

    def _count_impact(self, impact: Impact) -> None:
        """GreenOps: a local call's estimated footprint joins the session's registry (then
        `consumption_updated`) and, within a turn, the turn's sums; a local call costs
        nothing."""
        if not impact.estimated:
            return
        if current().turn_id is not None:  # the « LLM nu » screen has no turn
            self._turn_impacts.append(impact)
        journal = self._journal()
        record_spend(
            None,
            self.cfg.eur_per_usd,
            lambda spend: journal.emit("consumption_updated", spend),
            impact=impact,
        )

    def consumption(self) -> dict[str, Any] | None:
        """FinOps, `/api/state`: the session's API spend (and GreenOps footprint) as the last
        `consumption_updated` says it, for a reloaded page; `None` before the first paid call
        or call with a footprint."""
        return session_spend(self.cfg.eur_per_usd)

    def _call_model_chat(
        self, rendered: RenderedChat, cancel: CancelToken, reserve: int
    ) -> _ModelOutput:
        """AD-5, chat mode: the body sent as is, under `origin = model`; a provider's refusal
        becomes `harness_error` (AD-16); `usage` reconciles the gauge (AD-4)."""
        entry = self._cloud
        assert entry is not None
        journal = self._journal()
        scope = current()
        step_id = scope.step_id or ""
        total = round(rendered.raw_total * self._ratio)
        in_sub = self._ratio_key() == "sub"
        try:
            with scoped(origin="model"):  # AD-15: traced with the call's scope, key masked
                call = run_call(
                    self._engine,
                    ChatBody(rendered.body.encode("utf-8")),
                    cancel,
                    phase_label=self._t(
                        "session.cloud.sending_context",
                        provider=entry.provider,
                        tokens=self._n(total),
                    ),
                    estimated_prompt=total,
                    chars_per_token=self.cfg.chars_per_token,
                    call_id=lambda index: self._new_call_id(step_id, index),
                    sampling_trace=self._sampling_trace(None),
                    eur_per_usd=self.cfg.eur_per_usd,
                )
        except ProviderError as error:
            if error.cost is not None:  # FinOps: an output had come, the call is billed
                self._turn_costs.append(error.cost)
            if error.impact is not None and error.impact.estimated:  # GreenOps, likewise
                self._turn_impacts.append(error.impact)
            effect_text = Message("delegation.error.effect" if in_sub else "session.turn.over")
            journal.emit("harness_error", error.payload(effect_text, lang=self._language))
            return _ModelOutput("error", message_text=error.message_text)
        if call.cost is not None:
            self._turn_costs.append(call.cost)
        if call.impact is not None and call.impact.estimated:  # GreenOps
            self._turn_impacts.append(call.impact)
        prompt_tokens = int((call.usage or {}).get("prompt_tokens") or 0)
        if prompt_tokens:  # AD-4: `usage` is the total; the ratio learns from real calls only
            payload = self._chat_gauge(rendered, prompt_tokens, "api", reserve)
            journal.emit("context_reconciled", payload | {"call_id": scope.call_id or ""})
            if rendered.raw_total:
                self._ratio = min(1.5, max(0.8, prompt_tokens / rendered.raw_total))
        if call.stop_reason == "cancelled":
            return _ModelOutput("cancelled")
        out = _ModelOutput(
            "completed",
            text=call.text,
            reasoning=call.reasoning,
            reconciled=payload if prompt_tokens else None,
        )
        # AD-10: what a malformed output reinjects: `failed_generation`, else the text and
        # each call's name and arguments as emitted.
        out.raw = "\n".join(
            [call.text, *(f"{c['name']} {c['arguments']}" for c in call.calls)]
        ).strip()
        if call.malformed is not None:
            out.raw, detail = call.malformed
            out.malformed = Malformed(out.raw, detail)
        elif call.stop_reason == "stop":
            out.calls = [
                ToolCall(c["name"], c["parsed"], f"{c['name']} {c['arguments']}")
                for c in call.calls
            ]
            out.ids = [c["id"] for c in call.calls]
            out.arguments = [c["arguments"] for c in call.calls]
            out.extras = [c.get("extra_content") for c in call.calls]
            out.extra_for = entry.id
        if call.stop_reason == "length":
            journal.emit(
                "output_truncated",
                {
                    "channel": call.channel,
                    "output_tokens": call.output_tokens,
                    "max_tokens": reserve,
                },
            )
            if call.channel != "tool_call":  # the reconciled figures stay (AD-4)
                return _ModelOutput("limit", reconciled=out.reconciled)
            out.calls, out.ids, out.arguments, out.extras = [], [], [], []
            out.malformed = Malformed(
                out.raw, Message("tools.parser.cut", limit=self._num_lazy(reserve))
            )
        return out

    # ---------- story 29: the « LLM nu » screen (context `llm`, no turn) ----------

    @staticmethod
    def _lab_scope(request_id: str, call: bool = False) -> dict[str, Any]:
        """The screen's trace scope: context `llm`, no turn, `step_id` (and, for a model call,
        `call_id`) `llm{n}`; the workshop's projections ignore it (story 29)."""
        return {
            "turn_id": None,
            "context_id": "llm",
            "step_id": request_id,
            "call_id": request_id if call else None,
            "parent_step": None,
            "brick": None,
            "component": None,
            "edge": None,
        }

    def _lab_content(self) -> tuple[llm_lab.LabContent | None, str | None]:
        """`content/llm_lab.yaml`, or why it cannot be read (AD-19): traced as `harness_error`
        once per message, the page staying served."""
        try:
            return self._localized(llm_lab.load_lab_content), None
        except Exception as exc:  # noqa: BLE001 - AD-16: an invalid file never breaks the page
            error_text = self._t("session.llm_lab.content_invalid")
            cause = f"{type(exc).__name__}: {exc}"
            if self._lab_error_traced != cause:
                self._lab_error_traced = cause
                with scoped(**self._lab_scope("llm")):
                    self._error(
                        error_text, cause, Message("session.llm_lab.content_invalid_effect")
                    )
            llm_lab.load_lab_content.cache_clear()  # corrected, the file is read again
            detail = (str(exc).splitlines() or [type(exc).__name__])[0][:200]
            return None, self._t("session.detail", text=error_text, detail=detail)

    def _tokenizer_state(self) -> dict[str, Any]:
        """Whether the active model's tokenizer cuts exactly here, and why in French."""
        with self._lock:
            engine, cloud, active = self._engine, self._cloud, self._active
        if engine is None:
            return {
                "exact": False,
                "reason_text": self._t("session.llm_lab.tokenizer.none"),
            }
        if cloud is not None:
            return {
                "exact": False,
                "reason_text": self._t(
                    "session.llm_lab.tokenizer.cloud", model=cloud.model, provider=cloud.provider
                ),
            }
        if active is not None and active.kind == "server":
            how = Message(
                "session.llm_lab.tokenizer.llama_server"
                if active.provider == "llama-server"
                else "session.llm_lab.tokenizer.ollama"
            )
            return {
                "exact": True,
                "reason_text": self._t("session.llm_lab.tokenizer.exact", how=how),
            }
        return {"exact": True, "reason_text": self._t("session.llm_lab.tokenizer.exact_loaded")}

    def lab_state(self) -> dict[str, Any]:
        """`GET /api/llm_lab` (story 29, AD-1): what the page needs before the stream, from
        `seq` on: its texts (or why not), the active model, the session's state and the
        tokenizer's exactness."""
        tip = self._journal().last_seq()
        content, error_text = self._lab_content()
        with self._lock:
            state, reason_text = self.state, self.reason_text
        return {
            "content": content.model_dump() if content is not None else None,
            "content_error_text": error_text,
            "active_model": self.active_model(),
            "session_state": {"state": state, "reason_text": reason_text},
            "tokenizer": self._tokenizer_state(),
            "sampling": self._lab_sampling(),
            "last_load": self._last_load(tip),
            "reasoning": self._lab_reasoning(),
            "candidates": self._lab_candidates(),
            "seq": tip,
        }

    def _lab_request(self) -> str:
        """A screen request's id, `llm{n}`: accepted in `idle` with a model only (AD-3)."""
        with self._lock:
            if self.state != "idle" or self._engine is None or self.reason_text:
                raise SendRefused(self._refusal_reason())
            self._labs += 1
            return f"llm{self._labs}"

    def llm_tokenize(self, text: str) -> str:
        """Intention `llm_tokenize` (story 29): the raw text, without template, cut by the
        active model's tokenizer on the worker; the state does not change. Refused outside
        `idle` (`SendRefused`). Returns the request's id; `llm_tokenized` answers it."""
        request_id = self._lab_request()
        self._executor.submit(self._run_lab_tokenize, request_id, text)
        return request_id

    def _run_lab_tokenize(self, request_id: str, text: str) -> None:
        with scoped(**self._lab_scope(request_id)):
            try:
                payload = LlmTokenizedPayload.model_validate(
                    in_language(self._lab_tokenized(request_id, text), self._language)
                )
                self._journal().emit("llm_tokenized", payload.model_dump(mode="json"))
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(
                    exc.message_text
                    if isinstance(exc, ServerError)
                    else Message("session.llm_lab.tokenize_failed"),
                    exc,
                    Message("session.llm_lab.nothing_changed"),
                )

    def _lab_tokenized(self, request_id: str, text: str) -> dict[str, Any]:
        with self._lock:
            engine, cloud = self._engine, self._cloud
        model = self.active_model() or {}
        base = {
            "request_id": request_id,
            "text": text,
            "char_count": len(text),
            "model_label": model.get("label") or "",
            "hosting": model.get("hosting") or "local",
            "tokenizer_text": self._tokenizer_state()["reason_text"],
            "figures_text": {"char_count": llm_lab.lang_int(len(text), self._language)},
        }
        if engine is None:
            raise RuntimeRefused("session.llm_lab.no_model")
        if cloud is not None:
            estimate = config.estimate_tokens(text, self.cfg.chars_per_token)
            ratio = f"{self.cfg.chars_per_token:g}"
            ratio = ratio if self._language == "en" else ratio.replace(".", ",")
            return base | {
                "exact": False,
                "tokens": [],
                "token_count": None,
                "estimate": estimate,
                "chars_per_token": self.cfg.chars_per_token,
                "figures_text": base["figures_text"]
                | {
                    "estimate": llm_lab.lang_int(estimate, self._language),
                    "chars_per_token": ratio,
                },
                "unavailable_text": base["tokenizer_text"],
                "dimensions": None,
                "dimensions_text": self._t(
                    "session.llm_lab.dimensions_cloud", provider=cloud.provider
                ),
            }
        ids = engine.tokenize(text)
        shown = ids[: llm_lab.TOKEN_LIMIT]
        rows, more = llm_lab.token_rows(
            ids, engine.token_pieces(shown), engine.metadata().special_tokens
        )
        dimensions = self._lab_dimensions(engine)
        return base | {
            "exact": True,
            "tokens": rows,
            "token_count": len(ids),
            "more": more,
            "figures_text": base["figures_text"]
            | {
                "token_count": llm_lab.lang_int(len(ids), self._language),
                "more": llm_lab.lang_int(more, self._language),
            },
            "dimensions": dimensions,
            "dimensions_text": llm_lab.dimensions_fr(dimensions, lang=self._language),
        }

    def _lab_dimensions(self, engine: Any) -> dict[str, Any]:
        """The model's sizes (story 29): the engine's own answer when it has `dimensions`,
        else the GGUF header of the file loaded; tolerated absent or failing (AD-16)."""
        source_text = self._t("session.llm_lab.dimensions_unknown")
        dims: dict[str, Any] | None = None
        read = getattr(engine, "dimensions", None)
        if read is not None:
            try:
                dims = read()
            except Exception:  # noqa: BLE001 - unknown sizes, never a failure
                dims = None
        if dims:
            source_text = str(dims.get("source_text") or source_text)
        else:
            with self._lock:
                active = self._active
            if active is not None and active.kind == "file":
                header = gguf_meta.try_read_metadata(active.ref)
                if header:
                    dims = gguf_meta.dimensions_from_header(header)
                    source_text = self._t("session.llm_lab.dimensions_gguf")
        return llm_lab.dimensions_payload(dims, source_text, lang=self._language)

    # ---------- story 29, increment 2: sampling, prompt reading, token by token ----------

    # The sampling settings, their names in `messages.yaml` (`session.llm_lab.sampling`).
    _SAMPLING_NAMES = ("temperature", "top_k", "top_p", "min_p")

    def _sampling_trace(self, sampling: Sampling | None) -> dict[str, Any]:
        """`model_call_started.sampling` (story 29): a local engine always takes the four
        values, the harness's (`harness`) or the screen's (`screen`); a cloud model takes
        only what its entry declares, and only from the screen, else nothing is sent and the
        provider keeps its own (`provider`)."""
        cloud = self._cloud
        if cloud is None:
            chosen = sampling or DEFAULT_SAMPLING
            return {
                "temperature": chosen.temperature,
                "top_k": chosen.top_k,
                "top_p": chosen.top_p,
                "min_p": chosen.min_p,
                "source": "screen" if sampling is not None else "harness",
                "note_text": None,
            }
        sent = list(cloud.sampling) if sampling is not None else []
        values = {
            name: (getattr(sampling, name) if name in sent else None)
            for name in self._SAMPLING_NAMES
        }
        if not sent:
            return values | {
                "source": "provider",
                "note_text": self._t(
                    "session.llm_lab.sampling.by_provider", provider=cloud.provider
                ),
            }
        missing = [self._sampling_name(n) for n in self._SAMPLING_NAMES if n not in sent]
        names = join(missing, self._language)
        return values | {
            "source": "screen",
            "note_text": self._t(
                "session.llm_lab.sampling.not_settable",
                names=names[:1].upper() + names[1:],
                provider=cloud.provider,
            ),
        }

    def _sampling_name(self, name: str) -> str:
        return self._t(f"session.llm_lab.sampling.names.{name}")

    def _sampling_fr(self, sampling: Sampling) -> str:
        """« T 0,7 · top-k 20 · top-p 0,8 · min-p 0 » (a decimal point in English)."""

        def num(value: float) -> str:
            text = f"{value:g}"
            return text if self._language == "en" else text.replace(".", ",")

        return (
            f"T {num(sampling.temperature)} · top-k {sampling.top_k} · "
            f"top-p {num(sampling.top_p)} · min-p {num(sampling.min_p)}"
        )

    def _lab_sampling(self) -> dict[str, Any]:
        """`lab_state().sampling`: the harness's values, the bounds, and, for each setting,
        why it cannot be set (`None`: it can)."""
        with self._lock:
            cloud = self._cloud
        supported: dict[str, str | None] = dict.fromkeys(self._SAMPLING_NAMES)
        if cloud is None:
            source_text = self._t("session.llm_lab.sampling.local")
        else:
            for name in supported:
                if name in cloud.sampling:
                    continue
                label = self._sampling_name(name)
                label = label[:1].upper() + label[1:]
                supported[name] = self._t(
                    "session.llm_lab.sampling.no_api"
                    if name in ("top_k", "min_p")
                    else "session.llm_lab.sampling.not_declared",
                    label=label,
                    provider=cloud.provider,
                )
            source_text = self._t(
                "session.llm_lab.sampling.cloud", model=cloud.model, provider=cloud.provider
            )
        return {
            "defaults": asdict(DEFAULT_SAMPLING),
            "defaults_text": self._t(
                "session.llm_lab.sampling.defaults", values=self._sampling_fr(DEFAULT_SAMPLING)
            ),
            "bounds": {name: list(b) for name, b in SAMPLING_BOUNDS.items()},
            "supported": supported,
            "source_text": source_text,
        }

    @staticmethod
    def _last_load(tip: int) -> list[dict[str, Any]]:
        """Story 29: the envelopes of the last model load up to `tip` (started, its steps,
        ended), read in the journal."""
        events = [e for e in get_journal().all_events() if e.seq <= tip]
        start = next(
            (i for i in range(len(events) - 1, -1, -1) if events[i].kind == "model_load_started"),
            None,
        )
        if start is None:
            return []
        kinds = ("model_load_started", "model_load_step", "model_load_ended")
        return [e.model_dump(mode="json") for e in events[start:] if e.kind in kinds]

    def _lab_reasoning(self) -> dict[str, Any]:
        """Story 29: how the active model reasons (`reasoning_mode`, the reasoning card's own
        rules), the budget (local mode) and the reserve."""
        with self._lock:
            caps, cloud, window = self._caps, self._cloud, self._window
        return self._reasoning_info(caps, cloud, window)

    def _reasoning_info(
        self, caps: Capabilities | None, cloud: CloudModel | None, window: int
    ) -> dict[str, Any]:
        mode, reason_text = reasoning_mode(caps, window if caps is not None else None)
        local = cloud is None and caps is not None and caps.reasoning_tags is not None
        return {
            "mode": mode,
            "reason_text": reason_text,
            "budget": self.cfg.reasoning_budget_tokens if local else None,
            "budget_text": self._reasoning_budget_fr(),
            "reserve": MAX_RESERVE,
        }

    def llm_generate(
        self,
        prompt: str,
        sampling: Sampling,
        reasoning: bool = False,
        candidates: bool = False,
    ) -> str:
        """Intention `llm_generate` (story 29, class b): accepted in `idle` only, switched to
        `llm_lab` under the lock in this call, then run on the worker; « Arrêter » stops it
        (class c). `reasoning`: refused when the model cannot reason (mode `never` or
        `unknown`), forced when it always does. Returns the request's id."""
        with self._memory_lock, self._lock:
            if self.state != "idle" or self._engine is None or self.reason_text:
                raise SendRefused(self._refusal_reason())
            # Checked under the lock: no model switch can come in between.
            lab = self._reasoning_info(self._caps, self._cloud, self._window)
            if reasoning and lab["mode"] in ("never", "unknown"):
                raise SendRefused(
                    Message(
                        "session.llm_lab.no_reasoning",
                        reason=lab["reason_text"] or Message("session.llm_lab.cannot_reason"),
                    )
                )
            offer = self._candidates_info(self._active, self._cloud, self._engine)
            if candidates and not offer["available"]:
                raise SendRefused(offer["reason_text"])
            self._labs += 1
            request_id = f"llm{self._labs}"
            cancel = self._cancel = CancelToken()
            self.state, self.reason_text = "llm_lab", _LAB_FR
        self._emit_state()
        self._executor.submit(
            self._run_lab, request_id, prompt, sampling, reasoning, cancel, candidates
        )
        return request_id

    def _lab_candidates(self) -> dict[str, Any]:
        """`lab_state().candidates` (story 29, increment 4): the candidates' probabilities are
        read in the in-process engine only (a file), with why elsewhere."""
        with self._lock:
            active, cloud, engine = self._active, self._cloud, self._engine
        return self._candidates_info(active, cloud, engine)

    @staticmethod
    def _candidates_info(
        active: ModelChoice | None, cloud: CloudModel | None, engine: Any
    ) -> dict[str, Any]:
        reason: str | None = None
        if engine is None or active is None:
            reason = Message("session.llm_lab.candidates.no_model")
        elif cloud is not None:
            reason = Message("session.llm_lab.candidates.cloud", provider=cloud.provider)
        elif active.kind == "server":
            reason = Message("session.llm_lab.candidates.server", provider=active.provider)
        return {"available": reason is None, "reason_text": reason, "n": CANDIDATES}

    def _run_lab(
        self,
        request_id: str,
        prompt: str,
        sampling: Sampling,
        reasoning: bool,
        cancel: CancelToken,
        candidates: bool = False,
    ) -> None:
        """One user message rendered by the model's template (AD-4), no brick, no history;
        the local call through `_call_model` (one `llm_token` per token), the cloud call
        through `run_call` directly (no `context_reconciled`, no `_ratio`). The main
        context's engine state is saved around it, else the next turn says why it reads
        again (`llm`). The workshop's conversation is never touched."""
        started = time.monotonic()
        journal = self._journal()
        ended: dict[str, Any] = {"request_id": request_id, "status": "error"}
        counts = {"reasoning": 0, "text": 0, "tool_call": 0}
        cloud_used = False
        touched, saved = False, None
        index = 0

        def token(
            text: str,
            token_id: int | None,
            channel: str,
            read: Any = None,
            parts: list[tuple[str, str]] | None = None,
        ) -> None:
            """One `llm_token`: `text` for its chip (its bytes when they are part of a
            character), `parts` the decoded text by channel, tags dropped (the lanes)."""
            nonlocal index
            counts[channel] = counts.get(channel, 0) + 1
            payload = LlmTokenPayload(
                request_id=request_id,
                index=index,
                token_id=token_id,
                text=text,
                channel=channel,  # type: ignore[arg-type]
                elapsed_ms=_ms(time.monotonic() - started),
                candidates=list(read) if read else None,
                parts=[{"channel": c, "text": t} for c, t in (parts or [])],
            )
            journal.emit("llm_token", payload.model_dump(mode="json"), actor="model")
            index += 1

        def local_token(fragment: Fragment, channel: str, parts: list[tuple[str, str]]) -> None:
            text = llm_lab.piece_text(fragment.piece) if fragment.piece else fragment.text
            token(text, fragment.token_id, channel, fragment.candidates, parts)

        with scoped(**self._lab_scope(request_id, call=True), origin="model", trigger="user"):
            try:
                with self._lock:
                    engine, caps, cloud = self._engine, self._caps, self._cloud
                    window = self._window
                assert engine is not None and caps is not None
                reasons = reasoning or caps.reasoning_always
                reserve = output_reserve(reasons)
                trace = self._sampling_trace(sampling)
                message = [{"role": "user", "content": Part(SegmentKind.USER_MESSAGE, prompt)}]
                if cloud is None:
                    meta = engine.metadata()
                    template_vars: dict[str, Any] = {}
                    if caps.reasoning_variable:
                        template_vars[caps.reasoning_variable] = reasons
                    rendered: RenderedContext | RenderedChat = render_context(
                        engine,
                        caps.chat_template or "",
                        message,
                        call_id=request_id,
                        special_tokens=meta.special_tokens,
                        bos_token=meta.bos_token,
                        eos_token=meta.eos_token,
                        add_generation_prompt=True,
                        **template_vars,
                        lang=self._language,
                    )
                    text, tokens, exact = rendered.prompt, len(rendered.ids), True
                    phase = self._t("session.llm_lab.reading", tokens=self._n(tokens))
                    with self._lock:
                        served = self._active is not None and self._active.kind == "server"
                    unit = "fragment" if served else "token"
                else:
                    content = self._cloud_content or self._localized(load_cloud_content)
                    rendered = render_chat_body(
                        message,
                        None,
                        call_id=request_id,
                        fields=chat_fields(cloud, reserve, reasons, sampling),
                        markers=self.cfg.cloud_markers,
                        estimate=lambda t: config.estimate_tokens(t, self.cfg.chars_per_token),
                        provider_label_text=content.provider_segment_text,
                        lang=self._language,
                    )
                    text, tokens, exact = rendered.body, rendered.raw_total, False
                    unit = "fragment"
                    phase = self._t(
                        "session.llm_lab.sending", provider=cloud.provider, tokens=self._n(tokens)
                    )
                usable = window - reserve
                figures = {"prompt_tokens": ("" if exact else "≈ ") + self._n(tokens)}
                started_payload = LlmGenerationStartedPayload(
                    request_id=request_id,
                    prompt=prompt,
                    rendered=text,
                    prompt_tokens=tokens,
                    exact=exact,
                    sampling=trace,  # type: ignore[arg-type]
                    reserve=reserve,
                    reasoning=reasons,
                    phase_label=phase,
                    unit=unit,
                    figures_text=figures | {"reserve": self._n(reserve), "usable": self._n(usable)},
                )
                journal.emit("llm_generation_started", started_payload.model_dump(mode="json"))
                if tokens > usable:
                    ended["message_text"] = self._t(
                        "session.llm_lab.too_long",
                        tokens=figures["prompt_tokens"],
                        usable=self._n(usable),
                        window=self._n(window),
                        reserve=self._n(reserve),
                    )
                    return
                mark = journal.last_seq()
                if cloud is None:
                    saved, touched = self._save_main_state(), True
                    out = self._call_model(
                        rendered,
                        cancel,
                        (),
                        reserve,
                        reasons=reasons,
                        sampling=sampling,
                        on_token=local_token,
                        candidates=CANDIDATES if candidates else 0,
                    )
                    ended["status"] = out.status
                else:
                    cloud_used = True
                    ended["status"] = self._lab_cloud_call(
                        rendered, cancel, cloud, tokens, trace, token, ended, request_id
                    )
                call = next(
                    (
                        e.payload
                        for e in reversed(journal.events_since(mark))
                        if e.kind == "model_call_ended" and e.step_id == request_id
                    ),
                    None,
                )
                evaluated = call.get("evaluated_tokens") if call else None
                prompt_ms = call.get("prompt_ms") if call else None
                if evaluated and prompt_ms:
                    ended["read_tps"] = round(evaluated / (prompt_ms / 1000), 1)
            except Exception as exc:  # noqa: BLE001 - AD-16: the screen's call never breaks
                ended["status"] = "error"
                ended["message_text"] = (
                    (getattr(exc, "message", None) or exc.message_text)
                    if isinstance(exc, ServerError)
                    else Message("session.llm_lab.interrupted")
                )
                self._error(
                    ended["message_text"],
                    exc,
                    Message("session.llm_lab.still_usable"),
                )
            finally:
                try:
                    if touched:
                        self._lab_restore(saved)
                    ended["reasoning_tokens"] = counts["reasoning"]
                    ended["answer_tokens"] = counts["text"] + counts.get("tool_call", 0)
                    ended["duration_ms"] = _ms(time.monotonic() - started)
                    approx = "≈ " if cloud_used else ""
                    ended["figures_text"] = {
                        "reasoning_tokens": approx + self._n(ended["reasoning_tokens"]),
                        "answer_tokens": approx + self._n(ended["answer_tokens"]),
                    } | (
                        {"read_tps": self._decimal(f"{ended['read_tps']:g}")}
                        if ended.get("read_tps")
                        else {}
                    )
                    payload = LlmGenerationEndedPayload.model_validate(
                        in_language(ended, self._language)
                    )
                    journal.emit("llm_generation_ended", payload.model_dump(mode="json"))
                except Exception as exc:  # noqa: BLE001 - AD-16: the state still comes back
                    self._error(
                        Message("session.llm_lab.end_untraced"),
                        exc,
                        Message("session.llm_lab.back_to_idle"),
                    )
                finally:
                    with self._lock:
                        self._cancel = None
                    # Out of the lab's scope: the workshop's projections read it (context
                    # `None`, as every session state out of a turn).
                    with scoped(
                        **self._lab_scope(request_id) | {"context_id": None, "step_id": None}
                    ):
                        self._set_state("idle")

    def _lab_cloud_call(
        self,
        rendered: RenderedChat,
        cancel: CancelToken,
        cloud: CloudModel,
        tokens: int,
        trace: dict[str, Any],
        token: Callable[[str, int | None, str], None],
        ended: dict[str, Any],
        request_id: str,
    ) -> str:
        """The screen's cloud call: `run_call` directly (neither `context_reconciled` nor the
        estimate's ratio: the workshop's gauge learns nothing from it), each fragment the
        provider sends one `llm_token`. Returns the generation's status."""
        engine = _TokenTap(
            self._engine, lambda channel, text: token(text, None, channel, None, [(channel, text)])
        )
        try:
            call = run_call(
                engine,
                ChatBody(rendered.body.encode("utf-8")),
                cancel,
                phase_label=self._t(
                    "session.llm_lab.sending", provider=cloud.provider, tokens=self._n(tokens)
                ),
                estimated_prompt=tokens,
                chars_per_token=self.cfg.chars_per_token,
                call_id=lambda index: f"{request_id}.{index}",
                sampling_trace=trace,
                eur_per_usd=self.cfg.eur_per_usd,
            )
        except ProviderError as error:
            self._journal().emit(
                "harness_error",
                error.payload(Message("session.llm_lab.stops"), lang=self._language),
            )
            ended["message_text"] = error.message_text
            return "error"
        return {"stop": "completed", "cancelled": "cancelled", "length": "limit"}.get(
            call.stop_reason, "error"
        )

    def _lab_restore(self, saved: EngineSnapshot | None) -> None:
        """The main context's engine state back after the screen's local call (AD-11's copy);
        without it, the next turn's first call says the screen took the cache (`llm`)."""
        if self._cloud is not None:
            return
        if self._restore_main_state(saved, 1) is not None:
            return
        if self._main_cache is None:  # no main context in the cache: nothing was evicted
            self._cache_evicted = None
            return
        self._cache_cause = self._cache_cause or "llm"

    # ---------- story 30: the RAG workshop (context `rag_lab`, no turn) ----------

    @staticmethod
    def _rag_lab_scope(step_id: str, component: str | None, brick: str | None = "rag") -> dict:
        """The workshop's trace scope: context `rag_lab`, no turn; the workshop's own
        components (`rag_lab.{kind}`), which the schema does not draw."""
        return {
            "turn_id": None,
            "context_id": "rag_lab",
            "call_id": None,
            "step_id": step_id,
            "parent_step": None,
            "brick": brick,
            "component": component,
            "edge": None,
            "actor": "harness",
            "trigger": "user",
        }

    def _rag_lab_content(self) -> tuple[rag_lab.RagLabContent | None, str | None]:
        """`content/rag_lab.yaml`, or why it cannot be read (AD-19): traced as `harness_error`
        once per message (outside the RAG brick: its card does not show it), the page staying
        served."""
        try:
            return self._localized(rag_lab.load_lab_content), None
        except Exception as exc:  # noqa: BLE001 - AD-16: an invalid file never breaks the page
            error_text = self._t("session.rag_lab.content_invalid")
            cause = f"{type(exc).__name__}: {exc}"
            if self._rag_lab_error_traced != cause:
                self._rag_lab_error_traced = cause
                with scoped(**self._rag_lab_scope("rag_lab", None, brick=None)):
                    self._error(
                        error_text, cause, Message("session.rag_lab.content_invalid_effect")
                    )
            rag_lab.load_lab_content.cache_clear()  # corrected, the file is read again
            detail = (str(exc).splitlines() or [type(exc).__name__])[0][:200]
            return None, self._t("session.detail", text=error_text, detail=detail)

    def _rag_lab_catalog(self, texts: rag_lab.RagLabContent) -> rag_lab.Catalog:
        """The options the workshop offers, named after the brick's models, with what a run
        would meet now: the embedding model's files, the brick's index, the reranker's files
        (the reasons of `_rag_unavailable` and `_rerank_availability`, read afresh)."""
        model, content = self._rag_model, self._rag_content
        options: dict[tuple[str, str], rag_lab.OptionState] = {}
        for kind, names in rag_lab.OPTIONS.items():
            for name in names:
                options[(kind, name)] = rag_lab.OptionState(texts.options[kind][name].label_text)
        embedding = options[("embedding", "declared")]
        store = options[("vector_store", "sqlite_vec")]
        if model is None or content is None:
            embedding.note_text = self._content_errors.get("rag") or Message(
                "session.rag.not_configured"
            )
        else:
            embedding.label_text = model.label_text
            _, index_error, _, _, _, missing_text = self._rag_index_state(model, content)
            embedding.note_text = missing_text
            store.note_text = index_error
        rerank = options[("rerank", "declared")]
        if self._rerank_model is not None:
            rerank.label_text = self._rerank_model.label_text
        rerank.note_text = self._rerank_static_reason()
        fastembed = options[("embedding", "fastembed")]
        declared, reason = self._rag_lab_fastembed()
        if declared is not None:
            fastembed.label_text = declared.label_text
        fastembed.available, fastembed.reason_text = declared is not None, reason
        for option, (module, _) in rag_lab.LIBRARIES.items():
            state = options[("vector_store", option)]
            if option in self._rag_lab_import_errors:
                state.available, state.reason_text = False, self._rag_lab_import_errors[option]
            elif option not in self._rag_lab_imported and not rag_lab.installed(module):
                state.available, state.reason_text = False, rag_lab.not_installed_fr(option)
        return rag_lab.Catalog(
            texts, rag_lab.default_pipeline(self.cfg), options, lang=self._language
        )

    def _rag_lab_fastembed(self) -> tuple[config.FastembedModel | None, str | None]:
        """Story 30: the fastembed option, offered only installed, declared and on the
        workstation (it is never downloaded), else why not."""
        if not rag_lab.installed("fastembed"):
            return None, Message("session.rag_lab.fastembed_missing")
        model, error = self.cfg.rag_lab_fastembed
        if model is None:
            return None, error
        if "fastembed" in self._rag_lab_import_errors:
            return None, self._rag_lab_import_errors["fastembed"]
        folder = embedding_module.fastembed_dir() / model.folder_name
        if not folder.is_dir() or not any(folder.rglob("*.onnx")):
            return None, Message("session.rag_lab.fastembed_files", folder=folder)
        return model, None

    def rag_lab_state(self) -> dict[str, Any]:
        """`GET /api/rag_lab` (story 30, AD-1): what the page needs before the stream, from
        `seq` on: the catalog and the shipped chain, its texts (or why not), the last run
        read in the journal and the session's state."""
        journal = self._journal()
        tip = journal.last_seq()
        texts, error_text = self._rag_lab_content()
        catalog = self._rag_lab_catalog(texts) if texts is not None else None
        with self._lock:
            state, reason_text = self.state, self.reason_text
        events = [e for e in journal.all_events() if e.seq <= tip]
        return {
            "catalog": catalog.payload() if catalog is not None else None,
            "default_pipeline": rag_lab.default_pipeline(self.cfg).model_dump(),
            "content": texts.model_dump() if texts is not None else None,
            "content_error_text": error_text,
            "unavailable_text": self._rag_lab_unavailable(),
            "last_run": rag_lab.last_run(events),
            "session_state": {"state": state, "reason_text": reason_text},
            "seq": tip,
        }

    def _rag_lab_unavailable(self) -> str | None:
        """Why no chain can run at all: the RAG brick's corpus and texts are unreadable."""
        if self._rag_content is None:
            return self._content_errors.get("rag") or Message("session.rag_lab.corpus_unreadable")
        return None

    def run_rag_lab(self, question: str, pipelines: list[rag_lab.Pipeline] | None = None) -> str:
        """Intention `rag_lab_run` (story 30, class b): accepted in `idle` only (a reason
        there, such as no model loaded, does not matter: nothing is generated), switched to
        `rag_lab` under the lock in this call, then run on the worker; « Arrêter » (class c)
        stops it between two stages, passages or candidates. A chain the workshop refuses:
        `SendRefused` with the reason, nothing emitted. Returns the run's id, `lab{n}`."""
        texts, error_text = self._rag_lab_content()
        if texts is None:
            raise SendRefused(error_text or Message("session.rag_lab.texts_unreadable"))
        unavailable = self._rag_lab_unavailable()
        if unavailable is not None:
            raise SendRefused(unavailable)
        catalog = self._rag_lab_catalog(texts)
        chains = list(pipelines) if pipelines else [catalog.default]
        if len(chains) > rag_lab.LANES_MAX:
            raise SendRefused(Message("session.rag_lab.two_chains"))
        for chain in chains:
            reason = rag_lab.validate_pipeline(chain, catalog)
            if reason is not None:
                if len(chains) > 1:
                    reason = Message("session.rag_lab.lane", chain=chain.label_text, reason=reason)
                raise SendRefused(reason)
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            previous = self.reason_text
            self._rag_labs += 1
            run_id = f"lab{self._rag_labs}"
            cancel = self._cancel = CancelToken()
            self.state, self.reason_text = "rag_lab", _RAG_LAB_FR
        self._emit_state()
        self._executor.submit(
            self._run_rag_lab, run_id, question, chains, texts, catalog, cancel, previous
        )
        return run_id

    def _rag_lab_recent_catalog(self, texts: rag_lab.RagLabContent) -> rag_lab.Catalog:
        """The catalog read from the disk (index, model files, installed libraries) at most
        `RAG_LAB_CATALOG_TTL_S` ago: a chain edited field by field is checked without reading
        the disk again each time. A run reads it afresh."""
        now = time.monotonic()
        kept = self._rag_lab_catalog_kept
        if kept is not None and kept[1] is texts and now - kept[0] < RAG_LAB_CATALOG_TTL_S:
            return kept[2]
        catalog = self._rag_lab_catalog(texts)
        self._rag_lab_catalog_kept = (now, texts, catalog)
        return catalog

    def validate_rag_lab(self, pipelines: list[rag_lab.Pipeline]) -> dict[str, Any]:
        """`POST /api/rag_lab/validate` (story 30, increment 4), read only: the reason each
        chain would be refused for, and the stage at fault, so that the page says it on the
        stage's card before « Lancer » (AD-1: the rules are the session's)."""
        texts, error_text = self._rag_lab_content()
        if texts is None:
            reason = error_text or Message("session.rag_lab.texts_unreadable")
            return {
                "valid": False,
                "refusals": [{"lane": None, "stage_id": None, "reason_text": reason}],
            }
        catalog = self._rag_lab_recent_catalog(texts)
        refusals = []
        for lane, chain in zip("ab", pipelines, strict=False):
            refusal = rag_lab.check_pipeline(chain, catalog)
            if refusal is not None:
                refusals.append({"lane": lane, "stage_id": refusal[1], "reason_text": refusal[0]})
        return {"valid": not refusals, "refusals": refusals}

    def _run_rag_lab(
        self,
        run_id: str,
        question: str,
        chains: list[rag_lab.Pipeline],
        texts: rag_lab.RagLabContent,
        catalog: rag_lab.Catalog,
        cancel: CancelToken,
        previous: str | None,
    ) -> None:
        """On the worker, in series with the turns and `_sync_rag`: a model the brick holds
        cannot be closed meanwhile. What the run loads is closed and freed at its end (AD-8),
        and the session goes back to `idle` with the reason it had."""
        loans = rag_lab.Loans(self._load_registry)
        lab_run: rag_lab.LabRun | None = None
        try:
            content = self._rag_content
            model = self._rag_model
            index_error = None
            if model is not None and content is not None:
                index_error = self._rag_index_state(model, content)[1]
            assert content is not None  # checked when the intention was accepted
            deps = rag_lab.LabDeps(
                content=content,
                texts=texts,
                catalog=catalog,
                shipped_chunk_max_chars=self.cfg.rag_chunk_max_chars,
                brick_index=self._rag_index_path(),
                brick_index_error=index_error,
                lab_dir=config.rag_lab_dir(),
                embedder=lambda option: self._rag_lab_embedder(option, loans),
                identity=self._rag_lab_identity,
                importer=self._rag_lab_import,
                reranker=lambda option: self._rag_lab_reranker(option, loans),
                cancelled=lambda: cancel.cancelled,
                emit=self._rag_lab_emit,
                rss=self._rss_now,
                lang=self._language,
            )
            lab_run = rag_lab.LabRun(run_id, question, chains, deps)
            lab_run.run()
        except Exception as exc:  # noqa: BLE001 - AD-16: the state still comes back
            with scoped(**self._rag_lab_scope(run_id, "rag_lab", brick=None)):
                self._error(
                    Message("session.rag_lab.interrupted"),
                    exc,
                    Message("session.llm_lab.back_to_idle"),
                )
            if lab_run is not None and not lab_run.ended:
                try:  # the page never stays « en cours »
                    lab_run.end("error", 0)
                except Exception:  # noqa: BLE001, S110 - the error above says it already
                    pass
        finally:
            errors = loans.close()
            if errors:
                with scoped(**self._rag_lab_scope(run_id, "rag_lab", brick=None)):
                    self._error(
                        Message("session.rag_lab.close_failed.message"),
                        " ; ".join(str(e) for e in errors),
                        Message("session.rag_lab.close_failed.effect"),
                    )
            with self._lock:
                self._cancel = None
            self._set_state("idle", previous)

    def _rag_lab_emit(
        self, kind: str, payload: dict[str, Any], step_id: str, component: str
    ) -> None:
        model = PAYLOAD_MODELS[kind]
        with scoped(**self._rag_lab_scope(step_id, component)):
            payload = in_language(payload, self._language)
            self._journal().emit(kind, model.model_validate(payload).model_dump(mode="json"))

    def _rag_lab_embedder(self, option: str, loans: rag_lab.Loans) -> rag_lab.Lent:
        """The brick's embedding model, borrowed when it holds it, else loaded as
        `_load_embedder` loads it (budget, declared sha256, factory) and closed at the run's
        end; its errors are said in the stage, never as `harness_error`."""
        if option == "fastembed":
            return self._rag_lab_fastembed_lent(loans)
        model = self._rag_model
        if option != "declared" or model is None:
            raise rag_lab.StageFailed(
                self._content_errors.get("rag") or Message("session.rag_lab.no_embedding")
            )
        with self._lock:
            borrowed = self._embedder
        missing = download_module.missing_files(model.files, config.models_dir())
        unavailable = None
        if missing:
            names = ", ".join(PurePosixPath(f.path).name for f in missing)
            unavailable = Message(
                "session.rag_lab.embedding_absent", names=names, folder=config.models_dir()
            )

        def open_model() -> Embedder:
            path = embedding_module.model_path(model)
            declared = model.load_file.sha256
            if declared and rag_index.file_sha256(path) != declared.lower():
                raise ValueRefused("session.rag.sha256", path=path, section="rag.embedding")
            return self._embedder_factory(model)

        return loans.lend(
            borrowed=borrowed,
            label_text=model.label_text,
            noun_text=Message("session.rag_lab.noun.embedding"),
            unavailable_text=unavailable,
            cost=self._load_registry.component_cost(
                model.measured_rss_mb, [f.size for f in model.files]
            ),
            slot=EMBEDDING,
            open_model=open_model,
        )

    def _rag_lab_fastembed_lent(self, loans: rag_lab.Loans) -> rag_lab.Lent:
        """The fastembed model, loaded for the run in its own slot (the brick's embedding
        slot may be held), within the budget, then closed."""
        model, reason = self._rag_lab_fastembed()
        if model is None:
            raise rag_lab.StageFailed(reason or Message("session.rag_lab.fastembed_unavailable"))
        self._rag_lab_import("fastembed")  # the library, counted for life (AD-8)
        folder = embedding_module.fastembed_dir() / model.folder_name
        sizes = [p.stat().st_size for p in folder.rglob("*") if p.is_file()]
        return loans.lend(
            borrowed=None,
            label_text=model.label_text,
            noun_text=Message("session.rag_lab.noun.embedding"),
            unavailable_text=None,
            cost=self._load_registry.component_cost(None, sizes),
            slot=RAG_LAB_EMBEDDING,
            open_model=lambda: embedding_module.FastembedEmbedder(model.model_name, model.dims),
        )

    def _rag_lab_import(self, option: str) -> rag_lab.Imported:
        """FAISS, LanceDB or fastembed, imported once for the life of WaveStack (AD-8): the
        budget first (`[rag_lab] faiss_cost_mb`, `lancedb_cost_mb`, `fastembed_cost_mb`),
        then the import and its grant in its own slot, never released. A failed import (a DLL
        blocked by AppLocker, a broken install) is said in French, recorded, and the option
        becomes unavailable."""
        module_name, label, slot, cost = {
            "faiss": ("faiss", "FAISS", RAG_LAB_FAISS, self.cfg.rag_lab_faiss_cost_bytes),
            "lancedb": ("lancedb", "LanceDB", RAG_LAB_LANCEDB, self.cfg.rag_lab_lancedb_cost_bytes),
            "fastembed": (
                "fastembed",
                "fastembed",
                RAG_LAB_FASTEMBED,
                self.cfg.rag_lab_fastembed_cost_bytes,
            ),
        }[option]
        if option in self._rag_lab_import_errors:
            raise rag_lab.StageFailed(self._rag_lab_import_errors[option])
        if option in self._rag_lab_imported:
            added = self._rag_lab_imported[option]
            said = (
                Message("session.rag_lab.import.first_added", size=self._mo_lazy(added))
                if added is not None
                else Message("session.rag_lab.import.no_measure")
            )
            return rag_lab.Imported(
                importlib.import_module(module_name),
                [
                    (
                        self._t("session.rag_lab.import.label"),
                        self._t("session.rag_lab.import.already", said=said),
                    )
                ],
            )
        refusal = self._load_registry.check_component(label, cost, slot)
        if refusal is not None:
            raise rag_lab.StageFailed(refusal)
        before = self._rss_now()
        try:
            module = importlib.import_module(module_name)
        except (ImportError, OSError) as exc:
            reason = Message(
                "session.rag_lab.import.refused", label=label, kind=type(exc).__name__, cause=exc
            )
            self._rag_lab_import_errors[option] = reason
            raise rag_lab.StageFailed(reason) from exc
        except Exception as exc:  # noqa: BLE001 - a broken install (numpy ABI…), said once
            reason = Message(
                "session.rag_lab.import.failed",
                label=label,
                kind=type(exc).__name__,
                cause=exc,
                install=rag_lab.INSTALL_FR,
            )
            self._rag_lab_import_errors[option] = reason
            raise rag_lab.StageFailed(reason) from exc
        after = self._rss_now()
        added = after - before if before is not None and after is not None else None
        self._load_registry.grant(label, cost, slot)
        self._rag_lab_imported[option] = added
        said = (
            Message("session.rag_lab.import.added", size=self._mo_lazy(added))
            if added is not None
            else Message("session.rag_lab.import.no_measure")
        )
        return rag_lab.Imported(
            module,
            [
                (
                    self._t("session.rag_lab.import.label"),
                    self._t("session.rag_lab.import.first", said=said),
                ),
                (
                    self._t("session.rag_lab.import.budget_label"),
                    self._t("session.rag_lab.import.budget", size=self._mo_lazy(cost)),
                ),
            ],
        )

    def _rag_lab_identity(self, option: str) -> dict[str, Any]:
        """What identifies an embedding model, the key of the workshop's vector cache: its id,
        its dimensions, its file's size and sha256 (declared, else computed once)."""
        if option == "fastembed":
            model, _ = self._rag_lab_fastembed()
            assert model is not None  # the stage loaded it
            size, sha = rag_lab.folder_identity(
                embedding_module.fastembed_dir() / model.folder_name
            )
            return {"id": model.model_name, "dims": model.dims, "size": size, "sha256": sha}
        model = self._rag_model
        assert model is not None  # the stage loaded it
        declared = model.load_file
        sha = declared.sha256 or rag_lab.file_digest(embedding_module.model_path(model))
        return {"id": model.id, "dims": model.dims, "size": declared.size, "sha256": sha.lower()}

    def _rag_lab_reranker(self, option: str, loans: rag_lab.Loans) -> rag_lab.Lent:
        """The brick's reranker, borrowed or loaded as `_load_reranker` loads it; without its
        declaration or its file, the stage is skipped and the chain goes on."""
        model = self._rerank_model
        if option != "declared" or model is None:
            raise rag_lab.StageSkipped(
                self._rerank_config_error or Message("session.rag_lab.no_reranker")
            )
        with self._lock:
            borrowed = self._reranker
        missing = download_module.missing_files(model.files, config.models_dir())
        unavailable = None
        if missing:
            names = ", ".join(PurePosixPath(f.path).name for f in missing)
            unavailable = Message(
                "session.rag_lab.reranker_absent", names=names, folder=config.models_dir()
            )

        def open_model() -> Reranker:
            path = reranker_module.model_path(model)
            declared = model.load_file.sha256
            if declared and rag_index.file_sha256(path) != declared.lower():
                raise ValueRefused("session.rag.sha256", path=path, section="rag.reranker")
            return self._reranker_factory(model)

        return loans.lend(
            borrowed=borrowed,
            label_text=model.label_text,
            noun_text=Message("session.rag_lab.noun.reranking"),
            unavailable_text=unavailable,
            cost=self._load_registry.component_cost(
                model.measured_rss_mb, [f.size for f in model.files]
            ),
            slot=RERANKER,
            open_model=open_model,
            soft=True,
        )

    # ---------- corrections of 2026-09-30, story 6: the MCP workshop (context `mcp_lab`) ----

    @staticmethod
    def _mcp_lab_scope(step_id: str, server_id: str | None) -> dict[str, Any]:
        """The workshop's trace scope: context `mcp_lab`, no turn, brick `mcp`, the
        workshop's own component (`mcp_lab.{server}`), which the schema does not draw."""
        return {
            "turn_id": None,
            "context_id": "mcp_lab",
            "call_id": None,
            "step_id": step_id,
            "parent_step": None,
            "brick": "mcp",
            "component": f"mcp_lab.{server_id}" if server_id else "mcp_lab",
            "edge": None,
            "actor": "harness",
            "trigger": "user",
        }

    def _mcp_lab_content(self) -> tuple[mcp_lab.McpLabContent | None, str | None]:
        """`content/mcp_lab.yaml`, or why it cannot be read (AD-19): traced as `harness_error`
        once per cause, the page staying served."""
        try:
            return self._localized(mcp_lab.load_lab_content), None
        except Exception as exc:  # noqa: BLE001 - AD-16: an invalid file never breaks the page
            error_text = self._t("session.mcp_lab.content_invalid")
            cause = f"{type(exc).__name__}: {exc}"
            if self._mcp_lab_error_traced != cause:
                self._mcp_lab_error_traced = cause
                with scoped(**self._mcp_lab_scope("mcp_lab", None)):
                    self._error(
                        error_text, cause, Message("session.mcp_lab.content_invalid_effect")
                    )
            mcp_lab.load_lab_content.cache_clear()  # type: ignore[attr-defined]
            detail = (str(exc).splitlines() or [type(exc).__name__])[0][:200]
            return None, self._t("session.detail", text=error_text, detail=detail)

    def _mcp_lab_servers(self) -> list[dict[str, Any]]:
        """The three servers of `content/mcp.yaml`, as section 1 draws them."""
        content = self._mcp_content
        servers = []
        for server_id, server in self._mcp_servers.items():
            text = content.servers.get(server_id) if content else None
            servers.append(
                {
                    "id": server_id,
                    "label_text": text.label_text if text else server_id,
                    "transport": mcp_lab.transport_of(server),
                    "url": server.url,
                    "command": mcp_lab.launch_command(server, self._language),
                    "network": server.network,
                    "sends_text": text.sends_text if text else None,
                }
            )
        return servers

    def mcp_lab_state(self) -> dict[str, Any]:
        """`GET /api/mcp_lab` (story 6, AD-1): what the page needs before the stream, from
        `seq` on: the servers, the texts (or why not), the call presets, the server the
        workshop's connection is open to, the last connection's envelopes and the state."""
        journal = self._journal()
        tip = journal.last_seq()
        texts, error_text = self._mcp_lab_content()
        with self._lock:
            state, reason_text = self.state, self.reason_text
            conn, first = self._mcp_lab_conn, self._mcp_lab_first
        events = [e for e in journal.all_events() if e.seq <= tip]
        presets = self._mcp_content.call_presets if self._mcp_content else {}
        return {
            "servers": self._mcp_lab_servers(),
            "content": texts.model_dump() if texts is not None else None,
            "content_error_text": error_text,
            "call_presets": {
                name: [p.model_dump() for p in entries] for name, entries in presets.items()
            },
            "open_server": conn.server.id if conn is not None and conn.alive else None,
            "last_session": mcp_lab.last_session(events, first),
            "session_state": {"state": state, "reason_text": reason_text},
            "seq": tip,
        }

    def _mcp_lab_begin(self) -> tuple[str, CancelToken, str | None]:
        """Under the lock: `idle` only (else `SendRefused` with the reason), then the state
        `mcp_lab`, a new exchange `mcp{n}` and its `CancelToken`."""
        if self.state != "idle":
            raise SendRefused(self._refusal_reason())
        previous = self.reason_text
        self._mcp_labs += 1
        cancel = self._cancel = CancelToken()
        self.state, self.reason_text = "mcp_lab", _MCP_LAB_FR
        return f"mcp{self._mcp_labs}", cancel, previous

    def mcp_lab_connect(self, server_id: str) -> str:
        """Intention `mcp_lab_connect` (story 6, class b): accepted in `idle` only, the
        session in `mcp_lab` until the handshake ends; the workshop's own connection, never
        the brick's (`_mcp_conns`, `_mcp_enabled` and `_mcp_lazy` untouched). `KeyError` for
        an unknown server. Returns the exchange's id, `mcp{n}`."""
        if server_id not in self._mcp_servers:
            raise KeyError(server_id)
        texts, error_text = self._mcp_lab_content()
        if texts is None:
            raise SendRefused(error_text or Message("session.mcp_lab.texts_unreadable"))
        with self._lock:
            step_id, cancel, previous = self._mcp_lab_begin()
            self._mcp_lab_first = self._mcp_labs
        self._emit_state()
        self._executor.submit(self._run_mcp_lab_connect, step_id, server_id, cancel, previous)
        return step_id

    def _run_mcp_lab_connect(
        self, step_id: str, server_id: str, cancel: CancelToken, previous: str | None
    ) -> None:
        """On the worker: the previous connection closed, the new one opened on the loop, its
        handshake captured message by message (`mcp_lab_message`), then the tools and their
        weight (`mcp_lab_connect_ended`); back to `idle` with the reason it had."""
        server = self._mcp_servers[server_id]
        started = time.monotonic()
        tools: list[Any] | None = None
        error_text: Any = None
        conn: mcp_lab.LabConnection | None = None
        try:
            self._mcp_lab_drop(wait=True)
            loop = self._loop
            if loop is None:
                error_text = Message("session.mcp.no_loop")
            else:

                def emit(payload: dict[str, Any], step: str) -> None:
                    self._mcp_lab_emit("mcp_lab_message", payload, step, server_id)

                scope = TraceScope(**self._mcp_lab_scope(step_id, server_id), origin="brick")
                conn = mcp_lab.LabConnection(
                    server,
                    loop,
                    capture=mcp_lab.Capture(emit),
                    scope=scope,
                    connect_timeout=self.cfg.mcp_connect_timeout_s,
                    call_timeout=self.cfg.mcp_call_timeout_s,
                    language=self._language,
                )
                conn.begin(step_id)
                with self._lock:
                    self._mcp_lab_conn = conn
                if cancel.cancelled:  # stopped before the connection was known
                    raise ConnectionError(step_id)
                future = asyncio.run_coroutine_threadsafe(conn.start(), loop)
                try:
                    tools = future.result(self.cfg.mcp_connect_timeout_s + MCP_LAB_CLOSE_WAIT_S)
                except BaseException:
                    future.cancel()
                    raise
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, said in section 2
            tools = None
            if cancel.cancelled:
                error_text = Message("session.mcp_lab.stopped")
            elif error_text is None:
                error_text = describe_error(exc, self.cfg.mcp_connect_timeout_s)
        try:
            if tools is None:
                self._mcp_lab_drop(conn, wait=True)
                payload: dict[str, Any] = {
                    "server": server_id,
                    "status": "error",
                    "error_text": error_text,
                }
            else:
                assert conn is not None
                with self._lock:
                    self._mcp_lab_tools = {tool.name: tool for tool in tools}
                payload = {"server": server_id, "status": "ok"} | self._mcp_lab_weights(
                    server, conn, tools
                )
            payload["duration_ms"] = _ms(time.monotonic() - started)
            self._mcp_lab_emit("mcp_lab_connect_ended", payload, step_id, server_id)
        except Exception as exc:  # noqa: BLE001 - AD-16: the state still comes back
            with scoped(**self._mcp_lab_scope(step_id, server_id)):
                self._error(
                    Message("session.mcp_lab.interrupted"),
                    exc,
                    Message("session.llm_lab.back_to_idle"),
                )
        finally:
            with self._lock:
                self._cancel = None
            self._set_state("idle", previous)

    def _mcp_lab_weights(
        self, server: Any, conn: mcp_lab.LabConnection, tools: list[Any]
    ) -> dict[str, Any]:
        """Story 6: what the server's documentation weighs in the context. Each tool's
        definition as `_tool_definitions` renders it (its exposed name `{server}__{tool}`, its
        schema, its description: the brick's `_mcp_spec`, the registry's `definition`), in
        documentation complète; in lazy loading, its line of `load_tool_doc`'s catalog
        (`_doc_catalog`) plus `load_tool_doc`'s own definition. Counted by the engine when one
        is loaded, else estimated (`_count_tokens`). Nothing is registered in the brick's
        registry: a registry of the workshop's own computes the definitions."""
        specs = [self._mcp_spec(server, conn, tool) for tool in tools]
        load_spec = self._load_tool_doc_spec() if self._mcp_content is not None else None
        registry = ToolRegistry([*specs, *([load_spec] if load_spec else [])])
        estimated = False

        def count(text: str) -> int:
            nonlocal estimated
            tokens, rough = self._count_tokens(text)
            estimated = estimated or rough
            return tokens

        listed, lines = [], []
        for spec, tool in zip(specs, tools, strict=True):
            name = ToolRegistry.exposed_name(spec)
            definition_text = json.dumps(registry.definition(name), ensure_ascii=False)
            line_text = mcp_lab.catalog_line(name, spec.description, DOC_LINE_MAX)
            lines.append(line_text)
            listed.append(
                {
                    "name": name,
                    "tool": tool.name,
                    "description": spec.description or "",
                    "schema": spec.schema or {},
                    "definition_text": definition_text,
                    "doc_tokens": count(definition_text),
                    "line_text": line_text,
                    "line_tokens": count(line_text),
                }
            )
        figures: dict[str, Any] = {
            "tools": listed,
            "full_tokens": sum(t["doc_tokens"] for t in listed),
        }
        if load_spec is not None:
            bare = registry.definition(LOAD_TOOL_DOC)
            lazy = json.loads(json.dumps(bare))
            lazy["function"]["description"] = "\n".join([load_spec.description or "", *lines])
            lazy_text = json.dumps(lazy, ensure_ascii=False)
            figures |= {
                "load_tool_doc_tokens": count(json.dumps(bare, ensure_ascii=False)),
                "lazy_definition_text": lazy_text,
                "lazy_tokens": count(lazy_text),
            }
        figures["estimated"] = estimated
        return figures

    def mcp_lab_call(self, server_id: str, tool: str, args: dict[str, Any]) -> str:
        """Intention `mcp_lab_call` (story 6, class b): a tool of the server the workshop is
        connected to, called through the workshop's connection; accepted in `idle` only, the
        session in `mcp_lab` until the answer. `KeyError` for an unknown server; `SendRefused`
        without a connection to it or for a tool it did not list. Returns `mcp{n}`."""
        if server_id not in self._mcp_servers:
            raise KeyError(server_id)
        label = self._mcp_label(server_id)
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            conn = self._mcp_lab_conn
            if conn is None or conn.server.id != server_id or not conn.alive:
                raise SendRefused(Message("session.mcp_lab.not_connected", server=label))
            if tool not in self._mcp_lab_tools:
                raise SendRefused(Message("session.mcp_lab.unknown_tool", server=label, tool=tool))
            step_id, cancel, previous = self._mcp_lab_begin()
        self._emit_state()
        self._executor.submit(
            self._run_mcp_lab_call, step_id, conn, tool, dict(args), cancel, previous
        )
        return step_id

    def _run_mcp_lab_call(
        self,
        step_id: str,
        conn: mcp_lab.LabConnection,
        tool: str,
        args: dict[str, Any],
        cancel: CancelToken,
        previous: str | None,
    ) -> None:
        """On the worker: `tools/call` captured both ways, then its raw answer and the text
        the harness would reinject (`result_text`, then `_bound_result`), or why not: an
        `is_error` answer, a JSON-RPC error, an unreachable server, a delay exceeded."""
        server_id = conn.server.id
        started = time.monotonic()
        payload: dict[str, Any] = {"server": server_id, "tool": tool, "status": "error"}
        try:
            conn.begin(step_id)
            try:
                result = conn.call_result(tool, args)
            except MCPError as exc:
                payload["raw"] = conn.capture.received("tools/call")
                if exc.code == CONNECTION_CLOSED:
                    payload["error_text"] = describe_error(exc, self.cfg.mcp_call_timeout_s)
                else:  # a JSON-RPC error answer (invalid arguments): the server is there
                    payload["error_text"] = Message("mcp.error.call_refused", cause=exc.message)
            except Exception as exc:  # noqa: BLE001 - AD-16: said in section 4
                if cancel.cancelled:
                    payload["error_text"] = Message("session.mcp_lab.stopped")
                elif isinstance(exc, ConnectionError):
                    payload["error_text"] = Message("session.mcp_lab.closed")
                else:
                    payload["error_text"] = describe_error(exc, self.cfg.mcp_call_timeout_s)
            else:
                payload["raw"] = conn.capture.received("tools/call")
                text = result_text(result, self._language)
                if result.is_error:
                    payload["text"] = text
                    payload["error_text"] = Message("session.mcp_lab.is_error")
                else:
                    payload["text"], payload["truncated"] = self._bound_result(text)
                    payload["status"] = "ok"
            if cancel.cancelled or not conn.alive:  # stopped, or the server is gone
                self._mcp_lab_drop(conn, wait=True)
            payload["duration_ms"] = _ms(time.monotonic() - started)
            self._mcp_lab_emit("mcp_lab_call_ended", payload, step_id, server_id)
        except Exception as exc:  # noqa: BLE001 - AD-16: the state still comes back
            with scoped(**self._mcp_lab_scope(step_id, server_id)):
                self._error(
                    Message("session.mcp_lab.interrupted"),
                    exc,
                    Message("session.llm_lab.back_to_idle"),
                )
        finally:
            with self._lock:
                self._cancel = None
            self._set_state("idle", previous)

    def _mcp_lab_emit(
        self, kind: str, payload: dict[str, Any], step_id: str, server_id: str
    ) -> None:
        """A `mcp_lab_*` event, validated by its model (`PAYLOAD_MODELS`), its texts in the
        session's language. Also called on the loop, by the capture of the messages."""
        model = PAYLOAD_MODELS[kind]
        with scoped(**self._mcp_lab_scope(step_id, server_id)):
            payload = in_language(payload, self._language)
            self._journal().emit(kind, model.model_validate(payload).model_dump(mode="json"))

    def _mcp_lab_drop(self, conn: Any = None, *, wait: bool = True) -> None:
        """Close the workshop's connection (`conn`: that one, the open one or not): at the
        next connection, at « Arrêter », at a change of language and at the session's close.
        The local server's process ends with it (AD-21). `wait` never on the loop's thread."""
        with self._lock:
            if conn is not None and conn is not self._mcp_lab_conn:
                closing = conn
            else:
                closing, self._mcp_lab_conn = self._mcp_lab_conn, None
                self._mcp_lab_tools = {}
        if closing is not None:
            closing.close(wait=wait)

    def _mcp_lab_stop(self) -> bool:
        """`stop` (class c) in `mcp_lab`: the exchange's token armed and the connection
        closed at once (the token alone cannot interrupt an await on the loop)."""
        with self._lock:
            if self.state != "mcp_lab":
                return False
            if self._cancel is not None:
                self._cancel.cancel()
            conn = self._mcp_lab_conn
        if conn is not None:
            conn.close(wait=False)
        return True
