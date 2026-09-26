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
import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
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
from wavestack.bricks.registry import BRICKS, check_unique_ids
from wavestack.cloud import active_model, chat_fields, load_cloud_content
from wavestack.config import MAX_RESERVE, CloudModel, output_reserve
from wavestack.context.render import (
    RenderedChat,
    RenderedContext,
    render_chat_body,
    render_context,
    with_total,
)
from wavestack.context.segments import Joined, Part, SegmentKind, SegmentLabels, load_labels
from wavestack.context.window import effective_window, gauge
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
from wavestack.models import probe as probe_module
from wavestack.models.capabilities import (
    TOOL_CALL_TAGS,
    Capabilities,
    ChannelSplitter,
    capabilities_for,
)
from wavestack.models.engine import CancelToken, Engine, LlamaCppEngine
from wavestack.models.load_registry import LoadRegistry, ModelChoice, process_rss
from wavestack.models.openai_chat import (
    ChatBody,
    OpenAIChatEngine,
    ProviderError,
    output_tps,
    run_call,
)
from wavestack.scenarios import EMPTY_PROGRAM, ScenariosContent, load_scenarios
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
    ToolError,
    ToolRegistry,
    ToolsContent,
    ToolSpec,
    load_tools_content,
)
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import current, scoped

DELTA_INTERVAL_S = 0.05  # AD-2: model_delta grouped every 50 ms at most
LOAD_TOOL_DOC = "load_tool_doc"  # the harness meta-tool of the lazy loading mode (AD-25)
DOC_LINE_MAX = 120  # characters of a tool's first description line in `load_tool_doc`
LOAD_SKILL = "load_skill"  # the harness meta-tool of the skills brick (AD-25)
REMEMBER = "remember"  # the harness meta-tool of the global memory brick (AD-25)
MEMORY = "file.memory"  # the schema node of `memory.json` (AD-12, AD-23)

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
_AWAITING_FR = "En attente de votre validation : autorisez ou refusez l'appel réseau."
_SERVER_ONLY_FR = (
    "Envoi indisponible : seul un serveur local (Ollama ou llama-server) a été trouvé, et son "
    "adaptateur arrive au palier 2. Indiquez le chemin d'un fichier GGUF sur la page de "
    "diagnostic."
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
# The heaviest harness-controlled segment names the cause (message first on ties).
_OVERFLOW_CAUSES_FR = {
    SegmentKind.USER_MESSAGE: (
        "Cause : le message à lui seul est trop long. "
        "Pour continuer la démo : raccourcissez le message et renvoyez-le."
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
}
_TOOL_CATALOG_FULL_FR = (
    "Cause : les descriptions d'outils occupent la plus grande part du contexte, chaque outil "
    "y entrant avec sa documentation complète. Pour continuer la démo : passez la carte MCP en "
    "lazy loading, ou désactivez un serveur MCP (ou des outils) dans le panneau des briques."
)
# AD-6: the French name of a model capability a brick requires.
_CAPABILITIES_FR = {
    "tool_call_parser": (
        "l'appel d'outils (aucun format d'appel connu pour cette famille de modèle)"
    ),
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
}
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


@dataclass(frozen=True)
class ArmedAction:
    """An action the user armed for the next turn (AD-3, AD-25): the session alone holds
    them. `kind`: a native tool call with its `args`, a skill, an MCP documentation, or a
    memory write with its `text` (story 14)."""

    armed_id: str
    kind: str  # tool | skill | tool_doc | memory
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


class _LoadFailed(Exception):
    """A load refused for a known reason (probe, incompatible template): `message_fr` for
    `harness_error`, `reason_fr` its cause, `idle_fr` the reason left in `idle` when no
    model is active afterwards."""

    def __init__(self, message_fr: str, reason_fr: str, idle_fr: str | None = None) -> None:
        super().__init__(reason_fr)
        self.message_fr, self.reason_fr, self.idle_fr = message_fr, reason_fr, idle_fr


def _fr(n: int) -> str:
    return f"{n:,}".replace(",", "\u202f")  # narrow no-break space, French style


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
    ) -> None:
        self.cfg = cfg or config.load_config()
        self._engine_factory = engine_factory
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
            self.cfg.memory_budget_bytes, self.cfg.load_margin_bytes, rss_fn or process_rss
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
        self._window = self.cfg.context_window
        self._labels: SegmentLabels | None = None
        self._turns = 0
        self._cancel: CancelToken | None = None
        # Bricks: in memory only, every launch starts as the bare LLM (no persistence).
        self._bricks = check_unique_ids(BRICKS if bricks is None else bricks)
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
        self._hook_steps = 0  # hook steps of the running turn, for their step ids
        self._turn_seq = 0  # seq of the running turn's `turn_started`: its events follow it
        self._load_content()
        self._registry = ToolRegistry(
            NATIVE_TOOLS + network_tools(self.cfg) + self._harness_tools(), self._tools_content
        )
        self._tool_executor = ToolExecutor(self._registry)
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
        self._last: tuple[str, str, tuple[Exchange, ...], frozenset[str], frozenset[str]] | None = (
            None
        )
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
        node.update(
            kind="mcp_server",
            label_fr=self._mcp_label(server_id),
            contact=contact,
            tools=self._mcp_tools(server_id) if contact == "available" else [],
        )
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
        if self._cloud is not None:  # AD-12: drawn in the network zone, with its provider
            model |= {"hosting": "network", "provider": self._cloud.provider}
            edges.append({"from": "core.harness", "to": "core.model", "crosses_boundary": True})
        nodes: list[dict[str, Any]] = [_CORE_HARNESS, model]
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
        }
        for file_id, (brick_id, label, detail_fr) in files.items():
            if file_id not in targets:
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
                    "category_fr": content.category_fr if content else brick.category,
                    "hosting_fr": content.hosting_fr if content else "",
                    "explanation_fr": content.explanation_fr if content else [],
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
                }
            )
            if brick.id == "reasoning":
                bricks[-1]["always_fr"] = self._always_fr()
            if brick.id == "global_memory":
                bricks[-1] |= self._memory_card()
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
        model `id`: a round trip through another model finds it again."""
        key = self._cloud.id if self._cloud is not None else ""
        return self._ratios.get(key, self.cfg.estimate_ratio)

    @_ratio.setter
    def _ratio(self, value: float) -> None:
        self._ratios[self._cloud.id if self._cloud is not None else ""] = value

    def _cost(self, choice: ModelChoice) -> int:
        """AD-8: a file's estimated cost at the configured window (an upper bound of the
        effective one); a cloud model costs nothing."""
        if choice.kind == "cloud":
            return 0
        return self._load_registry.file_cost(choice.ref, self.cfg.context_window)

    @staticmethod
    def _load_reason(choice: ModelChoice) -> str:
        if choice.entry is not None:
            return f"Préparation du modèle cloud {choice.entry.model} chez {choice.entry.provider}…"
        return f"Chargement du modèle {Path(choice.ref).name}…"

    @staticmethod
    def _model_payload(choice: ModelChoice) -> dict[str, Any]:
        """The `ActiveModel` of a model not loaded yet: `model_load_*`."""
        if choice.entry is not None:
            return active_model(choice.entry)
        name = Path(choice.ref).stem
        return {"id": name, "label": name, "hosting": "local", "kind": "file", "ref": choice.ref}

    def boot(self, model_path: str | None) -> Future[str]:
        """The launch's model (AD-21) on the worker thread: `model_load` → `idle`, then
        `context_preview`. `None`: a local server only, no file to load."""
        choice = ModelChoice("file", model_path) if model_path else None
        return self._executor.submit(self._boot, choice)

    def boot_cloud(self, entry: CloudModel) -> Future[str]:
        """The launch's cloud model, prepared without any request (AD-21)."""
        return self._executor.submit(self._boot, ModelChoice("cloud", entry.id, entry))

    def _boot(self, choice: ModelChoice | None) -> str:
        if choice is None:
            self._set_state("idle", _SERVER_ONLY_FR)
            self._emit_architecture()
            self._emit_bricks()
            return "error"
        with self._lock:
            previous = self._active
            self.state, self.reason_fr = "model_load", self._load_reason(choice)
        self._emit_state()
        return self._load(choice, previous, None, save=False)

    def switch_model(
        self, choice: ModelChoice, probe: Callable[[str], str | None] | None = None
    ) -> tuple[str, Future[str] | None]:
        """Intention `select_model` once past the diagnostic (class b, AD-3): accepted in
        `idle`, even with a reason; refused otherwise (`SendRefused`). The budget is checked
        before anything is released (AD-8): its refusal, in figures, leaves the active model.
        `probe(path)` probes a GGUF never probed, after the release: `None` if it loads, else
        why. Returns the French answer and the load's future (`None`: already active)."""
        cost = self._cost(choice)
        with self._lock:
            if self.state != "idle":
                raise SendRefused(self._refusal_reason())
            previous = self._active
            if choice.same_as(previous):
                return f"{choice.label} est déjà actif.", None
            refusal = self._load_registry.check(choice.label, cost)
            if refusal is None:  # switched under the lock: a second choice racing it is refused
                self.state, self.reason_fr = "model_load", self._load_reason(choice)
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
        probe: Callable[[str], str | None] | None,
        save: bool,
    ) -> str:
        """The single load path, on the worker, in `model_load` (AD-3, AD-8): release the
        active model, probe a GGUF never probed (AD-7), load; on failure, reload `previous`.
        Then `model_load_ended`, `idle`, and the bricks, schema and preview again. The choice
        is saved (`save`) after a success only. Returns `ok`, `restored` or `error`."""
        started = time.monotonic()
        model = self._model_payload(choice)
        journal = get_journal()
        off_turn = {"turn_id": None, "step_id": None, "call_id": None, "context_id": None}
        with scoped(**off_turn):
            journal.emit(
                "model_load_started", {"model": model, "phase_label": self._load_reason(choice)}
            )
        status, reason_fr, idle_fr = "error", None, _LOAD_FAILED_FR
        try:
            self._release()
            try:
                if (
                    choice.kind == "file"
                    and probe is not None
                    and probe_module.probed_entry(choice.ref) is None
                ):
                    why = probe(choice.ref)
                    if why is not None:
                        name = Path(choice.ref).name
                        raise _LoadFailed(f"Le fichier {name} est incompatible.", why)
                self._install(choice)
                status, idle_fr = "ok", None
            except Exception as exc:  # noqa: BLE001 - AD-16
                reason_fr, idle_fr, status = self._load_failed(choice, previous, exc)
            if status == "ok" and save:
                reason_fr = self._save_choice(choice)
        except Exception as exc:  # noqa: BLE001 - AD-16: e.g. the release itself failed
            self._error("Le changement de modèle s'est interrompu.", exc, _NO_TURN_FR)
            status, reason_fr, idle_fr = "error", str(exc), _LOAD_FAILED_FR
        finally:
            with scoped(**off_turn):
                journal.emit(
                    "model_load_ended",
                    {
                        "model": model,
                        "status": status,
                        "duration_ms": _ms(time.monotonic() - started),
                        "reason_fr": reason_fr,
                    },
                )
            self._set_state("idle", idle_fr)
            # AD-6, AD-9, AD-12: capabilities, window and model changed with the load.
            self._emit_architecture()
            self._emit_bricks()
            self._emit_preview()
        return status

    def _load_failed(
        self, choice: ModelChoice, previous: ModelChoice | None, exc: Exception
    ) -> tuple[str, str | None, str]:
        """AD-3: back to `previous` when there was one. Returns the `model_load_ended`
        reason, the reason left in `idle` and the status."""
        cause: BaseException | str = exc
        if isinstance(exc, _LoadFailed):
            message_fr, cause, idle_fr = exc.message_fr, exc.reason_fr, exc.idle_fr
        elif choice.entry is not None:
            message_fr = f"Le modèle cloud {choice.label} n'a pas pu être préparé."
            idle_fr = _CLOUD_FAILED_FR
        else:
            message_fr, idle_fr = "Le modèle n'a pas pu être chargé.", None
        cause_fr = cause if isinstance(cause, str) else str(cause)
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
        return (
            f"{choice.label} n'a pas pu être chargé ({cause_fr}) : {previous.label} est de "
            "nouveau actif.",
            None,
            "restored",
        )

    def _release(self) -> None:
        """AD-8: the active model is closed and leaves the registry before anything loads."""
        with self._lock:
            engine = self._engine
            self._engine, self._caps, self._cloud, self._active = None, None, None, None
            self._model_name = None
        if engine is not None:
            engine.close()
        self._load_registry.release()

    def _install(self, choice: ModelChoice) -> None:
        """Load `choice` as the active model, nothing being loaded: raises on failure."""
        if choice.entry is not None:
            self._install_cloud(choice.entry)
        else:
            engine = self._engine_factory(choice.ref, n_ctx=self.cfg.context_window)
            caps = capabilities_for(engine.metadata())
            if caps.incompatible_reason:
                engine.close()
                raise _LoadFailed(
                    "Modèle incompatible.", caps.incompatible_reason, caps.incompatible_reason
                )
            window = effective_window(self.cfg.context_window, caps.native_context)
            labels = self._load_labels()
            with self._lock:
                self._engine, self._caps, self._cloud = engine, caps, None
                self._model_name = Path(choice.ref).stem
                self._window = window
                self._window_source = (
                    "configured" if window == self.cfg.context_window else "native"
                )
                self._labels = labels
                self._active = choice
        self._load_registry.grant(choice.label, self._cost(choice))

    def _install_cloud(self, entry: CloudModel) -> None:
        key = config.cloud_key(entry)
        if key is None:
            raise ValueError("aucune clé enregistrée pour cette adresse")
        unavailable = config.cloud_unavailable_fr(entry)
        if unavailable:
            raise ValueError(unavailable)
        self._cloud_content = load_cloud_content()
        engine = self._cloud_factory(entry, key)
        # AD-6: declared capabilities; the API's structured format parses the tool calls.
        caps = Capabilities(
            family="openai_chat",
            chat_template=None,
            tool_call_parser="openai_chat" if entry.tools else None,
            stop_sequences=(),
            reasoning_variable=None,
            native_context=entry.context,
            reasoning_tags=None,
            reasoning=entry.reasoning is not None,
            reasoning_always=entry.always_reasons,
        )
        window, source = config.cloud_window(entry, self.cfg.context_window)
        labels = self._load_labels()
        with self._lock:
            self._engine, self._caps, self._cloud = engine, caps, entry
            self._model_name = entry.model
            self._window, self._window_source = window, source
            self._labels = labels
            self._active = ModelChoice("cloud", entry.id, entry)

    def _save_choice(self, choice: ModelChoice) -> str | None:
        """AD-20: `selected_model`, by the single applier (AD-23), after a success only.
        Returns the French notice when settings.json could not be written."""
        value = {"kind": choice.kind, "ref": choice.ref}
        try:
            apply_setting(SettingWrite(key="selected_model", value=value))
        except OSError as exc:
            notice = f"{choice.label} est actif ; choix non mémorisé pour les prochains lancements."
            self._error("Impossible d'écrire le fichier de réglages settings.json.", exc, notice)
            return notice
        return None

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
        missing = [c for c in brick.capabilities if not getattr(self._caps, c, None)]
        if "reasoning" in missing:
            return False, self._no_reasoning_fr()
        if brick_id == "reasoning" and self._window <= MAX_RESERVE:  # as the cloud `tpm` guard
            return False, (
                f"Indisponible : la fenêtre de contexte ({_fr(self._window)} tokens) ne laisse "
                f"aucune place au contexte une fois réservés les {_fr(MAX_RESERVE)} tokens de "
                "sortie du raisonnement. Agrandissez la fenêtre dans la configuration."
            )
        if missing and self._cloud is not None:  # AD-6: a capability not declared is absent
            return False, (
                f"Le modèle cloud « {self._cloud.id} » ne déclare pas l'appel d'outils (tools) : "
                "aucune action d'outil, pas même forcée. Déclarez tools = true si le modèle le "
                "gère, ou choisissez un autre modèle."
            )
        if missing:
            needs = ", ".join(_CAPABILITIES_FR.get(c, c) for c in missing)
            return False, f"Le modèle chargé n'offre pas {needs} : choisissez un autre modèle."
        if brick_id in self._content_errors:
            return False, self._content_errors[brick_id]
        if brick_id == "global_memory":
            with self._lock:
                error_fr = self._memory_error
            if error_fr is not None:
                return False, error_fr
        return True, None

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

    def _reasoning_on(self, state: TurnState) -> bool:
        """AD-6, AD-9: the model reasons in this turn: brick effective, or a cloud model
        that always reasons."""
        always = self._caps is not None and self._caps.reasoning_always
        return always or "reasoning" in state.effective

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
        if "global_memory" in effective:  # AD-4: read now, frozen for the turn's calls
            with self._lock:
                memory = tuple(e.text for e in self._memory)
            if self._caps is not None and self._caps.tool_call_parser:  # H4, AD-25
                tools.append(REMEMBER)
        hooks = [h for h in self._hook_ids() if h in hooks_enabled] if "hooks" in effective else []
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
    ) -> list[dict[str, Any]]:
        """Intermediate messages of a turn: `assistant_turn`/`tool_result` in the turn itself
        (or the step's own `kind`), `history` afterwards, where a step's `stub` replaces its
        content. Each call's name and arguments form one group (AD-4). Calls carry their
        session `id`, replies its `tool_call_id`. Chat mode (AD-4): the reasoning sent back
        only with `resend` (its `format`), an empty `content` omitted, `arguments` as the
        string emitted, a reply without `name`, and a malformed call's error sent as a `user`
        message."""
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
                content = [Part(kind, text, brick, component)]
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
                    ex.steps, history=True, group=ex.turn_id, chat=chat, resend=resend
                )
                messages.append(
                    self._assistant_message(
                        Part(SegmentKind.HISTORY, ex.text, *memory),
                        ex.reasoning,
                        chat=chat,
                        resend=resend,
                        omit_empty=False,  # a past answer keeps its `content`, even empty
                    )
                )
        user = [Part(SegmentKind.USER_MESSAGE, message)]
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

    def _render(
        self,
        state: TurnState,
        message: str,
        call_id: str | None,
        steps: list[dict[str, Any]] | None = None,
    ) -> tuple[RenderedContext | RenderedChat, dict[str, Any]]:
        assert self._engine is not None and self._caps is not None and self._labels is not None
        if self._cloud is not None:
            return self._render_chat(state, message, call_id, steps)
        meta = self._engine.metadata()
        template_vars: dict[str, Any] = {}
        if self._caps.reasoning_variable:  # AD-6: the brick sets the template's variable
            template_vars[self._caps.reasoning_variable] = self._reasoning_on(state)
        rendered = render_context(
            self._engine,
            self._caps.chat_template or "",
            self._messages(state, message, steps),
            call_id=call_id,
            special_tokens=meta.special_tokens,
            tools=self._tool_definitions(state),
            bos_token=meta.bos_token,
            eos_token=meta.eos_token,
            add_generation_prompt=True,
            **template_vars,
        )
        payload = gauge(
            rendered.segments,
            window=self._window,
            reserve=self._reserve_of(state),
            near_limit_ratio=self.cfg.near_limit_ratio,
            labels=self._labels,
            window_source=self._window_source,
        )
        return rendered, payload

    def _render_chat(
        self,
        state: TurnState,
        message: str,
        call_id: str | None,
        steps: list[dict[str, Any]] | None,
    ) -> tuple[RenderedChat, dict[str, Any]]:
        """AD-4, chat mode: `context` writes the body; before the call, the total is the
        estimates × `ratio`, and only their raw sum can block the call."""
        entry, content = self._cloud, self._cloud_content
        assert entry is not None and content is not None
        reserve = self._reserve_of(state)
        rendered = render_chat_body(
            self._messages(state, message, steps, chat=True),
            self._tool_definitions(state),
            call_id=call_id,
            fields=chat_fields(entry, reserve, reasoning=self._reasoning_on(state)),
            markers=self.cfg.cloud_markers,
            estimate=lambda text: config.estimate_tokens(text, self.cfg.chars_per_token),
            provider_label_fr=content.provider_segment_fr,
        )
        payload = self._chat_gauge(
            rendered, round(rendered.raw_total * self._ratio), "estimate", reserve
        )
        if not payload["overflow"] and payload["used"] > payload["usable"]:
            payload["uncertain_fr"] = content.uncertain_fr
        return rendered, payload

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
        )
        return payload | {"body": rendered.body, "usage_source": source}

    def _emit_preview(self) -> None:
        """AD-9: the next-turn gauge, rendered without any message. Runs on the worker."""
        if self._engine is None:
            return  # no model: nothing to preview
        state = self.build_turn_state()
        state = replace(state, injection=self._preview_injection(state))
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
                replay_of, message, history, skills, docs = self._last
                self._history[:] = history
                self._loaded_skills, self._loaded_docs = set(skills), set(docs)
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
            )
        self._emit_state()
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
        return specs

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

    def _emit_scenario(self) -> None:
        program = self._scenarios.payload() if self._scenarios else EMPTY_PROGRAM
        with self._lock:
            active = self._active_scenario
        get_journal().emit("scenario_changed", {"program": program, "active": active})

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

        self._reconfigure(scenario_id, apply)

    def reset(self) -> None:
        """Class (b): back to the launch state: bare LLM, no turn, no scenario."""
        self._reconfigure(None, lambda: None)

    def _reconfigure(self, scenario_id: str | None, apply: Callable[[], None]) -> None:
        """One `bricks_changed`, one `architecture_changed`, one preview; MCP servers
        connect or close on the difference only (AD-15)."""
        with self._memory_lock:  # no turn starts before the memory is restored
            with self._lock:
                if self.state != "idle":
                    raise SendRefused(self._refusal_reason())
                before = set(self._mcp_enabled) if "mcp" in self._wanted else set()
                self._history.clear()
                self._loaded_docs.clear()
                self._loaded_skills.clear()
                self._last = None  # nothing left to replay (story 9b)
                self._armed.clear()
                self._apply_launch_config()
                apply()
                after = set(self._mcp_enabled) if "mcp" in self._wanted else set()
                self._active_scenario = scenario_id
            journal = get_journal()
            journal.emit("conversation_cleared" if scenario_id else "harness_reset", {})
            if scenario_id is None:  # FR-39: the reset alone restores the demonstration memory
                self._restore_memory()
        self._emit_armed()
        self._emit_scenario()
        for server_id in sorted(before - after):
            self._mcp_disconnect(server_id)
        for server_id in sorted(after - before):
            self._mcp_connect(server_id)
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
        pending human validation is resolved as `cancelled`."""
        with self._lock:
            if self.state not in ("turn", "awaiting_human") or self._cancel is None:
                return False
            self._cancel.cancel()
            approval = self._approval
            if approval is None or approval.decision is not None:
                return True
            approval.decision = "cancelled"
        approval.answered.set()
        return True

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
                status, text, reasoning = self._turn(turn_id, message, cancel, state, steps)
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(
                    "Le tour s'est interrompu sur une erreur.",
                    exc,
                    "Le tour est terminé ; WaveStack reste utilisable.",
                )
            finally:
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
                self._set_state("idle")

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
        # AD-25: documentations loaded in this turn are callable at once. Locally, they enter
        # `tools` only from the next turn (the prefix stays append only); in chat mode, from
        # the next call, since a provider refuses a call to a tool its `tools` lacks.
        loaded_in_turn: list[str] = []
        # AD-3: the armed actions, after `on_user_message` and before the first call, outside
        # the call budget (AD-10).
        stopped, step = self._consume_armed(turn_id, state, cancel, steps, loaded_in_turn)
        if stopped:
            return "cancelled", "", ""
        for n in range(1, max_calls + 1):
            call_id = f"{turn_id}.main.c{n}"
            with scoped(call_id=call_id):
                decided = self._hook("before_model_call", state)
            if decided is not None and decided[1].decision == "block":
                return "blocked", "", ""
            step += 1
            with scoped(call_id=call_id, step_id=f"{turn_id}.main.s{step}", component="core.model"):
                shown = state if self._cloud is None else _with_loaded(state, loaded_in_turn)
                rendered, payload = self._render(shown, message, call_id, steps)
                journal.emit("context_rendered", payload)
                if previous is not None:  # not in chat mode, which has no ids (AD-4)
                    self._check_prefix(*previous, rendered.ids)
                if payload["overflow"]:
                    self._emit_overflow(payload, getattr(rendered, "raw_total", None))
                    return "overflow", "", ""
                out = self._call_model(
                    rendered, cancel, state.tools + tuple(loaded_in_turn), payload["reserve"]
                )
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
                (b for b in ("tools", "mcp", "skills", "global_memory") if b in state.effective),
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
                    steps.append(
                        {
                            "role": "assistant",
                            "content": out.text,
                            "tool_calls": [
                                {
                                    "id": call_ref,
                                    "name": c.name,
                                    "arguments": c.arguments,
                                    # AD-4: as emitted in chat mode, else serialized once.
                                    "arguments_json": (
                                        out.arguments[j]
                                        if out.arguments
                                        else json.dumps(c.arguments, ensure_ascii=False)
                                    ),
                                }
                                for j, (c, call_ref) in enumerate(
                                    zip(out.calls, out.ids, strict=True)
                                )
                            ],
                        }
                        | ({"reasoning": out.reasoning} if out.reasoning else {})
                    )
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
                        tool_step = {
                            "role": "tool",
                            "id": call_ref,
                            "name": call.name,
                            "content": result,
                            "component": component,
                            "brick": brick,
                        }
                        if blocker is not None:  # AD-4: the refusal is the hook's text
                            tool_step |= {"component": f"hooks.{blocker}", "brick": "hooks"}
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
        with scoped(step_id=step_id, brick=brick, component=spec.component):
            text = self._tool_executor.run(call, cancel, effects, apply=self._apply_now)
        if spec.is_mcp and text is not None:
            self._after_mcp_call(call.name, spec)
        if spec.network or spec.is_mcp:
            self._emit_architecture()  # its contact state may have changed
        if text is None:
            return None
        self._hook("after_tool", state, call=call, spec=spec, result=text)
        return text, None

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
            tool_step = {
                "role": "tool",
                "id": call_ref,
                "name": call.name,
                "content": result,
                "component": component,
                "brick": action.brick,
            }
            if blocker is not None:  # AD-4: the refusal is the hook's text
                tool_step |= {"component": f"hooks.{blocker}", "brick": "hooks"}
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
        step = f"{turn_id}.main.h{self._hook_steps}"  # the step of H5's `hook_decided`
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
            view = HookContext(point, turn_id, events=events, content=texts, **ctx)
            self._hook_steps += 1
            step_id = f"{turn_id}.main.h{self._hook_steps}"
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
        common = next(
            (i for i, (a, b) in enumerate(zip(expected, ids, strict=False)) if a != b),
            min(len(expected), len(ids)),
        )
        if common < len(expected):
            get_journal().emit(
                "prefix_not_reused",
                {
                    "common_tokens": common,
                    "message_fr": (
                        f"Cet appel ne prolonge pas exactement le précédent : seuls "
                        f"{_fr(common)} tokens sur {_fr(len(expected))} sont réutilisés, le "
                        "modèle relit le reste. Le gabarit réécrit la sortie du modèle "
                        "autrement qu'elle a été produite."
                    ),
                },
            )

    def _emit_overflow(self, payload: dict[str, Any], raw_used: int | None = None) -> None:
        """`raw_used` (chat mode): the raw sum of the estimates, which decided the block
        (AD-4), cited « ≈ »."""
        used, usable = payload["used"], payload["usable"]
        shown = f"≈ {_fr(raw_used)}" if raw_used is not None else _fr(used)
        tokens = dict.fromkeys(_OVERFLOW_CAUSES_FR, 0)
        for segment in payload["segments"]:
            if segment["kind"] in tokens:
                tokens[segment["kind"]] += segment["tokens"]
        heaviest = max(tokens, key=tokens.__getitem__)  # ties: the message
        with self._lock:
            lazy = self._sent[4]  # the mode frozen for this turn by `send`
        full = heaviest == SegmentKind.TOOL_CATALOG and not lazy
        cause = _TOOL_CATALOG_FULL_FR if full else _OVERFLOW_CAUSES_FR[heaviest]
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

    def _call_model(
        self,
        rendered: RenderedContext | RenderedChat,
        cancel: CancelToken,
        tools: tuple[str, ...],
        reserve: int,
    ) -> _ModelOutput:
        """One streamed call of at most `reserve` output tokens (AD-9); with tools on, its
        `<tool_call>` blocks are parsed, outside the reasoning (AD-6)."""
        assert self._engine is not None and self._caps is not None
        if isinstance(rendered, RenderedChat):
            return self._call_model_chat(rendered, cancel, reserve)
        step_id = current().step_id or ""
        journal = get_journal()
        started = time.monotonic()
        journal.emit(
            "model_call_started",
            {"phase_label": f"Lecture du contexte ({_fr(len(rendered.ids))} tokens)"},
        )
        tags = self._caps.reasoning_tags
        splitter = ChannelSplitter(
            tags,
            in_reasoning=bool(tags) and rendered.prompt.rstrip().endswith(tags[0]),
            tool_tags=TOOL_CALL_TAGS if tools else None,
        )
        raw: list[str] = []
        channels: dict[str, list[str]] = {"reasoning": [], "text": [], "tool_call": []}
        pending: list[tuple[str, str]] = []
        first_at: float | None = None
        last_flush = started
        output_tokens = 0
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
                },
                actor="model",
            )

        try:
            for fragment in self._engine.complete(
                rendered.ids, self._caps.stop_sequences, reserve, cancel
            ):
                output_tokens = fragment.output_tokens
                if first_at is None and output_tokens:
                    first_at = time.monotonic()
                    journal.emit("model_first_token", {}, actor="model")
                raw.append(fragment.text)
                take(splitter.feed(fragment.text))
                if fragment.stop_reason:
                    stop_reason = fragment.stop_reason
                if pending and time.monotonic() - last_flush >= DELTA_INTERVAL_S:
                    flush()
            take(splitter.flush())
            flush()
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
                    "output_tokens": output_tokens,
                    "max_tokens": reserve,
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
                    f"la sortie a été coupée à {_fr(reserve)} tokens au milieu de l'appel",
                ),
            )
        return out

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
        try:
            with scoped(origin="model"):  # AD-15: traced with the call's scope, no header
                call = run_call(
                    self._engine,
                    ChatBody(rendered.body.encode("utf-8")),
                    cancel,
                    phase_label=f"Envoi du contexte à {entry.provider} (≈ {_fr(total)} tokens)",
                    estimated_prompt=total,
                    chars_per_token=self.cfg.chars_per_token,
                    call_id=lambda index: self._new_call_id(step_id, index),
                )
        except ProviderError as error:
            journal.emit(
                "harness_error",
                error.payload("Le tour est terminé ; WaveStack reste utilisable."),
            )
            return _ModelOutput("error")
        prompt_tokens = int((call.usage or {}).get("prompt_tokens") or 0)
        if prompt_tokens:  # AD-4: `usage` is the total; the ratio learns from real calls only
            payload = self._chat_gauge(rendered, prompt_tokens, "api", reserve)
            journal.emit("context_reconciled", payload | {"call_id": scope.call_id or ""})
            if rendered.raw_total:
                self._ratio = min(1.5, max(0.8, prompt_tokens / rendered.raw_total))
        if call.stop_reason == "cancelled":
            return _ModelOutput("cancelled")
        out = _ModelOutput("completed", text=call.text, reasoning=call.reasoning)
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
            if call.channel != "tool_call":
                return _ModelOutput("limit")
            out.calls, out.ids, out.arguments = [], [], []
            out.malformed = Malformed(
                out.raw,
                f"la sortie a été coupée à {_fr(reserve)} tokens au milieu de l'appel",
            )
        return out
