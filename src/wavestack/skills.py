"""The skills of the `skills` brick: one `content/skills/{id}/SKILL.md` each (AD-19)."""

from __future__ import annotations

import re
from collections.abc import Iterable

import yaml
from pydantic import BaseModel, Field

from wavestack import config

_FRONT_MATTER = re.compile(r"---\n(.*?)\n---\n(.*)", re.DOTALL)


class SkillText(BaseModel):
    name: str = Field(min_length=1)  # the id, the one `load_skill` receives
    label_fr: str = Field(min_length=1)
    description: str = Field(min_length=1)  # seen by the model, in the catalog
    body: str = Field(min_length=1)  # seen by the model once loaded


class LoadSkillText(BaseModel):
    """The harness meta-tool of the brick (AD-25)."""

    label_fr: str = Field(min_length=1)
    description: str = Field(min_length=1)  # seen by the model, short and fixed
    skill: str = Field(min_length=1)  # the `skill` parameter's description


class SkillsContent(BaseModel):
    """`content/skills.yaml`, plus the `SKILL.md` of each declared skill."""

    catalog_intro: str = Field(min_length=1)
    load_skill: LoadSkillText
    skills: dict[str, SkillText] = {}


def load_skills_content(ids: Iterable[str]) -> SkillsContent:
    """Raises on a missing or invalid file (the session traces it)."""
    root = config.content_dir()
    content = SkillsContent.model_validate(
        yaml.safe_load((root / "skills.yaml").read_text(encoding="utf-8"))
    )
    for skill_id in ids:
        path = root / "skills" / skill_id / "SKILL.md"
        match = _FRONT_MATTER.fullmatch(path.read_text(encoding="utf-8-sig"))
        if match is None:
            raise ValueError(f"{path}: en-tête YAML entre deux lignes « --- » attendu")
        skill = SkillText.model_validate(
            {**(yaml.safe_load(match[1]) or {}), "body": match[2].strip()}
        )
        if skill.name != skill_id:
            raise ValueError(f"{path}: `name` vaut {skill.name!r}, attendu {skill_id!r}")
        content.skills[skill_id] = skill
    return content
