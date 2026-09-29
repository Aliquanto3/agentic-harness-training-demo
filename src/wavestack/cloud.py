"""French texts of the cloud models (AD-19, `content/cloud.yaml`) and what the session
builds from a declaration: the warning, the disclosure, `active_model` (AD-12, AD-20)."""

from __future__ import annotations

from functools import cache
from typing import Any

import yaml
from pydantic import BaseModel

from wavestack import config
from wavestack.config import CloudModel


class WarningText(BaseModel):
    title_fr: str
    sent_fr: str
    provider_fr: str
    unseen_fr: str
    confirm_fr: str
    cancel_fr: str


class CloudTestTool(BaseModel):
    name: str
    description: str


class CloudTestText(BaseModel):
    prompt: str
    tool: CloudTestTool
    tool_reply: str


class CloudContent(BaseModel):
    warning: WarningText
    training_fr: dict[str, str]
    trial_fr: str
    key_hint_fr: str
    no_key_fr: str
    host_changed_fr: str
    test_hint_fr: str
    banner_fr: str
    provider_segment_fr: str
    uncertain_fr: str
    test: CloudTestText


@cache
def load_cloud_content() -> CloudContent:
    """Read `content/cloud.yaml`. Raises on an invalid file (the caller traces it)."""
    path = config.content_dir() / "cloud.yaml"
    return CloudContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def fill(text: str, entry: CloudModel, content: CloudContent) -> str:
    return text.format(
        fournisseur=entry.provider,
        hebergement=entry.hosting_fr,
        entrainement=content.training_fr.get(entry.training, entry.training),
        essai=content.trial_fr if entry.trial else "",
        modele=entry.model,
    )


def warning_fr(entry: CloudModel, content: CloudContent) -> dict[str, str]:
    """The `cloud-warning` of EXPERIENCE.md: common text, provider part from the entry."""
    w = content.warning
    points = [fill(t, entry, content) for t in (w.sent_fr, w.provider_fr, w.unseen_fr)]
    if entry.notes_fr:
        points[1] += f" {entry.notes_fr}"
    return {
        "title_fr": w.title_fr,
        "sent_fr": points[0],
        "provider_fr": points[1],
        "unseen_fr": points[2],
        "confirm_fr": w.confirm_fr,
        "cancel_fr": w.cancel_fr,
    }


def chat_fields(entry: CloudModel, max_tokens: int, reasoning: bool = False) -> dict[str, Any]:
    """AD-4, chat mode: the body's fields besides `messages` and `tools`, in their order:
    `model`, `stream`, the output limit, `stream_options`, the reasoning parameters (`on`
    while the reasoning brick is effective or the model always reasons, else `off`)."""
    fields: dict[str, Any] = {"model": entry.model, "stream": True}
    fields[entry.max_tokens_field] = max_tokens
    if entry.stream_usage:
        fields["stream_options"] = {"include_usage": True}
    return {**fields, **entry.reasoning_params(reasoning)}


def disclosure(entry: CloudModel) -> dict[str, Any]:
    """AD-20: `active_model.disclosure` of a cloud model."""
    return {
        "hosting_fr": entry.hosting_fr,
        "training": entry.training,
        "trial": entry.trial,
        "notes_fr": entry.notes_fr,
    }


def active_model(entry: CloudModel) -> dict[str, Any]:
    """AD-12: the model indicator's only source; its tooltip is the warning's text."""
    try:
        content = load_cloud_content()
    except Exception:  # noqa: BLE001 - the caller traced it at boot; the indicator stays bare
        content = None
    warning = warning_fr(entry, content) if content else None
    return {
        "id": entry.id,
        "label": entry.model,
        "hosting": "network",
        "kind": "cloud",
        "ref": entry.id,
        "provider": entry.provider,
        "disclosure": disclosure(entry),
        "warning_fr": (
            " ".join(
                [
                    warning["title_fr"] + ".",
                    *(warning[k] for k in ("sent_fr", "provider_fr", "unseen_fr")),
                ]
            )
            if warning
            else None
        ),
        "banner_fr": fill(content.banner_fr, entry, content) if content else None,
    }
