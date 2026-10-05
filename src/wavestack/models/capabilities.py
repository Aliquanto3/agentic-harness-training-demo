"""Capability registry per model family (AD-6).

A family is detected from `general.architecture` and the chat template. An
unknown family falls back to what the GGUF says. A GGUF without
`chat_template` is incompatible, with the reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Literal

from wavestack.config import MAX_RESERVE
from wavestack.messages import Lazy, Message, number
from wavestack.models.engine import EngineMetadata, is_pooled, partial_suffix_len

if TYPE_CHECKING:
    from wavestack.config import CloudModel

_THINK_TAGS = ("<think>", "</think>")
CLOUD_FAMILY = "openai_chat"  # a cloud model: capabilities declared, no template (AD-6)
# AD-6: why a local model offers no tool call; the brick cards and the model table (story 25).
# Languages (5/5): the texts of this module are `Message`s, French as a text, rendered by
# the session in its language.
NO_TOOL_PARSER_FR = Message("models.capabilities.no_tool_parser")
# Lot 5c-1: a GGUF with `{arch}.pooling_type` is an embedding or reranking model, no chat model.
POOLING_FR = Message("models.capabilities.pooling")


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
    if is_pooled(meta.pooling_type):
        # Lot 5c-1: an embedding or reranking model (Qwen3-Embedding, Qwen3-Reranker) has a
        # chat template too; `{arch}.pooling_type` says what it is: never a chat model.
        return Capabilities(
            family=arch or "unknown",
            chat_template=None,
            tool_call_parser=None,
            stop_sequences=(),
            reasoning_variable=None,
            native_context=meta.native_context,
            reasoning_tags=None,
            incompatible_reason=POOLING_FR,
        )
    if not template:
        return Capabilities(
            family=arch or "unknown",
            chat_template=None,
            tool_call_parser=None,
            stop_sequences=(),
            reasoning_variable=None,
            native_context=meta.native_context,
            reasoning_tags=None,
            incompatible_reason=Message("models.capabilities.no_template"),
        )
    reasoning_variable = "enable_thinking" if "enable_thinking" in template else None
    # AD-6: llama-server exposes no architecture; its template says the family then: ChatML
    # with `<tool_call>` and Qwen3's reasoning (`enable_thinking` or `<think>`). A ChatML
    # template with tool calls only (Qwen2.5, Hermes) is not Qwen3.
    by_template = (
        meta.architecture is None
        and "<tool_call>" in template
        and ("enable_thinking" in template or "<think>" in template)
    )
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


def cloud_capabilities(entry: CloudModel) -> Capabilities:
    """AD-6: a cloud model's declared capabilities; the API's structured format parses the
    tool calls. A capability not declared is absent. Shared by the session's load and the
    model table (story 25)."""
    return Capabilities(
        family=CLOUD_FAMILY,
        chat_template=None,
        tool_call_parser="openai_chat" if entry.tools else None,
        stop_sequences=(),
        reasoning_variable=None,
        native_context=entry.context,
        reasoning_tags=None,
        reasoning=entry.reasoning is not None,
        reasoning_always=entry.always_reasons,
    )


ReasoningMode = Literal["never", "always", "toggle", "unknown"]
_NOT_READ = Message("models.capabilities.why.not_read")
REASONING_FR: dict[str, str] = {
    mode: Message(f"models.capabilities.reasoning.{mode}")
    for mode in ("never", "always", "toggle", "unknown")
}


def reasoning_window_fr(window: int) -> str | None:
    """AD-9: why the reasoning brick is unavailable in `window` (no room left once the
    reasoning's output reserve is kept), else `None`. The card (`AppSession`) and the model
    table (story 25) share it."""
    if window > MAX_RESERVE:
        return None
    return Message(
        "models.capabilities.window_too_small",
        window=_int(window),
        reserve=_int(MAX_RESERVE),
    )


def _int(n: int) -> Lazy:
    """`n` in the language its message is rendered in (French: a narrow no-break space)."""
    return Lazy(partial(number, n))


def reasoning_mode(
    caps: Capabilities | None, window: int | None = None
) -> tuple[ReasoningMode, str | None]:
    """Story 25: how the model reasons, by the reasoning card's own rules (AD-6, AD-9), and
    why in French: `toggle` exactly when the card can be switched on (a reasoning the model
    offers, in a `window` larger than the reasoning reserve), `always` when the model
    reasons whatever the brick says, `unknown` when nothing says it (no capabilities read,
    an incompatible model, or `<think>` tags without a variable), `never` otherwise."""
    if caps is None:
        return "unknown", _NOT_READ
    if caps.incompatible_reason:
        return "unknown", caps.incompatible_reason
    cloud = caps.family == CLOUD_FAMILY
    if caps.reasoning_always:
        return "always", Message("models.capabilities.why.always")
    if caps.reasoning and window is not None and (too_small := reasoning_window_fr(window)):
        return "never", too_small
    if caps.reasoning:
        return "toggle", (
            Message("models.capabilities.why.declared_reasoning")
            if cloud
            else Message("models.capabilities.why.template_variable", name=caps.reasoning_variable)
        )
    if caps.reasoning_tags:
        return "unknown", Message("models.capabilities.why.maybe")
    if cloud:
        return "never", Message("models.capabilities.why.undeclared_reasoning")
    return "never", Message("models.capabilities.why.no_variable")


def tools_summary(caps: Capabilities | None) -> tuple[bool | None, str, str | None]:
    """Story 25: whether the model calls tools, as the tool cards decide it (a known parser,
    AD-6): `(tools, word in French, reason)`; `None` when nothing says it."""
    unknown = Message("models.capabilities.tools.unknown")
    if caps is None:
        return None, unknown, _NOT_READ
    if caps.incompatible_reason:
        return None, unknown, caps.incompatible_reason
    cloud = caps.family == CLOUD_FAMILY
    if caps.tool_call_parser:
        return (
            True,
            Message("models.capabilities.tools.declared")
            if cloud
            else Message("models.capabilities.tools.parser", parser=caps.tool_call_parser),
            None,
        )
    no = Message("models.capabilities.tools.no")
    if cloud:
        return False, no, Message("models.capabilities.why.undeclared_tools")
    return False, no, NO_TOOL_PARSER_FR


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

    @property
    def holding(self) -> bool:
        """A possibly partial tag is held back: the channel may be about to change."""
        return bool(self._buffer)

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
