"""Context window, output reserve and gauge figures, all computed by the session side (AD-9)."""

from __future__ import annotations

from typing import Any

from wavestack.context.segments import Segment, SegmentKind, SegmentLabels

OUTPUT_RESERVE = 512
_MESSAGE_GROUP = "message"
# AD-4: `user_message` and `template` form one gauge group, « Message et gabarit ».
_GROUP_OF = {SegmentKind.USER_MESSAGE: _MESSAGE_GROUP, SegmentKind.TEMPLATE: _MESSAGE_GROUP}


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
) -> dict[str, Any]:
    """The `context_rendered` / `context_preview` / `context_reconciled` payload: figures and
    per-group breakdown. `raw_used` (chat mode): the raw sum of the estimates, which alone
    decides the overflow (AD-4); `used` is then the corrected total."""
    usable = window - reserve
    used = sum(s.tokens for s in segments)
    groups: dict[str, dict[str, Any]] = {}
    for kind in SegmentKind:  # stacking order
        tokens = sum(s.tokens for s in segments if s.kind == kind)
        if not any(s.kind == kind for s in segments):
            continue
        group = _GROUP_OF.get(kind, kind.value)
        label = labels.groups.get(group) or labels.kinds[kind]
        item = groups.setdefault(
            group, {"group": group, "label_fr": label, "tokens": 0, "kinds": []}
        )
        item["tokens"] += tokens
        item["kinds"].append(kind.value)
    ratio = used / usable if usable > 0 else float("inf")
    return {
        "segments": [
            {**s.model_dump(mode="json"), "label_fr": s.label_fr or labels.kinds[s.kind]}
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
    }
