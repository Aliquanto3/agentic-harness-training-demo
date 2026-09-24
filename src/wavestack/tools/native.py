"""The three offline native tools, confined whatever hooks say (AD-14)."""

from __future__ import annotations

import ast
import operator
from datetime import datetime
from pathlib import Path, PurePath

from wavestack import config
from wavestack.tools.registry import ToolError, ToolSpec

_WEEKDAYS_FR = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def get_datetime() -> str:
    now = datetime.now().astimezone()  # the workstation's local time, no zone to choose
    return f"{_WEEKDAYS_FR[now.weekday()]} {now.isoformat(timespec='seconds')}"


# ---------- calculator: `ast` with a whitelist, never `eval` ----------

_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
MAX_EXPONENT = 100
MAX_POWER_BITS = 4096  # an integer power beyond this is refused before being computed
MAX_EXPRESSION = 200
_ALLOWED_FR = "des nombres, + - * / // % ** et des parenthèses"


def _evaluate(node: ast.expr) -> int | float:
    match node:
        case ast.Constant(value=bool()):
            pass
        case ast.Constant(value=int() | float() as value):
            return value
        case ast.UnaryOp(op=op, operand=operand) if type(op) in _UNARY:
            return _UNARY[type(op)](_evaluate(operand))
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _BINARY:
            a, b = _evaluate(left), _evaluate(right)
            if isinstance(op, ast.Pow) and (
                abs(b) > MAX_EXPONENT
                or (
                    isinstance(a, int)
                    and isinstance(b, int)
                    and a.bit_length() * b > MAX_POWER_BITS
                )
            ):
                raise ToolError(
                    f"Puissance refusée : l'exposant {b} est trop grand pour la calculatrice "
                    f"(au plus {MAX_EXPONENT}, et un résultat de taille raisonnable)."
                )
            try:
                return _BINARY[type(op)](a, b)
            except ZeroDivisionError:
                raise ToolError("Division par zéro : le calcul n'a pas de résultat.") from None
            except OverflowError:
                raise ToolError("Résultat trop grand pour la calculatrice.") from None
    raise ToolError(f"Opération refusée : la calculatrice n'accepte que {_ALLOWED_FR}.")


def calculator(expression: str) -> str:
    text = expression.replace("×", "*").replace("÷", "/")
    if len(text) > MAX_EXPRESSION:
        raise ToolError(f"Expression trop longue : {MAX_EXPRESSION} caractères au plus.")
    try:
        tree = ast.parse(text.strip(), mode="eval")
    except SyntaxError:
        raise ToolError(
            f"Expression illisible : « {expression} ». Utilisez {_ALLOWED_FR}."
        ) from None
    value = _evaluate(tree.body)
    return str(value) if isinstance(value, int) else format(value, ".12g")


# ---------- read_file: confined to content/demo_files/ ----------


def demo_dir() -> Path:
    return (config.content_dir() / "demo_files").resolve()


def read_file(path: str) -> str:
    base = demo_dir()
    # Absolute, drive or UNC paths are refused before any filesystem access.
    target = None if PurePath(path).anchor else (base / path).resolve()
    if target is None or not target.is_relative_to(base):
        raise ToolError(
            f"Accès refusé : « {path} » sort du dossier de démonstration. Seuls les fichiers "
            "de content/demo_files/ sont lisibles, par un chemin relatif."
        )
    files = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
    if target.is_dir():
        return "Fichiers disponibles :\n" + "\n".join(files)
    if not target.is_file():
        raise ToolError(f"Fichier absent : « {path} ». Fichiers disponibles : {', '.join(files)}.")
    return target.read_text(encoding="utf-8")


NATIVE_TOOLS = [
    ToolSpec(name="get_datetime", run=get_datetime, params={}, component="tools.get_datetime"),
    ToolSpec(
        name="calculator",
        run=calculator,
        params={"expression": "string"},
        component="tools.calculator",
    ),
    ToolSpec(
        name="read_file",
        run=read_file,
        params={"path": "string"},
        component="tools.read_file",
        reads_local_path="path",
    ),
]
