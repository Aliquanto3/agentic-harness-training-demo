"""What a harness tool asks the session to apply: it never writes state itself (AD-23)."""

from __future__ import annotations

from typing import Literal, NamedTuple

from pydantic import BaseModel


class ToolDocLoaded(BaseModel):
    """`load_tool_doc` loaded `tool`'s documentation (AD-25)."""

    kind: Literal["tool_doc_loaded"] = "tool_doc_loaded"
    tool: str


# A one-member union today; each new harness tool adds its own effect here (AD-23).
Effect = ToolDocLoaded


class ToolReply(NamedTuple):
    """A tool's reply that carries effects besides the text reinjected to the model."""

    text: str
    effects: tuple[Effect, ...] = ()
