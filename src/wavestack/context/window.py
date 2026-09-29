"""Context window, output reserve and gauge figures, all computed by the session side (AD-9)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from wavestack.context.segments import Segment, SegmentKind, SegmentLabels
from wavestack.models.engine import EngineMetadata

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


def seen_prefix(previous: list[Segment] | None, current: list[Segment]) -> int:
    """Story 32: how many leading segments of `current` the previous call of the same context
    read already in this turn, compared on `(kind, brick, component, text)`, in order; 0
    without a previous call."""
    count = 0
    for before, now in zip(previous or [], current, strict=False):
        if (before.kind, before.brick, before.component, before.text) != (
            now.kind,
            now.brick,
            now.component,
            now.text,
        ):
            break
        count += 1
    return count


def context_sections(
    segments: list[Segment],
    labels: SegmentLabels,
    categories: Mapping[str, str] = {},  # noqa: B006 (read only)
    seen: int = 0,
) -> tuple[list[dict[str, Any]], int, int]:
    """Story 32: the reading sections of a context, then `seen_segments` and `seen_tokens`.

    A segment's source is `(kind, brick)`; a `template` has none. A non-template segment joins
    the current section when it has the same source and only `template` pieces lie between
    them: those are absorbed, their tokens counted in `template_tokens`. Any template piece not
    absorbed forms a section, merged with its template neighbours. A segment with a label of
    its own (the provider's, chat mode) is always alone, and the `seen` boundary always cuts.
    The sum of the sections' tokens is the sum of the segments' (AD-1)."""
    seen = max(0, min(seen, len(segments)))
    sections: list[dict[str, Any]] = []

    def open_section(start: int) -> dict[str, Any]:
        first = segments[start]
        is_template = first.kind == SegmentKind.TEMPLATE
        return {
            "start": start,
            "end": start + 1,
            "kind": first.kind.value,
            "label_fr": first.label_fr or labels.kinds[first.kind],
            "brick": None if is_template else first.brick,
            "discipline": NEUTRAL if is_template else discipline_of(first, categories),
            "tokens": first.tokens,
            "template_tokens": 0,
            "estimated": first.estimated,
            "seen": False,
        }

    def add(section: dict[str, Any], index: int, *, absorbed: bool = False) -> None:
        segment = segments[index]
        section["end"] = index + 1
        section["tokens"] += segment.tokens
        section["estimated"] = section["estimated"] or segment.estimated
        if absorbed:
            section["template_tokens"] += segment.tokens

    def own(index: int) -> bool:
        return segments[index].label_fr is not None

    def crosses(start: int, index: int) -> bool:
        return start < seen <= index  # joining would straddle the `seen` boundary

    def flush(pending: list[int]) -> None:
        """The template pieces no section absorbed, merged with their template neighbours,
        except a piece with a label of its own and across the `seen` boundary."""
        run: dict[str, Any] | None = None
        for index in pending:
            if (
                run is not None
                and run["end"] == index
                and not own(run["start"])
                and not own(index)
                and not crosses(run["start"], index)
            ):
                add(run, index)
                continue
            run = open_section(index)
            sections.append(run)

    current: dict[str, Any] | None = None  # the open non-template section
    pending: list[int] = []  # template pieces met since its last segment
    for index, segment in enumerate(segments):
        if segment.kind == SegmentKind.TEMPLATE:
            pending.append(index)
            continue
        if (
            current is not None
            and current["kind"] == segment.kind.value
            and current["brick"] == segment.brick
            and not own(current["start"])
            and not own(index)
            and not crosses(current["start"], index)
        ):
            for piece in pending:
                add(current, piece, absorbed=True)
            add(current, index)
            pending = []
            continue
        flush(pending)
        pending = []
        current = open_section(index)
        sections.append(current)
    flush(pending)
    for section in sections:
        section["seen"] = seen > 0 and section["end"] <= seen
    seen_tokens = sum(s.tokens for s in segments[:seen])
    return sections, seen, seen_tokens


def effective_window(configured: int, native: int | None) -> int:
    return min(configured, native) if native else configured


def window_for(meta: EngineMetadata, configured: int) -> tuple[int, str]:
    """AD-9: a local model's window, min(configured, native, the server's own context), and
    its source. The session's load and the model table (story 25) share it."""
    window = effective_window(configured, meta.native_context)
    source = "configured" if window == configured else "native"
    if meta.server_context and meta.server_context < window:
        window, source = meta.server_context, "server"
    return window, source


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
    seen: int = 0,
) -> dict[str, Any]:
    """The `context_rendered` / `context_preview` / `context_reconciled` payload: figures and
    per-group breakdown. `raw_used` (chat mode): the raw sum of the estimates, which alone
    decides the overflow (AD-4); `used` is then the corrected total. `categories` (story 33):
    brick id → category, for each segment's and group's `discipline` (AD-9). `seen` (story
    32): the segments the previous call of the same context read already in the turn."""
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
    sections, seen_segments, seen_tokens = context_sections(segments, labels, categories, seen)
    payload |= {"sections": sections, "seen_segments": seen_segments, "seen_tokens": seen_tokens}
    # Story 20 (AD-22): what the same context would weigh without compression, each compressed
    # segment counted at its tokens before (the front adds nothing up, AD-1).
    compressed = [s for s in segments if s.compressed_from is not None]
    if compressed:
        payload["uncompressed_used"] = used + sum(
            max(0, s.compressed_from.tokens_before - s.tokens)  # type: ignore[union-attr]
            for s in compressed
        )
    return payload
