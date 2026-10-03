"""Texts of the cloud models (AD-19, `content/cloud.yaml` and its translations) and what the session
builds from a declaration: the warning, the disclosure, `active_model` (AD-12, AD-20)."""

from __future__ import annotations

from functools import cache
from typing import Any

import yaml
from pydantic import BaseModel

from wavestack import config
from wavestack.config import CloudModel
from wavestack.messages import msg
from wavestack.models.engine import Sampling


class WarningText(BaseModel):
    title_text: str
    sent_text: str
    provider_text: str
    unseen_text: str
    confirm_text: str
    cancel_text: str


class CloudTestTool(BaseModel):
    name: str
    description: str


class CloudTestText(BaseModel):
    prompt: str
    tool: CloudTestTool
    tool_reply: str


class CloudContent(BaseModel):
    warning: WarningText
    training_text: dict[str, str]
    trial_text: str
    key_hint_text: str
    no_key_text: str
    host_changed_text: str
    test_hint_text: str
    banner_text: str
    provider_segment_text: str
    uncertain_text: str
    test: CloudTestText


@cache
def load_cloud_content(lang: str = config.DEFAULT_LANGUAGE) -> CloudContent:
    """Read `content/cloud.yaml` in `lang` (languages 3/5: the session's, never
    `settings.json`'s; one cache entry per language). Raises on an invalid file (the caller
    traces it)."""
    path = config.content_file("cloud.yaml", lang)
    return CloudContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def fill(text: str, entry: CloudModel, content: CloudContent) -> str:
    return text.format(
        fournisseur=entry.provider,
        hebergement=entry.hosting_text,
        entrainement=content.training_text.get(entry.training, entry.training),
        essai=content.trial_text if entry.trial else "",
        modele=entry.model,
    )


def warning_fr(entry: CloudModel, content: CloudContent) -> dict[str, str]:
    """The `cloud-warning` of EXPERIENCE.md: common text, provider part from the entry."""
    w = content.warning
    points = [fill(t, entry, content) for t in (w.sent_text, w.provider_text, w.unseen_text)]
    if entry.notes_text:
        points[1] += f" {entry.notes_text}"
    return {
        "title_text": w.title_text,
        "sent_text": points[0],
        "provider_text": points[1],
        "unseen_text": points[2],
        "confirm_text": w.confirm_text,
        "cancel_text": w.cancel_text,
    }


def chat_fields(
    entry: CloudModel,
    max_tokens: int,
    reasoning: bool = False,
    sampling: Sampling | None = None,
) -> dict[str, Any]:
    """AD-4, chat mode: the body's fields besides `messages` and `tools`, in their order:
    `model`, `stream`, the output limit, story 29's sampling (only when `sampling` is given,
    by the « LLM nu » screen, and only the fields the entry declares), `stream_options`, the
    reasoning parameters (`on` while the reasoning brick is effective or the model always
    reasons, else `off`). The workshop's bodies stay byte for byte what they were."""
    fields: dict[str, Any] = {"model": entry.model, "stream": True}
    fields[entry.max_tokens_field] = max_tokens
    if sampling is not None:  # native providers 3/5: none to Anthropic while it thinks
        for name in entry.sampling_sent(reasoning):
            fields[name] = getattr(sampling, name)
    if entry.stream_usage:
        fields["stream_options"] = {"include_usage": True}
    return {**fields, **entry.reasoning_params(reasoning)}


def usd_price_fr(value: float, lang: str = "fr") -> str:
    """FinOps: a price per million tokens, 2 decimals at least: « 0,30 $ » (French and
    German), « $0.30 » (English)."""
    text = f"{value:.4f}".rstrip("0")
    whole, _, decimals = text.partition(".")
    if lang == "en":
        return f"${whole}.{decimals.ljust(2, '0')}"
    return f"{whole},{decimals.ljust(2, '0')} $"


def price_fr(entry: CloudModel, lang: str = "fr") -> str | None:
    """FinOps: « 0,30 $ / 2,50 $ » (input / output, per million tokens); `None` without
    declared prices."""
    pricing = entry.pricing
    if pricing is None:
        return None
    return (
        f"{usd_price_fr(pricing.input_usd_per_mtok, lang)} / "
        f"{usd_price_fr(pricing.output_usd_per_mtok, lang)}"
    )


def price_reason_fr(entry: CloudModel, lang: str = "fr") -> str | None:
    """FinOps: what the price means and when it was read, in `lang`."""
    pricing = entry.pricing
    if pricing is None:
        return None
    checked = f"{pricing.checked:%d.%m.%Y}" if lang == "de" else f"{pricing.checked:%d/%m/%Y}"
    return msg("cloud.price.reason", lang, checked=checked)


def price_line_fr(entry: CloudModel, lang: str = "fr") -> str | None:
    """FinOps, the diagnostic's « Prix » line; `None` without declared prices."""
    price = price_fr(entry, lang)
    if not price:
        return None
    return msg("cloud.price.line", lang, price=price, reason=price_reason_fr(entry, lang))


def disclosure(entry: CloudModel) -> dict[str, Any]:
    """AD-20: `active_model.disclosure` of a cloud model."""
    return {
        "hosting_text": entry.hosting_text,
        "training": entry.training,
        "trial": entry.trial,
        "notes_text": entry.notes_text,
    }


def _readable_content(lang: str) -> CloudContent | None:
    try:
        return load_cloud_content(lang)
    except Exception:  # noqa: BLE001 - the caller traced it at boot; the indicator stays bare
        return None


def active_model(entry: CloudModel, lang: str = config.DEFAULT_LANGUAGE) -> dict[str, Any]:
    """AD-12: the model indicator's only source; its tooltip is the warning's text, in
    `lang` (the session's), in French when that translation cannot be read."""
    content = _readable_content(lang) or _readable_content(config.DEFAULT_LANGUAGE)
    warning = warning_fr(entry, content) if content else None
    return {
        "id": entry.id,
        "label": entry.model,
        "hosting": "network",
        "kind": "cloud",
        "ref": entry.id,
        "provider": entry.provider,
        "disclosure": disclosure(entry),
        "warning_text": (
            " ".join(
                [
                    warning["title_text"] + ".",
                    *(warning[k] for k in ("sent_text", "provider_text", "unseen_text")),
                ]
            )
            if warning
            else None
        ),
        "banner_text": fill(content.banner_text, entry, content) if content else None,
    }
