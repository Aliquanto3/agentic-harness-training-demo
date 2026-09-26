"""The training programme and its scenarios, from `content/scenarios.yaml` (AD-19, FR-38).

A scenario declares its whole configuration, not a difference from the previous one:
launching it applies the launch configuration, then its own.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from wavestack import config


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_fr: str = Field(min_length=1)
    description_fr: str = Field(min_length=1)
    bricks: list[str] = []
    # Sub-options enabled; `None` (absent) keeps the launch values.
    tools: list[str] | None = None
    mcp_servers: list[str] | None = None
    skills: list[str] | None = None
    hooks: list[str] | None = None
    mcp_lazy: bool = False
    rag_rerank: bool = False  # story 16: the RAG brick's reranking sub-option
    prompts: list[str] = Field(min_length=1)


class Module(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_fr: str = Field(min_length=1)
    duration_min: int = Field(ge=30, le=60)
    scenarios: list[str] = Field(min_length=1)


class ScenariosContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: list[Module]
    transverse: list[str] = []
    scenarios: dict[str, Scenario]

    def payload(self, fill: Callable[[str], str] = str) -> dict[str, Any]:
        """`scenario_changed.program`: modules then transverse, scenarios inlined; `fill`
        completes a description with the configuration's values (story 16: `{candidates}`,
        `{keep}`)."""

        def entry(scenario_id: str) -> dict[str, Any]:
            s = self.scenarios[scenario_id]
            return {
                "id": scenario_id,
                "title_fr": s.title_fr,
                "description_fr": fill(s.description_fr),
                "prompts": s.prompts,
            }

        return {
            "modules": [
                {
                    "title_fr": m.title_fr,
                    "duration_min": m.duration_min,
                    "scenarios": [entry(i) for i in m.scenarios],
                }
                for m in self.program
            ],
            "transverse": [entry(i) for i in self.transverse],
        }


EMPTY_PROGRAM: dict[str, Any] = {"modules": [], "transverse": []}


def load_scenarios(known: dict[str, set[str]]) -> ScenariosContent:
    """`known` maps `bricks`, `tools`, `mcp_servers`, `skills` and `hooks` to their ids.
    Raises on a missing or invalid file, or any unknown id."""
    path = config.content_dir() / "scenarios.yaml"
    content = ScenariosContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    unknown = []
    for scenario_id, scenario in content.scenarios.items():
        for field, ids in known.items():
            wanted = getattr(scenario, field) or []
            unknown += [f"{scenario_id}.{field}: {i}" for i in wanted if i not in ids]
    referenced = [i for m in content.program for i in m.scenarios] + content.transverse
    unknown += [f"programme : {i}" for i in referenced if i not in content.scenarios]
    if unknown:
        raise ValueError(f"{path}: unknown ids {unknown}")
    return content
