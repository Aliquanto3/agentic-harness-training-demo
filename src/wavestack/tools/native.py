"""The three offline native tools, confined whatever hooks say (AD-14)."""

from __future__ import annotations

import ast
import operator
from datetime import datetime
from pathlib import Path, PurePath, PurePosixPath

from wavestack import config
from wavestack.messages import msg
from wavestack.tools.registry import ToolError, ToolSpec

# Languages (5/5): the days from Monday, their names in `messages.yaml` (`tools.datetime`).
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def weekday(now: datetime, lang: str) -> str:
    """The day of the week of `now` in `lang` (« mercredi », « Wednesday », « Mittwoch »)."""
    return msg(f"tools.datetime.weekdays.{_WEEKDAYS[now.weekday()]}", lang)


def get_datetime(lang: str = config.DEFAULT_LANGUAGE) -> str:
    """The workstation's local time, no zone to choose, after its day in `lang` (the
    session's, bound as `read_file` is)."""
    now = datetime.now().astimezone()
    return f"{weekday(now, lang)} {now.isoformat(timespec='seconds')}"


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
    """The French demonstration folder: the confinement and the listing are always its own,
    whatever the language (languages 3/5)."""
    return (config.content_dir() / "demo_files").resolve()


def resolve_demo_path(path: str) -> Path | None:
    """`path` as `read_file` resolves it; `None` for an absolute, drive or UNC path, refused
    before any filesystem access. The hooks (H1) resolve it the same way (AD-14)."""
    return None if PurePath(path).anchor else (demo_dir() / path).resolve()


def demo_relative(path: str) -> PurePosixPath | None:
    """`path` relative to the French demonstration folder, as `read_file` resolves it;
    `None` when it leaves the folder. H1 and the translation judge this relative path,
    never the folder it is finally read from (languages 3/5)."""
    target = resolve_demo_path(path)
    base = demo_dir()
    if target is None or not target.is_relative_to(base):
        return None
    return PurePosixPath(target.relative_to(base).as_posix())


def read_file(path: str, lang: str = config.DEFAULT_LANGUAGE) -> str:
    """The demonstration file `path` in `lang` (the session's, never `settings.json`'s):
    its translation under `content/i18n/{lang}/demo_files/` when it exists, else the French
    file, file by file. The confinement and the listing are the French folder's."""
    base = demo_dir()
    rel = demo_relative(path)
    if rel is None:
        raise ToolError(
            f"Accès refusé : « {path} » sort du dossier de démonstration. Seuls les fichiers "
            "de content/demo_files/ sont lisibles, par un chemin relatif."
        )
    target = base / rel
    files = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())
    if target.is_dir():
        return "Fichiers disponibles :\n" + "\n".join(files)
    if not target.is_file():
        raise ToolError(f"Fichier absent : « {path} ». Fichiers disponibles : {', '.join(files)}.")
    return config.content_file(PurePosixPath("demo_files") / rel, lang).read_text(encoding="utf-8")


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
