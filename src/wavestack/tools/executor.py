"""The single tool executor (AD-14): validation, execution, events. Never raises (AD-16).

The session sets the trace scope (call, step, component) before each call.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Literal

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
_TYPES_FR = {
    "string": "un texte",
    "integer": "un entier",
    "number": "un nombre",
    "boolean": "un booléen",
    "object": "un objet",
    "array": "une liste",
}


Contact = tuple[Literal["available", "unavailable"], str | None]
# Applies some of a reply's effects before `tool_ended`; returns the others and the failure
# in French, which turns the call into an error (story 14: a memory write).
ApplyNow = Callable[[tuple[Effect, ...]], tuple[tuple[Effect, ...], str | None]]


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        # Network and MCP tools (AD-12): the state left by the last call actually sent, and
        # its reason.
        self.contact: dict[str, Contact] = {}

    def check(
        self, call: ToolCall, enabled: Sequence[str], loadable: Sequence[str] = ()
    ) -> str | None:
        """Why `call` cannot run, in French (unknown or disabled tool, documentation not
        loaded, invalid arguments). `loadable`: the MCP tools `load_tool_doc` offers (AD-25)."""
        spec = self.registry.get(call.name)
        if call.name in loadable and call.name not in enabled:
            return (
                f"La documentation de « {call.name} » n'est pas chargée : appelle d'abord "
                f'load_tool_doc avec tool="{call.name}".'
            )
        if spec is None or call.name not in enabled:
            available = ", ".join(enabled) or "aucun"
            return (
                f"L'outil « {call.name} » n'existe pas ou est désactivé. "
                f"Outils disponibles : {available}."
            )
        problems = [
            f"argument inconnu « {arg} »" for arg in call.arguments if arg not in spec.params
        ]
        required = spec.params if spec.required is None else spec.required
        for arg, kind in spec.params.items():
            if arg not in call.arguments:
                if arg in required:
                    problems.append(f"argument « {arg} » manquant")
                continue
            value = call.arguments[arg]
            wrong_bool = isinstance(value, bool) and kind != "boolean"
            if wrong_bool or not isinstance(value, _JSON_TYPES.get(kind, (object,))):
                problems.append(f"« {arg} » doit être {_TYPES_FR.get(kind, kind)}")
        if problems:
            return f"Arguments invalides pour « {call.name} » : {', '.join(problems)}."
        return None

    def reject(
        self, raw: str, fragment: str, detail_fr: str, reaction: Literal["retry", "stop"]
    ) -> str:
        """Trace a malformed, unknown or invalid call; returns the error reinjected to the model."""
        get_journal().emit(
            "tool_call_malformed",
            {"raw": raw, "fragment": fragment, "detail_fr": detail_fr, "reaction": reaction},
        )
        sentence = detail_fr if detail_fr.endswith(".") else f"{detail_fr}."
        return f"Erreur : {sentence} Corrige l'appel ou réponds sans outil."

    def run(
        self,
        call: ToolCall,
        cancel: CancelToken,
        effects: list[Effect] | None = None,
        apply: ApplyNow | None = None,
    ) -> str | None:
        """Execute a checked call; returns the text reinjected, or `None` if the turn is stopped.

        A `ToolReply`'s effects go to `effects`, for the session to apply (AD-23), but those
        `apply` applies at once, before `tool_ended`: its failure is the call's error."""
        if cancel.cancelled:
            return None
        spec = self.registry.get(call.name)
        assert spec is not None  # `check` passed
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
                    else f"Exécution de l'outil {self.registry.label(call.name)}"
                ),
                "source": spec.source,
            },
        )
        result = error_fr = None
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
                        raise ToolError(failure)
                if effects is not None:
                    effects.extend(pending)
                reply = reply.text
            result = reply
        except ToolError as exc:
            error_fr = exc.message_fr
            unreachable = isinstance(exc, Unreachable)
        except Exception as exc:  # noqa: BLE001 - AD-16: an execution error is reinjected
            error_fr = f"L'outil a échoué ({type(exc).__name__} : {exc})."
        if sent:
            self.contact[call.name] = (
                ("unavailable", error_fr) if unreachable else ("available", None)
            )
        journal.emit(
            "tool_ended",
            {
                "status": "ok" if error_fr is None else "error",
                "result": result,
                "error_fr": error_fr,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return result if error_fr is None else f"Erreur : {error_fr}"
