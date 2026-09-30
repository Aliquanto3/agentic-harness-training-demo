"""The hooks of the `hooks` brick: deterministic code at fixed points of the turn (AD-13).

A hook is a pure function `hook(ctx) -> HookResult | None`: it reads a frozen view of the
turn and returns a decision, never writes a file or a state (AD-23). The session calls the
active hooks, validates their decision, emits it and applies its effects.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NamedTuple, get_args

import httpx
import yaml
from pydantic import BaseModel, Field, model_validator

from wavestack import config
from wavestack.session.effects import AuditAppend, Effect
from wavestack.tools.native import demo_relative, weekday
from wavestack.tools.parser import ToolCall
from wavestack.tools.registry import ToolError, ToolSpec
from wavestack.trace.catalog import HookDecision, HookPoint
from wavestack.trace.envelope import Envelope

POINTS: tuple[HookPoint, ...] = get_args(HookPoint)
# AD-13: the decisions each point accepts; any other is traced and counts as `allow`.
ALLOWED: dict[HookPoint, frozenset[HookDecision]] = {
    "on_user_message": frozenset({"allow", "modify"}),
    "before_model_call": frozenset({"allow", "block"}),
    "before_tool": frozenset({"allow", "block", "modify", "ask_human"}),
    "after_tool": frozenset({"allow"}),
    "on_turn_end": frozenset({"allow", "block"}),
}
CONFIDENTIAL = "confidentiel"  # the sub-folder of `content/demo_files/` H1 protects
AUDIT = "file.audit"  # the component of the audit log's node and `effect_applied`
_MONTHS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
_APPROVAL_FR = {"approved": "autorisé", "refused": "refusé", "cancelled": "annulé"}
# Languages (1/5): H3's date in English and German, days from Monday.
_WEEKDAYS = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "de": ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
}
_MONTHS = {
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
    "de": (
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ),
}


class HookText(BaseModel):
    label_text: str = Field(min_length=1)
    description_text: str = Field(min_length=1)


class HooksContent(BaseModel):
    """`content/hooks.yaml` (AD-19)."""

    hooks: dict[str, HookText]
    points: dict[HookPoint, str]
    injection: str = Field(min_length=1)  # H3's text, `{date}` replaced at each turn
    audit_label_text: str = Field(min_length=1)
    # Languages (1/5): the language the texts were asked in, set by `load_hooks_content`
    # (never in the file); H3 writes its date in it.
    language: str = config.DEFAULT_LANGUAGE

    @model_validator(mode="after")
    def _every_point_labelled(self) -> HooksContent:
        missing = set(POINTS) - set(self.points)
        if missing:
            raise ValueError(f"missing point labels for {sorted(missing)}")
        return self


def load_hooks_content(ids: Iterable[str], lang: str | None = None) -> HooksContent:
    """Raises on a missing or invalid file, or a declared hook without text. `language` is
    the one of the file read (H3's date follows its sentence): French when it answered."""
    asked = config.as_language(lang) if lang is not None else config.current_language()
    path = config.content_file("hooks.yaml", asked)
    language = asked if path != config.content_file("hooks.yaml", "fr") else "fr"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    content = HooksContent.model_validate(data).model_copy(update={"language": language})
    missing = [i for i in ids if i not in content.hooks]
    if missing:
        raise ValueError(f"{path}: no text for hooks {missing}")
    return content


@dataclass(frozen=True)
class HookContext:
    """A read-only view of the turn at one point (AD-13)."""

    point: HookPoint
    turn_id: str
    call: ToolCall | None = None  # before_tool, after_tool: the resolved call
    spec: ToolSpec | None = None
    result: str | None = None  # after_tool: the text reinjected
    events: tuple[Envelope, ...] = ()  # the turn's events so far
    status: str | None = None  # on_turn_end: the turn's status
    context_id: str = "main"  # `main` or a sub-agent's `sub{n}` (AD-11)
    content: HooksContent | None = None
    now: datetime = field(default_factory=lambda: datetime.now().astimezone())


@dataclass(frozen=True)
class HookResult:
    decision: HookDecision
    detail_text: str
    effects: tuple[Effect, ...] = ()
    injection: str | None = None  # on_user_message `modify`: the text placed before it
    arguments: dict[str, Any] | None = None  # before_tool `modify`: the new arguments
    preview: dict[str, str] | None = None  # before_tool `ask_human`: {method, url, body}


class Hook(NamedTuple):
    id: str
    points: frozenset[HookPoint]
    fn: Callable[[HookContext], HookResult | None]


# ---------- H1: sensitive file guard ----------


def guard(ctx: HookContext) -> HookResult | None:
    """Blocks any `reads_local_path` tool whose path, resolved as `read_file` resolves it,
    is the confidential folder or inside it. Compares flags and the path relative to the
    demonstration folder (AD-14): `confidentiel/…` is refused whatever the language, and
    whatever folder the file is finally read from (languages 3/5)."""
    spec, call = ctx.spec, ctx.call
    if spec is None or call is None or not spec.reads_local_path:
        return None
    path = call.arguments.get(spec.reads_local_path)
    if not isinstance(path, str):
        return None
    rel = demo_relative(path)
    if rel is None:
        return None  # outside the demo folder: `read_file`'s confinement refuses it (AD-14)
    # Case-folded: on a case-insensitive filesystem, `CONFIDENTIEL/` is the same folder.
    if rel.parts and rel.parts[0].casefold() == CONFIDENTIAL:
        return HookResult(
            "block",
            f"Bloqué par le hook garde-fou : « {path} » est dans le dossier confidentiel, "
            "dont la lecture est interdite.",
        )
    return HookResult("allow", f"« {path} » est hors du dossier confidentiel : lecture permise.")


# ---------- H2: audit log ----------


def _line(ts: datetime, turn_id: str, what: str, detail: str, status: str) -> str:
    detail = " ".join(detail.replace("|", "/").split()) or "-"
    stamp = ts.astimezone().isoformat(timespec="seconds")
    return f"{stamp} | {turn_id} | {what} | {detail} | {status}"


def audit(ctx: HookContext) -> HookResult | None:
    """Stateless: logs the turn's events after its last write (`effect_applied` on
    `file.audit`), so the file stays in order though it writes at two points."""
    events = ctx.events
    last = max(
        (i for i, e in enumerate(events) if e.kind == "effect_applied" and e.component == AUDIT),
        default=-1,
    )
    lines = []
    # Each `tool_ended` names the tool its `tool_started` (same step) ran: a delegation's
    # sub-agent runs its own tools in between (story 19), maybe logged before it ends.
    started = {
        e.step_id: f"{e.payload['tool']} {json.dumps(e.payload['arguments'], ensure_ascii=False)}"
        for e in events
        if e.kind == "tool_started"
    }
    asked = {  # a refused call has no `tool_started`: its tool and host come from here
        e.payload["approval_id"]: e.payload for e in events if e.kind == "approval_requested"
    }

    def where(event: Envelope) -> str:
        """The turn, and a sub-agent's context when the event is its own (story 19)."""
        context = event.context_id or ""
        return f"{ctx.turn_id}.{context}" if context.startswith("sub") else ctx.turn_id

    for event in events[last + 1 :]:
        p = event.payload
        if event.kind == "model_call_ended":
            read, made = p["prompt_tokens"], p["output_tokens"]
            detail = f"{read} tokens lus, {made} produits"
            lines.append(_line(event.ts, where(event), "appel au modèle", detail, p["stop_reason"]))
        elif event.kind == "tool_ended":
            tool = started.get(event.step_id, "?")
            lines.append(_line(event.ts, where(event), "appel d'outil", tool, p["status"]))
        elif event.kind == "tool_call_malformed":
            what = "appel d'outil refusé"
            lines.append(_line(event.ts, where(event), what, p["detail_text"], "refusé"))
        elif event.kind == "hook_decided" and p["decision"] == "block":
            what = f"appel bloqué par {p['hook'].upper()}"
            lines.append(_line(event.ts, where(event), what, p["detail_text"], "bloqué"))
        elif event.kind == "approval_resolved":
            request = asked.get(p["approval_id"], {"tool": "?", "destination": "?"})
            detail = f"{request['tool']} vers {request['destination']}"
            status = _APPROVAL_FR[p["decision"]]
            lines.append(_line(event.ts, where(event), "validation humaine", detail, status))
    if ctx.point == "on_turn_end":
        lines.append(_line(ctx.now, ctx.turn_id, "fin du tour", "", ctx.status or "?"))
    if not lines:
        return None
    s = "s" if len(lines) > 1 else ""
    return HookResult(
        "allow",
        f"{len(lines)} ligne{s} pour le journal d'audit.",
        effects=(AuditAppend(lines=lines),),
    )


# ---------- H3: context injection ----------


def date_fr(now: datetime) -> str:
    """« jeudi 24 septembre 2026, 10 h 12 »."""
    day = f"{weekday(now, 'fr')} {now.day} {_MONTHS_FR[now.month - 1]} {now.year}"
    return f"{day}, {now.hour} h {now.minute:02d}"


def date_text(now: datetime, lang: str) -> str:
    """H3's date in `lang`: « Thursday 24 September 2026, 10:12 », « Donnerstag, 24.
    September 2026, 10:12 Uhr »; French (`date_fr`) for any other language."""
    if lang == "en":
        day = f"{_WEEKDAYS['en'][now.weekday()]} {now.day} {_MONTHS['en'][now.month - 1]}"
        return f"{day} {now.year}, {now.hour}:{now.minute:02d}"
    if lang == "de":
        day = f"{_WEEKDAYS['de'][now.weekday()]}, {now.day}. {_MONTHS['de'][now.month - 1]}"
        return f"{day} {now.year}, {now.hour}:{now.minute:02d} Uhr"
    return date_fr(now)


def inject(ctx: HookContext) -> HookResult | None:
    """Adds the workstation's date and the mission's rules before the user's message."""
    if ctx.content is None:
        return None
    text = ctx.content.injection.replace("{date}", date_text(ctx.now, ctx.content.language))
    return HookResult(
        "modify", "Date du poste et règles de la mission ajoutées avant le message.", injection=text
    )


# ---------- H5: human validation ----------


def ask(ctx: HookContext) -> HookResult | None:
    """Asks a human before any network tool sends its request, showing exactly what would
    leave the workstation. A refused preview sends nothing: the executor refuses the call."""
    spec, call = ctx.spec, ctx.call
    if spec is None or call is None or not spec.network or spec.preview is None:
        return None
    try:
        preview = spec.preview(**call.arguments)
    except ToolError:
        return None
    return HookResult(
        "ask_human",
        f"L'appel à « {call.name} » enverrait une requête vers {host(preview['url'])} : le "
        "harnais demande votre accord avant tout envoi.",
        preview=preview,
    )


def host(url: str) -> str:
    """The destination as the sender parses it (`httpx`), never another parser."""
    return httpx.URL(url).host or url


DEMO_HOOKS = (
    Hook("h1", frozenset({"before_tool"}), guard),
    Hook("h2", frozenset({"after_tool", "on_turn_end"}), audit),
    Hook("h3", frozenset({"on_user_message"}), inject),
    Hook("h5", frozenset({"before_tool"}), ask),
)
