"""Capability registry per model family (AD-6).

A family is detected from `general.architecture` and the chat template. An
unknown family falls back to what the GGUF says. A GGUF without
`chat_template` is incompatible, with the reason.
"""

from __future__ import annotations

from dataclasses import dataclass

from wavestack.models.engine import EngineMetadata, partial_suffix_len

_THINK_TAGS = ("<think>", "</think>")


@dataclass(frozen=True)
class Capabilities:
    family: str
    chat_template: str | None
    tool_call_parser: str | None  # name only: the parser itself arrives with the tools story
    stop_sequences: tuple[str, ...]
    reasoning_variable: str | None
    native_context: int | None
    reasoning_tags: tuple[str, str] | None
    incompatible_reason: str | None = None


def capabilities_for(meta: EngineMetadata) -> Capabilities:
    arch = meta.architecture or ""
    template = meta.chat_template
    if not template:
        return Capabilities(
            family=arch or "unknown",
            chat_template=None,
            tool_call_parser=None,
            stop_sequences=(),
            reasoning_variable=None,
            native_context=meta.native_context,
            reasoning_tags=None,
            incompatible_reason=(
                "Ce fichier GGUF ne contient pas de gabarit de conversation "
                "(tokenizer.chat_template) : WaveStack ne peut pas construire le prompt. "
                "Choisissez un autre modèle."
            ),
        )
    reasoning_variable = "enable_thinking" if "enable_thinking" in template else None
    if arch.startswith("qwen3") and "<|im_start|>" in template:
        return Capabilities(
            family="qwen3",
            chat_template=template,
            tool_call_parser="qwen3_coder" if "<function=" in template else "hermes",
            stop_sequences=("<|im_end|>",),
            reasoning_variable=reasoning_variable,
            native_context=meta.native_context,
            reasoning_tags=_THINK_TAGS,
        )
    return Capabilities(
        family=arch or "unknown",
        chat_template=template,
        tool_call_parser=None,
        stop_sequences=(),
        reasoning_variable=reasoning_variable,
        native_context=meta.native_context,
        reasoning_tags=_THINK_TAGS if _THINK_TAGS[0] in template else None,
    )


class ChannelSplitter:
    """Incremental separator of the output stream into `reasoning` / `text` (AD-6).

    Tags are dropped from the channels (they stay in the raw output); a
    possibly partial tag at the end of a chunk is held back until the next one.
    """

    def __init__(self, tags: tuple[str, str] | None, *, in_reasoning: bool = False) -> None:
        self._tags = tags
        self._in_reasoning = in_reasoning
        self._buffer = ""

    @property
    def channel(self) -> str:
        return "reasoning" if self._in_reasoning else "text"

    def feed(self, text: str) -> list[tuple[str, str]]:
        if self._tags is None:
            return [("text", text)] if text else []
        self._buffer += text
        out: list[tuple[str, str]] = []
        while True:
            tag = self._tags[1] if self._in_reasoning else self._tags[0]
            at = self._buffer.find(tag)
            if at < 0:
                break
            if at:
                out.append((self.channel, self._buffer[:at]))
            self._buffer = self._buffer[at + len(tag) :]
            self._in_reasoning = not self._in_reasoning
        keep = partial_suffix_len(self._buffer, [tag])
        if len(self._buffer) > keep:
            out.append((self.channel, self._buffer[: len(self._buffer) - keep]))
            self._buffer = self._buffer[len(self._buffer) - keep :]
        return out

    def flush(self) -> list[tuple[str, str]]:
        out = [(self.channel, self._buffer)] if self._buffer else []
        self._buffer = ""
        return out
