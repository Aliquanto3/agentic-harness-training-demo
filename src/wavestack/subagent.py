"""The texts of the `subagent` brick (story 19, AD-11, AD-19): `content/subagent.yaml` for the
harness's words, `content/prompts/subagent.md` for the sub-agent's system prompt."""

from __future__ import annotations

import yaml
from pydantic import BaseModel, Field, model_validator

from wavestack import config
from wavestack.tools.registry import ToolPreset


class DelegateText(BaseModel):
    """The harness meta-tool `delegate` (AD-25): what the model reads."""

    description: str = Field(min_length=1)
    task: str = Field(min_length=1)  # the `task` parameter's description


class SubagentContent(BaseModel):
    delegate: DelegateText
    phase_label_fr: str = Field(min_length=1)  # « Appel au sous-agent »
    force_label_fr: str = Field(min_length=1)  # « Déléguer au sous-agent »
    task_label_fr: str = Field(min_length=1)  # the forced form's field help, for the user
    presets: list[ToolPreset] = []
    overflow_cause_fr: str = Field(min_length=1)
    prompt: str = Field(min_length=1)  # content/prompts/subagent.md

    @model_validator(mode="after")
    def _presets_fill_the_task(self) -> SubagentContent:
        for preset in self.presets:
            if set(preset.args) != {"task"} or not str(preset.args["task"]).strip():
                raise ValueError(f"preset {preset.label_fr!r}: `task` only, not empty")
        return self


def load_subagent_content() -> SubagentContent:
    """Raises on a missing or invalid file (the session traces it)."""
    root = config.content_dir()
    data = yaml.safe_load((root / "subagent.yaml").read_text(encoding="utf-8")) or {}
    prompt = (root / "prompts" / "subagent.md").read_text(encoding="utf-8-sig").strip()
    return SubagentContent.model_validate({**data, "prompt": prompt})
