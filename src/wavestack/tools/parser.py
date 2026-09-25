"""Tool-call parsers, one per family format (AD-6).

- `qwen3_coder`: `<tool_call><function=NAME><parameter=ARG>value</parameter>`
  `</function></tool_call>`, values converted according to the tool's schema;
- `hermes`: `<tool_call>{"name": ..., "arguments": {...}}</tool_call>`.

A parse never raises: it returns the calls, or what is malformed and why, in French.
"""

from __future__ import annotations

import hashlib
import json
import re
import string
from dataclasses import dataclass, field
from typing import Any

from wavestack.models.capabilities import TOOL_CALL_TAGS

OPEN, CLOSE = TOOL_CALL_TAGS
_BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase


def tool_call_id(step_id: str, index: int) -> str:
    """AD-4: 9 base-62 characters of the hash of `"{step_id}#{index}"`, attributed by the
    session to every call it creates (model output, forced action)."""
    n = int.from_bytes(hashlib.sha256(f"{step_id}#{index}".encode()).digest(), "big")
    digits = []
    for _ in range(9):
        n, r = divmod(n, 62)
        digits.append(_BASE62[r])
    return "".join(digits)


_FUNCTION = re.compile(r"\s*<function=([^>\s]+)>(.*)</function>\s*", re.DOTALL)
_PARAMETER = re.compile(r"<parameter=([^>\s]+)>(.*?)</parameter>", re.DOTALL)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    source: str = field(default="", compare=False)  # its `<tool_call>…</tool_call>` block


@dataclass(frozen=True)
class Malformed:
    fragment: str  # the faulty part of the raw output
    detail_fr: str


def convert_value(value: str, kind: str | None) -> Any:
    """`qwen3_coder` values are text: convert them per the schema, keep the text on failure."""
    try:
        match kind:
            case "integer":
                return int(value)
            case "number":
                return float(value)
            case "boolean" if value.strip().lower() in ("true", "false"):
                return value.strip().lower() == "true"
            case "object" | "array":
                return json.loads(value)
    except ValueError:
        pass
    return value


def _qwen3_coder(inner: str, schemas: dict[str, dict[str, str]]) -> ToolCall | str:
    function = _FUNCTION.fullmatch(inner)
    if function is None:
        return "la balise <function=…>…</function> est absente ou mal fermée"
    name, body = function.groups()
    params = _PARAMETER.findall(body)
    if len(params) != body.count("<parameter="):
        return "une balise <parameter=…> n'est pas fermée par </parameter>"
    schema = schemas.get(name, {})
    arguments = {}
    for arg, value in params:
        value = value.removeprefix("\n").removesuffix("\n")
        arguments[arg] = convert_value(value, schema.get(arg))
    return ToolCall(name, arguments)


def _hermes(inner: str, _schemas: dict[str, dict[str, str]]) -> ToolCall | str:
    try:
        data = json.loads(inner)
    except ValueError as exc:
        return f"le JSON de l'appel est illisible ({exc})"
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        return "l'appel n'est pas un objet JSON avec un champ « name »"
    arguments = data.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return "le champ « arguments » n'est pas un objet JSON"
    if not isinstance(arguments, dict):
        return "le champ « arguments » n'est pas un objet JSON"
    return ToolCall(data["name"], arguments)


_FORMATS = {"qwen3_coder": _qwen3_coder, "hermes": _hermes}


def parse_tool_calls(
    raw: str, parser: str, schemas: dict[str, dict[str, str]]
) -> tuple[list[ToolCall], Malformed | None]:
    """Every `<tool_call>` block of `raw`; one malformed block makes the whole output malformed."""
    parse = _FORMATS[parser]
    calls: list[ToolCall] = []
    pos = 0
    while (start := raw.find(OPEN, pos)) >= 0:
        end = raw.find(CLOSE, start)
        if end < 0:
            return [], Malformed(raw[start:], "la balise <tool_call> n'est jamais fermée")
        block = raw[start : end + len(CLOSE)]
        result = parse(raw[start + len(OPEN) : end], schemas)
        if isinstance(result, str):
            return [], Malformed(block, result)
        calls.append(ToolCall(result.name, result.arguments, block))
        pos = end + len(CLOSE)
    return calls, None
