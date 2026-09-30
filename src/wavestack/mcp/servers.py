"""The three MCP servers of the `mcp` brick, and their French labels (AD-19)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml
from pydantic import BaseModel, Field

from wavestack import config

LOCAL = "local"


@dataclass(frozen=True)
class McpServer:
    id: str
    url: str | None  # None: the local server, a child process over stdio

    @property
    def network(self) -> bool:
        return self.url is not None

    @property
    def source(self) -> str:
        return "mcp_public" if self.network else "mcp_local"

    @property
    def component(self) -> str:
        return f"mcp.{self.id}"


def mcp_servers(cfg: config.Config) -> dict[str, McpServer]:
    """In the brick's display order: the local server, then the public ones."""
    urls = cfg.mcp_urls
    return {
        LOCAL: McpServer(LOCAL, None),
        "datagouv": McpServer("datagouv", urls["datagouv"]),
        "mslearn": McpServer("mslearn", urls["mslearn"]),
    }


class ServerText(BaseModel):
    label_text: str = Field(min_length=1)
    # Story 34, public servers: what leaves the workstation on each call.
    sends_text: str | None = None


class LoadToolDocText(BaseModel):
    """The harness meta-tool of the lazy loading mode (AD-25)."""

    label_text: str = Field(min_length=1)
    intro: str = Field(min_length=1)  # seen by the model, before one line per tool
    tool: str = Field(min_length=1)  # the `tool` parameter's description


class CallPreset(BaseModel):
    """Lot K: arguments that prefill the form of an MCP tool's forced call, shown by
    `label_text` (the tool's parameters come from its server, at connection)."""

    label_text: str = Field(min_length=1)
    args: dict[str, Any]


class McpContent(BaseModel):
    """`content/mcp.yaml`."""

    servers: dict[str, ServerText]
    lazy_label_text: str = Field(min_length=1)
    load_tool_doc: LoadToolDocText
    # Lot K: the presets of « Forcer l'appel », by full tool name (`{server}__{tool}`).
    call_presets: dict[str, list[CallPreset]] = {}


def load_mcp_content(lang: str | None = None) -> McpContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_file("mcp.yaml", lang)
    return McpContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class LocalToolsText(BaseModel):
    """`content/mcp_local/tools.yaml`: the local server's tool descriptions, seen by the model."""

    list_terms: str = Field(min_length=1)
    define_term: str = Field(min_length=1)


def load_local_tools(lang: str | None = None) -> LocalToolsText:
    """Raises on a missing or invalid file (the local server then does not start)."""
    path = config.content_file("mcp_local/tools.yaml", lang)
    return LocalToolsText.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
