"""What a harness tool asks the session to apply: it never writes state itself (AD-23)."""

from __future__ import annotations

from typing import Literal, NamedTuple

from pydantic import BaseModel


class ToolDocLoaded(BaseModel):
    """`load_tool_doc` loaded `tool`'s documentation (AD-25)."""

    kind: Literal["tool_doc_loaded"] = "tool_doc_loaded"
    tool: str


class SkillLoaded(BaseModel):
    """`load_skill` loaded the skill `skill_id` (AD-25)."""

    kind: Literal["skill_loaded"] = "skill_loaded"
    skill_id: str


# Each new harness tool adds its own effect here (AD-23), discriminated by `kind`.
Effect = ToolDocLoaded | SkillLoaded


class ToolReply(NamedTuple):
    """A tool's reply that carries effects besides the text reinjected to the model."""

    text: str
    effects: tuple[Effect, ...] = ()
