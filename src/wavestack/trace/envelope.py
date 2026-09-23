"""The AD-2 event envelope, shared by every module that emits.

A story adds `kind` values to the catalog; it never changes this envelope.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, field_validator

from wavestack.trace.catalog import PAYLOAD_MODELS, Actor, Trigger


class Envelope(BaseModel):
    seq: int
    ts: datetime
    session_epoch: int
    turn_id: str | None = None
    context_id: str | None = None
    call_id: str | None = None
    step_id: str | None = None
    parent_step: str | None = None
    kind: str
    actor: Actor
    trigger: Trigger
    brick: str | None = None
    component: str | None = None
    edge: str | None = None
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def _validate_payload_against_catalog(
        cls, payload: dict[str, Any], info: Any
    ) -> dict[str, Any]:
        kind = info.data.get("kind")
        model = PAYLOAD_MODELS.get(kind)
        if model is not None:
            model.model_validate(payload)
        return payload


def now_iso() -> datetime:
    return datetime.now(UTC)
