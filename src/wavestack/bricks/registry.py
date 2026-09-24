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
    BrickDeclaration(
        id="tools",
        category="harness",
        capabilities=["tool_call_parser"],
        network=True,
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
