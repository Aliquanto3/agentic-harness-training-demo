"""AD-9: how far a public MCP server's live `tools/list` drifts from its versioned snapshot.

`scripts/snapshot_mcp.py` writes `content/mcp_snapshots/{server_id}.json` (the tools as the
client lists them, `model_dump(by_alias=True, exclude_none=True)`); the scenario window test
counts it. At connection, the session compares the live list with it: tools added or
removed, and the weight of their documentation (description and input schema, in
characters). Pure functions, no network.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wavestack import config

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Drift:
    """The live list against the snapshot: names added and removed, documentation weights
    (characters) before and after, and `ratio`, the larger of the two relative gaps."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    weight_before: int
    weight_after: int
    ratio: float


def snapshot_path(server_id: str) -> Path:
    return config.content_dir() / "mcp_snapshots" / f"{server_id}.json"


def load_snapshot(server_id: str) -> list[dict[str, Any]] | None:
    """The snapshot's tools, `None` when there is none or it cannot be read (logged)."""
    path = snapshot_path(server_id)
    if not path.is_file():
        return None
    try:
        tools = json.loads(path.read_text(encoding="utf-8"))["tools"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _log.warning("MCP snapshot %s unreadable: %s", path, exc)
        return None
    if not isinstance(tools, list) or not all(isinstance(t, dict) for t in tools):
        _log.warning("MCP snapshot %s unreadable: `tools` is not a list of objects", path)
        return None
    return tools


def tool_weight(tool: dict[str, Any]) -> int:
    """What a tool's documentation weighs in the context: its description and its input
    schema, in characters (the schema as compact JSON, keys sorted)."""
    schema = tool.get("inputSchema") or {}
    text = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return len(str(tool.get("description") or "")) + len(text)


def documentation_weight(tools: list[dict[str, Any]]) -> int:
    """A server's documentation weight: the sum of its tools' (`tool_weight`)."""
    return sum(tool_weight(t) for t in tools)


def drift(snapshot: list[dict[str, Any]], live: list[dict[str, Any]]) -> Drift:
    before = {str(t.get("name")): t for t in snapshot}
    after = {str(t.get("name")): t for t in live}
    added = tuple(n for n in after if n not in before)
    removed = tuple(n for n in before if n not in after)
    weight_before = documentation_weight(list(before.values()))
    weight_after = documentation_weight(list(after.values()))
    tools_gap = (len(added) + len(removed)) / len(before) if before else float(bool(after))
    if weight_before:
        weight_gap = abs(weight_after - weight_before) / weight_before
    else:
        weight_gap = float(bool(weight_after))
    return Drift(added, removed, weight_before, weight_after, max(tools_gap, weight_gap))
