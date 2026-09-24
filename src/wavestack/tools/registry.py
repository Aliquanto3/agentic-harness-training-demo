"""Tool declarations, their French content, and the single registry of exposed names (AD-14)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from wavestack import config
from wavestack.trace.journal import get_journal

Source = Literal["native", "harness", "mcp_local", "mcp_public"]
Hosting = Literal["local_process", "local_file", "network_service"]


class ToolError(Exception):
    """A refusal or failure the tool explains in French; reinjected to the model."""

    def __init__(self, message_fr: str) -> None:
        super().__init__(message_fr)
        self.message_fr = message_fr


@dataclass(frozen=True)
class ToolSpec:
    name: str
    run: Callable[..., str]
    params: dict[str, str]  # argument -> JSON schema type, all required
    component: str
    source: Source = "native"
    hosting: Hosting = "local_process"
    network: bool = False
    reads_local_path: str | None = None  # the argument holding a path, if any


class ToolText(BaseModel):
    label_fr: str = Field(min_length=1)
    description: str = Field(min_length=1)  # seen by the model
    parameters: dict[str, str] = {}


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
        for spec in self.specs:
            name = spec.name  # native or harness tool: the bare name; MCP arrives with story 6
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
            self._by_name[name] = spec
        if self.content is not None:  # a tool without content cannot be described to the model
            self._by_name = {n: s for n, s in self._by_name.items() if n in self.content.tools}

    @property
    def names(self) -> list[str]:
        return list(self._by_name)

    def get(self, name: str) -> ToolSpec | None:
        return self._by_name.get(name)

    def label(self, name: str) -> str:
        text = self.content.tools.get(name) if self.content else None
        return text.label_fr if text else name

    def definition(self, name: str) -> dict[str, Any]:
        """The JSON definition for the template's `tools` variable.

        Key order is chosen for attribution (AD-4): the name comes first and the
        description last, so the whole definition between them is enclosed in its
        `tool_catalog` segment and almost nothing is left to `template`.
        """
        spec = self._by_name[name]
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
