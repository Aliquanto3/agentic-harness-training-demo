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
from wavestack.mcp.connection import McpConnection, describe_error
from wavestack.mcp.servers import McpContent, load_mcp_content, mcp_servers
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
    RERANKER,
    LoadRegistry,
    ModelChoice,
    process_rss,
)
from wavestack.models.openai_chat import (
    ChatBody,
    OpenAIChatEngine,
    ProviderError,
    output_tps,
    run_call,
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
from wavestack.tools.native import NATIVE_TOOLS
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
from wavestack.trace.scope import current, scoped

DELTA_INTERVAL_S = 0.05  # AD-2: model_delta grouped every 50 ms at most
LOAD_TOOL_DOC = "load_tool_doc"  # the harness meta-tool of the lazy loading mode (AD-25)
DOC_LINE_MAX = 120  # characters of a tool's first description line in `load_tool_doc`
LOAD_SKILL = "load_skill"  # the harness meta-tool of the skills brick (AD-25)
REMEMBER = "remember"  # the harness meta-tool of the global memory brick (AD-25)
MEMORY = "file.memory"  # the schema node of `memory.json` (AD-12, AD-23)
DELEGATE = "delegate"  # the harness meta-tool of the subagent brick (AD-11, AD-25)
_NO_SUB_TEXT_FR = "(Le sous-agent n'a rendu aucun texte.)"
RAG_INDEX = "file.rag_index"  # the schema node of the RAG index (story 15, AD-12)
# Lot G: the card's reason when another program keeps the index open (Windows).
INDEX_HELD_FR = (
    "un autre programme garde l'index ouvert (un antivirus, un outil de synchronisation ou "
    "le script de construction) : fermez-le, puis cliquez de nouveau sur « Construire "
    "l'index »"
)
RAG_TARGET = "rag_embedding"  # a `download_model` target: the embedding model (story 15)
RERANK_TARGET = "rag_reranker"  # the other one: the reranking model (story 16)
RAG_RERANKER = "rag.reranker"  # the reranker's schema node (story 16, AD-12)

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

_TURN_FR = "Un tour est en cours : attendez sa fin ou arrêtez-le."
# Lot A (AD-4): why a turn's first call does not extend what the engine holds in cache.
_PREFIX_CAUSES_FR = {
    "system": (
        "Le message système a changé depuis le tour précédent (prompt système, mémoire "
        "globale, descriptions d'outils, catalogue de skills ou skill chargé)."
    ),
    "history": (
        "L'historique n'est plus rendu tel que le modèle l'a lu (mémoire courte éteinte : "
        "l'échange précédent n'est pas renvoyé ; extraits RAG retirés, documentation "
        "remplacée par son talon, texte compressé ou réponse réécrite)."
    ),
    "template": (
        "Une brique activée ou désactivée, ou le gabarit, rend autrement une partie du "
        "contexte déjà lue."
    ),
    "reset": (
        "La conversation a été vidée, ou un scénario ou la réinitialisation l'a remplacée : "
        "le cache du moteur contient encore l'ancienne."
    ),
    "replay": (
        "Rejeu : le tour repart de l'état qui précédait le tour rejoué, alors que le cache "
        "du moteur contient ce tour."
    ),
    "abandoned": (
        "Le tour précédent n'a pas abouti (arrêté, en erreur, bloqué ou dépassé) : sa "
        "sortie est dans le cache du moteur, pas dans l'historique."
    ),
    "subagent": "Le sous-agent a occupé le cache du moteur{why}.",
    # Story 29: a generation of the « LLM nu » screen, between two turns.
    "llm": "L'écran « LLM nu » a occupé le cache du moteur{why}.",
}
_LAB_FR = "L'écran « LLM nu » génère une réponse : attendez sa fin ou arrêtez-la."
_RAG_LAB_FR = "Atelier RAG : exécution en cours ; attendez sa fin ou arrêtez-la."
CANDIDATES = 5  # story 29: the candidates read with each token, the one drawn added if apart
_SUBAGENT_EVICTED_FR = {
    "stateless": " : ce moteur ne sait pas sauvegarder l'état du contexte principal",
    "failed": " : la sauvegarde ou la restauration de l'état du contexte principal a échoué",
}
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
_AWAITING_FR = "En attente de votre validation : autorisez ou refusez l'appel réseau."
_NO_MODEL_FR = (
    "Envoi indisponible : aucun modèle n'est choisi. Choisissez-en un sur la page de diagnostic."
)
_LOAD_FAILED_FR = (
    "Envoi indisponible : le modèle n'a pas pu être chargé. Choisissez un autre fichier GGUF "
    "sur la page de diagnostic."
)
_CLOUD_FAILED_FR = (
    "Envoi indisponible : le modèle cloud n'a pas pu être préparé. Choisissez un modèle sur la "
    "page de diagnostic."
)
_NO_TURN_FR = "Aucun tour possible."
# Lot E (E4): a load stopped with no previous model to come back to.
_LOAD_STOPPED_FR = (
    "Envoi indisponible : le chargement du modèle a été arrêté et aucun modèle n'est chargé. "
    "Choisissez un modèle sur la page de diagnostic."
)
# Story 26: the read rate is measured on a call that evaluated at least this many tokens, not
# on a cache hit (lot A).
READ_MIN_TOKENS = 64
# Story 26 (AD-9): what the window panel says of a model's context cache and read time when
# they are not WaveStack's to measure.
_KV_CLOUD_FR = "Cache de contexte : chez le fournisseur, aucune mémoire sur ce poste"
_KV_NO_MODEL_FR = "Cache de contexte : calculé au chargement d'un modèle"
_READ_CLOUD_FR = (
    "Temps de lecture : chez le fournisseur, non estimé (le temps mesuré est surtout celui du "
    "réseau)"
)
_READ_NO_MODEL_FR = "Temps de lecture : pas encore mesuré, aucun modèle actif"

# Lot B: the heaviest kind of segment names the cause (message first on ties), every kind
# but the template counted, some with another (`_OVERFLOW_GROUP`).
_OVERFLOW_CAUSES_FR = {
    SegmentKind.USER_MESSAGE: (
        "Cause : le message à lui seul est trop long. "
        "Pour continuer la démo : raccourcissez le message et renvoyez-le."
    ),
    SegmentKind.RAG_EXCERPT: (  # story 15: after the message, which wins the ties
        "Cause : les extraits RAG occupent la plus grande part du contexte. Pour continuer la "
        "démo : désactivez la brique RAG ou baissez [rag] top_k dans settings.json."
    ),
    SegmentKind.HISTORY: (
        "Cause : l'historique de la conversation occupe la plus grande part du contexte. "
        "Pour continuer la démo : videz la conversation ou raccourcissez le message."
    ),
    SegmentKind.SYSTEM_PROMPT: (
        "Cause : le prompt système occupe la plus grande part du contexte. "
        "Pour continuer la démo : raccourcissez le prompt système ou rétablissez le prompt "
        "par défaut."
    ),
    SegmentKind.TOOL_CATALOG: (  # in lazy loading; see `_TOOL_CATALOG_FULL_FR`
        "Cause : les descriptions d'outils occupent la plus grande part du contexte. Pour "
        "continuer la démo : désactivez un serveur MCP (ou des outils) dans le panneau des "
        "briques, ou videz la conversation pour décharger les documentations chargées."
    ),
    SegmentKind.TOOL_RESULT: (  # lot B: `_compression_hint_fr` fills `{compression}`
        "Cause : les résultats d'outils (fichiers lus, recherches) occupent la plus grande part "
        "du contexte. Pour continuer la démo : posez une question plus précise, pour des "
        "résultats plus courts{compression}, ou videz la conversation."
    ),
    SegmentKind.HOOK_INJECTION: (
        "Cause : le texte injecté par le hook H3 (injection de contexte) occupe la plus grande "
        "part du contexte. Pour continuer la démo : désactivez H3 dans la carte des hooks, ou "
        "raccourcissez son texte (injection dans content/hooks.yaml)."
    ),
    SegmentKind.SUBAGENT_RESULT: (
        "Cause : le résultat du sous-agent occupe la plus grande part du contexte. Pour "
        "continuer la démo : confiez-lui une tâche plus ciblée, ou videz la conversation."
    ),
    SegmentKind.GLOBAL_MEMORY: (
        "Cause : la mémoire globale occupe la plus grande part du contexte. Pour continuer la "
        "démo : retirez des entrées depuis « Modifier la mémoire », ou désactivez la brique "
        "Mémoire globale."
    ),
    SegmentKind.SKILL_BODY: (  # with the catalog (`_OVERFLOW_GROUP`)
        "Cause : les skills (leur catalogue et les skills chargés) occupent la plus grande "
        "part du contexte. Pour continuer la démo : videz la conversation pour décharger les "
        "skills chargés, ou désactivez la brique Skills."
    ),
}
# Lot B: the kinds counted with another's cause.
_OVERFLOW_GROUP = {
    SegmentKind.SKILL_CATALOG: SegmentKind.SKILL_BODY,
    SegmentKind.ASSISTANT_TURN: SegmentKind.HISTORY,  # the turn's calls, its exchanges
}
_OVERFLOW_COMPRESSION_FR = " ; allumez la compression, qui raccourcit les gros résultats"
_TOOL_CATALOG_FULL_FR = (
    "Cause : les descriptions d'outils occupent la plus grande part du contexte, chaque outil "
    "y entrant avec sa documentation complète. Pour continuer la démo : passez la carte MCP en "
    "lazy loading, ou désactivez un serveur MCP (ou des outils) dans le panneau des briques."
)
# AD-6: the French name of a model capability a brick requires.
_CAPABILITIES_FR = {
    "tool_call_parser": f"l'appel d'outils ({NO_TOOL_PARSER_FR})",
}
_LIMITS_FR = {
    "calls": (
        "Borne atteinte : {n} appels au modèle dans ce tour. Le harnais arrête la boucle pour "
        "éviter qu'un modèle n'appelle des outils sans fin."
    ),
    "retries": (
        "Le modèle n'a pas pu utiliser l'outil : {n} appels refusés dans ce tour (mal formés, "
        "outil inconnu ou arguments invalides). Le harnais arrête là au lieu de relancer "
        "indéfiniment."
    ),
    "sub_retries": (
        "Le sous-agent n'a pas pu utiliser ses outils : {n} appels refusés (mal formés, outil "
        "inconnu ou arguments invalides). Le harnais arrête le sous-agent ; le tour principal "
        "continue avec une erreur à la place du résultat."
    ),
    "sub_calls": (
        "Borne du sous-agent atteinte : {n} appels au modèle pour cette délégation. Le harnais "
        "arrête le sous-agent ; le tour principal continue avec une erreur à la place du "
        "résultat."
    ),
}
# Lot B (N3): appended to a network or MCP tool's result the harness cut, seen by the model.
_TRUNCATED_FR = (
    "\n\n[Résultat tronqué par le harnais : {kept} tokens sur {total}. Réponds avec ce qui "
    "est gardé, ou relance l'outil avec une demande plus précise.]"
)
_OVERFLOW_STRATEGIES_FR = [
    "Fenêtre glissante : ne garder que les échanges les plus récents.",
    "Compaction : résumer les anciens échanges en quelques lignes.",
    "Retrait des anciens résultats d'outils.",
    "Lazy loading : ne charger la documentation des outils qu'à la demande.",
]


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
    # Chat mode: the call's `context_reconciled` payload once `usage` came back (AD-4); a
    # provider's refusal: its French message (for a failed delegation, AD-11).
    reconciled: dict[str, Any] | None = None
    message_fr: str = ""


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
    label_fr: str

    def payload(self) -> dict[str, Any]:
        return {
            "armed_id": self.armed_id,
            "kind": self.kind,
            "brick": self.brick,
            "target": self.target,
            "args": self.args,
            "label_fr": self.label_fr,
        }


class ArmRefused(Exception):
    """An arming the session refuses: unknown target (`not_found`) or invalid arguments."""

    def __init__(self, reason_fr: str, *, not_found: bool = False) -> None:
        super().__init__(reason_fr)
        self.reason_fr = reason_fr
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
    rag_rerank_skipped_fr: str | None = None
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
    """How a sub-agent's loop ended; `message_fr` is the error reinjected on a failure."""

    status: str  # completed | limit | overflow | error | cancelled
    result: str = ""
    message_fr: str = ""


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
    def __init__(self, reason_fr: str) -> None:
        super().__init__(reason_fr)
        self.reason_fr = reason_fr


# AD-7, story 24: a hot switch's probe of a GGUF (`DiagnosticSession.probe_path`): `None`
# when it loads or when « Arrêter » (the load's token) killed it, else why, in French.
ProbeFn = Callable[[str, CancelToken | None], str | None]


class _LoadCancelled(Exception):
    """Lot E (E4): « Arrêter » during a load, seen at one of `_load`'s checkpoints."""


class _LoadFailed(Exception):
    """A load refused for a known reason (probe, incompatible template): `message_fr` for
    `harness_error`, `reason_fr` its cause, `idle_fr` the reason left in `idle` when no
    model is active afterwards."""

    def __init__(
        self,
        message_fr: str,
        reason_fr: str,
        idle_fr: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(reason_fr)
        self.message_fr, self.reason_fr, self.idle_fr = message_fr, reason_fr, idle_fr
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


def _missing_model_fr(noun: str, label_fr: str, missing: list[ModelFile], tail: str = "") -> str:
    """Stories 15 and 16: « modèle absent » (or another file there) for the embedding or the
    reranking model, with what to download or copy by hand, and where. Reads the disk: called
    when the files are read again, never at each emission."""
    names = ", ".join(PurePosixPath(f.path).name for f in missing)
    folder = config.models_dir() / PurePosixPath(missing[0].path).parent
    size = _mo(sum(f.size for f in missing))
    if any((config.models_dir() / f.path).is_file() for f in missing):
        return (
            f"Indisponible : le fichier {names} de {folder} n'est pas le modèle {noun} déclaré "
            f"({label_fr}, {size} Mo attendus). Cliquez sur « Télécharger » pour le "
            f"remplacer.{tail}"
        )
    return (
        f"Indisponible : modèle absent. Le modèle {noun} {label_fr} ({size} Mo) n'est pas sur "
        f"le poste. Cliquez sur « Télécharger », ou copiez à la main {names} dans {folder}, "
        f"puis cliquez de nouveau sur « Télécharger ».{tail}"
    )


_log = logging.getLogger(__name__)


def _join_fr(items: list[str]) -> str:
    """« a, b et c »: a French enumeration."""
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + f" et {items[-1]}"


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
        self.reason_fr: str | None = "Diagnostic de démarrage en cours."
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
        self._rag_missing_fr: str | None = None  # its reason, read with the files
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
        self._rerank_missing_fr: str | None = None  # its reason, read with the files
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
        self._load_content()
        self._registry = ToolRegistry(
            NATIVE_TOOLS + network_tools(self.cfg) + self._harness_tools(), self._tools_content
        )
        self._tool_executor = ToolExecutor(self._registry)
        self._check_subagent_tools()
        self._tools_enabled: set[str]  # sub-options: see `_apply_launch_config`
        # MCP servers (story 6): the local one starts enabled, the public ones disabled. A
        # server is contacted only while enabled with the brick wanted (AD-15).
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mcp_servers = mcp_servers(self.cfg)
        self._mcp_enabled: set[str]
        self._mcp_conns: dict[str, McpConnection] = {}
        self._mcp_state: dict[str, tuple[str, str | None]] = {}  # contact, reason_fr
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

    def _set_state(self, state: str, reason_fr: str | None = None) -> None:
        with self._lock:
            self.state, self.reason_fr = state, reason_fr
        self._emit_state()

    def active_model(self) -> dict[str, Any] | None:
        """AD-12: the model indicator's only source, from the file or the cloud entry."""
        if self._cloud is not None:
            return active_model(self._cloud)
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
            state, reason_fr = self.state, self.reason_fr
        get_journal().emit(
            "session_state",
            {"state": state, "reason_fr": reason_fr, "active_model": self.active_model()},
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
        return text.label_fr if text else server_id

    def _hook_ids(self) -> list[str]:
        """The declared hooks, in the registry's order, which is their call order."""
        brick = self._bricks.get("hooks")
        return [c.id.removeprefix("hooks.") for c in brick.components] if brick else []

    def _hook_label(self, hook_id: str) -> str:
        text = self._hooks_content.hooks.get(hook_id) if self._hooks_content else None
        return text.label_fr if text else hook_id

    def _skill_ids(self) -> list[str]:
        """The declared skills, in the registry's order."""
        brick = self._bricks.get("skills")
        return [c.id.removeprefix("skills.") for c in brick.components] if brick else []

    def _skill_text(self, skill_id: str) -> SkillText | None:
        return self._skills_content.skills.get(skill_id) if self._skills_content else None

    def _skill_label(self, skill_id: str) -> str:
        text = self._skill_text(skill_id)
        return text.label_fr if text else skill_id

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
            label_fr=self._mcp_label(server_id),
            contact=contact,
            tools=self._mcp_tools(server_id) if contact == "available" else [],
        )
        if node["hosting"] == "network" and text is not None:  # story 34, AD-19
            node["sends_fr"] = text.sends_fr
        if node["available"] and contact == "unavailable":
            node["available"], node["reason_fr"] = False, why

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
            available, reason_fr = self._availability("subagent")
            sub_model = {
                **model,
                "id": "core.model_sub",
                "label_fr": "Modèle (sous-agent)",
                "available": available,
                "reason_fr": reason_fr,
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
                self._tools_content.demo_dir_label_fr if self._tools_content else "demo_files",
                None,
            ),
            AUDIT: (
                "hooks",
                self._hooks_content.audit_label_fr if self._hooks_content else "audit.log",
                str(config.audit_path()),
            ),
            MEMORY: (
                "global_memory",
                self._memory_content.file_label_fr if self._memory_content else "memory.json",
                str(config.memory_path()),
            ),
            RAG_INDEX: (
                "rag",
                self._rag_content.index_label_fr if self._rag_content else "rag_index.sqlite",
                self._rag_index_detail(),
            ),
        }
        for file_id, (brick_id, label, detail_fr) in files.items():
            if file_id not in targets or brick_id not in self._bricks:
                continue
            available, reason_fr = self._availability(brick_id)
            nodes.append(
                {
                    "id": file_id,
                    "kind": "file",
                    "hosting": "local",
                    "label_fr": label,
                    "wanted": True,
                    "available": available,
                    "reason_fr": reason_fr,
                    "detail_fr": detail_fr,
                }
            )
        drawn = {n["id"] for n in nodes} | {c.id for cs in components.values() for c in cs}
        for brick in wanted:
            available, reason_fr = self._availability(brick.id)
            for component in components[brick.id]:
                hosting = "network" if component.hosting == "network_service" else "local"
                is_tool = component.kind == "tool"
                is_skill = component.kind == "skill"
                is_hook = component.kind == "hook"
                node = {
                    "id": component.id,
                    "kind": component.kind if is_tool or is_skill or is_hook else "brick",
                    "hosting": hosting,
                    "label_fr": (
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
                    "reason_fr": reason_fr,
                }
                if is_tool and hosting == "network":
                    name = component.id.removeprefix("tools.")
                    contact, why = self._tool_executor.contact.get(name, ("not_contacted", None))
                    node["contact"] = contact
                    node["sends_fr"] = self._registry.sends(name)  # story 34, AD-19
                    if available and contact == "unavailable":
                        node["available"], node["reason_fr"] = False, why
                if component.kind == "mcp_server":
                    self._mcp_node(node, component.id.removeprefix("mcp."))
                if is_skill:  # its tooltip gives its description and state (FR-3)
                    skill_id = component.id.removeprefix("skills.")
                    text = self._skill_text(skill_id)
                    with self._lock:
                        node["loaded"] = skill_id in self._loaded_skills
                    node["detail_fr"] = text.description if text else None
                if is_hook and self._hooks_content:  # its tooltip says when it acts
                    hook = self._hooks_content.hooks.get(component.id.removeprefix("hooks."))
                    node["detail_fr"] = hook.description_fr if hook else None
                if component.id == "rag.retriever" and self._rag_model is not None:
                    node["detail_fr"] = f"Modèle d'embedding {self._rag_model.id}, processus local"
                if component.id == RAG_RERANKER:  # story 16: its label, model and own reason
                    if self._rag_content is not None:
                        node["label_fr"] = self._rag_content.rerank_label_fr
                    if self._rerank_model is not None:
                        node["detail_fr"] = (
                            f"Modèle de reranking {self._rerank_model.id}, processus local"
                        )
                    ok, why = self._rerank_availability()
                    if node["available"] and not ok:
                        node["available"], node["reason_fr"] = False, why
                if component.id == "compression.compressor":
                    node["detail_fr"] = (
                        f"{self._compressor_label()}, bibliothèque dans le processus du "
                        "harnais, hors ligne"
                    )
                nodes.append(node)
                edges += [
                    {"from": component.id, "to": target, "crosses_boundary": hosting == "network"}
                    for target in component.edges_to
                    if target in drawn  # e.g. a `file.*` node not emitted yet
                ]
        get_journal().emit("architecture_changed", {"nodes": nodes, "edges": edges})

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
                "label_fr": self._mcp_label(server.id),
                "enabled": server.id in enabled,
                "hosting_fr": "RÉSEAU" if server.network else "Local",
                "network": server.network,
                # Story 9: the tools whose documentation « Charger la documentation » loads.
                "tools": tools.get(server.id, []),
            }
            for server in self._mcp_servers.values()
        ]

    def _skill_options(self) -> list[dict[str, Any]]:
        with self._lock:
            enabled = set(self._skills_enabled)
        return [
            {
                "id": skill_id,
                "label_fr": self._skill_label(skill_id),
                "enabled": skill_id in enabled,
                "hosting_fr": "Local",
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
                "label_fr": self._hook_label(hook_id),
                "enabled": hook_id in enabled,
                "hosting_fr": "Local",
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
                    "label_fr": self._registry.label(name),
                    "enabled": name in enabled,
                    "hosting_fr": "RÉSEAU" if spec.network else "Local",
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
        return (
            f"Bornes du tour : {self.cfg.tool_max_calls} appels au modèle au plus, dont "
            f"{self.cfg.tool_max_retries} nouveaux essais après un appel refusé (mal formé, "
            "outil inconnu ou arguments invalides)."
        )

    def _subagent_card(self, text: SubagentContent) -> dict[str, Any]:
        """Story 19: « Déléguer au sous-agent » on the card (no sub-option), and the bounds."""
        tools = ", ".join(self._registry.label(n) for n in self.cfg.subagent_tools) or "aucun"
        n = self.cfg.subagent_max_calls
        return {
            "force": {
                "kind": "delegate",
                "target": DELEGATE,
                "label_fr": text.force_label_fr,
                "parameters": {"task": text.task_label_fr},
                "presets": [p.model_dump() for p in text.presets],
            },
            "limits_fr": (
                f"Sous-agent : {n} appel{'s' if n > 1 else ''} au modèle au plus, nouveaux essais "
                f"compris ; outils : {tools}, s'ils sont activés dans la brique Outils."
            ),
        }

    def _outbound_fr(self, brick_id: str, content: BrickContent | None) -> str | None:
        """Story 23: the card's « what leaves the workstation, and where to read it », built
        from `content/bricks/*.yaml` (AD-19): the network tools, in the registry's order, and
        the public MCP servers. None for a brick with nothing that can leave."""
        if content is None or content.outbound_fr is None or brick_id not in ("tools", "mcp"):
            return None
        servers = [self._mcp_label(s.id) for s in self._mcp_servers.values() if s.network]
        tools: list[str] = []
        if brick_id == "tools":
            tools = [o["label_fr"] for o in self._tool_options() if o["network"]]
            if not tools and not servers:
                return None
        elif not servers:
            return None
        try:
            return content.outbound_fr.format(
                tools=_join_fr(tools) or "aucun outil réseau", servers=_join_fr(servers) or "aucun"
            )
        except (KeyError, IndexError, ValueError, AttributeError, TypeError) as exc:
            # A placeholder the session does not fill (`{x}`, `{tools.x}`, `{0}`): no line,
            # but the cards still go out.
            _log.warning("outbound_fr of %s ignored: %s: %s", brick_id, type(exc).__name__, exc)
            return None

    def _emit_bricks(self) -> None:
        pending = self._pending_ids()
        with self._lock:
            wanted = set(self._wanted)
            custom = self._custom_prompt
            lazy = self._mcp_lazy
        bricks = []
        for brick in self._bricks.values():
            available, reason_fr = self._availability(brick.id)
            content = self._content.get(brick.id)
            bricks.append(
                {
                    "id": brick.id,
                    "label_fr": self._label(brick.id),
                    "category": brick.category,
                    "group": brick.group,
                    "category_fr": content.category_fr if content else brick.category,
                    "hosting_fr": content.hosting_fr if content else "",
                    "explanation_fr": self._explanation(content),
                    "wanted": brick.id in wanted,
                    "available": available,
                    "reason_fr": reason_fr,
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
                    "limits_fr": self._limits_fr() if brick.id == "tools" else None,
                    "outbound_fr": self._outbound_fr(brick.id, content),
                }
            )
            if brick.id == "reasoning":
                bricks[-1]["always_fr"] = self._always_fr()
                bricks[-1]["limits_fr"] = self._reasoning_budget_fr()
            if brick.id == "global_memory":
                bricks[-1] |= self._memory_card()
            if brick.id == "subagent" and self._subagent_content is not None:
                bricks[-1] |= self._subagent_card(self._subagent_content)
            if brick.id == "rag":
                bricks[-1] |= self._rag_offers() | {"rerank": self._rerank_card()}
            if brick.id == "compression" and self._compression_content is not None:
                bricks[-1]["limits_fr"] = self._compression_content.limits_fr.format(
                    min_chars=self.cfg.compression_min_chars
                )
            if brick.id == "mcp":
                bricks[-1] |= {
                    "mode": "lazy" if lazy else "full",
                    "lazy_label_fr": (
                        self._mcp_content.lazy_label_fr if self._mcp_content else "Lazy loading"
                    ),
                }
        text = custom if custom is not None else self._default_prompt
        get_journal().emit(
            "bricks_changed",
            {
                "bricks": bricks,
                "system_prompt": {"text": text, "is_default": text == self._default_prompt},
            },
        )

    def _error(self, message_fr: str, exc: BaseException | str, effect_fr: str) -> None:
        cause = exc if isinstance(exc, str) else f"{type(exc).__name__}: {exc}"
        get_journal().emit(
            "harness_error", {"message_fr": message_fr, "cause": cause, "effect_fr": effect_fr}
        )

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
            return f"Préparation du modèle cloud {choice.entry.model} chez {choice.entry.provider}…"
        if choice.kind == "server":
            return f"Préparation du modèle servi par {choice.provider}…"
        return f"Chargement du modèle {choice.file_name}…"

    @staticmethod
    def _model_payload(choice: ModelChoice) -> dict[str, Any]:
        """The `ActiveModel` of a model not loaded yet: `model_load_*`."""
        if choice.entry is not None:
            return active_model(choice.entry)
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
            self.state, self.reason_fr = "model_load", self._load_reason(choice)
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
                return f"{choice.label} est déjà actif.", None
            refusal = (
                self._load_registry.check(choice.label, cost) if self._checked(choice) else None
            )
            if refusal is None:  # switched under the lock: a second choice racing it is refused
                self.state, self.reason_fr = "model_load", self._load_reason(choice)
                self._load_cancel = CancelToken()  # lot E (E4): « Arrêter » from now on
        if refusal is not None:
            self._error(refusal, "budget mémoire dépassé (AD-8)", "Rien n'est libéré ni écrit.")
            raise SendRefused(refusal)
        self._emit_state()
        future = self._executor.submit(self._load, choice, previous, probe, True)
        return f"Chargement de {choice.label}…", future

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
        journal = get_journal()
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
        status, reason_fr, idle_fr = "error", None, _LOAD_FAILED_FR
        with self._lock:
            cancel = self._load_cancel
        # Story 29: each step passed, with WaveStack's RSS, for the « LLM nu » screen.
        rss_before = self._rss_now()
        last_step = started

        def step(name: str, label_fr: str) -> None:
            nonlocal last_step
            now = time.monotonic()
            with scoped(**off_turn):
                journal.emit(
                    "model_load_step",
                    {
                        "model": model,
                        "step": name,
                        "label_fr": label_fr,
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
                        "Sonde du fichier dans un processus à part : "
                        + ("il se charge." if why is None else "incompatible."),
                    )
                    if why is not None:
                        raise _LoadFailed(f"Le fichier {choice.file_name} est incompatible.", why)
                    # AD-8: the probe's measure replaces the file size of the first check.
                    refusal = self._load_registry.check(choice.label, self._cost(choice))
                    if refusal is not None:
                        over_fr = "Le modèle dépasse le budget mémoire une fois mesuré."
                        raise _LoadFailed(over_fr, refusal)
                step("check", self._check_fr(choice, window))
                self._install(choice, window)
                step("engine", self._engine_fr(choice))
                self._last_checkpoint(cancel)
                step("ready", f"Prêt : {choice.label} est actif.")
                status, idle_fr = "ok", None
            except _LoadCancelled:
                self._last_checkpoint(None)
                reason_fr, idle_fr, status = self._load_cancelled(previous, window is not None)
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._last_checkpoint(None)  # « Arrêter » cannot stop the way back
                reason_fr, idle_fr, status = self._load_failed(choice, previous, exc, window)
            if status == "ok" and save:
                reason_fr = self._save_choice(choice)
            if status == "ok" and window is not None:  # story 26: applied, then saved
                with self._lock:
                    self._configured_window = window
                reason_fr = self._save_window(window) or (
                    f"Fenêtre de contexte : {_fr(window)} tokens (conversation gardée)."
                )
        except Exception as exc:  # noqa: BLE001 - AD-16: never let the worker die silently
            self._error("Le changement de modèle s'est interrompu.", exc, _NO_TURN_FR)
            status, reason_fr, idle_fr = "error", str(exc), _LOAD_FAILED_FR
        finally:
            with self._lock:  # « Arrêter » acts on this load no longer
                self._load_cancel = None
                scenario = self._active_scenario
            if scenario is not None:  # lot E (E5): the bricks the new model cannot offer
                try:
                    self._emit_scenario(refresh=True)
                except Exception as exc:  # noqa: BLE001 - AD-16: the load still ends
                    self._error(
                        "Les briques indisponibles du scénario n'ont pas pu être relues.",
                        exc,
                        "Le chargement se termine ; la carte de chaque brique reste juste.",
                    )
            memory = self._loaded_memory(choice, rss_before, window) if status == "ok" else None
            with scoped(**off_turn):
                journal.emit(
                    "model_load_ended",
                    {
                        "model": model,
                        "status": status,
                        "duration_ms": _ms(time.monotonic() - started),
                        "reason_fr": reason_fr,
                    }
                    | ({"memory": memory} if memory is not None else {}),
                )
            self._set_state("idle", idle_fr)
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
        after = f" : WaveStack occupe {config.size_fr(rss)}" if rss else ""
        if previous is None:
            return f"Aucun modèle à libérer{after}."
        return f"Modèle précédent libéré ({previous.label}){after}."

    def _check_fr(self, choice: ModelChoice, window: int | None) -> str:
        """The step « check »: the budget was checked before anything was released (AD-3,
        and again after a probe); this says it is confirmed. A label only: never a failure."""
        try:
            return self._check_label_fr(choice, window)
        except Exception:  # noqa: BLE001 - a figure shown, never a load's failure
            return "Budget confirmé : contrôlé avant la libération du modèle précédent."

    def _check_label_fr(self, choice: ModelChoice, window: int | None) -> str:
        if choice.kind == "cloud":
            return "Budget confirmé : rien à charger sur ce poste (modèle cloud)."
        cost = self._cost(choice, window)
        budget = config.size_fr(self._load_registry.budget_bytes)
        if choice.kind == "server" and not self._checked(choice):
            return (
                f"Budget confirmé : {config.size_fr(cost)} déjà en mémoire chez "
                f"{choice.provider}, comptés sans refus (budget de {budget})."
            )
        return (
            f"Budget confirmé (contrôlé avant la libération) : environ {config.size_fr(cost)} "
            f"demandés, budget de {budget}."
        )

    @staticmethod
    def _engine_fr(choice: ModelChoice) -> str:
        if choice.kind == "cloud":
            return "Préparation, sans chargement (modèle cloud)"
        if choice.kind == "server":
            return f"Connexion à {choice.provider}"
        return "Lecture du fichier et copie des poids en mémoire vive"

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
            provider = choice.entry.provider if choice.entry is not None else "le fournisseur"
            where_fr = f"Aucune mémoire sur ce poste : le modèle tourne chez {provider}."
        elif choice.kind == "server":
            where_fr = (
                f"Chargé par {choice.provider}, dans son propre processus, en RAM de ce poste : "
                f"environ {config.size_fr(cost)} comptés par le budget."
            )
        else:
            before = config.size_fr(rss_before) if rss_before else "?"
            after = config.size_fr(rss_after) if rss_after else "?"
            where_fr = (
                "Mémoire vive (RAM) du processeur, pas de carte graphique : WaveStack est passé "
                f"de {before} à {after} ; le budget compte environ {config.size_fr(cost)}. Les "
                "poids, lus en mmap, montent en RAM au premier appel."
            )
        return {
            "rss_before": rss_before,
            "rss_after": rss_after,
            "cost_bytes": cost,
            "where_fr": where_fr,
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
            message_fr, reason, idle_fr = exc.message_fr, exc.reason_fr, exc.idle_fr
            cause = exc.detail or exc.reason_fr  # lot E (E6): the raw message, a detail
        elif choice.entry is not None:
            message_fr = f"Le modèle cloud {choice.label} n'a pas pu être préparé."
            idle_fr = _CLOUD_FAILED_FR
        elif choice.kind == "server":
            message_fr = (
                f"Le modèle {choice.label}, servi par {choice.provider}, n'a pas pu être préparé."
            )
            idle_fr = None
            if isinstance(exc, ServerError):
                cause = exc.message_fr
            elif isinstance(exc, TokenizerRefused):  # the loader's message, a detail
                cause, reason = exc.detail, exc.reason_fr
        else:
            message_fr, idle_fr = "Le modèle n'a pas pu être chargé.", None
        cause_fr = reason or (cause if isinstance(cause, str) else str(cause))
        self._release()  # whatever the failed load left
        if previous is None:
            self._error(message_fr, cause, _NO_TURN_FR)
            return cause_fr, idle_fr or _LOAD_FAILED_FR, "error"
        self._error(message_fr, cause, f"Retour au modèle précédent : {previous.label}.")
        try:
            self._install(previous)
        except Exception as back:  # noqa: BLE001 - AD-16
            self._release()
            self._error(
                f"Le modèle précédent ({previous.label}) n'a pas pu être rechargé.",
                back,
                _NO_TURN_FR,
            )
            return (
                f"{message_fr} Le modèle précédent ({previous.label}) n'a pas pu être rechargé.",
                _LOAD_FAILED_FR,
                "error",
            )
        if window is not None:
            return (
                f"Fenêtre de {_fr(window)} tokens non appliquée ({cause_fr}) : "
                f"{previous.label} est de nouveau actif avec {_fr(self._window)} "
                "tokens.",
                None,
                "restored",
            )
        return (
            f"{choice.label} n'a pas pu être chargé ({cause_fr}) : {previous.label} est de "
            "nouveau actif.",
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
            return "Chargement arrêté : aucun modèle n'est actif.", _LOAD_STOPPED_FR, "cancelled"
        try:
            self._install(previous)
        except Exception as back:  # noqa: BLE001 - AD-16
            self._release()
            self._error(
                f"Le modèle précédent ({previous.label}) n'a pas pu être rechargé.",
                back,
                _NO_TURN_FR,
            )
            return (
                f"Chargement arrêté ; le modèle précédent ({previous.label}) n'a pas pu être "
                "rechargé.",
                _LOAD_FAILED_FR,
                "error",
            )
        if reload:
            return (
                f"Rechargement arrêté : {previous.label} est de nouveau actif avec "
                f"{_fr(self._window)} tokens.",
                None,
                "cancelled",
            )
        return f"Chargement arrêté : {previous.label} est de nouveau actif.", None, "cancelled"

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
                        "Le modèle n'a pas pu être chargé.",
                        probe_module.incompatible_fr(),
                        detail=str(exc) or type(exc).__name__,
                    ) from exc
            try:
                meta = engine.metadata()
                caps = capabilities_for(meta)
                if caps.incompatible_reason:
                    raise _LoadFailed(
                        "Modèle incompatible.", caps.incompatible_reason, caps.incompatible_reason
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

    def _install_cloud(self, entry: CloudModel, configured: int | None = None) -> None:
        key = config.cloud_key(entry)
        if key is None:
            raise ValueError("aucune clé enregistrée pour cette adresse")
        unavailable = config.cloud_unavailable_fr(entry)
        if unavailable:
            raise ValueError(unavailable)
        self._cloud_content = load_cloud_content()
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
            notice = f"{choice.label} est actif ; choix non mémorisé pour les prochains lancements."
            self._error("Impossible d'écrire le fichier de réglages settings.json.", exc, notice)
            return notice
        return None

    # ---------- context window (story 26, AD-9) ----------

    @staticmethod
    def _reload_reason(choice: ModelChoice, window: int) -> str:
        return f"Rechargement de {choice.label} avec une fenêtre de {_fr(window)} tokens…"

    @staticmethod
    def _locked_fr(entry: CloudModel | None) -> str | None:
        """AD-9: a cloud model that declares its `window` takes no other: why, in French."""
        if entry is None or not entry.window:
            return None
        return (
            "Réglage désactivé : fenêtre fixée par la déclaration du modèle "
            f"({entry.model} déclare window = {_fr(entry.window)})."
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
                return f"La fenêtre est déjà de {_fr(window)} tokens.", None
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
                bound = bound_fr(source, effective)
                message = (
                    f"Fenêtre de contexte : {_fr(window)} tokens, prise en compte au prochain "
                    f"tour, sans rechargement{f' ({bound})' if bound else ''}."
                )
            else:
                self._executor.submit(self._emit_window_state)
                message = (
                    f"Fenêtre de {_fr(window)} tokens enregistrée : elle s'appliquera au "
                    "prochain chargement d'un modèle."
                )
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
            bound = bound_fr(source, effective, active.provider)
            return notice or (
                f"Fenêtre de {_fr(window)} tokens enregistrée ; la fenêtre effective de "
                f"{active.label} reste de {_fr(effective)} tokens"
                f"{f' ({bound})' if bound else ''}, sans rechargement."
            ), None
        refusal = self._window_refusal(active, window, current)
        with self._lock:
            if self.state != "idle" or self._active is not active:
                raise SendRefused(self._refusal_reason())
            if refusal is None:  # switched under the lock: a second intention is refused
                self.state, self.reason_fr = "model_load", self._reload_reason(active, window)
                self._load_cancel = CancelToken()  # « Arrêter » from now on
        if refusal is not None:
            self._error(
                refusal, "budget mémoire dépassé (AD-8)", "Rien n'est libéré, écrit ni rechargé."
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
            return (
                f"Fenêtre de {_fr(window)} tokens refusée : le coût de {active.label} avec "
                "cette fenêtre est inconnu (fichier du modèle illisible depuis WaveStack). "
                f"{active.label} reste actif avec {_fr(current)} tokens."
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
            notice = (
                f"Fenêtre de {_fr(window)} tokens appliquée ; choix non mémorisé pour les "
                "prochains lancements."
            )
            self._error("Impossible d'écrire le fichier de réglages settings.json.", exc, notice)
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
            "bound_fr": None,
            "kv_bytes": None,
            "read_s": None,
            "fits": True,
            "refusal_fr": None,
        }
        if active is None:
            return row | {
                "effective": window,
                "source": "configured",
                "kv_fr": _KV_NO_MODEL_FR,
                "read_fr": _READ_NO_MODEL_FR,
            }
        if active.entry is not None:
            effective, source = config.cloud_window(active.entry, window)
            return row | {
                "effective": effective,
                "source": source,
                "bound_fr": bound_fr(source, effective),
                "kv_fr": _KV_CLOUD_FR,
                "read_fr": _READ_CLOUD_FR,
            }
        effective, source = window_for(meta, window) if meta else (window, "configured")
        llama = active.kind == "server" and active.provider == "llama-server"
        if llama:
            slot = (meta.server_context if meta else None) or active.server.n_ctx
            kv_text = "Cache de contexte : réservé par llama-server" + (
                f" (-c {_fr(slot)}), inchangé" if slot else ", inchangé"
            )
            kv_bytes = None
        else:
            kv_bytes = kv_per_token * effective if kv_per_token else None
            kv_text = f"Cache de contexte : {kv_fr(kv_bytes)}"
        read_s = read_seconds(effective, tps)
        refusal = None if current else self._window_refusal(active, window, now)
        return row | {
            "effective": effective,
            "source": source,
            "bound_fr": bound_fr(source, effective, active.provider),
            "kv_bytes": kv_bytes,
            "kv_fr": kv_text,
            "read_s": round(read_s, 1) if read_s is not None else None,
            "read_fr": f"Temps de lecture : {read_time_fr(effective, tps)}",
            "fits": refusal is None,
            "refusal_fr": refusal,
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
            note = "Aucun modèle actif : la fenêtre choisie s'appliquera au prochain chargement."
        elif not local:
            note = (
                "Modèle cloud : « Appliquer » ne recharge rien, la fenêtre compte dès le "
                "prochain tour. La lecture du contexte se fait chez le fournisseur."
            )
        elif tps is None:
            note = (
                f"« Appliquer » recharge {active.label}, la conversation est gardée. Débit de "
                "lecture pas encore mesuré : envoyez un message, le temps de lecture de chaque "
                "fenêtre s'affichera."
            )
        else:
            note = (
                f"« Appliquer » recharge {active.label}, la conversation est gardée. Débit de "
                f"lecture mesuré : {_fr(round(tps))} tokens/s, sur le dernier appel qui a lu "
                f"au moins {READ_MIN_TOKENS} tokens. Le temps affiché est une borne basse : le "
                "débit baisse quand le contexte s'allonge."
            )
        return {
            "configured": configured,
            "default": DEFAULT_WINDOW,
            "window": effective,
            "window_source": source,
            "bound_fr": bound_fr(source, effective, active.provider if active else None),
            "model_label": active.label if active else None,
            "hosting": active.kind if active else None,
            "read_tps": round(tps, 1) if tps else None,
            "read_note_fr": note,
            "locked_fr": self._locked_fr(active.entry if active else None),
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
                "Le coût des fenêtres de contexte n'a pas pu être calculé.",
                exc,
                "Le panneau « Fenêtre » garde ses chiffres précédents.",
            )
            return
        with scoped(turn_id=None, step_id=None, call_id=None, context_id=None):
            get_journal().emit("context_window_state", payload)

    def hold(self, state: str, reason_fr: str, run: Callable[[], Any]) -> Any:
        """AD-3: runs `run` holding the operation lock in `state` (`test_cloud_model`:
        `model_load`), then gives the previous state back. Refused (`SendRefused`) outside
        `idle` and `diagnostic`."""
        with self._lock:
            if self.state not in ("idle", "diagnostic"):
                raise SendRefused(self._refusal_reason())
            previous = (self.state, self.reason_fr)
            self.state, self.reason_fr = state, reason_fr
        self._emit_state()
        try:
            return run()
        finally:
            with self._lock:  # a boot may have moved the session meanwhile: leave it there
                mine = (self.state, self.reason_fr) == (state, reason_fr)
            if mine:
                self._set_state(*previous)

    def _load_labels(self) -> SegmentLabels:
        try:
            return load_labels()
        except Exception as exc:  # noqa: BLE001 - AD-19: invalid content is traced, not fatal
            self._error(
                "Le fichier des libellés de segments est invalide.",
                exc,
                "Les types de segment s'affichent sous leur nom technique.",
            )
            return SegmentLabels(kinds={k: k.value for k in SegmentKind}, groups={})

    def _load_content(self) -> None:
        """AD-19: an invalid file makes its brick unavailable with the reason, never a crash."""
        for brick_id in self._bricks:
            try:
                self._content[brick_id] = load_brick_content(brick_id)
            except Exception as exc:  # noqa: BLE001
                self._content_errors[brick_id] = (
                    f"Le fichier content/bricks/{brick_id}.yaml est absent ou invalide : "
                    "corrigez-le puis relancez WaveStack."
                )
                self._error(
                    f"L'explication de la brique « {brick_id} » est invalide.",
                    exc,
                    "La brique est indisponible ; le reste de WaveStack fonctionne.",
                )
        if "tools" in self._bricks:
            try:
                self._tools_content = load_tools_content()
            except Exception as exc:  # noqa: BLE001
                self._content_errors["tools"] = (
                    "Le fichier content/tools.yaml est absent ou invalide : corrigez-le puis "
                    "relancez WaveStack."
                )
                self._error(
                    "Les descriptions des outils sont invalides.",
                    exc,
                    "La brique « Outils » est indisponible ; le reste de WaveStack fonctionne.",
                )
        if "mcp" in self._bricks:
            try:
                self._mcp_content = load_mcp_content()
            except Exception as exc:  # noqa: BLE001
                self._content_errors["mcp"] = (
                    "Le fichier content/mcp.yaml est absent ou invalide : corrigez-le puis "
                    "relancez WaveStack."
                )
                self._error(
                    "Les libellés des serveurs MCP sont invalides.",
                    exc,
                    "La brique « MCP » est indisponible ; le reste de WaveStack fonctionne.",
                )
        if "skills" in self._bricks:
            try:
                self._skills_content = load_skills_content(self._skill_ids())
            except Exception as exc:  # noqa: BLE001
                self._content_errors["skills"] = (
                    "Un fichier des skills (content/skills.yaml ou content/skills/*/SKILL.md) "
                    "est absent ou invalide : corrigez-le puis relancez WaveStack."
                )
                self._error(
                    "Les skills sont invalides.",
                    exc,
                    "La brique « Skills » est indisponible ; le reste de WaveStack fonctionne.",
                )
        if "hooks" in self._bricks:
            try:
                self._hooks_content = load_hooks_content(self._hook_ids())
            except Exception as exc:  # noqa: BLE001
                self._content_errors["hooks"] = (
                    "Le fichier content/hooks.yaml est absent ou invalide : corrigez-le puis "
                    "relancez WaveStack."
                )
                self._error(
                    "Les textes des hooks sont invalides.",
                    exc,
                    "La brique « Hooks » est indisponible ; le reste de WaveStack fonctionne.",
                )
        if "global_memory" in self._bricks:
            self._load_memory()
        if "subagent" in self._bricks:
            try:
                self._subagent_content = load_subagent_content()
            except Exception as exc:  # noqa: BLE001
                self._content_errors["subagent"] = (
                    "Le fichier content/subagent.yaml ou le prompt du sous-agent "
                    "(content/prompts/subagent.md) est absent ou invalide : corrigez-le puis "
                    "relancez WaveStack."
                )
                self._error(
                    "Les textes du sous-agent sont invalides.",
                    exc,
                    "La brique « Sous-agent » est indisponible ; le reste de WaveStack fonctionne.",
                )
        if "rag" in self._bricks:
            self._load_rag()
        if "compression" in self._bricks:
            try:
                self._compression_content = load_compression_content()
            except Exception as exc:  # noqa: BLE001
                self._content_errors["compression"] = (
                    "Le fichier content/compression.yaml est absent ou invalide : corrigez-le "
                    "puis relancez WaveStack."
                )
                self._error(
                    "Les textes de la compression sont invalides.",
                    exc,
                    "La brique « Compression » est indisponible ; le reste fonctionne.",
                )
        if "system_prompt" not in self._bricks:
            return
        try:
            self._default_prompt = load_default_system_prompt()
        except Exception as exc:  # noqa: BLE001
            self._content_errors["system_prompt"] = (
                "Le prompt système par défaut (content/prompts/system.md) est absent ou vide : "
                "corrigez-le puis relancez WaveStack."
            )
            self._error(
                "Le prompt système par défaut est illisible.",
                exc,
                "La brique « Prompt système » est indisponible ; le reste fonctionne.",
            )

    def _load_memory(self) -> None:
        """Story 14 (AD-19, AD-20): its texts, then `memory.json`. An absent file gives the
        demonstration memory, in memory only; an unreadable one makes the brick unavailable,
        and is never written again but by a reset."""
        try:
            self._memory_content = memory_file.load_memory_content()
        except Exception as exc:  # noqa: BLE001
            self._content_errors["global_memory"] = (
                "Le fichier content/memory/memory.yaml est absent ou invalide : corrigez-le puis "
                "relancez WaveStack."
            )
            self._error(
                "Les textes de la mémoire globale sont invalides.",
                exc,
                "La brique « Mémoire globale » est indisponible ; le reste de WaveStack "
                "fonctionne.",
            )
            return
        path = config.memory_path()
        try:
            entries = memory_file.read_memory(path)
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            self._memory_error = (
                f"Le fichier de la mémoire globale ({path}) est illisible ou invalide : "
                "corrigez-le puis relancez WaveStack, ou cliquez sur « Réinitialiser » pour "
                "restaurer la mémoire de démonstration (le fichier sera remplacé)."
            )
            self._error(
                "La mémoire globale est illisible.",
                exc,
                "La brique « Mémoire globale » est indisponible ; le fichier n'est pas modifié.",
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
            self._rag_content = load_rag_content()
        except Exception as exc:  # noqa: BLE001
            self._content_errors["rag"] = (
                "Le fichier content/rag.yaml est absent ou invalide : corrigez-le puis relancez "
                "WaveStack."
            )
            self._error(
                "Les textes de la brique RAG sont invalides.",
                exc,
                "La brique « RAG » est indisponible ; le reste de WaveStack fonctionne.",
            )
            return
        model, error_fr = self.cfg.rag_embedding
        if model is None:
            self._content_errors["rag"] = error_fr or "La section [rag.embedding] est invalide."
            if self.cfg.get("rag", "embedding") is not None:  # absent: said by the card only
                self._error(
                    "La déclaration du modèle d'embedding est invalide.",
                    error_fr or "",
                    "La brique « RAG » est indisponible ; le reste de WaveStack fonctionne.",
                )
            return
        self._rag_model = model
        self._rag_refresh()

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
        path = self.cfg.rag_index_path()
        kind, reason, chunks, longest, missing, missing_fr = self._rag_index_state(model, content)
        with self._lock:
            self._rag_index_kind, self._rag_index_error = kind, reason
            self._rag_chunks = chunks
            self._rag_stamp = _stamp(path)
            self._rag_longest, self._rag_missing = longest, missing
            self._rag_missing_fr = missing_fr

    def _rag_index_state(
        self, model: EmbeddingModel, content: RagContent
    ) -> tuple[str | None, str | None, int, list[Chunk], list[ModelFile], str | None]:
        """What the index and the model's files are now, read without storing anything
        (story 30: the RAG workshop reads it too, and never changes the brick's state): the
        index's kind and reason, its excerpts, the preview's excerpts, the files missing and
        their reason."""
        path = self.cfg.rag_index_path()
        kind, reason, chunks, longest = None, None, 0, []
        missing = download_module.missing_files(model.files, config.models_dir())
        build = "Cliquez sur « Construire l'index » sur la carte RAG"
        if missing:
            build = (
                "Téléchargez d'abord le modèle d'embedding, puis cliquez sur « Construire l'index »"
            )
        why = rag_index.vec_unavailable()
        if why is not None:
            kind, reason = (
                "vec",
                (
                    "Indisponible : l'extension sqlite-vec ne se charge pas dans ce Python "
                    f"({why}). Le RAG ne peut pas lire son index ; les autres briques fonctionnent."
                ),
            )
        elif not path.is_file():
            kind, reason = (
                "absent",
                (
                    f"Indisponible : index absent ({path}). {build} (ou lancez uv run python "
                    "scripts/build_rag_index.py)."
                ),
            )
        else:
            try:
                meta = rag_index.read_meta(path)
                longest = rag_index.longest_chunks(path, self.cfg.rag_top_k)
            except Exception as exc:  # noqa: BLE001 - a state, never a crash
                kind, reason = (
                    "unreadable",
                    (
                        f"Indisponible : l'index {path} est illisible ({type(exc).__name__}). "
                        f"{build} pour le reconstruire."
                    ),
                )
            else:
                chunks = meta.chunks
                kind, reason = self._rag_index_mismatch(meta, model, content, build)
        missing_fr = _missing_model_fr("d'embedding", model.label_fr, missing) if missing else None
        return kind, reason, chunks, longest, missing, missing_fr

    def _rerank_refresh(self) -> None:
        """Story 16: the reranker's files read again, and the reason they give."""
        model = self._rerank_model
        missing = download_module.missing_files(model.files, config.models_dir()) if model else []
        missing_fr = None
        if model is not None and missing:
            tail = " Le RAG fonctionne sans reranking."
            missing_fr = _missing_model_fr("de reranking", model.label_fr, missing, tail)
        with self._lock:
            self._rerank_missing, self._rerank_missing_fr = missing, missing_fr

    def _rag_index_mismatch(
        self, meta: rag_index.IndexMeta, model: EmbeddingModel, content: RagContent, build: str
    ) -> tuple[str | None, str | None]:
        """An index built by another model (id, dimensions, file), or from another corpus or
        another `chunk_max_chars`: its kind and French reason, else `(None, None)`."""
        declared = model.load_file
        other_file = (meta.model_size and meta.model_size != declared.size) or (
            meta.model_sha256
            and declared.sha256
            and meta.model_sha256.lower() != declared.sha256.lower()
        )
        if meta.embedding_model_id != model.id or meta.dims != model.dims or other_file:
            built = f"« {meta.embedding_model_id} » ({meta.dims} dimensions"
            built += f", fichier de {_mo(meta.model_size)} Mo)" if meta.model_size else ")"
            return "other_model", (
                f"Indisponible : l'index a été construit avec le modèle d'embedding {built}, "
                f"alors que [rag.embedding] déclare « {model.id} » ({model.dims} dimensions, "
                f"fichier de {_mo(declared.size)} Mo). {build} pour le reconstruire."
            )
        chunks = chunk_corpus(content, self.cfg.rag_chunk_max_chars)
        stale = meta.chunk_max_chars != self.cfg.rag_chunk_max_chars or (
            meta.corpus_sha256 and meta.corpus_sha256 != rag_index.corpus_digest(chunks)
        )
        if stale or not meta.corpus_sha256:
            return "stale", (
                "Indisponible : index périmé. Le corpus (content/corpus) ou [rag] "
                f"chunk_max_chars ont changé depuis sa construction ({meta.built_at}). "
                f"{build} pour le reconstruire."
            )
        return None, None

    def _rag_unavailable(self) -> str | None:
        """Story 15, AD-12: the RAG's reasons after its content (1), in order: sqlite-vec,
        index absent, unreadable, of another model or stale (2-4), model's files missing (5),
        then, once wanted, loading (6) and a refused or failed load (7)."""
        model = self._rag_model
        with self._lock:
            index_error, missing_fr = self._rag_index_error, self._rag_missing_fr
            wanted = "rag" in self._wanted
            loading, load_error, loaded = (
                self._rag_loading,
                self._rag_load_error,
                self._embedder is not None,
            )
        if index_error is not None:
            return index_error
        if missing_fr is not None:
            return missing_fr
        if not wanted or loaded:
            return None
        if loading:
            return f"Chargement du modèle d'embedding {model.label_fr if model else ''}…"
        return load_error or (
            "Modèle d'embedding non chargé : désactivez puis réactivez la brique RAG."
        )

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
            label = content.download_label_fr.format(size_mb=size_mb)
            return none | {"download": {"target": RAG_TARGET, "label_fr": label}}
        if kind is not None:
            return none | {"build_index": {"label_fr": content.build_label_fr}}
        return none

    def _rag_index_detail(self) -> str:
        """The index node's tooltip: its path, its excerpts and its embedding model."""
        path = self.cfg.rag_index_path()
        with self._lock:
            chunks, error = self._rag_chunks, self._rag_index_error
        if not chunks:
            return f"{path} · index absent ou illisible"
        model = self._rag_model.id if self._rag_model else "?"
        detail = f"{path} · {chunks} extraits · modèle d'embedding {model}"
        return f"{detail} · {error}" if error else detail

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
            return self._content_errors.get("rag") or "Brique RAG non configurée."
        with self._lock:
            index_error, missing = self._rag_index_error, bool(self._rag_missing)
        return index_error or ("modèle absent" if missing else None)

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
        label = f"le modèle d'embedding {model.label_fr}"
        cost = self._load_registry.component_cost(
            model.measured_rss_mb, [f.size for f in model.files]
        )
        refusal = self._load_registry.check_component(label, cost, EMBEDDING)
        if refusal is not None:
            with scoped(brick="rag", component="rag.retriever"):
                self._error(
                    refusal,
                    "budget mémoire dépassé (AD-8)",
                    "La brique « RAG » est indisponible ; rien n'est chargé. Elle se charge "
                    "d'elle-même après un changement de modèle, ou en la réactivant.",
                )
            return None, None, f"Indisponible : {refusal}"
        path = embedding_module.model_path(model)
        embedder: Embedder | None = None
        try:
            declared = model.load_file.sha256
            if declared and rag_index.file_sha256(path) != declared.lower():
                raise ValueError(
                    f"le fichier {path} n'est pas le modèle déclaré (sha256 différent de "
                    "celui de [rag.embedding])"
                )
            embedder = self._embedder_factory(model)
            retriever = SqliteVecRetriever(self.cfg.rag_index_path(), embedder, self.cfg.rag_top_k)
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            self._close_embedder(embedder, None)
            with scoped(brick="rag", component="rag.retriever"):
                self._error(
                    "Le modèle d'embedding n'a pas pu être chargé.",
                    exc,
                    "La brique « RAG » est indisponible ; le reste de WaveStack fonctionne.",
                )
            return (
                None,
                None,
                (
                    f"Indisponible : le modèle d'embedding n'a pas pu être chargé "
                    f"({type(exc).__name__}: {exc}). Vérifiez le fichier {path}, ou "
                    "supprimez-le, puis désactivez et réactivez la brique RAG : elle relit ses "
                    "fichiers et propose de le télécharger à nouveau."
                ),
            )
        self._load_registry.grant(model.label_fr, cost, EMBEDDING)
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
                self._error("Le modèle d'embedding n'a pas pu être fermé.", exc, "Il est oublié.")
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
            return self._rerank_config_error or "Indisponible : [rag.reranker] non configurée."
        with self._lock:
            return self._rerank_missing_fr

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
            return False, f"Chargement du modèle de reranking {model.label_fr if model else ''}…"
        if error is not None:
            return False, error
        if not embedder:  # the reranker loads after the embedding model, never alone
            rag = self._rag_unavailable()
            return False, (
                "Indisponible tant que la brique RAG l'est"
                + (f" ({rag.removeprefix('Indisponible : ')})" if rag else "")
                + " : le reranker ne se charge qu'après le modèle d'embedding."
            )
        return True, None

    def _rerank_skipped_fr(self) -> str | None:
        """Why a turn with the sub-option enabled runs without reranking (said by its RAG
        step), or `None`."""
        ok, why = self._rerank_availability()
        if not ok:
            return f"Reranking demandé mais non appliqué à ce tour. {why}"
        return "Reranking demandé mais non appliqué à ce tour : le reranker n'est pas chargé."

    def _rerank_card(self) -> dict[str, Any] | None:
        """The RAG card's « Reranking » switch, its reason and « Télécharger » (AD-21)."""
        content, model = self._rag_content, self._rerank_model
        if content is None:
            return None
        with self._lock:
            enabled, missing = self._rag_rerank, list(self._rerank_missing)
        available, reason_fr = self._rerank_availability()
        download = None
        if model is not None and missing:
            size_mb = max(1, round(sum(f.size for f in missing) / 1_000_000))
            download = {
                "target": RERANK_TARGET,
                "label_fr": content.rerank_download_label_fr.format(size_mb=size_mb),
            }
        return {
            "label_fr": content.rerank_label_fr,
            "enabled": enabled,
            "available": available,
            "reason_fr": reason_fr,
            "hosting_fr": "Local",
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
        label = f"le modèle de reranking {model.label_fr}"
        cost = self._load_registry.component_cost(
            model.measured_rss_mb, [f.size for f in model.files]
        )
        refusal = self._load_registry.check_component(label, cost, RERANKER)
        if refusal is not None:
            with scoped(brick="rag", component=RAG_RERANKER):
                self._error(
                    refusal,
                    "budget mémoire dépassé (AD-8)",
                    "Le reranking est indisponible ; le RAG fonctionne sans lui. Il se charge de "
                    "lui-même après un changement de modèle, ou en le réactivant.",
                )
            return None, f"Indisponible : {refusal}"
        path = reranker_module.model_path(model)
        reranker: Reranker | None = None
        try:
            declared = model.load_file.sha256
            if declared and rag_index.file_sha256(path) != declared.lower():
                raise ValueError(
                    f"le fichier {path} n'est pas le modèle déclaré (sha256 différent de "
                    "celui de [rag.reranker])"
                )
            reranker = self._reranker_factory(model)
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            self._close_reranker(reranker)
            with scoped(brick="rag", component=RAG_RERANKER):
                self._error(
                    "Le modèle de reranking n'a pas pu être chargé.",
                    exc,
                    "Le reranking est indisponible ; le RAG fonctionne sans lui.",
                )
            return None, (
                f"Indisponible : le modèle de reranking n'a pas pu être chargé "
                f"({type(exc).__name__}: {exc}). Vérifiez le fichier {path}, ou supprimez-le "
                "et cliquez sur « Télécharger »."
            )
        self._load_registry.grant(model.label_fr, cost, RERANKER)
        return reranker, None

    def _close_reranker(self, reranker: Reranker | None) -> None:
        if reranker is not None:
            try:
                reranker.close()
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error("Le modèle de reranking n'a pas pu être fermé.", exc, "Il est oublié.")
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
            return compressor.label_fr
        return str(getattr(self._compressor_factory, "label_fr", "le compresseur"))

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
            named = getattr(self._compressor_factory, "label_fr", None)
            return f"Chargement de {named}…" if named else "Chargement du compresseur…"
        return error or "Compresseur non chargé : désactivez puis réactivez la brique."

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
                    "budget mémoire dépassé (AD-8)",
                    "La brique « Compression » est indisponible ; rien n'est chargé. Elle se "
                    "charge d'elle-même après un changement de modèle, ou en la réactivant.",
                )
            return None, f"Indisponible : {refusal}"
        try:
            compressor = self._compressor_factory()
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            with scoped(brick="compression", component="compression.compressor"):
                self._error(
                    "Headroom n'a pas pu être chargé.",
                    exc,
                    "La brique « Compression » est indisponible ; le reste de WaveStack "
                    "fonctionne.",
                )
            return None, (
                f"Indisponible : Headroom n'a pas pu être chargé ({type(exc).__name__}: {exc}). "
                "Réinstallez-le avec `uv sync --extra compression`, puis relancez WaveStack."
            )
        self._compressor_imported = True
        self._load_registry.grant(compressor.label_fr, cost, COMPRESSOR)
        return compressor, None

    def _close_compressor(self, compressor: Compressor | None) -> None:
        if compressor is not None:
            try:
                compressor.close()
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error("Le compresseur n'a pas pu être fermé.", exc, "Il est oublié.")
        self._load_registry.release(COMPRESSOR)

    def _release_compressor(self) -> None:
        with self._lock:
            compressor, self._compressor = self._compressor, None
        self._close_compressor(compressor)

    def _emit_memory(self) -> None:
        """AD-1: the drawer and the card project the last `memory_changed`."""
        if "global_memory" not in self._bricks:
            return
        error_fr = self._memory_unavailable_fr()
        with self._lock:
            entries = [e.model_dump() for e in self._memory] if error_fr is None else []
        get_journal().emit(
            "memory_changed",
            {
                "entries": entries,
                "path": str(config.memory_path()),
                "error_fr": error_fr,
                "max_entries": memory_file.MAX_ENTRIES,
                "max_chars": memory_file.MAX_CHARS,
            },
        )

    # ---------- bricks (AD-12) ----------

    def _label(self, brick_id: str) -> str:
        content = self._content.get(brick_id)
        return content.label_fr if content else brick_id

    def _availability(self, brick_id: str) -> tuple[bool, str | None]:
        """The single point computing `available` and its French reason (AD-12)."""
        brick = self._bricks.get(brick_id)
        if brick is None:
            return False, f"La brique « {brick_id} » n'existe pas dans cette version."
        with self._lock:
            wanted = set(self._wanted)
        for dep in brick.requires:
            if dep not in wanted or not self._availability(dep)[0]:
                return False, f"Nécessite la brique « {self._label(dep)} » : activez-la d'abord."
        if (reason := self._capability_reason(brick_id)) is not None:
            return False, reason
        if brick_id in self._content_errors:
            return False, self._content_errors[brick_id]
        if brick_id == "global_memory":
            with self._lock:
                error_fr = self._memory_error
            if error_fr is not None:
                return False, error_fr
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
            return (
                f"Le modèle cloud « {self._cloud.id} » ne déclare pas l'appel d'outils (tools) : "
                "aucune action d'outil, pas même forcée. Déclarez tools = true si le modèle le "
                "gère, ou choisissez un autre modèle."
            )
        if missing:
            needs = ", ".join(_CAPABILITIES_FR.get(c, c) for c in missing)
            return f"Le modèle chargé n'offre pas {needs} : choisissez un autre modèle."
        return None

    def _no_reasoning_fr(self) -> str:
        """EXPERIENCE.md's reason, then its cause: no model, the template, or the cloud
        declaration."""
        if self._caps is None:
            return "Indisponible : aucun modèle chargé."
        if self._cloud is not None:
            return (
                "Indisponible : le modèle actif ne sait pas raisonner. Le modèle cloud "
                f"« {self._cloud.id} » ne déclare pas de raisonnement (reasoning) : déclarez-le "
                "si le modèle le gère, ou choisissez un autre modèle."
            )
        return (
            "Indisponible : le modèle actif ne sait pas raisonner. Son gabarit de conversation "
            "n'a pas de variable de raisonnement : choisissez un modèle qui raisonne."
        )

    def _memory_card(self) -> dict[str, Any]:
        """What the memory card and its drawer say (AD-19): the note without a tool parser
        (H4), the empty drawer's text, the forced write's field help."""
        note_fr = self._memory_note_fr()
        content = self._memory_content
        if content is None:
            return {"note_fr": note_fr}
        drawer = content.drawer
        return {
            "note_fr": note_fr,
            "empty_fr": drawer.empty_no_parser_fr if note_fr else drawer.empty_fr,
            "text_help_fr": drawer.text_help_fr.replace("{max_chars}", str(memory_file.MAX_CHARS)),
        }

    def _memory_note_fr(self) -> str | None:
        """H4: without a tool parser, the memory is injected and edited, not written by the
        model."""
        if self._caps is None or self._caps.tool_call_parser:
            return None
        return (
            "Le modèle actif ne sait pas appeler d'outil : il ne peut pas écrire en mémoire "
            "lui-même, et « Écrire en mémoire » ne s'applique pas. La mémoire reste injectée "
            "dans le contexte et modifiable depuis « Modifier la mémoire »."
        )

    def _always_fr(self) -> str | None:
        """AD-6: a cloud model that always reasons shows it on the reasoning card."""
        entry = self._cloud
        if entry is None or not entry.always_reasons:
            return None
        return (
            f"Toujours active pour ce modèle : {entry.model} raisonne à chaque réponse ; ce "
            f"modèle ne permet pas de l'éteindre. La réserve de sortie reste de "
            f"{_fr(MAX_RESERVE)} tokens."
        )

    def _reasoning_budget_fr(self) -> str | None:
        """Lot C (N4): the reasoning budget, local mode only (a cloud provider manages its
        own reasoning effort)."""
        caps = self._caps
        if self._cloud is not None or caps is None or not (caps.reasoning_tags and caps.reasoning):
            return None
        budget = self.cfg.reasoning_budget_tokens
        return (
            f"Budget de réflexion : {_fr(budget)} tokens ; au-delà, le harnais ferme la "
            f"réflexion et garde {_fr(MAX_RESERVE - budget)} tokens pour la réponse."
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
            rag_rerank_skipped_fr=skipped,
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
    ) -> list[dict[str, Any]]:
        """Intermediate messages of a turn: `assistant_turn`/`tool_result` in the turn itself
        (or the step's own `kind`), `history` afterwards, where a step's `stub` replaces its
        content. Each call's name and arguments form one group (AD-4). Calls carry their
        session `id`, replies its `tool_call_id`. Chat mode (AD-4): the reasoning sent back
        only with `resend` (its `format`), an empty `content` omitted, `arguments` as the
        string emitted, a reply without `name`, and a malformed call's error sent as a `user`
        message. `wrap` (lot A, local mode): a past step rendered as it was produced
        (`_as_produced`)."""
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
                    answer["tool_calls"].append(
                        {"id": call.get("id"), "type": "function", "function": function}
                    )
            messages.append(answer)
        return messages

    @staticmethod
    def _assistant_message(
        content: Part, reasoning: str, *, chat: bool, resend: str | None, omit_empty: bool
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
            tagged = thought._replace(text=f"<think>{reasoning}</think>")
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
            body = f"Skill « {text.label_fr} » ({s}) :\n{text.body}"
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
                    ex.steps, history=True, group=ex.turn_id, chat=chat, resend=resend, wrap=wrap
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
            steps or [], history=False, group="turn", chat=chat, resend=resend
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
            first = next(iter((tool.description or "").strip().splitlines()), "").strip()
            if len(first) > DOC_LINE_MAX:
                first = first[:DOC_LINE_MAX].rstrip() + "…"
            text = f"- {name} : {first}" if first else f"- {name}"
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
            provider_label_fr=content.provider_segment_fr,
        )
        rendered.seen = seen_prefix(read_before, rendered.segments)
        payload = self._chat_gauge(
            rendered,
            round(rendered.raw_total * self._ratio),
            "estimate",
            reserve,
        )
        if not payload["overflow"] and payload["used"] > payload["usable"]:
            payload["uncertain_fr"] = content.uncertain_fr
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
                    [(i, c.title_fr, c.text) for i, c in enumerate(longest, start=1)]
                ),
            )
        try:
            _, payload = self._render(state, "", None)
        except Exception as exc:  # noqa: BLE001 - AD-16
            self._error(
                "L'aperçu du contexte n'a pas pu être calculé.",
                exc,
                "La jauge reste vide jusqu'au premier tour.",
            )
            return
        get_journal().emit("context_preview", payload)

    def _rag_texts(self, excerpts: list[tuple[int, str, str]]) -> tuple[str, ...]:
        """The intro, then each `(position, title_fr, text)` in `excerpt_format_fr`."""
        content = self._rag_content
        if content is None or not excerpts:
            return ()
        return (content.intro_fr, *(content.excerpt(*excerpt) for excerpt in excerpts))

    def _preview_injection(self, state: TurnState) -> str:
        """What the active `on_user_message` hooks would add, for the gauge only: no
        decision emitted, a failing hook left out."""
        texts = []
        for hook in self._hooks:
            if hook.id not in state.hooks or "on_user_message" not in hook.points:
                continue
            try:
                result = hook.fn(HookContext("on_user_message", "", content=self._hooks_content))
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
            if self.state != "idle" or self._engine is None or self.reason_fr:
                raise SendRefused(self._refusal_reason())
            if message is None:
                if self._last is None:
                    raise SendRefused("Aucun prompt à rejouer : envoyez d'abord un message.")
                replay_of, message, history, skills, docs, memory = self._last
                self._history[:] = history
                self._loaded_skills, self._loaded_docs = set(skills), set(docs)
                self._memory_snapshot = memory  # N1: the memory of its conversation
                self._cache_cause = self._cache_cause or "replay"
            self._turns += 1
            turn_id = f"t{self._turns}"
            cancel = self._cancel = CancelToken()
            # Switched under the lock, so a second `send` racing this one is refused.
            self.state, self.reason_fr = "turn", _TURN_FR
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
        if kind == "tool":  # a tool of the tools brick, never an MCP one (2026-09-25)
            spec = self._registry.get(target)
            if spec is None or spec.is_mcp or spec.source == "harness":
                raise ArmRefused(
                    f"Outil inconnu : « {target} » n'est pas un outil de la brique Outils. "
                    "Rien n'est armé.",
                    not_found=True,
                )
            # The form's fields are text: converted per the tool's schema, as a model's call.
            args = {
                arg: convert_value(value, spec.params.get(arg)) if isinstance(value, str) else value
                for arg, value in args.items()
            }
            detail = self._tool_executor.check(ToolCall(target, args), [target])
            if detail is not None:
                raise ArmRefused(f"{detail} Rien n'est armé.")
            brick = spec.brick or spec.component.split(".")[0]
            shown = ", ".join(str(value) for value in args.values())
            label = self._registry.label(target)
            label_fr = f"{label} ({shown})" if shown else label
        elif kind == "skill":
            if self._skills_content is None or target not in self._skill_ids():
                raise ArmRefused(f"Skill inconnu : « {target} ». Rien n'est armé.", not_found=True)
            args, brick, label_fr = {}, "skills", self._skill_label(target)
        elif kind == "tool_doc":
            spec = self._registry.get(target)
            if self._mcp_content is None or spec is None or not spec.is_mcp:
                raise ArmRefused(
                    f"Outil MCP inconnu : « {target} » n'est l'outil d'aucun serveur connecté. "
                    "Rien n'est armé.",
                    not_found=True,
                )
            args, brick, label_fr = {}, "mcp", f"Documentation de {target}"
        elif kind == "memory":
            if self._memory_content is None or target != REMEMBER:
                raise ArmRefused(
                    f"Action de mémoire inconnue : « {target} ». Rien n'est armé.", not_found=True
                )
            try:
                text = memory_file.check_text(args.get("text"))
            except ValueError as exc:
                raise ArmRefused(f"{exc} Rien n'est armé.") from None
            shown = text if len(text) <= 40 else f"{text[:40].rstrip()}…"
            args, brick, label_fr = {"text": text}, "global_memory", f"Écrire en mémoire ({shown})"
        elif kind == "delegate":  # story 19: the card's action, its target fixed
            if self._subagent_content is None or target != DELEGATE:
                raise ArmRefused(
                    f"Action inconnue : « {target} » n'est pas la délégation au sous-agent. "
                    "Rien n'est armé.",
                    not_found=True,
                )
            extra = sorted(set(args) - {"task"})
            if extra:
                raise ArmRefused(
                    f"Argument inconnu pour la délégation : {', '.join(extra)}. Seule la tâche "
                    "(« task ») est attendue. Rien n'est armé."
                )
            task = args.get("task", "")
            if not isinstance(task, str):
                raise ArmRefused("La tâche du sous-agent doit être un texte. Rien n'est armé.")
            task = task.strip()
            if not task:
                raise ArmRefused("La tâche du sous-agent est vide. Rien n'est armé.")
            shown = task if len(task) <= 40 else f"{task[:40].rstrip()}…"
            args, brick, label_fr = {"task": task}, "subagent", f"Délégation : « {shown} »"
        else:
            raise ArmRefused(f"Action inconnue : « {kind} ». Rien n'est armé.", not_found=True)
        with self._lock:
            self._arms += 1
            action = ArmedAction(f"arm{self._arms}", kind, brick, target, args, label_fr)
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
                f"Aucune action armée « {armed_id} » : elle a déjà été consommée ou désarmée.",
                not_found=True,
            )
        self._emit_armed()

    def _emit_armed(self) -> None:
        """AD-1: the front projects the chips from this event, replayed on reload."""
        with self._lock:
            actions = [a.payload() for a in self._armed]
        get_journal().emit("armed_actions_changed", {"actions": actions})

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
                    label_fr=text.label_fr,
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
                    label_fr=text.label_fr,
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
                    label_fr=text.phase_label_fr,  # the working indicator's phase (EXPERIENCE)
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
            raise DelegationFailed("Délégation impossible hors d'un tour.", "error")
        task = task.strip()
        if not task:
            raise DelegationFailed(
                "La tâche du sous-agent est vide : décris-la dans l'argument « task ».", "error"
            )
        state, cancel = ctx
        self._subs += 1
        sub = _SubContext(f"sub{self._subs}", task, text.prompt, state.subagent_tools)
        journal = get_journal()
        started = time.monotonic()
        # `estimated`: chat mode, the context's figures not reconciled by `usage` (AD-4).
        figures = {"calls": 0, "context_tokens": 0, "kept_tokens": 0, "estimated": 0}
        outcome = _SubOutcome("error", message_fr="le sous-agent s'est interrompu.")
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
                {"task": task, "tools": list(sub.tools), "phase_label": text.phase_label_fr},
            )
            try:
                outcome = self._run_subagent(sub, state, cancel, figures)
            except Exception as exc:  # noqa: BLE001 - AD-16: the delegation fails, not the turn
                self._error(
                    "Le sous-agent s'est interrompu sur une erreur.",
                    exc,
                    "La délégation échoue ; le tour principal continue.",
                )
            finally:
                restore_ms = self._restore_main_state(saved, figures["calls"])
                done = outcome.status == "completed"
                failure = None if done else self._delegation_failure(outcome)
                # What the main context reads: the result, or the error the executor
                # reinjects in its place (« Erreur : … »).
                result = outcome.result if done else f"Erreur : {failure.message_fr}"
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
            return DelegationFailed(
                "Délégation arrêtée à la demande de l'utilisateur.", "cancelled"
            )
        status = outcome.status if outcome.status in ("limit", "overflow") else "error"
        return DelegationFailed(
            f"La délégation au sous-agent a échoué : {outcome.message_fr} Réponds sans ce "
            "résultat, ou délègue une tâche plus simple.",
            status,
        )

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
                f"[subagent] tools nomme des outils inconnus : {', '.join(unknown)}.",
                f"Outils de la brique Outils : {', '.join(sorted(known))}.",
                "Ces noms sont ignorés : le sous-agent n'a que les outils connus et activés.",
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
        journal = get_journal()
        turn_id, cid = current().turn_id or "", sub.context_id
        max_calls, max_retries = self.cfg.subagent_max_calls, self.cfg.tool_max_retries
        retries = step = 0
        steps: list[dict[str, Any]] = []
        previous: tuple[list[int], str] | None = None
        read_before: list[Segment] | None = None  # story 32: its previous call's segments
        stopped = _SubOutcome("cancelled", message_fr="délégation arrêtée.")
        for n in range(1, max_calls + 1):
            call_id = f"{turn_id}.{cid}.c{n}"
            with scoped(call_id=call_id):
                decided = self._hook("before_model_call", state)
            if decided is not None and decided[1].decision == "block":
                label = self._hook_label(decided[0])
                return _SubOutcome(
                    "error", message_fr=f"le hook « {label} » a bloqué son appel au modèle."
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
                        message_fr=f"son contexte est dépassé ({_fr(payload['used'])} tokens pour "
                        f"{_fr(payload['usable'])} utilisables).",
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
                    message_fr=f"sa sortie a été coupée à {_fr(payload['reserve'])} tokens.",
                )
            if out.status != "completed":  # a provider's refusal, traced in `sub{n}` (AD-16)
                return _SubOutcome("error", message_fr=out.message_fr or "appel au modèle refusé.")
            if not out.calls and out.malformed is None:
                return _SubOutcome("completed", result=out.text.strip() or _NO_SUB_TEXT_FR)
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
                            out.raw, out.malformed.fragment, out.malformed.detail_fr, reaction
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
                        "limit",
                        message_fr=f"{retries} appels d'outil refusés (mal formés, outil inconnu "
                        "ou arguments invalides).",
                    )
            if cancel.cancelled:
                return stopped
        self._emit_limit("sub_calls", max_calls)
        return _SubOutcome(
            "limit", message_fr=f"il a atteint sa borne de {max_calls} appels au modèle."
        )

    @staticmethod
    def _assistant_step(out: _ModelOutput) -> dict[str, Any]:
        """The assistant step of an output with tool calls: each call with its session id,
        its arguments and their JSON, as emitted in chat mode, else serialized once (AD-4)."""
        return {
            "role": "assistant",
            "content": out.text,
            "tool_calls": [
                {
                    "id": call_ref,
                    "name": c.name,
                    "arguments": c.arguments,
                    "arguments_json": (
                        out.arguments[j]
                        if out.arguments
                        else json.dumps(c.arguments, ensure_ascii=False)
                    ),
                }
                for j, (c, call_ref) in enumerate(zip(out.calls, out.ids, strict=True))
            ],
        } | ({"reasoning": out.reasoning} if out.reasoning else {})

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
            label_fr=text.label_fr,
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
            return f"La documentation de « {tool} » est déjà chargée."
        if tool not in available:
            loadable = ", ".join(n for n in available if n not in loaded) or "aucun"
            raise ToolError(
                f"Aucun outil MCP disponible ne s'appelle « {tool} ». Outils chargeables : "
                f"{loadable}."
            )
        definition = json.dumps(self._registry.definition(tool), ensure_ascii=False)
        return ToolReply(definition, (ToolDocLoaded(tool=tool),))

    def _load_skill(self, skill: str) -> ToolReply | str:
        """AD-25: reads the skills, writes nothing; the session applies the effect (AD-23)."""
        with self._lock:
            enabled, loaded = set(self._skills_enabled), set(self._loaded_skills)
        if skill in enabled and skill in loaded:
            return f"Le skill « {skill} » est déjà chargé."
        text = self._skill_text(skill)
        if skill not in enabled or text is None:
            loadable = [s for s in self._skill_ids() if s in enabled and s not in loaded]
            raise ToolError(
                f"Aucun skill activé ne s'appelle « {skill} ». Skills chargeables : "
                f"{', '.join(loadable) or 'aucun'}."
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
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        if self._memory_unavailable_fr() is not None:  # the brick is unavailable then
            raise ToolError("La mémoire globale est illisible : rien n'est écrit.")
        with self._lock:
            entries = list(self._memory)
        if any(memory_file.same_text(e.text, text) for e in entries):
            return f"Déjà en mémoire : « {text} ». Rien n'est ajouté."
        if len(entries) >= memory_file.MAX_ENTRIES:
            raise ToolError(
                f"La mémoire globale est pleine ({memory_file.MAX_ENTRIES} entrées) : rien "
                "n'est écrit. Réponds sans retenir cette information."
            )
        write = MemoryWrite(op="add", entry_id=memory_file.new_entry_id(), text=text)
        return ToolReply(
            f"Retenu en mémoire globale : « {text} ». Cette information sera dans le "
            "contexte des prochaines conversations.",
            (write,),
        )

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
                    "La mémoire globale n'a pas été modifiée.",
                    exc,
                    "Elle reste inchangée ; le reste de WaveStack fonctionne.",
                )
                return "La mémoire globale n'a pas été modifiée : rien n'est retenu."
            try:
                memory_file.write_memory(config.memory_path(), updated)
            except OSError as exc:
                self._error(
                    "La mémoire globale n'a pas pu être écrite.",
                    exc,
                    "Elle reste inchangée ; le reste de WaveStack fonctionne.",
                )
                return "La mémoire globale n'a pas pu être écrite : rien n'est retenu."
            with self._lock:
                self._memory = updated
                self._memory_error = None  # written: readable again (reset, H5)
            with scoped(brick="global_memory", component=MEMORY):
                for write in writes:
                    get_journal().emit(
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
                        raise ValueError(f"« {text} » est déjà en mémoire : rien n'est modifié.")
                    writes = [MemoryWrite(op="replace", entry_id=entry.id, text=text)]
                elif op == "delete":
                    writes = [MemoryWrite(op="delete", entry_id=entry.id, text=entry.text)]
                else:
                    raise ValueError(f"Opération inconnue : « {op} ».")
            if not writes:
                return
            with scoped(trigger="user"):
                if self._apply_memory(writes, "user") is not None:
                    raise OSError(
                        "La mémoire globale n'a pas pu être écrite : elle reste inchangée."
                    )
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
                entries, error_fr = list(self._memory), self._memory_error
            if error_fr is None and memory_file.is_demo(entries, demo):
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
                )
                if loop is not None
                else None
            )
            if conn is not None:
                self._mcp_conns[server_id] = conn
        journal = get_journal()
        with scoped(brick="mcp", component=server.component):
            journal.emit(
                "mcp_connect_started",
                {
                    "server": server_id,
                    "phase_label": f"Connexion au serveur MCP {self._mcp_label(server_id)}",
                },
            )
        started = time.monotonic()
        if conn is None:
            reason = "Connexion impossible : la boucle asyncio de WaveStack n'est pas démarrée."
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
        error_fr = None
        if error is not None:
            error_fr = (
                str(error)
                if conn is None
                else describe_error(error, self.cfg.mcp_connect_timeout_s)
            )
        if conn is not current_conn:  # disabled or closed meanwhile: nothing to apply
            error_fr = "Connexion abandonnée : le serveur a été désactivé."
        elif error_fr is not None:
            with self._lock:
                self._mcp_conns.pop(server_id, None)
                self._mcp_state[server_id] = ("unavailable", error_fr)
        else:
            specs = [self._mcp_spec(server, conn, tool) for tool in tools]
            self._registry.remove(f"{server_id}__")
            names = self._registry.add(specs)
            with self._lock:
                self._mcp_state[server_id] = ("available", None)
        with scoped(brick="mcp", component=server.component):
            get_journal().emit(
                "mcp_connect_ended",
                {
                    "server": server_id,
                    "status": "ok" if error_fr is None else "error",
                    "tools": names,
                    "error_fr": error_fr,
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
            run=lambda **arguments: conn.call(name, arguments),
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

    def _mcp_failed(self, server_id: str, reason_fr: str | None) -> None:
        """On the worker: a call could not reach its server, which becomes `unavailable`."""
        with self._lock:
            conn = self._mcp_conns.pop(server_id, None)
            if conn is None:  # disabled during the call: it stays « non contacté »
                return
            self._mcp_state[server_id] = ("unavailable", reason_fr)
        conn.close(wait=False)
        self._registry.remove(f"{server_id}__")

    async def aclose_mcp(self) -> None:
        """On the loop, at shutdown: close every connection before `close` (AD-21)."""
        with self._lock:
            conns = list(self._mcp_conns.values())
            self._mcp_conns.clear()
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
        get_journal().emit("conversation_cleared", {})
        self._emit_architecture()
        self._executor.submit(self._emit_preview)

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
            self._scenarios = load_scenarios(known)
        except Exception as exc:  # noqa: BLE001
            self._error(
                "Le fichier des scénarios (content/scenarios.yaml) est absent ou invalide.",
                exc,
                "Le sélecteur de scénario est vide ; le reste de WaveStack fonctionne.",
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
            for block in content.explanation_fr
        ]

    def _emit_scenario(self, *, refresh: bool = False) -> None:
        """`refresh` (lot E, E5): the same scenario, its unavailable bricks read again after a
        model load; not a launch."""
        program = self._scenarios.payload(self._fill) if self._scenarios else EMPTY_PROGRAM
        with self._lock:
            active = self._active_scenario
        get_journal().emit(
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
                    {"brick": brick_id, "label_fr": self._label(brick_id), "reason_fr": reason}
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
            journal = get_journal()
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
            return "Un tour est déjà en cours : attendez sa fin ou cliquez sur « Arrêter »."
        if self.reason_fr:
            return self.reason_fr
        return "Aucun modèle n'est chargé : terminez le diagnostic de démarrage."

    def stop(self) -> bool:
        """Intention class (c): arms the turn's `CancelToken`; no effect outside a turn. A
        pending human validation is resolved as `cancelled`. Story 15: stops a download or an
        index build. Lot E (E4): stops a model load at its next checkpoint."""
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
        noun = "de reranking" if rerank else "d'embedding"
        if model is None:
            raise SendRefused(
                (self._rerank_config_error if rerank else self._content_errors.get("rag"))
                or f"La brique RAG n'a pas de modèle {noun} déclaré."
            )
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
        dest = config.models_dir()
        missing = download_module.missing_files(model.files, dest)
        if not missing:  # e.g. copied by hand meanwhile: the card catches up now
            self._rag_caught_up()
            raise SendRefused(
                f"Rien à télécharger : les fichiers du modèle {noun} sont déjà dans {dest}."
            )
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

    def _enter_rag_job(self, state: str, reason_fr: str, cancel: CancelToken) -> str | None:
        """`download` or `index_build`, switched under the lock from `idle` (class b). Returns
        the reason `idle` had (e.g. no model loaded), given back afterwards."""
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            previous = self.reason_fr
            self.state, self.reason_fr = state, reason_fr
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
    def _download_fr(done: int, total: int, noun: str = "d'embedding") -> str:
        percent = int(done * 100 / total) if total else 100
        return f"Téléchargement du modèle {noun} : {percent} % ({_mo(done)} / {_mo(total)} Mo)"

    def _throttled(self, state: str, text: Callable[[int, int], str]) -> Callable[[int, int], None]:
        """A progress callback: `session_state.reason_fr` at most once a second."""
        last = time.monotonic()

        def progress(done: int, total: int) -> None:
            nonlocal last
            if time.monotonic() - last < 1.0:
                return
            last = time.monotonic()
            with self._lock:
                if self.state != state:
                    return
                self.reason_fr = text(done, total)
            self._emit_state()

        return progress

    def _run_download(
        self,
        files: list[ModelFile],
        dest: Path,
        cancel: CancelToken,
        previous: str | None,
        *,
        noun: str = "d'embedding",
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
            failed, stopped = exc.reason_fr, exc.cancelled
        except Exception as exc:  # noqa: BLE001 - AD-16: a state, never a crash
            failed = f"{type(exc).__name__}: {exc}"
        with self._lock:
            self._download_cancel = None
        with scoped(brick="rag", component=component):  # the card shows it (AD-1)
            if failed is not None:
                names = ", ".join(PurePosixPath(f.path).name for f in files)
                folder = dest / PurePosixPath(files[0].path).parent
                self._error(
                    f"Téléchargement du modèle {noun} arrêté."
                    if stopped
                    else f"Le téléchargement du modèle {noun} a échoué.",
                    failed,
                    f"Rien n'est installé. Pour continuer, copiez le fichier à la main dans "
                    f"{folder} ({names}), puis cliquez de nouveau sur « Télécharger ».",
                )
            else:
                get_journal().emit(
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
            raise SendRefused(
                self._content_errors.get("rag") or "La brique RAG n'a pas de modèle déclaré."
            )
        self._rag_refresh()  # the files may have been copied, the corpus edited
        if self._rag_offers()["build_index"] is None:
            with self._lock:
                kind, missing = self._rag_index_kind, bool(self._rag_missing)
            self._rag_caught_up()
            if missing:
                raise SendRefused(
                    "Construction impossible : le modèle d'embedding n'est pas sur le poste. "
                    "Cliquez d'abord sur « Télécharger »."
                )
            if kind == "vec":
                raise SendRefused(self._rag_index_error or "sqlite-vec ne se charge pas.")
            raise SendRefused("Rien à construire : l'index est à jour.")
        cancel = CancelToken()
        previous = self._enter_rag_job("index_build", self._build_fr(0, 0), cancel)
        threading.Thread(
            target=self._run_build,
            args=(model, content, cancel, previous),
            name="wavestack-index-build",
            daemon=True,
        ).start()
        return self._build_fr(0, 0)

    @staticmethod
    def _build_fr(done: int, total: int) -> str:
        if not total:
            return "Construction de l'index RAG : chargement du modèle d'embedding…"
        return f"Construction de l'index RAG : {done} / {total} extraits"

    def _run_build(
        self,
        model: EmbeddingModel,
        content: RagContent,
        cancel: CancelToken,
        previous: str | None,
    ) -> None:
        """The build thread: its own embedding model, through the registry (AD-8), closed
        afterwards; the index written then read again; the brick loads if wanted."""
        path = self.cfg.rag_index_path()
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
                )
            except rag_index.BuildCancelled as exc:
                failed, stopped = str(exc), True
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
                    "Construction de l'index RAG arrêtée."
                    if stopped
                    else "L'index RAG n'a pas pu être construit.",
                    failed,
                    f"L'index {path} n'est pas modifié.",
                )
            elif meta is not None:
                get_journal().emit(
                    "effect_applied",
                    {
                        "effect": "rag_index_write",
                        "lines": [
                            f"{path} · {meta.chunks} extraits · modèle d'embedding "
                            f"{meta.embedding_model_id} ({meta.dims} dimensions)"
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
        label = f"le modèle d'embedding {model.label_fr}"
        cost = self._load_registry.component_cost(
            model.measured_rss_mb, [f.size for f in model.files]
        )
        refusal = self._load_registry.check_component(label, cost, EMBEDDING)
        if refusal is not None:
            return None, refusal
        try:
            embedder = self._embedder_factory(model)
        except Exception as exc:  # noqa: BLE001 - AD-16
            return None, (
                f"le modèle d'embedding n'a pas pu être chargé ({type(exc).__name__}: {exc})"
            )
        self._load_registry.grant(model.label_fr, cost, EMBEDDING)
        return embedder, None

    def answer_approval(self, approval_id: str, approved: bool, disable_hook: bool) -> None:
        """Intention class (c): answers the pending validation; the first answer wins.
        `disable_hook` only counts with `approved`. Raises `SendRefused` otherwise."""
        with self._lock:
            approval = self._approval
            if approval is None or approval.id != approval_id:
                raise SendRefused(
                    f"Aucune validation « {approval_id} » n'est en attente : elle n'existe pas "
                    "ou a déjà reçu une réponse."
                )
            if approval.decision is not None:
                raise SendRefused("Cette validation a déjà reçu une réponse : la première compte.")
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
        journal = get_journal()
        self._hook_steps = 0
        self._approvals = 0
        self._turn_called = False  # lot A: set by `_keep_cache`
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
                    exc.message_fr
                    if isinstance(exc, ServerError)
                    else "Le tour s'est interrompu sur une erreur.",
                    exc,
                    "Le tour est terminé ; WaveStack reste utilisable.",
                )
            finally:
                self._turn_ctx = None
                try:
                    ended = self._hook("on_turn_end", state, status=status)
                except Exception as exc:  # noqa: BLE001 - AD-16: the turn still ends
                    ended = None
                    self._error(
                        "Les hooks de fin de tour se sont interrompus.",
                        exc,
                        "Le tour se termine sans eux.",
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
                    {"status": status, "duration_ms": _ms(time.monotonic() - started)},
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
        journal = get_journal()
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
        # the call budget (AD-10).
        stopped, step = self._consume_armed(turn_id, state, cancel, steps, loaded_in_turn)
        if stopped:
            return "cancelled", "", ""
        if "rag" in state.effective:  # story 15: once per turn, main context, before any call
            step += 1
            excerpts = self._rag_search(
                turn_id, step, message, state.rag_rerank, state.rag_rerank_skipped_fr
            )
            if state.rag_rerank and excerpts and not cancel.cancelled:  # story 16: its own step
                step += 1
                excerpts = self._rag_rerank_step(turn_id, step, message, excerpts, cancel)
            texts = [(e.position, e.title_fr, e.text) for e in excerpts[: self.cfg.rag_top_k]]
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
                            out.raw, out.malformed.fragment, out.malformed.detail_fr, reaction
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
        # (source_fr, kind, brick, component, text, where: ("step" | "rag", index))
        candidates: list[tuple[str, SegmentKind, str | None, str | None, str, tuple]] = []
        if first:
            for i, text in enumerate(state.rag_excerpts):
                if i > 0 and len(text.strip()) >= minimum:  # 0: the excerpts' intro
                    source = content.rag_source_fr.format(n=i)
                    candidates.append(
                        (source, SegmentKind.RAG_EXCERPT, "rag", "rag.retriever", text, ("rag", i))
                    )
        for i in range(sent, len(steps)):
            reply = steps[i]
            if self._compressible(reply):
                source = content.tool_source_fr.format(tool=reply.get("name"))
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
        journal = get_journal()
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
                    "phase_label": content.phase_label_fr,
                    "title_fr": content.step_title_fr,
                    "items": len(candidates),
                    "compressor_fr": compressor.label_fr,
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
                        "compressor_fr": compressor.label_fr,
                        "items": items,
                        "tokens_before": total_before,
                        "tokens_after": total_after,
                        "saved_tokens": max(0, total_before - total_after),
                        "estimated": estimated,
                        "unchanged_fr": content.unchanged_fr,
                        "error_fr": " ".join(errors) or None,
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
        after_text, transforms, error_fr = original, (), None
        try:
            result = compressor.compress(text)
            after_text = (result.text or "").strip()
            transforms = tuple(str(t) for t in (result.transforms or ()))
        except Exception as exc:  # noqa: BLE001 - AD-16: the original goes on
            error_fr = f"{source} : la compression a échoué ({type(exc).__name__}: {exc})."
            errors.append(error_fr)
            self._error(
                "La compression d'un texte a échoué.",
                exc,
                "Le texte d'origine part tel quel ; le tour continue.",
            )
        after, estimate_after = self._count_tokens(after_text) if after_text else (0, False)
        changed = error_fr is None and bool(after_text) and after_text != original
        changed = changed and after < before
        return {
            "source_fr": source,
            "kind": kind.value,
            "tokens_before": before,
            "tokens_after": after if changed else before,
            "text_before": original,
            "text_after": after_text if changed else None,
            "changed": changed,
            "transforms": list(transforms),
            "error_fr": error_fr,
            "estimated": estimated or estimate_after,
        }

    def _rag_current_retriever(self) -> SqliteVecRetriever:
        """The loaded retriever, on the index as it is now. An index replaced since it was
        read (rebuilt by the script) is read again; one that no longer fits the model makes
        the brick unavailable, and this search fails with the reason."""
        with self._lock:
            embedder, retriever, stamp = self._embedder, self._rag_retriever, self._rag_stamp
        if embedder is None or retriever is None:
            raise RuntimeError("le modèle d'embedding n'est pas chargé")
        path = self.cfg.rag_index_path()
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
            raise RuntimeError(f"l'index a été remplacé pendant la séance. {reason}")
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
        rerank_skipped_fr: str | None = None,
    ) -> list[Excerpt]:
        """Story 15 (AD-2, AD-22): the search, a step of the harness with its pair of events.
        Returns the excerpts found; a failure is traced and the turn goes on without excerpts
        (as a failing hook lets the turn through). Story 16: with `rerank`, the reranker's
        candidates, none of which goes to the context directly; `rerank_skipped_fr`: why the
        reranking enabled does not apply to this turn, said by the step."""
        content = self._rag_content
        assert content is not None  # the brick is unavailable without it
        top_k = self.cfg.rag_top_k
        placement_fr = content.placement_fr
        if rerank:
            placement_fr = content.rerank_search_placement_fr.format(
                candidates=self.cfg.rag_rerank_candidates, keep=top_k
            )
            top_k = self.cfg.rag_rerank_candidates
        journal = get_journal()
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
                {"query": message, "top_k": top_k, "phase_label": content.phase_label_fr},
            )
            started = time.monotonic()
            try:
                excerpts = self._rag_current_retriever().search(message, top_k)
            except Exception as exc:  # noqa: BLE001 - AD-16: the turn goes on
                self._error(
                    "La recherche RAG a échoué.", exc, "Le tour continue sans extraits RAG."
                )
                journal.emit(
                    "rag_search_ended",
                    {
                        "status": "error",
                        "excerpts": [],
                        "placement_fr": placement_fr,
                        "error_fr": (
                            f"La recherche a échoué ({type(exc).__name__}: {exc}). Le tour "
                            "continue sans extraits RAG."
                        ),
                        "duration_ms": _ms(time.monotonic() - started),
                        "rerank_skipped_fr": rerank_skipped_fr,
                    },
                )
                return []
            journal.emit(
                "rag_search_ended",
                {
                    "status": "ok",
                    "excerpts": [e.payload() for e in excerpts],
                    "placement_fr": placement_fr,
                    "error_fr": None,
                    "duration_ms": _ms(time.monotonic() - started),
                    "rerank_skipped_fr": rerank_skipped_fr,
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
        placement_fr = content.rerank_placement_fr.format(candidates=len(candidates), keep=keep)
        journal = get_journal()
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
                    "phase_label": content.rerank_phase_label_fr,
                },
            )
            started = time.monotonic()
            try:
                with self._lock:
                    reranker = self._reranker
                if reranker is None:
                    raise RuntimeError("le modèle de reranking n'est pas chargé")
                # As the index embeds them: each excerpt with its document's title.
                passages = [f"{c.title_fr}\n{c.text}" for c in candidates]
                raw = reranker.score(message, passages, lambda: cancel.cancelled, progress)
                if len(raw) != len(candidates):
                    raise ValueError(f"{len(raw)} scores pour {len(candidates)} extraits")
                scores, truncated = [], []
                for item in raw:
                    value = float(item.score)  # raises on what is not a figure
                    if not math.isfinite(value):
                        raise ValueError(f"score non fini : {item.score!r}")
                    scores.append(round(min(1.0, max(0.0, value)), 3))
                    truncated.append(bool(item.truncated))
            except Exception as exc:  # noqa: BLE001 - AD-16: the turn goes on
                stopped = isinstance(exc, RerankCancelled)
                if not stopped:
                    self._error(
                        "Le reranking a échoué.",
                        exc,
                        f"Le tour continue avec les {keep} premiers extraits de l'embedding.",
                    )
                journal.emit(
                    "rag_rerank_ended",
                    {
                        "status": "cancelled" if stopped else "error",
                        "excerpts": [],
                        "keep": keep,
                        "placement_fr": placement_fr,
                        "error_fr": (
                            "Reranking arrêté."
                            if stopped
                            else f"Le reranking a échoué ({type(exc).__name__}: {exc}). Le tour "
                            f"continue avec les {keep} premiers extraits de l'embedding."
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
                    "title_fr": candidates[i].title_fr,
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
                    "placement_fr": placement_fr,
                    "error_fr": None,
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
                return result.detail_fr, hook_id
            if result.arguments is not None:
                call = replace(call, arguments=result.arguments)
            if result.decision == "ask_human" and result.preview is not None:
                answer = self._await_human(hook_id, call, result.preview)
                if answer == "cancelled":
                    return None
                if answer == "refused":  # nothing sent; not a new attempt either
                    return (
                        "Refusé par l'utilisateur (validation humaine) : l'appel à "
                        f"« {call.name} » vers {host(result.preview['url'])} n'a pas été envoyé.",
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

        def cut(prefix: str) -> tuple[str, int, bool]:
            kept, rough = count(prefix)
            return prefix + _TRUNCATED_FR.format(kept=kept, total=total), kept, rough

        # The mention at its widest (as many digits kept as in total): one count per step.
        widest = _TRUNCATED_FR.format(kept=total, total=total)
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
    ) -> tuple[bool, int]:
        """AD-3, AD-25: runs the actions the turn took, in arming order, each through the
        single executor, hooks included, with `trigger = user`. Each is rendered as an
        assistant call attributed to its brick, then its reply. A failure (H1's block, a tool
        error) is reinjected, never a new attempt; an unavailable target is dropped with its
        reason. Returns whether the turn was stopped, and the steps numbered so far."""
        step = 0
        for action in state.armed:
            if cancel.cancelled:
                return True, step
            call = self._armed_call(action)
            spec = self._registry.get(call.name)
            reason = self._armed_unavailable(action, state, loaded_in_turn)
            if reason is None and spec is None:
                reason = f"l'outil « {call.name} » n'est plus déclaré"
            if reason is None:
                reason = self._tool_executor.check(call, [call.name])
            if reason is not None or spec is None:
                with scoped(brick=action.brick, trigger="user"):
                    get_journal().emit(
                        "action_dropped",
                        {
                            "armed_id": action.armed_id,
                            "reason_fr": (
                                f"Action forcée « {action.label_fr} » abandonnée : "
                                f"{(reason or '').rstrip('.')}. Le tour continue sans elle."
                            ),
                        },
                    )
                continue
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
            steps.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_ref,
                            "name": call.name,
                            "arguments": call.arguments,
                            "arguments_json": json.dumps(call.arguments, ensure_ascii=False),
                        }
                    ],
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
        if action.kind == "tool":
            if "tools" not in state.effective:
                return "la brique « Outils » n'est pas active dans ce tour"
            if target not in state.tools:
                return f"l'outil « {self._registry.label(target)} » est décoché"
            return None
        if action.kind == "skill":
            if "skills" not in state.effective:
                return "la brique « Skills » n'est pas active dans ce tour"
            with self._lock:
                loaded = target in self._loaded_skills
            if target in state.skills or loaded:
                return f"le skill « {self._skill_label(target)} » est déjà chargé"
            if target not in state.skill_catalog:
                return f"le skill « {self._skill_label(target)} » est décoché"
            return None
        if action.kind == "memory":
            if "global_memory" not in state.effective:
                return "la brique « Mémoire globale » n'est pas active dans ce tour"
            if REMEMBER not in state.tools:  # H4: no tool parser
                return (
                    "le modèle actif ne sait pas appeler d'outil, et l'écriture forcée passe par "
                    "l'outil remember"
                )
            return None
        if action.kind == "delegate":
            if "subagent" not in state.effective:
                return "la brique « Sous-agent » n'est pas active dans ce tour"
            return None
        if "mcp" not in state.effective:
            return "la brique « MCP » n'est pas active dans ce tour"
        with self._lock:
            lazy = self._sent[4]  # the mode frozen for this turn by `send`
        if not lazy and target in state.tools:
            return (
                "la brique « MCP » est en documentation complète : la documentation de "
                f"« {target} » est déjà dans le contexte"
            )
        if target in loaded_in_turn or target in state.tools:
            return f"la documentation de « {target} » est déjà chargée"
        if target not in state.loadable:
            return f"le serveur de l'outil « {target} » n'est pas connecté ou est désactivé"
        return None

    def _await_human(self, hook_id: str, call: ToolCall, preview: dict[str, str]) -> str:
        """H5 (AD-13): `awaiting_human` until the user answers or stops the turn, without
        delay; on the hook's own step. Returns `approved`, `refused` or `cancelled`."""
        journal = get_journal()
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
                    self.state, self.reason_fr = "awaiting_human", _AWAITING_FR
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
        journal = get_journal()
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
                        f"Le hook « {label} » a échoué.",
                        exc,
                        "Il laisse passer : le tour continue.",
                    )
                    continue
                if result is None:  # not concerned: nothing is emitted
                    continue
                if result.decision not in ALLOWED[point]:
                    self._error(
                        f"Le hook « {label} » a rendu la décision « {result.decision} », non "
                        f"permise au point « {point} ».",
                        "Décision hors de la liste permise (AD-13).",
                        "Elle vaut « allow » : le tour continue.",
                    )
                    result = replace(result, decision="allow")
                journal.emit(
                    "hook_decided",
                    {
                        "hook": hook.id,
                        "point": point,
                        "decision": result.decision,
                        "detail_fr": result.detail_fr,
                        "hook_fr": label,
                        "point_fr": texts.points[point] if texts else point,
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
                "Le journal d'audit n'a pas pu être écrit.",
                exc,
                "Ces lignes ne sont pas écrites ; le tour continue. La journalisation les "
                "reprendra à son prochain déclenchement dans ce tour, s'il y en a un ; sinon "
                "elles sont perdues.",
            )
            return
        with scoped(component=AUDIT):
            get_journal().emit("effect_applied", {"effect": "audit_append", "lines": lines})

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
            "stub": f"Documentation de « {tool} » chargée.",
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
            "stub": f"Skill « {self._skill_label(skill_id)} » chargé.",
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
                "Identifiant d'appel d'outil en double dans ce tour.",
                f"{step_id}#{index} donne {call_ref}, déjà attribué.",
                "Le tour continue ; deux réponses d'outil partagent cet identifiant.",
            )
        self._call_ids.add(call_ref)
        return call_ref

    def _emit_limit(self, limit: str, n: int) -> None:
        get_journal().emit(
            "limit_reached", {"limit": limit, "message_fr": _LIMITS_FR[limit].format(n=n)}
        )

    def _check_prefix(self, previous_ids: list[int], raw: str, ids: list[int]) -> None:
        """AD-4: within a turn, call n+1 should extend call n and its output (append only)."""
        assert self._engine is not None
        expected = previous_ids + self._engine.tokenize(raw)
        common = _common_prefix(expected, ids)
        if common < len(expected):
            get_journal().emit(
                "prefix_not_reused",
                {
                    "common_tokens": common,
                    "cause": "in_turn",
                    "message_fr": (
                        f"Cet appel ne prolonge pas exactement le précédent : seuls "
                        f"{_fr(common)} tokens sur {_fr(len(expected))} sont réutilisés, le "
                        "modèle relit le reste. Le gabarit réécrit la sortie du modèle "
                        "autrement qu'elle a été produite."
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
        why = _PREFIX_CAUSES_FR[cause].format(why=_SUBAGENT_EVICTED_FR.get(evicted or "", ""))
        again = len(ids) - common
        hybrid = (
            f", et tout le contexte ({_fr(len(ids))} tokens) sur un modèle hybride comme "
            "Qwen3.5, qui ne sait pas tronquer son cache."
        )
        if not again:  # the new ids end inside the cache: nothing new, but a cut
            tail = (
                f" Les {_fr(len(ids))} tokens du contexte sont déjà en cache, suivis d'autres "
                f"({_fr(len(cached))} en tout) : le moteur doit recalculer au moins le dernier "
                "token" + hybrid
            )
        elif cached:
            tail = (
                f" Seuls {_fr(common)} tokens sur {_fr(len(cached))} en cache sont "
                f"réutilisés : le moteur relit {_fr(again)} tokens" + (hybrid if common else ".")
            )
        else:
            tail = f" Le moteur relit les {_fr(again)} tokens du contexte."
        get_journal().emit(
            "prefix_not_reused",
            {"common_tokens": common, "cause": cause, "message_fr": why + tail},
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
        shown = f"≈ {_fr(raw_used)}" if raw_used is not None else _fr(used)
        tokens = dict.fromkeys(_OVERFLOW_CAUSES_FR, 0)
        for segment in payload["segments"]:
            kind = _OVERFLOW_GROUP.get(segment["kind"], segment["kind"])
            if kind in tokens:  # every kind but the template
                tokens[kind] += segment["tokens"]
        heaviest = max(tokens, key=tokens.__getitem__)  # ties: the message
        with self._lock:
            lazy = self._sent[4]  # the mode frozen for this turn by `send`
        full = heaviest == SegmentKind.TOOL_CATALOG and not lazy
        cause = _TOOL_CATALOG_FULL_FR if full else _OVERFLOW_CAUSES_FR[heaviest]
        if heaviest == SegmentKind.TOOL_RESULT:
            cause = cause.format(compression=self._compression_hint_fr())
        if self._ratio_key() == "sub" and self._subagent_content is not None:
            cause = self._subagent_content.overflow_cause_fr  # AD-11: the sub-agent's context
        get_journal().emit(
            "context_overflow",
            {
                "used": used if raw_used is None else raw_used,
                "usable": usable,
                "message_fr": (
                    f"Le contexte compte {shown} tokens pour {_fr(usable)} utilisables "
                    f"(fenêtre de {_fr(payload['window'])} moins {_fr(payload['reserve'])} "
                    f"réservés à la réponse). {cause}"
                ),
                "strategies_fr": _OVERFLOW_STRATEGIES_FR,
            },
        )

    def _compression_hint_fr(self) -> str:
        """Lot B: « allumez la compression » only when the brick is available and off."""
        if "compression" not in self._bricks or not self._availability("compression")[0]:
            return ""
        with self._lock:
            off = "compression" not in self._wanted
        return _OVERFLOW_COMPRESSION_FR if off else ""

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
        step_id = current().step_id or ""
        journal = get_journal()
        started = time.monotonic()
        journal.emit(
            "model_call_started",
            {
                "phase_label": f"Lecture du contexte ({_fr(len(rendered.ids))} tokens)",
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
                },
                actor="model",
            )

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
                        "message_fr": (
                            f"Raisonnement coupé par le harnais à {_fr(reasoning_tokens)} "
                            f"tokens : la réflexion a atteint le budget de {_fr(budget)} tokens "
                            f"sans se fermer. Le harnais la ferme lui-même ({tags[1]}) et "
                            f"relance le modèle, qui garde {_fr(left)} tokens pour la réponse."
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
                error.message_fr, error.cause, "Le tour est terminé ; WaveStack reste utilisable."
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
                Malformed(
                    fragment,
                    f"la sortie a été coupée à {_fr(limit)} tokens au milieu de l'appel",
                ),
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

    def _call_model_chat(
        self, rendered: RenderedChat, cancel: CancelToken, reserve: int
    ) -> _ModelOutput:
        """AD-5, chat mode: the body sent as is, under `origin = model`; a provider's refusal
        becomes `harness_error` (AD-16); `usage` reconciles the gauge (AD-4)."""
        entry = self._cloud
        assert entry is not None
        journal = get_journal()
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
                    phase_label=f"Envoi du contexte à {entry.provider} (≈ {_fr(total)} tokens)",
                    estimated_prompt=total,
                    chars_per_token=self.cfg.chars_per_token,
                    call_id=lambda index: self._new_call_id(step_id, index),
                    sampling_trace=self._sampling_trace(None),
                )
        except ProviderError as error:
            effect_fr = (
                "La délégation échoue ; le tour principal continue."
                if in_sub
                else "Le tour est terminé ; WaveStack reste utilisable."
            )
            journal.emit("harness_error", error.payload(effect_fr))
            return _ModelOutput("error", message_fr=error.message_fr)
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
            out.calls, out.ids, out.arguments = [], [], []
            out.malformed = Malformed(
                out.raw,
                f"la sortie a été coupée à {_fr(reserve)} tokens au milieu de l'appel",
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
            return llm_lab.load_lab_content(), None
        except Exception as exc:  # noqa: BLE001 - AD-16: an invalid file never breaks the page
            error_fr = (
                "Textes de l'écran « LLM nu » illisibles (content/llm_lab.yaml) : corrigez le "
                "fichier puis rechargez la page."
            )
            cause = f"{type(exc).__name__}: {exc}"
            if self._lab_error_traced != cause:
                self._lab_error_traced = cause
                with scoped(**self._lab_scope("llm")):
                    self._error(error_fr, cause, "La page « LLM nu » reste servie sans ses textes.")
            llm_lab.load_lab_content.cache_clear()  # corrected, the file is read again
            detail = (str(exc).splitlines() or [type(exc).__name__])[0][:200]
            return None, f"{error_fr} Détail : {detail}"

    def _tokenizer_state(self) -> dict[str, Any]:
        """Whether the active model's tokenizer cuts exactly here, and why in French."""
        with self._lock:
            engine, cloud, active = self._engine, self._cloud, self._active
        if engine is None:
            return {"exact": False, "reason_fr": "Aucun modèle actif : aucun tokenizer à montrer."}
        if cloud is not None:
            return {
                "exact": False,
                "reason_fr": (
                    f"Le tokenizer de {cloud.model} est chez {cloud.provider}, pas sur ce poste : "
                    "WaveStack ne peut pas découper le texte comme lui. Il estime le nombre de "
                    "tokens à partir des caractères, sans aucune puce."
                ),
            }
        if active is not None and active.kind == "server":
            how = (
                "le tokenizer de llama-server (/tokenize)"
                if active.provider == "llama-server"
                else "le tokenizer du fichier GGUF qu'Ollama sert, ouvert par WaveStack"
            )
            return {"exact": True, "reason_fr": f"Découpage exact, par {how}."}
        return {"exact": True, "reason_fr": "Découpage exact, par le tokenizer du modèle chargé."}

    def lab_state(self) -> dict[str, Any]:
        """`GET /api/llm_lab` (story 29, AD-1): what the page needs before the stream, from
        `seq` on: its texts (or why not), the active model, the session's state and the
        tokenizer's exactness."""
        tip = get_journal().last_seq()
        content, error_fr = self._lab_content()
        with self._lock:
            state, reason_fr = self.state, self.reason_fr
        return {
            "content": content.model_dump() if content is not None else None,
            "content_error_fr": error_fr,
            "active_model": self.active_model(),
            "session_state": {"state": state, "reason_fr": reason_fr},
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
            if self.state != "idle" or self._engine is None or self.reason_fr:
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
                payload = LlmTokenizedPayload.model_validate(self._lab_tokenized(request_id, text))
                get_journal().emit("llm_tokenized", payload.model_dump(mode="json"))
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(
                    exc.message_fr
                    if isinstance(exc, ServerError)
                    else "Le découpage en tokens a échoué.",
                    exc,
                    "Rien n'a changé ; l'atelier et l'écran « LLM nu » restent utilisables.",
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
            "tokenizer_fr": self._tokenizer_state()["reason_fr"],
            "figures_fr": {"char_count": llm_lab.fr_int(len(text))},
        }
        if engine is None:
            raise RuntimeError("aucun modèle actif")
        if cloud is not None:
            estimate = config.estimate_tokens(text, self.cfg.chars_per_token)
            ratio = f"{self.cfg.chars_per_token:g}".replace(".", ",")
            return base | {
                "exact": False,
                "tokens": [],
                "token_count": None,
                "estimate": estimate,
                "chars_per_token": self.cfg.chars_per_token,
                "figures_fr": base["figures_fr"]
                | {"estimate": llm_lab.fr_int(estimate), "chars_per_token": ratio},
                "unavailable_fr": base["tokenizer_fr"],
                "dimensions": None,
                "dimensions_fr": (
                    f"Dimensions inconnues : le modèle tourne chez {cloud.provider}, qui ne les "
                    "publie pas dans son API."
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
            "figures_fr": base["figures_fr"]
            | {"token_count": llm_lab.fr_int(len(ids)), "more": llm_lab.fr_int(more)},
            "dimensions": dimensions,
            "dimensions_fr": llm_lab.dimensions_fr(dimensions),
        }

    def _lab_dimensions(self, engine: Any) -> dict[str, Any]:
        """The model's sizes (story 29): the engine's own answer when it has `dimensions`,
        else the GGUF header of the file loaded; tolerated absent or failing (AD-16)."""
        source_fr = "Ce moteur ne dit pas les dimensions du modèle."
        dims: dict[str, Any] | None = None
        read = getattr(engine, "dimensions", None)
        if read is not None:
            try:
                dims = read()
            except Exception:  # noqa: BLE001 - unknown sizes, never a failure
                dims = None
        if dims:
            source_fr = str(dims.get("source_fr") or source_fr)
        else:
            with self._lock:
                active = self._active
            if active is not None and active.kind == "file":
                header = gguf_meta.try_read_metadata(active.ref)
                if header:
                    dims = gguf_meta.dimensions_from_header(header)
                    source_fr = "Lues dans l'en-tête GGUF du fichier du modèle."
        return llm_lab.dimensions_payload(dims, source_fr)

    # ---------- story 29, increment 2: sampling, prompt reading, token by token ----------

    _SAMPLING_NAMES_FR = {
        "temperature": "température",
        "top_k": "top-k",
        "top_p": "top-p",
        "min_p": "min-p",
    }

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
                "note_fr": None,
            }
        sent = list(cloud.sampling) if sampling is not None else []
        values = {
            name: (getattr(sampling, name) if name in sent else None)
            for name in self._SAMPLING_NAMES_FR
        }
        if not sent:
            return values | {
                "source": "provider",
                "note_fr": (
                    f"Réglé par {cloud.provider} : WaveStack n'envoie aucun réglage "
                    "d'échantillonnage."
                ),
            }
        missing = [self._SAMPLING_NAMES_FR[n] for n in self._SAMPLING_NAMES_FR if n not in sent]
        return values | {
            "source": "screen",
            "note_fr": f"{_join_fr(missing).capitalize()} non réglables chez {cloud.provider}.",
        }

    @staticmethod
    def _sampling_fr(sampling: Sampling) -> str:
        """« T 0,7 · top-k 20 · top-p 0,8 · min-p 0 »."""

        def num(value: float) -> str:
            return f"{value:g}".replace(".", ",")

        return (
            f"T {num(sampling.temperature)} · top-k {sampling.top_k} · "
            f"top-p {num(sampling.top_p)} · min-p {num(sampling.min_p)}"
        )

    def _lab_sampling(self) -> dict[str, Any]:
        """`lab_state().sampling`: the harness's values, the bounds, and, for each setting,
        why it cannot be set (`None`: it can)."""
        with self._lock:
            cloud = self._cloud
        supported: dict[str, str | None] = dict.fromkeys(self._SAMPLING_NAMES_FR)
        if cloud is None:
            source_fr = (
                "Envoyés au moteur à chaque génération de l'écran ; l'atelier garde les valeurs "
                "du harnais."
            )
        else:
            for name in supported:
                if name in cloud.sampling:
                    continue
                label = self._SAMPLING_NAMES_FR[name].capitalize()
                supported[name] = (
                    f"{label} non réglable chez {cloud.provider} : l'API compatible OpenAI ne "
                    "le prévoit pas."
                    if name in ("top_k", "min_p")
                    else f"{label} non réglable chez {cloud.provider} : le modèle ne le déclare "
                    "pas (sampling) dans la configuration ; le fournisseur garde sa valeur."
                )
            source_fr = (
                f"Seuls les réglages que {cloud.model} déclare partent chez {cloud.provider} ; "
                "les tours de l'atelier n'en envoient aucun."
            )
        return {
            "defaults": asdict(DEFAULT_SAMPLING),
            "defaults_fr": f"Valeurs du harnais : {self._sampling_fr(DEFAULT_SAMPLING)}",
            "bounds": {name: list(b) for name, b in SAMPLING_BOUNDS.items()},
            "supported": supported,
            "source_fr": source_fr,
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
        mode, reason_fr = reasoning_mode(caps, window if caps is not None else None)
        local = cloud is None and caps is not None and caps.reasoning_tags is not None
        return {
            "mode": mode,
            "reason_fr": reason_fr,
            "budget": self.cfg.reasoning_budget_tokens if local else None,
            "budget_fr": self._reasoning_budget_fr(),
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
            if self.state != "idle" or self._engine is None or self.reason_fr:
                raise SendRefused(self._refusal_reason())
            # Checked under the lock: no model switch can come in between.
            lab = self._reasoning_info(self._caps, self._cloud, self._window)
            if reasoning and lab["mode"] in ("never", "unknown"):
                raise SendRefused(
                    "Raisonnement indisponible : "
                    + (lab["reason_fr"] or "le modèle actif ne sait pas raisonner.")
                )
            offer = self._candidates_info(self._active, self._cloud, self._engine)
            if candidates and not offer["available"]:
                raise SendRefused(offer["reason_fr"])
            self._labs += 1
            request_id = f"llm{self._labs}"
            cancel = self._cancel = CancelToken()
            self.state, self.reason_fr = "llm_lab", _LAB_FR
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
            reason = "Aucun modèle actif."
        elif cloud is not None:
            reason = (
                f"Probabilités indisponibles : le modèle tourne chez {cloud.provider}, qui ne "
                "les envoie pas à WaveStack sous une forme qu'il sait vérifier."
            )
        elif active.kind == "server":
            reason = (
                f"Probabilités indisponibles avec {active.provider} : WaveStack ne les lit que "
                "dans le moteur qui tourne dans son propre processus (un fichier GGUF chargé par "
                "WaveStack)."
            )
        return {"available": reason is None, "reason_fr": reason, "n": CANDIDATES}

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
        journal = get_journal()
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
                    )
                    text, tokens, exact = rendered.prompt, len(rendered.ids), True
                    phase = f"Lecture du prompt ({_fr(tokens)} tokens)"
                    with self._lock:
                        served = self._active is not None and self._active.kind == "server"
                    unit = "fragment" if served else "token"
                else:
                    content = self._cloud_content or load_cloud_content()
                    rendered = render_chat_body(
                        message,
                        None,
                        call_id=request_id,
                        fields=chat_fields(cloud, reserve, reasons, sampling),
                        markers=self.cfg.cloud_markers,
                        estimate=lambda t: config.estimate_tokens(t, self.cfg.chars_per_token),
                        provider_label_fr=content.provider_segment_fr,
                    )
                    text, tokens, exact = rendered.body, rendered.raw_total, False
                    unit = "fragment"
                    phase = f"Envoi du prompt à {cloud.provider} (≈ {_fr(tokens)} tokens)"
                usable = window - reserve
                figures = {"prompt_tokens": ("" if exact else "≈ ") + _fr(tokens)}
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
                    figures_fr=figures | {"reserve": _fr(reserve), "usable": _fr(usable)},
                )
                journal.emit("llm_generation_started", started_payload.model_dump(mode="json"))
                if tokens > usable:
                    ended["message_fr"] = (
                        f"Prompt trop long : {figures['prompt_tokens']} tokens pour "
                        f"{_fr(usable)} utilisables (fenêtre de {_fr(window)} moins "
                        f"{_fr(reserve)} réservés à la réponse). Raccourcissez-le : l'appel "
                        "n'est pas envoyé."
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
                ended["message_fr"] = (
                    exc.message_fr
                    if isinstance(exc, ServerError)
                    else "La génération de l'écran « LLM nu » s'est interrompue sur une erreur."
                )
                self._error(
                    ended["message_fr"],
                    exc,
                    "L'écran « LLM nu » et l'atelier restent utilisables.",
                )
            finally:
                try:
                    if touched:
                        self._lab_restore(saved)
                    ended["reasoning_tokens"] = counts["reasoning"]
                    ended["answer_tokens"] = counts["text"] + counts.get("tool_call", 0)
                    ended["duration_ms"] = _ms(time.monotonic() - started)
                    approx = "≈ " if cloud_used else ""
                    ended["figures_fr"] = {
                        "reasoning_tokens": approx + _fr(ended["reasoning_tokens"]),
                        "answer_tokens": approx + _fr(ended["answer_tokens"]),
                    } | (
                        {"read_tps": f"{ended['read_tps']:g}".replace(".", ",")}
                        if ended.get("read_tps")
                        else {}
                    )
                    payload = LlmGenerationEndedPayload.model_validate(ended)
                    journal.emit("llm_generation_ended", payload.model_dump(mode="json"))
                except Exception as exc:  # noqa: BLE001 - AD-16: the state still comes back
                    self._error(
                        "La fin de la génération de l'écran « LLM nu » n'a pas pu être tracée.",
                        exc,
                        "La session revient en attente ; l'atelier reste utilisable.",
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
                phase_label=f"Envoi du prompt à {cloud.provider} (≈ {_fr(tokens)} tokens)",
                estimated_prompt=tokens,
                chars_per_token=self.cfg.chars_per_token,
                call_id=lambda index: f"{request_id}.{index}",
                sampling_trace=trace,
            )
        except ProviderError as error:
            get_journal().emit(
                "harness_error",
                error.payload("La génération de l'écran s'arrête ; WaveStack reste utilisable."),
            )
            ended["message_fr"] = error.message_fr
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
            return rag_lab.load_lab_content(), None
        except Exception as exc:  # noqa: BLE001 - AD-16: an invalid file never breaks the page
            error_fr = (
                "Textes de l'atelier RAG illisibles (content/rag_lab.yaml) : corrigez le fichier "
                "puis rechargez la page."
            )
            cause = f"{type(exc).__name__}: {exc}"
            if self._rag_lab_error_traced != cause:
                self._rag_lab_error_traced = cause
                with scoped(**self._rag_lab_scope("rag_lab", None, brick=None)):
                    self._error(error_fr, cause, "La page « Atelier RAG » reste servie sans eux.")
            rag_lab.load_lab_content.cache_clear()  # corrected, the file is read again
            detail = (str(exc).splitlines() or [type(exc).__name__])[0][:200]
            return None, f"{error_fr} Détail : {detail}"

    def _rag_lab_catalog(self, texts: rag_lab.RagLabContent) -> rag_lab.Catalog:
        """The options the workshop offers, named after the brick's models, with what a run
        would meet now: the embedding model's files, the brick's index, the reranker's files
        (the reasons of `_rag_unavailable` and `_rerank_availability`, read afresh)."""
        model, content = self._rag_model, self._rag_content
        options: dict[tuple[str, str], rag_lab.OptionState] = {}
        for kind, names in rag_lab.OPTIONS.items():
            for name in names:
                options[(kind, name)] = rag_lab.OptionState(texts.options[kind][name].label_fr)
        embedding = options[("embedding", "declared")]
        store = options[("vector_store", "sqlite_vec")]
        if model is None or content is None:
            embedding.note_fr = self._content_errors.get("rag") or "Brique RAG non configurée."
        else:
            embedding.label_fr = model.label_fr
            _, index_error, _, _, _, missing_fr = self._rag_index_state(model, content)
            embedding.note_fr = missing_fr
            store.note_fr = index_error
        rerank = options[("rerank", "declared")]
        if self._rerank_model is not None:
            rerank.label_fr = self._rerank_model.label_fr
        rerank.note_fr = self._rerank_static_reason()
        return rag_lab.Catalog(texts, rag_lab.default_pipeline(self.cfg), options)

    def rag_lab_state(self) -> dict[str, Any]:
        """`GET /api/rag_lab` (story 30, AD-1): what the page needs before the stream, from
        `seq` on: the catalog and the shipped chain, its texts (or why not), the last run
        read in the journal and the session's state."""
        journal = get_journal()
        tip = journal.last_seq()
        texts, error_fr = self._rag_lab_content()
        catalog = self._rag_lab_catalog(texts) if texts is not None else None
        with self._lock:
            state, reason_fr = self.state, self.reason_fr
        events = [e for e in journal.all_events() if e.seq <= tip]
        return {
            "catalog": catalog.payload() if catalog is not None else None,
            "default_pipeline": rag_lab.default_pipeline(self.cfg).model_dump(),
            "content": texts.model_dump() if texts is not None else None,
            "content_error_fr": error_fr,
            "unavailable_fr": self._rag_lab_unavailable(),
            "last_run": rag_lab.last_run(events),
            "session_state": {"state": state, "reason_fr": reason_fr},
            "seq": tip,
        }

    def _rag_lab_unavailable(self) -> str | None:
        """Why no chain can run at all: the RAG brick's corpus and texts are unreadable."""
        if self._rag_content is None:
            return self._content_errors.get("rag") or (
                "Le corpus de la brique RAG (content/rag.yaml) est illisible : l'atelier RAG ne "
                "peut rien découper."
            )
        return None

    def run_rag_lab(self, question: str, pipelines: list[rag_lab.Pipeline] | None = None) -> str:
        """Intention `rag_lab_run` (story 30, class b): accepted in `idle` only (a reason
        there, such as no model loaded, does not matter: nothing is generated), switched to
        `rag_lab` under the lock in this call, then run on the worker; « Arrêter » (class c)
        stops it between two stages, passages or candidates. A chain the workshop refuses:
        `SendRefused` with the reason, nothing emitted. Returns the run's id, `lab{n}`."""
        texts, error_fr = self._rag_lab_content()
        if texts is None:
            raise SendRefused(error_fr or "Textes de l'atelier RAG illisibles.")
        unavailable = self._rag_lab_unavailable()
        if unavailable is not None:
            raise SendRefused(unavailable)
        catalog = self._rag_lab_catalog(texts)
        chains = list(pipelines) if pipelines else [catalog.default]
        for chain in chains:
            reason = rag_lab.validate_pipeline(chain, catalog)
            if reason is not None:
                raise SendRefused(reason)
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            previous = self.reason_fr
            self._rag_labs += 1
            run_id = f"lab{self._rag_labs}"
            cancel = self._cancel = CancelToken()
            self.state, self.reason_fr = "rag_lab", _RAG_LAB_FR
        self._emit_state()
        self._executor.submit(
            self._run_rag_lab, run_id, question, chains, texts, catalog, cancel, previous
        )
        return run_id

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
                brick_index=self.cfg.rag_index_path(),
                brick_index_error=index_error,
                embedder=lambda option: self._rag_lab_embedder(option, loans),
                reranker=lambda option: self._rag_lab_reranker(option, loans),
                cancelled=lambda: cancel.cancelled,
                emit=self._rag_lab_emit,
                rss=self._rss_now,
            )
            rag_lab.LabRun(run_id, question, chains, deps).run()
        except Exception as exc:  # noqa: BLE001 - AD-16: the state still comes back
            with scoped(**self._rag_lab_scope(run_id, "rag_lab", brick=None)):
                self._error(
                    "L'atelier RAG s'est interrompu sur une erreur.",
                    exc,
                    "La session revient en attente ; l'atelier reste utilisable.",
                )
        finally:
            errors = loans.close()
            if errors:
                with scoped(**self._rag_lab_scope(run_id, "rag_lab", brick=None)):
                    self._error(
                        "Un modèle chargé par l'atelier RAG n'a pas pu être fermé.",
                        " ; ".join(errors),
                        "Il est oublié ; son créneau mémoire est libéré.",
                    )
            with self._lock:
                self._cancel = None
            self._set_state("idle", previous)

    def _rag_lab_emit(
        self, kind: str, payload: dict[str, Any], step_id: str, component: str
    ) -> None:
        model = PAYLOAD_MODELS[kind]
        with scoped(**self._rag_lab_scope(step_id, component)):
            get_journal().emit(kind, model.model_validate(payload).model_dump(mode="json"))

    def _rag_lab_embedder(self, option: str, loans: rag_lab.Loans) -> rag_lab.Lent:
        """The brick's embedding model, borrowed when it holds it, else loaded as
        `_load_embedder` loads it (budget, declared sha256, factory) and closed at the run's
        end; its errors are said in the stage, never as `harness_error`."""
        model = self._rag_model
        if option != "declared" or model is None:
            raise rag_lab.StageFailed(
                self._content_errors.get("rag") or "Aucun modèle d'embedding n'est déclaré."
            )
        with self._lock:
            borrowed = self._embedder
        missing = download_module.missing_files(model.files, config.models_dir())
        unavailable = None
        if missing:
            names = ", ".join(PurePosixPath(f.path).name for f in missing)
            unavailable = (
                f"Modèle d'embedding absent ({names} dans {config.models_dir()}). Téléchargez-le "
                "depuis la carte RAG de l'atelier."
            )

        def open_model() -> Embedder:
            path = embedding_module.model_path(model)
            declared = model.load_file.sha256
            if declared and rag_index.file_sha256(path) != declared.lower():
                raise ValueError(
                    f"le fichier {path} n'est pas le modèle déclaré (sha256 différent de "
                    "celui de [rag.embedding])"
                )
            return self._embedder_factory(model)

        return loans.lend(
            borrowed=borrowed,
            label_fr=model.label_fr,
            noun_fr="modèle d'embedding",
            unavailable_fr=unavailable,
            cost=self._load_registry.component_cost(
                model.measured_rss_mb, [f.size for f in model.files]
            ),
            slot=EMBEDDING,
            open_model=open_model,
        )

    def _rag_lab_reranker(self, option: str, loans: rag_lab.Loans) -> rag_lab.Lent:
        """The brick's reranker, borrowed or loaded as `_load_reranker` loads it; without its
        declaration or its file, the stage is skipped and the chain goes on."""
        model = self._rerank_model
        if option != "declared" or model is None:
            raise rag_lab.StageSkipped(
                self._rerank_config_error or "Aucun modèle de reranking n'est déclaré."
            )
        with self._lock:
            borrowed = self._reranker
        missing = download_module.missing_files(model.files, config.models_dir())
        unavailable = None
        if missing:
            names = ", ".join(PurePosixPath(f.path).name for f in missing)
            unavailable = (
                f"Modèle de reranking absent ({names} dans {config.models_dir()}) : "
                "téléchargez-le depuis la carte RAG de l'atelier "
                "(sous-option « Reranking »). La construction du contexte garde l'ordre de la "
                "recherche."
            )

        def open_model() -> Reranker:
            path = reranker_module.model_path(model)
            declared = model.load_file.sha256
            if declared and rag_index.file_sha256(path) != declared.lower():
                raise ValueError(
                    f"le fichier {path} n'est pas le modèle déclaré (sha256 différent de "
                    "celui de [rag.reranker])"
                )
            return self._reranker_factory(model)

        return loans.lend(
            borrowed=borrowed,
            label_fr=model.label_fr,
            noun_fr="modèle de reranking",
            unavailable_fr=unavailable,
            cost=self._load_registry.component_cost(
                model.measured_rss_mb, [f.size for f in model.files]
            ),
            slot=RERANKER,
            open_model=open_model,
            soft=True,
        )
