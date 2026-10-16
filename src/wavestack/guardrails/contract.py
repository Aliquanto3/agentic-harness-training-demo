"""The common interface every guardrail shares (CAP-5): one `classify`, one `Verdict`.

A guardrail never decides on its own what a verdict means for the turn: the
`GuardrailsManager` reads `GuardrailMode` and decides to block, flag or mask. This keeps a
new guardrail (textdetox instead of gravitee, Prompt Guard later) a drop-in replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

GuardrailId = Literal["toxicity", "pii", "injection"]
Direction = Literal["input", "output"]
# "flag" masks personal data instead of merely annotating it (CAP-5: "signaler" → "masquer").
GuardrailMode = Literal["block", "flag", "off"]
GuardrailStatus = Literal["active", "off", "not_installed", "loading", "error"]


@dataclass(frozen=True)
class Entity:
    """One thing a guardrail found in the text (pii: a NIR, an email... toxicity: none)."""

    label: str
    start: int
    end: int
    score: float


@dataclass(frozen=True)
class Classification:
    """What a guardrail's `classify` returns: whether it triggered, its confidence, and the
    entities found (empty for toxicity, the PII spans for the personal-data guardrail)."""

    detected: bool
    score: float
    threshold: float
    entities: tuple[Entity, ...] = ()
    # Story 5: only part of the text was scored (toxicity's window budget, `_MAX_WINDOWS`).
    partial: bool = False


class Classifier(Protocol):
    """What `ToxicityGuardrail` and `PiiGuardrail` both implement; a test fake needs only
    this, never a real model (story 4: no pytest downloads one)."""

    def classify(self, text: str) -> Classification: ...

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        """Entities replaced by `[LABEL]`; toxicity has none to mask, so `text` unchanged."""
        ...

    def unload(self) -> None: ...


@dataclass(frozen=True)
class Verdict:
    """What the manager reports for one guardrail, one direction, one turn (CAP-5): shown
    in Vue humain (verdict-banner) and in Orchestration (the same shape as `hook_decided`,
    story 4's reuse of the hooks brick's event)."""

    guardrail: GuardrailId
    direction: Direction
    mode: GuardrailMode
    status: GuardrailStatus
    detected: bool = False
    score: float | None = None
    threshold: float | None = None
    entities: tuple[str, ...] = field(default_factory=tuple)
    masked_text: str | None = None
    detail_text: str = ""
    partial: bool = False

    @property
    def blocks(self) -> bool:
        return self.mode == "block" and self.detected

    @property
    def masks(self) -> bool:
        return self.mode == "flag" and self.detected and self.masked_text is not None
