"""Tool declarations, their French content, and the single registry of exposed names (AD-14)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from wavestack import config
from wavestack.messages import KeyedError, Message, msg
from wavestack.session.effects import ToolReply
from wavestack.trace.journal import get_journal

Source = Literal["native", "harness", "mcp_local", "mcp_public"]
Hosting = Literal["local_process", "local_file", "network_service"]


class ToolError(KeyedError):
    """A refusal or failure the tool explains, reinjected to the model: a key of
    `messages.yaml` and its variables (languages 5/5), rendered in the session's language
    by the executor; `message_text` and `str()` give the French."""

    @property
    def message_text(self) -> str:
        return str(self)


class Unreachable(ToolError):
    """A network tool could not reach its service (connection failed or refused)."""


class DelegationFailed(ToolError):
    """Story 19 (AD-11): the sub-agent could not finish; `status` is `delegate`'s
    `tool_ended` status, the French message what the main model reads."""

    def __init__(
        self,
        key: str | Message,
        status: Literal["limit", "overflow", "error", "cancelled"],
        /,
        **kw: object,
    ) -> None:
        super().__init__(key, **kw)
        self.status = status


@dataclass(frozen=True)
class ToolSpec:
    name: str
    run: Callable[..., str | ToolReply]
    params: dict[str, str]  # argument -> JSON schema type, all required
    component: str
    source: Source = "native"
    hosting: Hosting = "local_process"
    network: bool = False
    reads_local_path: str | None = None  # the argument holding a path, if any
    # Network tools (AD-14): `preview(**args) -> {method, url, body}`, exactly what `run` sends.
    preview: Callable[..., dict[str, str]] | None = None
    # MCP tools (story 6): their own documentation, as the server lists it. `params` then maps
    # each argument to its schema type ("" when not a plain type), `required` names the
    # required ones (None: all of `params`).
    description: str | None = None
    schema: dict[str, Any] | None = None
    required: tuple[str, ...] | None = None
    # Harness tools (AD-25): the brick they belong to when it is not the component's own
    # (`load_tool_doc`: brick `mcp`, component `core.harness`), and their French label.
    brick: str | None = None
    label_text: str | None = None

    @property
    def is_mcp(self) -> bool:
        return self.source in ("mcp_local", "mcp_public")


class ToolPreset(BaseModel):
    """Arguments that prefill the form of a forced call (story 9), shown by `label_text`."""

    label_text: str = Field(min_length=1)
    args: dict[str, Any]


class ToolText(BaseModel):
    label_text: str = Field(min_length=1)
    description: str = Field(min_length=1)  # seen by the model
    parameters: dict[str, str] = {}
    presets: list[ToolPreset] = []
    # Story 34, network tools: what leaves the workstation when the tool runs.
    sends_text: str | None = None

    @model_validator(mode="after")
    def _presets_use_declared_parameters(self) -> ToolText:
        for preset in self.presets:
            unknown = sorted(set(preset.args) - set(self.parameters))
            if unknown:
                raise ValueError(
                    f"preset {preset.label_text!r}: arguments {unknown} are not declared parameters"
                )
        return self


class ToolsContent(BaseModel):
    """`content/tools.yaml` (AD-19)."""

    demo_dir_label_text: str = Field(min_length=1)
    tools: dict[str, ToolText]


def load_tools_content(lang: str | None = None) -> ToolsContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_file("tools.yaml", lang)
    return ToolsContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass
class ToolRegistry:
    """The only place that assigns the names exposed to the model (AD-14)."""

    specs: list[ToolSpec]
    content: ToolsContent | None = None
    # Languages (5/5): the session's language, that of the errors the registry traces.
    language: Callable[[], str] = lambda: config.DEFAULT_LANGUAGE
    _by_name: dict[str, ToolSpec] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.add(self.specs)

    @staticmethod
    def exposed_name(spec: ToolSpec) -> str:
        """Native or harness tool: the bare name; MCP tool: `{server_id}__{tool}`."""
        if spec.is_mcp:
            return f"{spec.component.removeprefix('mcp.')}__{spec.name}"
        return spec.name

    def add(self, specs: list[ToolSpec]) -> list[str]:
        """Register `specs`; returns the names exposed. A colliding name stays unavailable."""
        added = []
        for spec in specs:
            name = self.exposed_name(spec)
            if name in self._by_name:
                lang = self.language()
                get_journal().emit(
                    "harness_error",
                    {
                        "message_text": msg("tools.registry.collision", lang, name=name),
                        "cause": msg("tools.registry.collision_cause", lang),
                        "effect_text": msg("tools.registry.collision_effect", lang),
                    },
                )
                continue
            # A native tool without content cannot be described to the model.
            if spec.description is None and self.content and name not in self.content.tools:
                continue
            self._by_name[name] = spec
            added.append(name)
        return added

    def replace(self, specs: list[ToolSpec]) -> None:
        """Languages (1/5): tools already registered, described again in another language;
        a name not registered is left out."""
        for spec in specs:
            name = self.exposed_name(spec)
            if name in self._by_name:
                self._by_name[name] = spec

    def remove(self, prefix: str) -> None:
        """Unregister every tool whose exposed name starts with `prefix` (e.g. `local__`)."""
        for name in [n for n in self._by_name if n.startswith(prefix)]:
            del self._by_name[name]

    @property
    def names(self) -> list[str]:
        return list(self._by_name)

    def get(self, name: str) -> ToolSpec | None:
        return self._by_name.get(name)

    def label(self, name: str) -> str:
        spec = self._by_name.get(name)
        if spec is not None and spec.label_text:
            return spec.label_text
        text = self.content.tools.get(name) if self.content else None
        return text.label_text if text else name

    def sends(self, name: str) -> str | None:
        """Story 34: what a tool sends out of the workstation, from `content/tools.yaml`."""
        text = self.content.tools.get(name) if self.content else None
        return text.sends_text if text else None

    def definition(self, name: str) -> dict[str, Any]:
        """The JSON definition for the template's `tools` variable.

        Key order is chosen for attribution (AD-4): the name comes first and the
        description last, so the whole definition between them is enclosed in its
        `tool_catalog` segment and almost nothing is left to `template`.
        """
        spec = self._by_name[name]
        if spec.description is not None:  # MCP (or harness): its own documentation, as is
            return {
                "type": "function",
                "function": {
                    "name": name,
                    "parameters": spec.schema or {"type": "object", "properties": {}},
                    "description": spec.description,
                },
            }
        text = (
            self.content.tools[name]
            if self.content
            else ToolText(label_text=name, description=name)
        )
        return {
            "type": "function",
            "function": {
                "name": name,
                "parameters": {
                    "type": "object",
                    "required": list(spec.params),
                    "properties": {
                        arg: {"type": kind, "description": text.parameters.get(arg, arg)}
                        for arg, kind in spec.params.items()
                    },
                },
                "description": text.description,
            },
        }
