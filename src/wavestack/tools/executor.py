"""The single tool executor (AD-14): validation, execution, events. Never raises (AD-16).

The session sets the trace scope (call, step, component) before each call.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any, Literal

from wavestack import config
from wavestack.messages import Message, msg, render
from wavestack.models.engine import CancelToken
from wavestack.session.effects import Effect, ToolReply
from wavestack.tools.parser import ToolCall
from wavestack.tools.registry import ToolError, ToolRegistry, Unreachable
from wavestack.trace.journal import get_journal

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


# The reason is a `Message` (languages 5/5): the session renders it where it shows it.
Contact = tuple[Literal["available", "unavailable"], str | None]
# Applies some of a reply's effects before `tool_ended`; returns the others and the failure
# (a `Message`), which turns the call into an error (story 14: a memory write).
ApplyNow = Callable[[tuple[Effect, ...]], tuple[tuple[Effect, ...], str | None]]
# Lot B (N3): bounds a successful result before `tool_ended`; returns the text reinjected and,
# when it cut, `{tokens, total_tokens, estimated}` (`ToolResultTruncated`), else `None`.
Bound = Callable[[str], tuple[str, dict[str, Any] | None]]


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        language: Callable[[], str] = lambda: config.DEFAULT_LANGUAGE,
    ) -> None:
        self.registry = registry
        # Languages (5/5): the session's language, read at each call (never `settings.json`):
        # every text the model or the user reads from here is written in it.
        self.language = language
        # Network and MCP tools (AD-12): the state left by the last call actually sent, and
        # its reason.
        self.contact: dict[str, Contact] = {}

    def check(
        self, call: ToolCall, enabled: Sequence[str], loadable: Sequence[str] = ()
    ) -> str | None:
        """Why `call` cannot run, in the session's language (unknown or disabled tool,
        documentation not loaded, invalid arguments). `loadable`: the MCP tools
        `load_tool_doc` offers (AD-25)."""
        lang = self.language()
        spec = self.registry.get(call.name)
        if call.name in loadable and call.name not in enabled:
            return msg("tools.check.doc_not_loaded", lang, name=call.name)
        if spec is None or call.name not in enabled:
            available = ", ".join(enabled) or msg("tools.check.none", lang)
            return msg("tools.check.unknown_tool", lang, name=call.name, available=available)
        problems = [
            msg("tools.check.unknown_argument", lang, arg=arg)
            for arg in call.arguments
            if arg not in spec.params
        ]
        required = spec.params if spec.required is None else spec.required
        for arg, kind in spec.params.items():
            if arg not in call.arguments:
                if arg in required:
                    problems.append(msg("tools.check.missing_argument", lang, arg=arg))
                continue
            value = call.arguments[arg]
            wrong_bool = isinstance(value, bool) and kind != "boolean"
            if wrong_bool or not isinstance(value, _JSON_TYPES.get(kind, (object,))):
                expected = msg(f"tools.check.types.{kind}", lang) if kind in _JSON_TYPES else kind
                problems.append(msg("tools.check.wrong_type", lang, arg=arg, expected=expected))
        if problems:
            return msg(
                "tools.check.invalid_arguments", lang, name=call.name, problems=", ".join(problems)
            )
        return None

    def reject(
        self, raw: str, fragment: str, detail_text: str, reaction: Literal["retry", "stop"]
    ) -> str:
        """Trace a malformed, unknown or invalid call; returns the error reinjected to the
        model. `detail_text` may be a `Message` (the parser's), rendered here."""
        lang = self.language()
        detail_text = render(detail_text, lang)
        get_journal().emit(
            "tool_call_malformed",
            {"raw": raw, "fragment": fragment, "detail_text": detail_text, "reaction": reaction},
        )
        sentence = detail_text if detail_text.endswith(".") else f"{detail_text}."
        return msg("tools.reject", lang, sentence=sentence)

    def run(
        self,
        call: ToolCall,
        cancel: CancelToken,
        effects: list[Effect] | None = None,
        apply: ApplyNow | None = None,
        bound: Bound | None = None,
    ) -> str | None:
        """Execute a checked call; returns the text reinjected, or `None` if the turn is stopped.

        A `ToolReply`'s effects go to `effects`, for the session to apply (AD-23), but those
        `apply` applies at once, before `tool_ended`: its failure is the call's error. `bound`
        (lot B) cuts a successful result only, before `tool_ended`, which then carries it."""
        if cancel.cancelled:
            return None
        spec = self.registry.get(call.name)
        assert spec is not None  # `check` passed
        lang = self.language()
        journal = get_journal()
        started = time.monotonic()
        journal.emit(
            "tool_started",
            {
                "tool": call.name,
                "arguments": call.arguments,
                "phase_label": (
                    self.registry.label(call.name)
                    if spec.source == "harness"
                    else msg("tools.phase_label", lang, label=self.registry.label(call.name))
                ),
                "source": spec.source,
            },
        )
        result = error_text = reason = None
        status = "error"  # a failure's status: a failed delegation carries its own (AD-11)
        sent = spec.is_mcp  # an MCP call always reaches its server's connection
        unreachable = False
        try:
            if spec.preview is not None:
                spec.preview(**call.arguments)  # a refusal raises here, before anything is sent
                sent = True
            reply = spec.run(**call.arguments)
            if isinstance(reply, ToolReply):
                pending = reply.effects
                if apply is not None:
                    pending, failure = apply(pending)
                    if failure is not None:
                        raise ToolError(_as_message(failure))
                if effects is not None:
                    effects.extend(pending)
                reply = reply.text
            result = reply
        except ToolError as exc:
            error_text, reason = exc.render(lang), exc.message
            unreachable = isinstance(exc, Unreachable)
            status = getattr(exc, "status", "error")
        except Exception as exc:  # noqa: BLE001 - AD-16: an execution error is reinjected
            error_text = msg("tools.failed", lang, kind=type(exc).__name__, cause=exc)
        if sent:
            self.contact[call.name] = (
                ("unavailable", reason) if unreachable else ("available", None)
            )
        duration_ms = round((time.monotonic() - started) * 1000)
        truncated = None
        if bound is not None and error_text is None and result is not None:
            result, truncated = bound(result)
        ended: dict[str, Any] = {
            "status": "ok" if error_text is None else status,
            "result": result,
            "error_text": error_text,
            "duration_ms": duration_ms,
        }
        if truncated is not None:
            ended["truncated"] = truncated
        journal.emit("tool_ended", ended)
        return result if error_text is None else msg("tools.error", lang, text=error_text)


def _as_message(text: str) -> Message:
    """A failure as a `Message`: itself, or a text written elsewhere, kept as it is."""
    return text if isinstance(text, Message) else Message("common.verbatim", text=text)
