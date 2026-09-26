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
    tool_call_parser: str | None  # a format of `wavestack.tools.parser`
    stop_sequences: tuple[str, ...]
    reasoning_variable: str | None
    native_context: int | None
    reasoning_tags: tuple[str, str] | None
    incompatible_reason: str | None = None
    # AD-6: the model can reason on demand (a template variable, or a cloud declaration),
    # and, for a cloud model, reasons at every answer whatever the brick says.
    reasoning: bool = False
    reasoning_always: bool = False


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
    # AD-6: llama-server exposes no architecture; its template says the family then.
    by_template = meta.architecture is None and "<tool_call>" in template
    if (arch.startswith("qwen3") or by_template) and "<|im_start|>" in template:
        return Capabilities(
            family="qwen3",
            chat_template=template,
            tool_call_parser="qwen3_coder" if "<function=" in template else "hermes",
            stop_sequences=("<|im_end|>",),
            reasoning_variable=reasoning_variable,
            native_context=meta.native_context,
            reasoning_tags=_THINK_TAGS,
            reasoning=reasoning_variable is not None,
        )
    return Capabilities(
        family=arch or "unknown",
        chat_template=template,
        tool_call_parser=None,
        stop_sequences=(),
        reasoning_variable=reasoning_variable,
        native_context=meta.native_context,
        reasoning_tags=_THINK_TAGS if _THINK_TAGS[0] in template else None,
        reasoning=reasoning_variable is not None,
    )


TOOL_CALL_TAGS = ("<tool_call>", "</tool_call>")  # shared by `qwen3_coder` and `hermes`


class ChannelSplitter:
    """Incremental separator of the output stream into `reasoning` / `text` / `tool_call` (AD-6).

    Tags are dropped from the channels (they stay in the raw output); a
    possibly partial tag at the end of a chunk is held back until the next one.
    `outside` is the raw output without the reasoning and its tags, tool-call tags kept:
    where tool calls count (AD-6).
    """

    def __init__(
        self,
        tags: tuple[str, str] | None,
        *,
        in_reasoning: bool = False,
        tool_tags: tuple[str, str] | None = None,
    ) -> None:
        self._pairs = {
            channel: pair
            for channel, pair in (("reasoning", tags), ("tool_call", tool_tags))
            if pair is not None
        }
        self._channel = "reasoning" if in_reasoning else "text"
        self._buffer = ""
        self._outside: list[str] = []

    @property
    def outside(self) -> str:
        return "".join(self._outside)

    def _emit(self, out: list[tuple[str, str]], text: str) -> None:
        out.append((self._channel, text))
        if self._channel != "reasoning":
            self._outside.append(text)

    @property
    def channel(self) -> str:
        return self._channel

    def feed(self, text: str) -> list[tuple[str, str]]:
        self._buffer += text
        out: list[tuple[str, str]] = []
        while True:
            if self._channel == "text":  # the earliest opening tag wins
                markers = [pair[0] for pair in self._pairs.values()]
                hits = [
                    (at, channel, pair[0])
                    for channel, pair in self._pairs.items()
                    if (at := self._buffer.find(pair[0])) >= 0
                ]
                if not hits:
                    break
                at, following, tag = min(hits)
            else:
                tag = self._pairs[self._channel][1]
                markers = [tag]
                at, following = self._buffer.find(tag), "text"
                if at < 0:
                    break
            if at:
                self._emit(out, self._buffer[:at])
            if "reasoning" not in (self._channel, following):  # a tool-call tag stays
                self._outside.append(tag)
            self._buffer = self._buffer[at + len(tag) :]
            self._channel = following
        keep = partial_suffix_len(self._buffer, markers)
        if len(self._buffer) > keep:
            self._emit(out, self._buffer[: len(self._buffer) - keep])
            self._buffer = self._buffer[len(self._buffer) - keep :]
        return out

    def flush(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if self._buffer:
            self._emit(out, self._buffer)
        self._buffer = ""
        return out
