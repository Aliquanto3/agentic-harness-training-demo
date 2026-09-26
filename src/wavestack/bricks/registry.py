"""Declared bricks, and the id uniqueness check run at load time (AD-12)."""

from __future__ import annotations

from wavestack.bricks.contract import BrickDeclaration, Component

# Fixed nodes of the schema, reserved for the harness itself.
RESERVED_NODES = frozenset(
    {
        "core.harness",
        "core.model",
        "core.model_sub",
        "file.memory",
        "file.audit",
        "file.demo_dir",
        "file.rag_index",
    }
)

# Story 7: the skills of the `skills` brick, in display order; one SKILL.md each (AD-19).
SKILLS = (
    "caveman",
    "meeting_minutes",
    "pirate",
    "explain_like_ten",
    "budget_review",
    "working_days",
)

# Story 8: the hooks of the `hooks` brick, in the order they are called (AD-13); H5: 8b.
HOOKS = ("h1", "h2", "h3", "h5")

BRICKS = [
    BrickDeclaration(
        id="short_memory",
        category="context",
        components=[
            Component(
                id="short_memory.history",
                kind="memory",
                hosting="local_process",
                edges_to=["core.harness"],
            )
        ],
    ),
    BrickDeclaration(
        id="system_prompt",
        category="prompt",
        components=[
            Component(
                id="system_prompt.prompt",
                kind="prompt",
                hosting="local_process",
                edges_to=["core.harness"],
            )
        ],
    ),
    # Story 14: the global memory, a local file the harness alone writes (AD-20, AD-23); no
    # capability required: without a tool parser, it is injected and edited, not written by
    # the model.
    BrickDeclaration(
        id="global_memory",
        category="context",
        components=[
            Component(
                id="global_memory.memory",
                kind="memory",
                hosting="local_file",
                edges_to=["core.harness", "file.memory"],
            )
        ],
    ),
    # Story 13: the model's reasoning mode, available when the model can reason (AD-6).
    BrickDeclaration(
        id="reasoning",
        category="prompt",
        capabilities=["reasoning"],
        components=[
            Component(
                id="reasoning.mode",
                kind="reasoning",
                hosting="local_process",
                edges_to=["core.harness"],
            )
        ],
    ),
    # Story 19: its tools also serve the sub-agent's context (AD-11), per `[subagent] tools`.
    BrickDeclaration(
        id="tools",
        category="harness",
        capabilities=["tool_call_parser"],
        network=True,
        contributes_to=["main", "sub"],
        components=[
            Component(
                id="tools.get_datetime",
                kind="tool",
                hosting="local_process",
                edges_to=["core.harness"],
            ),
            Component(
                id="tools.calculator",
                kind="tool",
                hosting="local_process",
                edges_to=["core.harness"],
            ),
            Component(
                id="tools.read_file",
                kind="tool",
                hosting="local_process",
                edges_to=["core.harness", "file.demo_dir"],
            ),
            *(
                Component(
                    id=f"tools.{name}",
                    kind="tool",
                    hosting="network_service",
                    edges_to=["core.harness"],
                )
                for name in ("public_holidays", "wikipedia_summary", "fetch_page")
            ),
        ],
    ),
    # Story 6: one component per MCP server; the brick does not require `tools`.
    BrickDeclaration(
        id="mcp",
        category="harness",
        capabilities=["tool_call_parser"],
        network=True,
        components=[
            Component(
                id="mcp.local",
                kind="mcp_server",
                hosting="local_process",
                edges_to=["core.harness"],
            ),
            *(
                Component(
                    id=f"mcp.{server}",
                    kind="mcp_server",
                    hosting="network_service",
                    edges_to=["core.harness"],
                )
                for server in ("datagouv", "mslearn")
            ),
        ],
    ),
    # Story 7: one component per skill, a local file; no dependency on another brick.
    BrickDeclaration(
        id="skills",
        category="context",
        capabilities=["tool_call_parser"],
        components=[
            Component(
                id=f"skills.{skill}",
                kind="skill",
                hosting="local_file",
                edges_to=["core.harness"],
            )
            for skill in SKILLS
        ],
    ),
    # Story 8: one component per hook; H2 also writes the audit log.
    BrickDeclaration(
        id="hooks",
        category="harness",
        components=[
            Component(
                id=f"hooks.{hook}",
                kind="hook",
                hosting="local_process",
                edges_to=["core.harness"] + (["file.audit"] if hook == "h2" else []),
            )
            for hook in HOOKS
        ],
    ),
    # Story 19: the sub-agent, the same model in a context of its own (AD-11). Its component
    # is a chip of the harness; the schema draws its model as `core.model_sub`.
    BrickDeclaration(
        id="subagent",
        category="harness",
        capabilities=["tool_call_parser"],
        contributes_to=["main", "sub"],
        components=[
            Component(
                id="subagent.agent",
                kind="subagent",
                hosting="local_process",
                edges_to=["core.harness"],
            )
        ],
    ),
    # Story 15: the simple RAG, a local process (the embedding model) that reads the index;
    # no capability required, no network.
    BrickDeclaration(
        id="rag",
        category="context",
        components=[
            Component(
                id="rag.retriever",
                kind="retriever",
                hosting="local_process",
                edges_to=["core.harness", "file.rag_index"],
            ),
            # Story 16: the reranking model, drawn while its sub-option is enabled.
            Component(
                id="rag.reranker",
                kind="reranker",
                hosting="local_process",
                edges_to=["core.harness"],
            ),
        ],
    ),
]


def check_unique_ids(bricks: list[BrickDeclaration]) -> dict[str, BrickDeclaration]:
    """Brick ids, component ids and reserved nodes never collide. Raises `ValueError`."""
    seen = set(RESERVED_NODES)
    for brick in bricks:
        for node_id in [brick.id, *(c.id for c in brick.components)]:
            if node_id in seen:
                raise ValueError(f"duplicate brick or component id: {node_id!r}")
            seen.add(node_id)
    return {brick.id: brick for brick in bricks}
