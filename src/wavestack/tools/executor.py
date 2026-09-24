"""The single tool executor (AD-14): validation, execution, events. Never raises (AD-16).

The session sets the trace scope (call, step, component) before each call.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Literal

from wavestack.models.engine import CancelToken
from wavestack.tools.parser import ToolCall
from wavestack.tools.registry import ToolError, ToolRegistry
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


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def check(self, call: ToolCall, enabled: Sequence[str]) -> str | None:
        """Why `call` cannot run, in French (unknown or disabled tool, invalid arguments)."""
        spec = self.registry.get(call.name)
        if spec is None or call.name not in enabled:
            available = ", ".join(enabled) or "aucun"
            return (
                f"L'outil « {call.name} » n'existe pas ou est désactivé. "
                f"Outils disponibles : {available}."
            )
        problems = [
            f"argument inconnu « {arg} »" for arg in call.arguments if arg not in spec.params
        ]
        for arg, kind in spec.params.items():
            if arg not in call.arguments:
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

    def run(self, call: ToolCall, cancel: CancelToken) -> str | None:
        """Execute a checked call; returns the text reinjected, or `None` if the turn is stopped."""
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
                "phase_label": f"Exécution de l'outil {self.registry.label(call.name)}",
            },
        )
        result = error_fr = None
        try:
            result = spec.run(**call.arguments)
        except ToolError as exc:
            error_fr = exc.message_fr
        except Exception as exc:  # noqa: BLE001 - AD-16: an execution error is reinjected
            error_fr = f"L'outil a échoué ({type(exc).__name__} : {exc})."
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
