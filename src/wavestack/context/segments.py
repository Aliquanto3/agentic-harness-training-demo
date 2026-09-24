"""Segment types of the context (AD-4) and their French labels (AD-19)."""

from __future__ import annotations

from enum import StrEnum
from functools import cache
from typing import NamedTuple

import yaml
from pydantic import BaseModel, model_validator

from wavestack import config


class SegmentKind(StrEnum):
    """Closed enumeration, in the gauge's stacking order. Adding one amends the spine."""

    SYSTEM_PROMPT = "system_prompt"
    GLOBAL_MEMORY = "global_memory"
    TOOL_CATALOG = "tool_catalog"
    SKILL_CATALOG = "skill_catalog"
    SKILL_BODY = "skill_body"
    HISTORY = "history"
    RAG_EXCERPT = "rag_excerpt"
    TOOL_RESULT = "tool_result"
    SUBAGENT_RESULT = "subagent_result"
    HOOK_INJECTION = "hook_injection"
    USER_MESSAGE = "user_message"
    ASSISTANT_TURN = "assistant_turn"
    TEMPLATE = "template"


class Part(NamedTuple):
    """One harness-owned text placed in a message before rendering."""

    kind: SegmentKind
    text: str
    brick: str | None = None
    component: str | None = None


class Segment(BaseModel):
    id: str
    kind: SegmentKind
    brick: str | None = None
    component: str | None = None
    text: str
    tokens: int = 0


class SegmentLabels(BaseModel):
    kinds: dict[SegmentKind, str]
    groups: dict[str, str]

    @model_validator(mode="after")
    def _every_kind_labelled(self) -> SegmentLabels:
        missing = set(SegmentKind) - set(self.kinds)
        if missing:
            raise ValueError(f"missing labels for {sorted(missing)}")
        return self


@cache
def load_labels() -> SegmentLabels:
    """Read `content/labels/segment_kinds.yaml`. Raises on an invalid file (caller traces it)."""
    path = config.content_dir() / "labels" / "segment_kinds.yaml"
    return SegmentLabels.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
