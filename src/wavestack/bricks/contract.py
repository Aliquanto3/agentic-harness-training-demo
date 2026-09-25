"""The brick contract (AD-12) and its content loaders (AD-19)."""

from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from wavestack import config

Category = Literal["prompt", "context", "harness"]
Hosting = Literal["local_process", "local_file", "network_service"]


class Component(BaseModel):
    id: str  # "{brick}.{component}"
    kind: str
    hosting: Hosting
    edges_to: list[str] = []


class BrickDeclaration(BaseModel):
    id: str
    category: Category
    requires: list[str] = []  # brick ids that must be effective
    capabilities: list[str] = []  # truthy `Capabilities` fields the model must offer (AD-6)
    network: bool = False
    contributes_to: list[str] = ["main"]
    components: list[Component]

    @model_validator(mode="after")
    def _component_ids_are_prefixed(self) -> BrickDeclaration:
        for component in self.components:
            if not component.id.startswith(f"{self.id}."):
                raise ValueError(f"component {component.id!r} must start with {self.id!r}.")
        return self


class BrickContent(BaseModel):
    """`content/bricks/{id}.yaml`: what the brick card says, in French."""

    label_fr: str = Field(min_length=1)
    category_fr: str = Field(min_length=1)
    hosting_fr: str = Field(min_length=1)
    # Each item is a paragraph (`str`, rendered `<p>`) or a bullet list (`list[str]`, `<ul><li>`).
    explanation_fr: list[str | list[str]] = Field(min_length=1)


class SystemPromptContent(BaseModel):
    text: str = Field(min_length=1)


def load_brick_content(brick_id: str) -> BrickContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_dir() / "bricks" / f"{brick_id}.yaml"
    return BrickContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def load_default_system_prompt() -> str:
    """Raises on a missing or blank `content/prompts/system.md`."""
    path = config.content_dir() / "prompts" / "system.md"
    return SystemPromptContent(text=path.read_text(encoding="utf-8-sig").strip()).text
