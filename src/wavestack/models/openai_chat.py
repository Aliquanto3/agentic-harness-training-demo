"""`openai_chat` adapter (AD-5): `POST {base_url}/chat/completions`, streamed.

The Chat Completions API (Groq, Mistral, Gemini, Gemma…), whose message format is also the
pivot the session keeps its history in (AD-26). What every adapter shares (the headers, the
refusals of AD-16, the masking, the spacing, FinOps, `run_call`) is in `cloud_base`; its
names stay importable from here. This module reads the stream: `content`, the reasoning in
its three forms (`reasoning`/`reasoning_content`, Mistral's `thinking` blocks, the
`think_tags`), and the `tool_calls` fragments.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from wavestack.messages import Message
from wavestack.models.capabilities import ChannelSplitter
from wavestack.models.cloud_base import (
    _BACK_TO_LOCAL_FR,
    DELTA_INTERVAL_S,
    PROVIDER_MESSAGE_MAX,
    CallCost,
    ChatBody,
    ChatCall,
    ChatEnd,
    CloudEngine,
    ProviderError,
    _clip,
    _last_start,
    _quota_scope,
    call_cost,
    mask_key,
    output_tokens,
    output_tps,
    pace,
    record_spend,
    reset_spend,
    run_call,
    session_spend,
)
from wavestack.models.engine import CancelToken

# Compatibility: the names callers and tests imported from here before the common base
# (`_last_start` is the very registry `pace` reads, not a copy).
__all__ = [
    "CallCost",
    "ChatBody",
    "ChatCall",
    "ChatEnd",
    "CloudEngine",
    "DELTA_INTERVAL_S",
    "OpenAIChatEngine",
    "PROVIDER_MESSAGE_MAX",
    "ProviderError",
    "_last_start",
    "_quota_scope",
    "call_cost",
    "mask_key",
    "output_tokens",
    "output_tps",
    "pace",
    "record_spend",
    "reset_spend",
    "run_call",
    "session_spend",
]

# Mistral ends a cut output with `model_length`.
_FINISH = {"stop": "stop", "tool_calls": "stop", "length": "length", "model_length": "length"}


def _is_thought(delta: dict[str, Any]) -> bool:
    """Gemini may mark a `content` delta as thought (`extra_content.google.thought`)."""
    extra = delta.get("extra_content")
    google = extra.get("google") if isinstance(extra, dict) else None
    return isinstance(google, dict) and google.get("thought") is True


class OpenAIChatEngine(CloudEngine):
    """The Chat Completions adapter: `POST {base_url}/chat/completions`, its SSE chunks read
    by `_read` and `_channels`."""

    api = "openai_chat"
    endpoint = "/chat/completions"

    def _read(
        self, response: httpx.Response, cancel: CancelToken
    ) -> Iterator[tuple[str, str] | ChatEnd]:
        entry = self.entry
        reasoning = entry.reasoning
        think = reasoning is not None and reasoning.format == "think_tags"
        splitter = ChannelSplitter(tuple(reasoning.tags)) if think else None
        calls: dict[Any, dict[str, Any]] = {}
        raw: list[str] = []
        usage = groq_usage = None
        stop = "stop"
        for line in response.iter_lines():
            if cancel.cancelled:
                stop = "cancelled"
                break  # leaving the `with` closes the stream (AD-5)
            if not line or line.startswith((":", "event:", "id:", "retry:")):
                continue
            data = line[5:].strip() if line.startswith("data:") else None
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data) if data is not None else None
            except ValueError:
                chunk = None
            if not isinstance(chunk, dict):
                raise self._error(
                    self._text("unreadable_stream", provider=entry.provider),
                    line[:300],
                    [
                        Message("models.openai_chat.hint.retry_turn"),
                        _BACK_TO_LOCAL_FR,
                    ],
                )
            if chunk.get("error"):
                error = chunk["error"] if isinstance(chunk["error"], dict) else {}
                said = str(error.get("message") or chunk["error"])
                if error.get("code") == "tool_use_failed":
                    generation = str(error.get("failed_generation") or said)
                    raw_output = self.mask("\n".join(raw))
                    message = _clip(self.mask(said)) or None
                    yield ChatEnd(
                        "stop",
                        [],
                        usage,
                        raw_output,
                        provider_error=self.mask(generation),
                        provider_message=message,
                    )
                    return
                raise self._error(
                    self._text("interrupted", provider=entry.provider),
                    said,
                    [
                        Message("models.openai_chat.hint.retry_turn"),
                        _BACK_TO_LOCAL_FR,
                    ],
                    provider_message=said,
                )
            usage = chunk.get("usage") or usage
            groq_usage = (chunk.get("x_groq") or {}).get("usage") or groq_usage
            choices = chunk.get("choices") or []
            if not choices:  # a usage-only chunk (Azure)
                continue
            choice = choices[0]
            delta = choice.get("delta") or {}
            raw.append(json.dumps(delta, ensure_ascii=False))
            for channel, text in self._channels(delta, splitter, calls):
                yield channel, self.mask(text)  # AD-15: every provider string is masked
            finish = choice.get("finish_reason")
            if finish:
                if finish not in _FINISH:
                    raise self._error(
                        self._text("stopped", provider=entry.provider, finish=finish),
                        f"finish_reason: {finish}",
                        [
                            Message("models.openai_chat.hint.rephrase"),
                            _BACK_TO_LOCAL_FR,
                        ],
                    )
                stop = _FINISH[finish]
        if splitter is not None:
            for channel, text in splitter.flush():
                yield channel, self.mask(text)
        # By `index` (then opening order) when every call has one; else (Gemini sends none,
        # calls keyed by `id`) in arrival order: ids do not sort (`call_99999` would follow
        # `call_100002`).
        indexed = all(isinstance(key, int) for key, _ in calls)
        ordered = [
            {
                k: self.mask(v) if isinstance(v, str) and k != "extra_content" else v
                for k, v in calls[key].items()
            }
            for key in (sorted(calls) if indexed else calls)
        ]
        yield ChatEnd(stop, ordered, usage or groq_usage, self.mask("\n".join(raw)))

    @staticmethod
    def _channels(
        delta: dict[str, Any], splitter: ChannelSplitter | None, calls: dict[Any, dict[str, Any]]
    ) -> Iterator[tuple[str, str]]:
        for name in ("reasoning", "reasoning_content"):
            if isinstance(delta.get(name), str) and delta[name]:
                yield "reasoning", delta[name]
        content = delta.get("content")
        # Gemini marks its thought chunks (`extra_content.google.thought`), tags included: with
        # `think_tags`, the tags decide (the closing one comes in an unmarked chunk); the mark
        # alone decides only without them.
        if isinstance(content, str) and content and splitter is None and _is_thought(delta):
            yield "reasoning", content
        elif isinstance(content, str) and content:
            yield from splitter.feed(content) if splitter else [("text", content)]
        elif isinstance(content, list):  # Mistral: `thinking` and `text` blocks
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text" and block.get("text"):
                    yield "text", str(block["text"])
                elif block.get("type") == "thinking":
                    thinking = block.get("thinking")
                    parts = thinking if isinstance(thinking, list) else [thinking]
                    for part in parts:
                        text = part.get("text") if isinstance(part, dict) else part
                        if isinstance(text, str) and text:
                            yield "reasoning", text
        for call in delta.get("tool_calls") or []:
            # Story 2 of the deferred leftovers (E048): keyed `(index or id, n)`. A fragment
            # that starts a call (a `function.name`) under another `id` than the call open on
            # its key opens a new call there: two parallel calls sent under the same `index`
            # stay two calls. Without a name, it continues the open call (a server that sends
            # a fresh `id` on each delta of one call).
            key = call.get("index", call.get("id"))
            n = max((k[1] for k in calls if k[0] == key), default=None)
            open_id = calls[(key, n)]["provider_id"] if n is not None else None
            named = bool((call.get("function") or {}).get("name"))
            if n is None or (named and call.get("id") and open_id and call["id"] != open_id):
                n = 0 if n is None else n + 1
            acc = calls.setdefault((key, n), {"provider_id": None, "name": "", "arguments": ""})
            if call.get("id"):
                acc["provider_id"] = call["id"]
            if isinstance(call.get("extra_content"), dict):  # Gemini 3.x: thought signature
                acc["extra_content"] = acc.get("extra_content", {}) | call["extra_content"]
            function = call.get("function") or {}
            text = (function.get("name") or "") + (function.get("arguments") or "")
            acc["name"] += function.get("name") or ""
            acc["arguments"] += function.get("arguments") or ""
            if text:
                yield "tool_call", text
