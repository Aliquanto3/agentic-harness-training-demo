"""What a harness tool asks the session to apply: it never writes state itself (AD-23)."""

from __future__ import annotations

from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, SecretStr

from wavestack import config
from wavestack.trace.journal import get_journal
from wavestack.trace.scope import scoped


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


class SettingWrite(BaseModel):
    """One top-level key of `settings.json`, never a secret (AD-23): `selected_model`..."""

    kind: Literal["setting_write"] = "setting_write"
    key: str
    value: Any


class ApiKeySet(BaseModel):
    """A cloud model's key, saved with the host it was typed for (AD-20, AD-23)."""

    kind: Literal["api_key_set"] = "api_key_set"
    id: str
    host: str
    key: SecretStr


# Each new harness tool or hook adds its own effect here (AD-23), discriminated by `kind`.
Effect = ToolDocLoaded | SkillLoaded | AuditAppend | ArmConsumed | SettingWrite | ApiKeySet


def apply_setting(effect: SettingWrite | ApiKeySet) -> None:
    """The single applier of the settings and key effects, for the diagnostic and the
    application sessions: written by `config`, then `effect_applied`. `ApiKeySet` shows
    only `{id, key_set}` (no component: the keys file is not drawn). Raises OSError."""
    if isinstance(effect, ApiKeySet):
        config.write_api_key(effect.id, effect.host, effect.key)
        payload = {"effect": "api_key_set", "id": effect.id, "key_set": True}
    else:
        config.save_setting(effect.key, effect.value)
        payload = {"effect": "setting_write", "key": effect.key}
    with scoped(component=None):
        get_journal().emit("effect_applied", payload)


class ToolReply(NamedTuple):
    """A tool's reply that carries effects besides the text reinjected to the model."""

    text: str
    effects: tuple[Effect, ...] = ()
