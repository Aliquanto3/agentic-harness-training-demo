"""The three MCP servers of the `mcp` brick, and their French labels (AD-19)."""

from __future__ import annotations

from dataclasses import dataclass

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
    label_fr: str = Field(min_length=1)


class LoadToolDocText(BaseModel):
    """The harness meta-tool of the lazy loading mode (AD-25)."""

    label_fr: str = Field(min_length=1)
    intro: str = Field(min_length=1)  # seen by the model, before one line per tool
    tool: str = Field(min_length=1)  # the `tool` parameter's description


class McpContent(BaseModel):
    """`content/mcp.yaml`."""

    servers: dict[str, ServerText]
    lazy_label_fr: str = Field(min_length=1)
    load_tool_doc: LoadToolDocText


def load_mcp_content() -> McpContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_dir() / "mcp.yaml"
    return McpContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
