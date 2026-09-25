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


class AuditAppend(BaseModel):
    """H2 asks for `lines` to be appended to `audit.log` (story 8)."""

    kind: Literal["audit_append"] = "audit_append"
    lines: list[str]


class ArmConsumed(BaseModel):
    """A turn took the armed action `armed_id` at its sending: it leaves the list at the
    turn's end, whatever its status (AD-3, story 9)."""

    kind: Literal["arm_consumed"] = "arm_consumed"
    armed_id: str


# Each new harness tool or hook adds its own effect here (AD-23), discriminated by `kind`.
Effect = ToolDocLoaded | SkillLoaded | AuditAppend | ArmConsumed


class ToolReply(NamedTuple):
    """A tool's reply that carries effects besides the text reinjected to the model."""

    text: str
    effects: tuple[Effect, ...] = ()
