"""Tool declarations, their French content, and the single registry of exposed names (AD-14)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from wavestack import config
from wavestack.session.effects import ToolReply
from wavestack.trace.journal import get_journal

Source = Literal["native", "harness", "mcp_local", "mcp_public"]
Hosting = Literal["local_process", "local_file", "network_service"]


class ToolError(Exception):
    """A refusal or failure the tool explains in French; reinjected to the model."""

    def __init__(self, message_fr: str) -> None:
        super().__init__(message_fr)
        self.message_fr = message_fr


class Unreachable(ToolError):
    """A network tool could not reach its service (connection failed or refused)."""


class DelegationFailed(ToolError):
    """Story 19 (AD-11): the sub-agent could not finish; `status` is `delegate`'s
    `tool_ended` status, the French message what the main model reads."""

    def __init__(
        self, message_fr: str, status: Literal["limit", "overflow", "error", "cancelled"]
    ) -> None:
        super().__init__(message_fr)
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
    label_fr: str | None = None

    @property
    def is_mcp(self) -> bool:
        return self.source in ("mcp_local", "mcp_public")


class ToolPreset(BaseModel):
    """Arguments that prefill the form of a forced call (story 9), shown by `label_fr`."""

    label_fr: str = Field(min_length=1)
    args: dict[str, Any]


class ToolText(BaseModel):
    label_fr: str = Field(min_length=1)
    description: str = Field(min_length=1)  # seen by the model
    parameters: dict[str, str] = {}
    presets: list[ToolPreset] = []

    @model_validator(mode="after")
    def _presets_use_declared_parameters(self) -> ToolText:
        for preset in self.presets:
            unknown = sorted(set(preset.args) - set(self.parameters))
            if unknown:
                raise ValueError(
                    f"preset {preset.label_fr!r}: arguments {unknown} are not declared parameters"
                )
        return self


class ToolsContent(BaseModel):
    """`content/tools.yaml` (AD-19)."""

    demo_dir_label_fr: str = Field(min_length=1)
    tools: dict[str, ToolText]


def load_tools_content() -> ToolsContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_dir() / "tools.yaml"
    return ToolsContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass
class ToolRegistry:
    """The only place that assigns the names exposed to the model (AD-14)."""

    specs: list[ToolSpec]
    content: ToolsContent | None = None
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
                get_journal().emit(
                    "harness_error",
                    {
                        "message_fr": f"Deux outils portent le nom « {name} » : le second est "
                        "indisponible.",
                        "cause": "Collision de noms dans le registre d'outils (AD-14).",
                        "effect_fr": "Le premier outil déclaré reste utilisable.",
                    },
                )
                continue
            # A native tool without content cannot be described to the model.
            if spec.description is None and self.content and name not in self.content.tools:
                continue
            self._by_name[name] = spec
            added.append(name)
        return added

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
        if spec is not None and spec.label_fr:
            return spec.label_fr
        text = self.content.tools.get(name) if self.content else None
        return text.label_fr if text else name

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
            self.content.tools[name] if self.content else ToolText(label_fr=name, description=name)
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
