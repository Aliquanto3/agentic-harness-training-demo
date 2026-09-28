"""Context window, output reserve and gauge figures, all computed by the session side (AD-9)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from wavestack.context.segments import Segment, SegmentKind, SegmentLabels

_MESSAGE_GROUP = "message"
# AD-4: `user_message` and `template` form one gauge group, « Message et gabarit ».
_GROUP_OF = {SegmentKind.USER_MESSAGE: _MESSAGE_GROUP, SegmentKind.TEMPLATE: _MESSAGE_GROUP}
# Story 33: a segment without a brick, or of a brick missing from the table.
NEUTRAL = "neutral"


def discipline_of(segment: Segment, categories: Mapping[str, str]) -> str:
    """Story 33: a segment's discipline is its brick's category (`prompt`, `context`,
    `harness`); `neutral` without a brick (template, user message) or for an unknown one."""
    return categories.get(segment.brick, NEUTRAL) if segment.brick else NEUTRAL


def tokens_by_brick(segments: list[Segment]) -> list[dict[str, Any]]:
    """Story 33: the tokens of each brick's segments, in order of first appearance; segments
    without a brick are left out. `estimated`: at least one of them is an estimate (AD-4)."""
    rows: dict[str, dict[str, Any]] = {}
    for s in segments:
        if not s.brick:
            continue
        row = rows.setdefault(s.brick, {"brick": s.brick, "tokens": 0, "estimated": False})
        row["tokens"] += s.tokens
        row["estimated"] = row["estimated"] or s.estimated
    return list(rows.values())


def _group_discipline(segments: list[Segment], group: str, categories: Mapping[str, str]) -> str:
    """Story 33: a gauge group's discipline, the one carrying the most tokens among its
    segments (a group may mix bricks: tools and MCP descriptions, tool results); a tie goes to
    the discipline met first in context order."""
    weights: dict[str, int] = {}  # insertion order = context order
    for s in segments:
        if _GROUP_OF.get(s.kind, s.kind.value) == group:
            d = discipline_of(s, categories)
            weights[d] = weights.get(d, 0) + s.tokens
    return max(weights, key=weights.__getitem__)  # `max` keeps the first of equal weights


def effective_window(configured: int, native: int | None) -> int:
    return min(configured, native) if native else configured


def gauge(
    segments: list[Segment],
    *,
    window: int,
    reserve: int,
    near_limit_ratio: float,
    labels: SegmentLabels,
    window_source: str = "configured",
    raw_used: int | None = None,
    categories: Mapping[str, str] = {},  # noqa: B006 (read only)
) -> dict[str, Any]:
    """The `context_rendered` / `context_preview` / `context_reconciled` payload: figures and
    per-group breakdown. `raw_used` (chat mode): the raw sum of the estimates, which alone
    decides the overflow (AD-4); `used` is then the corrected total. `categories` (story 33):
    brick id → category, for each segment's and group's `discipline` (AD-9)."""
    usable = window - reserve
    used = sum(s.tokens for s in segments)
    groups: dict[str, dict[str, Any]] = {}
    for kind in SegmentKind:  # stacking order
        tokens = sum(s.tokens for s in segments if s.kind == kind)
        if not any(s.kind == kind for s in segments):
            continue
        group = _GROUP_OF.get(kind, kind.value)
        label = labels.groups.get(group) or labels.kinds[kind]
        if group not in groups:
            groups[group] = {
                "group": group,
                "label_fr": label,
                "tokens": 0,
                "kinds": [],
                "discipline": _group_discipline(segments, group, categories),
            }
        groups[group]["tokens"] += tokens
        groups[group]["kinds"].append(kind.value)
    ratio = used / usable if usable > 0 else float("inf")
    payload: dict[str, Any] = {
        "segments": [
            {
                **s.model_dump(mode="json", exclude={"compressed_from"}),
                "label_fr": s.label_fr or labels.kinds[s.kind],
                "discipline": discipline_of(s, categories),
            }
            | ({"compressed_from": s.compressed_from.model_dump()} if s.compressed_from else {})
            for s in segments
        ],
        "window": window,
        "window_source": window_source,
        "reserve": reserve,
        "usable": usable,
        "used": used,
        "percent": round(ratio * 100, 1) if usable > 0 else 100.0,
        "near_limit": ratio >= near_limit_ratio,
        "near_limit_ratio": near_limit_ratio,
        "overflow": (used if raw_used is None else raw_used) > usable,
        "breakdown": list(groups.values()),
        "by_brick": tokens_by_brick(segments),
    }
    # Story 20 (AD-22): what the same context would weigh without compression, each compressed
    # segment counted at its tokens before (the front adds nothing up, AD-1).
    compressed = [s for s in segments if s.compressed_from is not None]
    if compressed:
        payload["uncompressed_used"] = used + sum(
            max(0, s.compressed_from.tokens_before - s.tokens)  # type: ignore[union-attr]
            for s in compressed
        )
    return payload
