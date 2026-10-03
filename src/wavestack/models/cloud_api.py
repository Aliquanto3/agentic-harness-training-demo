"""The engine of a cloud model, chosen by its entry's `api` (AD-26, CAP-1).

One registry, `api → engine class`, read by every place that creates a cloud engine (the
application session, the diagnostic's « Tester »). The body's translator is chosen by the
same `api` in `context/render.py` (`context` alone writes the body, AD-4). An API enters
both registries with its adapter, and only then `CloudModel.api` accepts it.
"""

from __future__ import annotations

import httpx
from pydantic import SecretStr

from wavestack.config import CloudModel
from wavestack.models.anthropic_messages import AnthropicMessagesEngine
from wavestack.models.cloud_base import CloudEngine
from wavestack.models.openai_chat import OpenAIChatEngine

ENGINES: dict[str, type[CloudEngine]] = {
    OpenAIChatEngine.api: OpenAIChatEngine,
    AnthropicMessagesEngine.api: AnthropicMessagesEngine,  # native providers 3/5
}


def create_cloud_engine(
    entry: CloudModel,
    key: SecretStr,
    *,
    connect_timeout_s: float,
    read_timeout_s: float,
    transport: httpx.BaseTransport | None = None,
) -> CloudEngine:
    """The adapter of `entry.api`, its client from `net/factory.create_client`."""
    return ENGINES[entry.api](
        entry,
        key,
        transport=transport,
        connect_timeout_s=connect_timeout_s,
        read_timeout_s=read_timeout_s,
    )
