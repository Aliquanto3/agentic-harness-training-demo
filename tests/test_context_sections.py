"""Story 32: the reading sections of a context and its « déjà lu » prefix, computed by the
session in `gauge()` (AD-1, AD-9)."""

from __future__ import annotations

from wavestack.context.segments import Segment, SegmentKind, load_labels
from wavestack.context.window import context_sections, gauge, seen_prefix
from wavestack.trace.catalog import ContextWindowPayload

T, SP, UM, TC, TR, AT = (
    SegmentKind.TEMPLATE,
    SegmentKind.SYSTEM_PROMPT,
    SegmentKind.USER_MESSAGE,
    SegmentKind.TOOL_CATALOG,
    SegmentKind.TOOL_RESULT,
    SegmentKind.ASSISTANT_TURN,
)
_CATEGORIES = {"system_prompt": "prompt", "tools": "harness", "mcp": "harness"}
_BRICK = {SP: "system_prompt", TC: "tools", TR: "tools", AT: None, UM: None, T: None}


def seg(
    n: int,
    kind: SegmentKind,
    tokens: int = 1,
    *,
    text: str | None = None,
    brick: str | None = "",
    component: str | None = None,
    estimated: bool = False,
    label_text: str | None = None,
) -> Segment:
    return Segment(
        id=f"t1.main.c1.{n}",
        kind=kind,
        brick=_BRICK[kind] if brick == "" else brick,
        component=component,
        text=f"{kind.value}-{n}" if text is None else text,
        tokens=tokens,
        estimated=estimated,
        label_text=label_text,
    )


def _gauge(segments: list[Segment], seen: int = 0) -> dict:
    return gauge(
        segments,
        window=4096,
        reserve=512,
        near_limit_ratio=0.8,
        labels=load_labels(),
        categories=_CATEGORIES,
        seen=seen,
    )


def _cuts(payload: dict) -> list[tuple[int, int]]:
    return [(s["start"], s["end"]) for s in payload["sections"]]


def test_simple_sources_give_one_section_per_segment():
    payload = _gauge([seg(0, T), seg(1, SP, 5), seg(2, T), seg(3, UM, 4), seg(4, T)])

    assert _cuts(payload) == [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    labels = load_labels()
    assert [s["label_text"] for s in payload["sections"]] == [
        labels.kinds[k] for k in (T, SP, T, UM, T)
    ]
    assert [s["discipline"] for s in payload["sections"]] == [
        "neutral",
        "prompt",
        "neutral",
        "neutral",
        "neutral",
    ]
    assert payload["sections"][1]["brick"] == "system_prompt"
    assert payload["sections"][0]["brick"] is None
    ContextWindowPayload.model_validate(payload)  # the catalogue's shape (AD-2)


def test_template_between_the_same_source_is_absorbed():
    segments = [
        seg(0, T, 2),
        seg(1, TC, 30, component="tools.calculator"),
        seg(2, T, 1, text="\n"),
        seg(3, TC, 20, component="tools.get_datetime"),
        seg(4, T, 3),
    ]
    payload = _gauge(segments)

    assert _cuts(payload) == [(0, 1), (1, 4), (4, 5)]
    middle = payload["sections"][1]
    assert (middle["kind"], middle["brick"], middle["discipline"]) == (
        "tool_catalog",
        "tools",
        "harness",
    )
    assert middle["tokens"] == 51 and middle["template_tokens"] == 1


def test_same_kind_of_another_brick_is_another_section():
    payload = _gauge([seg(0, TC, 3, brick="tools"), seg(1, T), seg(2, TC, 4, brick="mcp")])

    assert _cuts(payload) == [(0, 1), (1, 2), (2, 3)]
    assert [s["brick"] for s in payload["sections"]] == ["tools", None, "mcp"]


def test_a_segment_with_its_own_label_stands_alone():
    provider = "Gabarit appliqué chez le fournisseur (estimé)"
    segments = [
        seg(0, T, 0, estimated=True),
        seg(1, UM, 4, estimated=True),
        seg(2, T, 0, estimated=True),
        seg(3, T, 12, text="", estimated=True, label_text=provider),
    ]
    payload = _gauge(segments)

    assert _cuts(payload) == [(0, 1), (1, 2), (2, 3), (3, 4)]
    assert payload["sections"][-1]["label_text"] == provider
    assert all(s["estimated"] for s in payload["sections"])


def test_consecutive_templates_merge_and_the_sum_is_the_total():
    segments = [seg(0, T, 2), seg(1, T, 3), seg(2, SP, 5), seg(3, T, 1), seg(4, T, 1)]
    payload = _gauge(segments)

    assert _cuts(payload) == [(0, 2), (2, 3), (3, 5)]
    assert sum(s["tokens"] for s in payload["sections"]) == payload["used"] == 12
    assert payload["sections"][0]["template_tokens"] == 0  # a template section absorbs nothing


def test_estimated_when_one_segment_is():
    payload = _gauge([seg(0, TC, 3, estimated=True), seg(1, T, 0), seg(2, TC, 4)])

    assert _cuts(payload) == [(0, 3)]
    assert payload["sections"][0]["estimated"] is True


def test_first_call_has_nothing_seen():
    payload = _gauge([seg(0, T), seg(1, UM), seg(2, T)])

    assert (payload["seen_segments"], payload["seen_tokens"]) == (0, 0)
    assert not any(s["seen"] for s in payload["sections"])


def _call(n: int, extra: list[Segment]) -> list[Segment]:
    base = [seg(0, T, 2), seg(1, SP, 5), seg(2, T, 1), seg(3, UM, 4)]
    return [*base, seg(4, T, 1, text=f"gabarit-{n}"), *extra]


def test_the_seen_boundary_after_a_tool_call_always_cuts():
    first = _call(1, [])
    second = _call(2, [seg(5, AT, 6), seg(6, T, 1), seg(7, TR, 3), seg(8, T, 2)])

    seen = seen_prefix(first, second)
    payload = _gauge(second, seen)

    assert seen == 4  # the template after the message differs (the generation prompt)
    assert payload["seen_segments"] == 4 and payload["seen_tokens"] == 2 + 5 + 1 + 4
    assert _cuts(payload) == [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 8),
        (8, 9),
    ]
    assert [s["seen"] for s in payload["sections"]] == [True] * 4 + [False] * 5
    for s in payload["sections"]:  # no section straddles the boundary
        assert s["end"] <= seen or s["start"] >= seen
    tool = next(s for s in payload["sections"] if s["kind"] == "tool_result")
    assert tool["seen"] is False and tool["label_text"] == load_labels().kinds[TR]


def test_the_boundary_splits_what_would_otherwise_merge():
    segments = [seg(0, TC, 3, component="a"), seg(1, T, 1), seg(2, TC, 4, component="b")]
    assert _cuts(_gauge(segments, seen=2)) == [(0, 1), (1, 2), (2, 3)]
    assert _cuts(_gauge(segments, seen=1)) == [(0, 1), (1, 2), (2, 3)]
    assert _cuts(_gauge(segments, seen=3)) == [(0, 3)]
    templates = [seg(0, T, 1), seg(1, T, 1), seg(2, T, 1)]
    assert _cuts(_gauge(templates, seen=2)) == [(0, 2), (2, 3)]


def test_seen_prefix_compares_kind_brick_component_and_text_in_order():
    a = [seg(0, T), seg(1, SP), seg(2, TC, component="tools.x")]
    assert seen_prefix(None, a) == 0
    assert seen_prefix(a, a) == 3
    assert seen_prefix(a[:2], a) == 2
    other_component = [*a[:2], seg(2, TC, component="tools.y")]
    assert seen_prefix(a, other_component) == 2
    other_brick = [seg(0, T), seg(1, SP, brick="subagent"), a[2]]
    assert seen_prefix(a, other_brick) == 1
    other_text = [seg(0, T, text="autre"), *a[1:]]
    assert seen_prefix(a, other_text) == 0
    same_but_tokens = [s.model_copy(update={"tokens": 99, "id": "x"}) for s in a]
    assert seen_prefix(a, same_but_tokens) == 3  # tokens and ids are not compared


def test_context_sections_alone_matches_the_gauge():
    segments = _call(2, [seg(5, AT, 6), seg(6, T, 1), seg(7, TR, 3)])
    sections, seen, tokens = context_sections(segments, load_labels(), _CATEGORIES, 4)
    payload = _gauge(segments, 4)
    assert sections == payload["sections"] and (seen, tokens) == (4, 12)
    assert context_sections([], load_labels())[0] == []
