"""The local MCP server: the demo's glossary, over stdio, offline (story 6).

Launched by the session as `python -m wavestack.mcp.local_server` when its
sub-option is enabled. The network guard is installed first, loopback only,
before any third-party import (AD-15).
"""

from wavestack.net.guard import install

install([])

import yaml  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp_types import CallToolResult, TextContent  # noqa: E402

from wavestack import config  # noqa: E402


def load_glossary() -> dict[str, str]:
    path = config.content_dir() / "mcp_local" / "glossary.yaml"
    terms = yaml.safe_load(path.read_text(encoding="utf-8"))["terms"]
    return {str(term): " ".join(str(text).split()) for term, text in terms.items()}


server = MCPServer("wavestack-glossaire", log_level="WARNING")


@server.tool(description="Liste les termes du glossaire du démonstrateur WaveStack, un par ligne.")
def list_terms() -> str:
    return "\n".join(load_glossary())


@server.tool(
    description=(
        "Donne la définition d'une notion du démonstrateur WaveStack (harnais, contexte, "
        "outil, MCP, skill, hook, RAG…). Appeler list_terms pour connaître les termes."
    )
)
def define_term(term: str) -> CallToolResult:
    glossary = load_glossary()
    wanted = term.strip().casefold()
    for name, definition in glossary.items():
        if name.casefold() == wanted:
            return CallToolResult(content=[TextContent(type="text", text=f"{name} : {definition}")])
    known = ", ".join(glossary)
    text = f"Terme inconnu du glossaire : « {term} ». Termes disponibles : {known}."
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


if __name__ == "__main__":
    server.run("stdio")
