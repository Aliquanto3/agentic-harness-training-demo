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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

from wavestack import config
from wavestack.bricks.contract import (
    BrickContent,
    BrickDeclaration,
    Component,
    load_brick_content,
    load_default_system_prompt,
)
from wavestack.bricks.registry import BRICKS, check_unique_ids
from wavestack.context.render import RenderedContext, render_context
from wavestack.context.segments import Joined, Part, SegmentKind, SegmentLabels, load_labels
from wavestack.context.window import OUTPUT_RESERVE, effective_window, gauge
from wavestack.mcp.connection import McpConnection, describe_error
from wavestack.mcp.servers import McpContent, load_mcp_content, mcp_servers
from wavestack.models.capabilities import (
    TOOL_CALL_TAGS,
    Capabilities,
    ChannelSplitter,
    capabilities_for,
)
from wavestack.models.engine import CancelToken, Engine, LlamaCppEngine
from wavestack.session.effects import Effect, ToolDocLoaded, ToolReply
from wavestack.tools.executor import ToolExecutor
from wavestack.tools.native import NATIVE_TOOLS
from wavestack.tools.network import network_tools
from wavestack.tools.parser import Malformed, ToolCall, parse_tool_calls
from wavestack.tools.registry import (
    ToolError,
    ToolRegistry,
    ToolsContent,
    ToolSpec,
    load_tools_content,
)
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import scoped

DELTA_INTERVAL_S = 0.05  # AD-2: model_delta grouped every 50 ms at most
LOAD_TOOL_DOC = "load_tool_doc"  # the harness meta-tool of the lazy loading mode (AD-25)
DOC_LINE_MAX = 120  # characters of a tool's first description line in `load_tool_doc`

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

_SERVER_ONLY_FR = (
    "Envoi indisponible : seul un serveur local (Ollama ou llama-server) a été trouvé, et son "
    "adaptateur arrive au palier 2. Indiquez le chemin d'un fichier GGUF sur la page de "
    "diagnostic."
)
_LOAD_FAILED_FR = (
    "Envoi indisponible : le modèle n'a pas pu être chargé. Choisissez un autre fichier GGUF "
    "sur la page de diagnostic."
)
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
    `{role: tool, name, content, component}`.
    """

    turn_id: str
    user: str
    text: str
    reasoning: str
    steps: tuple[dict[str, Any], ...] = ()


@dataclass
class _ModelOutput:
    status: str  # completed | cancelled | limit
    raw: str = ""
    text: str = ""
    reasoning: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    malformed: Malformed | None = None


@dataclass(frozen=True)
class TurnState:
    """What a turn reads for all its calls, frozen at its start (AD-17)."""

    history: tuple[Exchange, ...]
    system_prompt: str
    effective: frozenset[str]  # brick ids, `wanted` and `available`
    tools: tuple[str, ...] = ()  # enabled tools of the effective tools and mcp bricks
    # Lazy loading (AD-25): the available MCP tools whose documentation is not loaded yet.
    loadable: tuple[str, ...] = ()


class SendRefused(Exception):
    def __init__(self, reason_fr: str) -> None:
        super().__init__(reason_fr)
        self.reason_fr = reason_fr


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
    ) -> None:
        self.cfg = cfg or config.load_config()
        self._engine_factory = engine_factory
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
        self._wanted: set[str] = set()
        self._history: list[Exchange] = []
        self._custom_prompt: str | None = None  # None: the default from content/
        self._content: dict[str, BrickContent] = {}
        self._content_errors: dict[str, str] = {}
        self._default_prompt = ""
        self._tools_content: ToolsContent | None = None
        self._mcp_content: McpContent | None = None
        self._load_content()
        self._registry = ToolRegistry(
            NATIVE_TOOLS + network_tools(self.cfg) + self._harness_tools(), self._tools_content
        )
        self._tool_executor = ToolExecutor(self._registry)
        # Offline tools start enabled; network tools start disabled (story 5b). Harness tools
        # are no sub-option: the session alone decides when they are offered.
        self._tools_enabled = {
            n
            for n in self._registry.names
            if not self._registry.get(n).network and self._registry.get(n).source != "harness"
        }
        # MCP servers (story 6): the local one starts enabled, the public ones disabled. A
        # server is contacted only while enabled with the brick wanted (AD-15).
        self._loop: asyncio.AbstractEventLoop | None = None
        self._mcp_servers = mcp_servers(self.cfg)
        self._mcp_enabled = {"local"}
        self._mcp_conns: dict[str, McpConnection] = {}
        self._mcp_state: dict[str, tuple[str, str | None]] = {}  # contact, reason_fr
        # Story 6b: documentation complète by default; the documentations loaded belong to
        # the conversation (AD-17), and wait while their server is off.
        self._mcp_lazy = False
        self._loaded_docs: set[str] = set()
        # Configuration frozen by the last `send`: `pending` is measured against it.
        self._sent: tuple[frozenset[str], str, frozenset[str], frozenset[str], bool] = (
            frozenset(),
            self._default_prompt,
            frozenset(),
            frozenset(),
            False,
        )

    # ---------- state ----------

    def _set_state(self, state: str, reason_fr: str | None = None) -> None:
        with self._lock:
            self.state, self.reason_fr = state, reason_fr
        get_journal().emit("session_state", {"state": state, "reason_fr": reason_fr})

    def emit_initial(self) -> None:
        get_journal().emit("session_state", {"state": self.state, "reason_fr": self.reason_fr})
        self._emit_architecture()
        self._emit_bricks()

    def _drawn_components(self, brick: BrickDeclaration) -> list[Component]:
        """A tool or an MCP server is drawn only while its sub-option is enabled."""
        with self._lock:
            if brick.id == "tools":
                enabled = {f"tools.{name}" for name in self._tools_enabled}
            elif brick.id == "mcp":
                enabled = {f"mcp.{server}" for server in self._mcp_enabled}
            else:
                return list(brick.components)
        return [c for c in brick.components if c.id in enabled]

    def _mcp_label(self, server_id: str) -> str:
        text = self._mcp_content.servers.get(server_id) if self._mcp_content else None
        return text.label_fr if text else server_id

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
        with self._lock:
            wanted = [b for b in self._bricks.values() if b.id in self._wanted]
        nodes: list[dict[str, Any]] = [_CORE_HARNESS, {**_CORE_MODEL, "model": self._model_name}]
        edges: list[dict[str, Any]] = []
        components = {b.id: self._drawn_components(b) for b in wanted}
        # The demo files node is drawn once a drawn component points to it.
        targets = {t for cs in components.values() for c in cs for t in c.edges_to}
        if "file.demo_dir" in targets:
            label = self._tools_content.demo_dir_label_fr if self._tools_content else "demo_files"
            available, reason_fr = self._availability("tools")
            nodes.append(
                {
                    "id": "file.demo_dir",
                    "kind": "file",
                    "hosting": "local",
                    "label_fr": label,
                    "wanted": True,
                    "available": available,
                    "reason_fr": reason_fr,
                }
            )
        drawn = {n["id"] for n in nodes} | {c.id for cs in components.values() for c in cs}
        for brick in wanted:
            available, reason_fr = self._availability(brick.id)
            for component in components[brick.id]:
                hosting = "network" if component.hosting == "network_service" else "local"
                is_tool = component.kind == "tool"
                node = {
                    "id": component.id,
                    "kind": "tool" if is_tool else "brick",
                    "hosting": hosting,
                    "label_fr": (
                        self._registry.label(component.id.removeprefix("tools."))
                        if is_tool
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
            sent_wanted, sent_prompt, sent_tools, sent_mcp, sent_lazy = self._sent
            pending = set(self._wanted) ^ sent_wanted
            prompt = self._custom_prompt or self._default_prompt
            if "system_prompt" in self._wanted and prompt != sent_prompt:
                pending.add("system_prompt")
            if "tools" in self._wanted and self._tools_enabled != sent_tools:
                pending.add("tools")
            mcp_changed = mcp_tools != sent_mcp or self._mcp_lazy != sent_lazy
            if "mcp" in self._wanted and mcp_changed:
                pending.add("mcp")
        return pending

    def _mcp_options(self) -> list[dict[str, Any]]:
        with self._lock:
            enabled = set(self._mcp_enabled)
        return [
            {
                "id": server.id,
                "label_fr": self._mcp_label(server.id),
                "enabled": server.id in enabled,
                "hosting_fr": "RÉSEAU" if server.network else "Local",
                "network": server.network,
            }
            for server in self._mcp_servers.values()
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
            options.append(
                {
                    "id": name,
                    "label_fr": self._registry.label(name),
                    "enabled": name in enabled,
                    "hosting_fr": "RÉSEAU" if spec.network else "Local",
                    "network": spec.network,
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
                    "explanation_fr": content.explanation_fr if content else "",
                    "wanted": brick.id in wanted,
                    "available": available,
                    "reason_fr": reason_fr,
                    "pending": brick.id in pending,
                    "options": (
                        self._tool_options()
                        if brick.id == "tools"
                        else self._mcp_options()
                        if brick.id == "mcp"
                        else []
                    ),
                    "limits_fr": self._limits_fr() if brick.id == "tools" else None,
                }
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
        if self._engine is not None:
            self._engine.close()
            self._engine = None

    def _on_loop(self) -> bool:
        try:
            return asyncio.get_running_loop() is self._loop
        except RuntimeError:
            return False

    # ---------- model load ----------

    @property
    def model_loaded(self) -> bool:
        return self._engine is not None

    def boot(self, model_path: str | None) -> Future[None]:
        """Load `model_path` on the worker thread: `model_load` → `idle`, then `context_preview`."""
        return self._executor.submit(self._boot, model_path)

    def _boot(self, model_path: str | None) -> None:
        if model_path is None:
            self._set_state("idle", _SERVER_ONLY_FR)
            self._emit_architecture()
            self._emit_bricks()
            return
        try:
            self._model_name = None  # no engine from here until this load succeeds
            self._set_state("model_load", f"Chargement du modèle {Path(model_path).name}…")
            self._emit_architecture()
            self._emit_bricks()
            if self._engine is not None:
                self._engine.close()
                self._engine = None
            engine = self._engine_factory(model_path, n_ctx=self.cfg.context_window)
            caps = capabilities_for(engine.metadata())
            if caps.incompatible_reason:
                engine.close()
                self._error(
                    "Modèle incompatible.", caps.incompatible_reason, "Aucun tour possible."
                )
                self._set_state("idle", caps.incompatible_reason)
                return
            self._engine, self._caps = engine, caps
            self._model_name = Path(model_path).stem
            self._window = effective_window(self.cfg.context_window, caps.native_context)
            self._labels = self._load_labels()
        except Exception as exc:  # noqa: BLE001 - AD-16
            self._error("Le modèle n'a pas pu être chargé.", exc, "Aucun tour possible.")
            self._set_state("idle", _LOAD_FAILED_FR)
            return
        self._set_state("idle")
        self._emit_architecture()  # availability may depend on the loaded model's capabilities
        self._emit_bricks()
        self._emit_preview()

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
        if missing:
            needs = ", ".join(_CAPABILITIES_FR.get(c, c) for c in missing)
            return False, f"Le modèle chargé n'offre pas {needs} : choisissez un autre modèle."
        if brick_id in self._content_errors:
            return False, self._content_errors[brick_id]
        return True, None

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

    def build_turn_state(self, origin_turn: str | None = None) -> TurnState:
        """AD-17: the conversational snapshot (branch history) plus the current configuration.

        `origin_turn` (replay, story 9) keeps the branch up to, not including, that turn.
        """
        with self._lock:
            history = list(self._history)
            prompt = self._custom_prompt
        if origin_turn is not None:
            ids = [e.turn_id for e in history]
            history = history[: ids.index(origin_turn)] if origin_turn in ids else history
        effective = self._effective()
        with self._lock:
            enabled = set(self._tools_enabled)
            lazy, loaded = self._mcp_lazy, set(self._loaded_docs)
        tools = [n for n in self._registry.names if n in enabled] if "tools" in effective else []
        loadable: list[str] = []
        if "mcp" in effective:
            mcp = self._mcp_tool_names()
            if lazy:  # AD-25: loaded documentations only, the others through `load_tool_doc`
                loadable = [n for n in mcp if n not in loaded]
                tools += [n for n in mcp if n in loaded] + ([LOAD_TOOL_DOC] if loadable else [])
            else:
                tools += mcp
        return TurnState(
            history=tuple(history),
            system_prompt=prompt if prompt is not None else self._default_prompt,
            effective=effective,
            tools=tuple(tools),
            loadable=tuple(loadable),
        )

    # ---------- rendering ----------

    @staticmethod
    def _step_messages(
        steps: tuple[dict[str, Any], ...] | list[dict[str, Any]], *, history: bool, group: str
    ) -> list[dict[str, Any]]:
        """Intermediate messages of a turn: `assistant_turn`/`tool_result` in the turn itself
        (or the step's own `kind`), `history` afterwards, where a step's `stub` replaces its
        content. Each call's name and string arguments form one group (AD-4)."""
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
                messages.append({"role": "tool", "content": [Part(kind, text, brick, component)]})
                continue
            kind, brick, component = (
                memory if history else (SegmentKind.ASSISTANT_TURN, None, "core.model")
            )
            answer: dict[str, Any] = {
                "role": "assistant",
                "content": [Part(kind, step["content"], brick, component)],
            }
            if step.get("reasoning"):
                answer["reasoning_content"] = step["reasoning"]  # plain, as for the history
            if step["tool_calls"]:
                answer["tool_calls"] = []
                for j, call in enumerate(step["tool_calls"]):
                    in_call = (brick, component, f"{group}.{i}.{j}")
                    # ponytail: only string values are wrapped; a number or an object stays
                    # plain (template), since a template may `tojson` them.
                    arguments = {
                        arg: Part(kind, value, *in_call) if isinstance(value, str) else value
                        for arg, value in call["arguments"].items()
                    }
                    name = Part(kind, call["name"], *in_call)
                    answer["tool_calls"].append(
                        {"type": "function", "function": {"name": name, "arguments": arguments}}
                    )
            messages.append(answer)
        return messages

    @classmethod
    def _messages(
        cls, state: TurnState, message: str, steps: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """AD-4 slots: system message, history, the turn's user message, then the turn's steps.

        Every brick off gives the bare LLM's single user message, byte for byte.
        """
        messages: list[dict[str, Any]] = []
        if "system_prompt" in state.effective:
            part = Part(
                SegmentKind.SYSTEM_PROMPT,
                state.system_prompt,
                "system_prompt",
                "system_prompt.prompt",
            )
            messages.append({"role": "system", "content": [part]})
        if "short_memory" in state.effective:
            for ex in state.history:
                memory = ("short_memory", "short_memory.history")
                messages.append(
                    {"role": "user", "content": [Part(SegmentKind.HISTORY, ex.user, *memory)]}
                )
                messages += cls._step_messages(ex.steps, history=True, group=ex.turn_id)
                answer: dict[str, Any] = {
                    "role": "assistant",
                    "content": [Part(SegmentKind.HISTORY, ex.text, *memory)],
                }
                if ex.reasoning:
                    # ponytail: passed as a plain template variable, so a template that keeps
                    # past reasoning counts it as `template`; attribute it once one does.
                    answer["reasoning_content"] = ex.reasoning
                messages.append(answer)
        messages.append({"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, message)]})
        messages += cls._step_messages(steps or [], history=False, group="turn")
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
    ) -> tuple[RenderedContext, dict[str, Any]]:
        assert self._engine is not None and self._caps is not None and self._labels is not None
        meta = self._engine.metadata()
        template_vars: dict[str, Any] = {}
        if self._caps.reasoning_variable:
            template_vars[self._caps.reasoning_variable] = False  # no reasoning brick yet
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
            reserve=OUTPUT_RESERVE,
            near_limit_ratio=self.cfg.near_limit_ratio,
            labels=self._labels,
        )
        return rendered, payload

    def _emit_preview(self) -> None:
        """AD-9: the next-turn gauge, rendered without any message. Runs on the worker."""
        if self._engine is None:
            return  # no model: nothing to preview
        try:
            _, payload = self._render(self.build_turn_state(), "", None)
        except Exception as exc:  # noqa: BLE001 - AD-16
            self._error(
                "L'aperçu du contexte n'a pas pu être calculé.",
                exc,
                "La jauge reste vide jusqu'au premier tour.",
            )
            return
        get_journal().emit("context_preview", payload)

    # ---------- intentions ----------

    def send(self, message: str) -> str:
        """Intention class (b): refused outside `idle`, with the reason."""
        with self._lock:
            if self.state != "idle" or self._engine is None or self.reason_fr:
                raise SendRefused(self._refusal_reason())
            self._turns += 1
            turn_id = f"t{self._turns}"
            cancel = self._cancel = CancelToken()
            # Switched under the lock, so a second `send` racing this one is refused.
            self.state, self.reason_fr = (
                "turn",
                "Un tour est en cours : attendez sa fin ou arrêtez-le.",
            )
        get_journal().emit("session_state", {"state": self.state, "reason_fr": self.reason_fr})
        state = self.build_turn_state()  # frozen now: a later toggle waits for the next turn
        had_pending = bool(self._pending_ids())
        mcp_tools = frozenset(self._mcp_tool_names())
        with self._lock:
            self._sent = (
                frozenset(self._wanted),
                self._custom_prompt or self._default_prompt,
                frozenset(self._tools_enabled),
                mcp_tools,
                self._mcp_lazy,
            )
        if had_pending:  # « Prend effet au prochain tour » is over for what this turn reads
            self._emit_bricks()
        self._executor.submit(self._run_turn, turn_id, message, cancel, state)
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
        """`load_tool_doc`, registered once; the turn state decides when it is offered."""
        if self._mcp_content is None:
            return []  # invalid content: the mcp brick is unavailable anyway
        text = self._mcp_content.load_tool_doc
        return [
            ToolSpec(
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
        ]

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
        return ToolSpec(
            name=name,
            run=lambda **arguments: conn.call(name, arguments),
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
        get_journal().emit("conversation_cleared", {})
        self._executor.submit(self._emit_preview)

    def _refusal_reason(self) -> str:
        if self.state == "turn":
            return "Un tour est déjà en cours : attendez sa fin ou cliquez sur « Arrêter »."
        if self.reason_fr:
            return self.reason_fr
        return "Aucun modèle n'est chargé : terminez le diagnostic de démarrage."

    def stop(self) -> bool:
        """Intention class (c): arms the turn's `CancelToken`; no effect outside a turn."""
        with self._lock:
            if self.state != "turn" or self._cancel is None:
                return False
            self._cancel.cancel()
            return True

    # ---------- turn ----------

    def _run_turn(self, turn_id: str, message: str, cancel: CancelToken, state: TurnState) -> None:
        started = time.monotonic()
        status = "error"
        journal = get_journal()
        with scoped(turn_id=turn_id, context_id="main", trigger="user"):
            try:
                journal.emit("turn_started", {"replay_of": None, "message": message}, actor="user")
                steps: list[dict[str, Any]] = []
                status, text, reasoning = self._turn(turn_id, message, cancel, state, steps)
                if status == "completed":  # AD-17: recorded even with short memory off
                    exchange = Exchange(turn_id, message, text, reasoning, tuple(steps))
                    with self._lock:
                        self._history.append(exchange)
            except Exception as exc:  # noqa: BLE001 - AD-16
                self._error(
                    "Le tour s'est interrompu sur une erreur.",
                    exc,
                    "Le tour est terminé ; WaveStack reste utilisable.",
                )
            finally:
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
        retries = step = 0
        previous: tuple[list[int], str] | None = None  # last call's ids and raw output
        # AD-25: documentations loaded in this turn are callable at once, but enter `tools`
        # only from the next turn (the prefix stays append only).
        loaded_in_turn: list[str] = []
        for n in range(1, max_calls + 1):
            call_id = f"{turn_id}.main.c{n}"
            step += 1
            with scoped(call_id=call_id, step_id=f"{turn_id}.main.s{step}", component="core.model"):
                rendered, payload = self._render(state, message, call_id, steps)
                journal.emit("context_rendered", payload)
                if previous is not None:
                    self._check_prefix(*previous, rendered.ids)
                if payload["overflow"]:
                    self._emit_overflow(payload)
                    return "overflow", "", ""
                out = self._call_model(rendered, cancel, state.tools + tuple(loaded_in_turn))
            if out.status != "completed":
                return out.status, "", ""
            if not out.calls and out.malformed is None:
                return "completed", out.text, out.reasoning
            previous = (rendered.ids, out.raw)

            # A failed call earns a new attempt while retries and calls remain (AD-10, AD-14).
            reaction = "retry" if retries < max_retries and n < max_calls else "stop"
            failed = False
            harness_brick = "tools" if "tools" in state.effective else "mcp"
            with scoped(call_id=call_id, brick=harness_brick, component="core.harness"):
                if out.malformed is not None:
                    failed = True
                    step += 1
                    with scoped(step_id=f"{turn_id}.main.s{step}"):
                        error = self._tool_executor.reject(
                            out.raw, out.malformed.fragment, out.malformed.detail_fr, reaction
                        )
                    # The raw output already holds any reasoning: not passed twice.
                    steps.append({"role": "assistant", "content": out.raw, "tool_calls": []})
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
                                {"name": c.name, "arguments": c.arguments} for c in out.calls
                            ],
                        }
                        | ({"reasoning": out.reasoning} if out.reasoning else {})
                    )
                    for call in out.calls:
                        step += 1
                        detail = self._tool_executor.check(
                            call, state.tools + tuple(loaded_in_turn), state.loadable
                        )
                        spec = self._registry.get(call.name) if detail is None else None
                        if detail is not None:
                            failed = True
                        # AD-4: the step and its result belong to the tool's own brick.
                        component = spec.component if spec else "core.harness"
                        brick = (spec.brick or component.split(".")[0]) if spec else harness_brick
                        effects: list[Effect] = []
                        with scoped(
                            step_id=f"{turn_id}.main.s{step}", brick=brick, component=component
                        ):
                            if spec is None:
                                result = self._tool_executor.reject(
                                    out.raw, call.source, detail, reaction
                                )
                            else:
                                result = self._tool_executor.run(call, cancel, effects)
                        if spec is not None and spec.is_mcp and result is not None:
                            self._after_mcp_call(call.name, spec)
                        if spec is not None and (spec.network or spec.is_mcp):
                            self._emit_architecture()  # its contact state may have changed
                        if result is None:
                            return "cancelled", "", ""
                        tool_step = {
                            "role": "tool",
                            "name": call.name,
                            "content": result,
                            "component": component,
                            "brick": brick,
                        }
                        for effect in effects:  # AD-23: the session applies them
                            tool_step |= self._apply_doc_loaded(effect.tool, loaded_in_turn)
                        steps.append(tool_step)
            if failed:
                retries += 1
                if retries > max_retries:
                    self._emit_limit("retries", retries)
                    return "limit", "", ""
            if cancel.cancelled:
                return "cancelled", "", ""
        self._emit_limit("calls", max_calls)
        return "limit", "", ""

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

    def _after_mcp_call(self, name: str, spec: ToolSpec) -> None:
        """A call that could not reach its server (transport, delay) makes it unavailable."""
        contact, why = self._tool_executor.contact.get(name, ("available", None))
        if contact == "unavailable":
            self._mcp_failed(spec.component.removeprefix("mcp."), why)

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

    def _emit_overflow(self, payload: dict[str, Any]) -> None:
        used, usable = payload["used"], payload["usable"]
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
                "used": used,
                "usable": usable,
                "message_fr": (
                    f"Le contexte compte {_fr(used)} tokens pour {_fr(usable)} utilisables "
                    f"(fenêtre de {_fr(payload['window'])} moins {_fr(payload['reserve'])} "
                    f"réservés à la réponse). {cause}"
                ),
                "strategies_fr": _OVERFLOW_STRATEGIES_FR,
            },
        )

    def _call_model(
        self, rendered: RenderedContext, cancel: CancelToken, tools: tuple[str, ...]
    ) -> _ModelOutput:
        """One streamed call; with tools on, its `<tool_call>` blocks are parsed (AD-6)."""
        assert self._engine is not None and self._caps is not None
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
                    "gen_ms": _ms(ended - first),
                    "stop_reason": reason,
                    "duration_ms": _ms(ended - started),
                },
                actor="model",
            )

        try:
            for fragment in self._engine.complete(
                rendered.ids, self._caps.stop_sequences, OUTPUT_RESERVE, cancel
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
        )
        if tools and out.status == "completed":
            assert self._caps.tool_call_parser is not None  # the brick requires it (AD-6)
            schemas = {name: spec.params for name in tools if (spec := self._registry.get(name))}
            out.calls, out.malformed = parse_tool_calls(
                out.raw, self._caps.tool_call_parser, schemas
            )
        end(stop_reason, out.calls)

        if stop_reason == "length":
            journal.emit(
                "output_truncated",
                {
                    "channel": splitter.channel,
                    "output_tokens": output_tokens,
                    "max_tokens": OUTPUT_RESERVE,
                },
            )
            if splitter.channel != "tool_call":
                return _ModelOutput("limit")
            # AD-9: cut inside a tool call, the output follows the malformed-call path.
            fragment = out.malformed.fragment if out.malformed else out.raw
            out.calls, out.malformed = (
                [],
                Malformed(
                    fragment,
                    f"la sortie a été coupée à {_fr(OUTPUT_RESERVE)} tokens au milieu de l'appel",
                ),
            )
        return out
