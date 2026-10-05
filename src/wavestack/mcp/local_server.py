"""The local MCP server: the demo's glossary, over stdio, offline (story 6).

Lot 4 of 2026-10-04 (AD-27): it announces the three primitives, its two tools, the static
resource `glossary://terms` and the prompt `explain_term(term)`, their texts in
`content/mcp_local/` in its language.

Launched by the session as `python -m wavestack.mcp.local_server` when its
sub-option is enabled. The network guard is installed first, loopback only,
before any third-party import (AD-15).
"""

import sys

from wavestack.net.guard import install

install([])

from typing import Annotated  # noqa: E402

import yaml  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.prompts.base import UserMessage  # noqa: E402
from mcp_types import CallToolResult, TextContent  # noqa: E402
from pydantic import Field  # noqa: E402

from wavestack import config  # noqa: E402
from wavestack.mcp.servers import load_local_primitives, load_local_tools  # noqa: E402
from wavestack.messages import msg  # noqa: E402

# Languages (1/5): the session names the language as the only argument (the process gets a
# default environment, without the data dir); French when imported or without one.
LANGUAGE = config.as_language(sys.argv[1] if __name__ == "__main__" and len(sys.argv) > 1 else None)


def load_glossary() -> dict[str, str]:
    path = config.content_file("mcp_local/glossary.yaml", LANGUAGE)
    terms = yaml.safe_load(path.read_text(encoding="utf-8"))["terms"]
    return {str(term): " ".join(str(text).split()) for term, text in terms.items()}


# The tools' descriptions, seen by the model (AD-19), in `LANGUAGE`: after a change of
# language, the session starts the process again. An invalid translation: the French ones.
try:
    _TOOLS = load_local_tools(LANGUAGE)
except Exception:  # noqa: BLE001
    _TOOLS = load_local_tools(config.DEFAULT_LANGUAGE)
try:
    _PRIMITIVES = load_local_primitives(LANGUAGE)
except Exception:  # noqa: BLE001
    _PRIMITIVES = load_local_primitives(config.DEFAULT_LANGUAGE)

server = MCPServer("wavestack-glossaire", log_level="WARNING")


@server.tool(description=_TOOLS.list_terms)
def list_terms() -> str:
    return "\n".join(load_glossary())


@server.tool(description=_TOOLS.define_term)
def define_term(term: str) -> CallToolResult:
    glossary = load_glossary()
    wanted = term.strip().casefold()
    for name, definition in glossary.items():
        if name.casefold() == wanted:
            return CallToolResult(content=[TextContent(type="text", text=f"{name} : {definition}")])
    known = ", ".join(glossary)
    text = msg("mcp.glossary.unknown_term", LANGUAGE, term=term, known=known)
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


@server.resource(
    "glossary://terms",
    name="terms",
    title=_PRIMITIVES.terms.title,
    description=_PRIMITIVES.terms.description,
    mime_type="text/plain",
)
def terms() -> str:
    return "\n".join(load_glossary())


_PROMPT = _PRIMITIVES.explain_term


@server.prompt(name="explain_term", title=_PROMPT.title, description=_PROMPT.description)
def explain_term(term: Annotated[str, Field(description=_PROMPT.term)]) -> list[UserMessage]:
    glossary = load_glossary()
    wanted = term.strip().casefold()
    for name, definition in glossary.items():
        if name.casefold() == wanted:
            return [UserMessage(_PROMPT.text.format(term=name, definition=definition))]
    return [UserMessage(_PROMPT.unknown_text.format(term=term, known=", ".join(glossary)))]


if __name__ == "__main__":
    server.run("stdio")
