"""Chat-template rendering and exact token attribution (AD-4).

The six attribution steps are normative:
1. the prompt sent is always the template rendered with the real values;
2. every non-template text is normalized (outer blanks, private-use chars,
   special-token strings neutralized with an event);
3. a second render wraps every non-empty text in private-use sentinels;
4. once the sentinels are stripped, that render must equal the prompt byte
   for byte, otherwise `harness_error` and the unlocated text goes to `template`;
5. the prompt is cut into ordered, disjoint segments;
6. the prompt is tokenized once; each token belongs to the segment holding
   its first byte, so the per-segment sum equals the total by construction.
"""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from itertools import accumulate
from typing import Any

from jinja2 import nodes
from jinja2.exceptions import TemplateError
from jinja2.ext import Extension, loopcontrols
from jinja2.sandbox import ImmutableSandboxedEnvironment

from wavestack.context.segments import Part, Segment, SegmentKind
from wavestack.models.engine import Engine
from wavestack.trace.journal import get_journal

_START, _MID, _END = "\ue000", "\ue001", "\ue002"
_MARKER = re.compile("\ue000(\\d+)\ue001|\ue002")
_PRIVATE_USE = re.compile("[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]")
_ZWSP = "\u200b"
# ponytail: fixed separator between parts of one message; revisit when a story
# puts several parts (hook_injection, rag_excerpt) in the same message.
PART_SEPARATOR = "\n\n"


# ---------- Jinja environment, configured like transformers ----------


class _GenerationExtension(Extension):
    """`{% generation %}` blocks render their body unchanged, as in transformers."""

    tags = {"generation"}

    def parse(self, parser: Any) -> nodes.Node:
        lineno = next(parser.stream).lineno
        body = parser.parse_statements(("name:endgeneration",), drop_needle=True)
        call = self.call_method("_render_body")
        return nodes.CallBlock(call, [], [], body).set_lineno(lineno)

    def _render_body(self, caller: Any) -> str:
        return caller()


def _tojson(
    x: Any,
    ensure_ascii: bool = False,
    indent: int | None = None,
    separators: tuple[str, str] | None = None,
    sort_keys: bool = False,
) -> str:
    return json.dumps(
        x, ensure_ascii=ensure_ascii, indent=indent, separators=separators, sort_keys=sort_keys
    )


def _raise_exception(message: str) -> None:
    raise TemplateError(message)


def _strftime_now(fmt: str) -> str:
    return datetime.now().strftime(fmt)


@cache
def _environment() -> ImmutableSandboxedEnvironment:
    env = ImmutableSandboxedEnvironment(
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=[loopcontrols, _GenerationExtension],
    )
    env.filters["tojson"] = _tojson
    env.globals["raise_exception"] = _raise_exception
    env.globals["strftime_now"] = _strftime_now
    return env


def render_template(
    template: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    add_generation_prompt: bool = True,
    bos_token: str = "",
    eos_token: str = "",
    **extra: Any,
) -> str:
    """Render `tokenizer.chat_template` with the AD-4 variables (plus e.g. `enable_thinking`)."""
    return (
        _environment()
        .from_string(template)
        .render(
            messages=messages,
            tools=tools,
            add_generation_prompt=add_generation_prompt,
            bos_token=bos_token,
            eos_token=eos_token,
            **extra,
        )
    )


# ---------- attribution ----------


@dataclass
class RenderedContext:
    prompt: str
    ids: list[int]
    segments: list[Segment]


def _neutralize(part: Part, special: re.Pattern[str] | None) -> Part:
    """Step 2: strip outer blanks and private-use chars, break special-token strings."""
    text = _PRIVATE_USE.sub("", part.text).strip()
    found: list[str] = []
    while special is not None and (hits := special.findall(text)):
        found += hits
        text = special.sub(lambda m: m[0][0] + _ZWSP + m[0][1:], text)
    if found:
        get_journal().emit(
            "special_token_neutralized",
            {
                "segment_kind": part.kind,
                "tokens": sorted(set(found)),
                "message_fr": (
                    f"Le texte contenait {len(found)} marqueur(s) réservé(s) du modèle "
                    f"({', '.join(sorted(set(found)))}). Ils ont été neutralisés : un contenu "
                    f"ne peut pas modifier la structure de la conversation."
                ),
            },
        )
    return part._replace(text=text)


def _split_marked(marked: str) -> list[tuple[int | None, str]]:
    """Step 5: cut the sentinel render into disjoint (owner index | None, text) pieces."""
    pieces: list[tuple[int | None, str]] = []
    stack: list[int] = []
    pos = 0
    for match in _MARKER.finditer(marked):
        if match.start() > pos:
            pieces.append((stack[-1] if stack else None, marked[pos : match.start()]))
        if match.group(1) is not None:
            stack.append(int(match.group(1)))
        elif stack:
            stack.pop()
        pos = match.end()
    if pos < len(marked):
        pieces.append((stack[-1] if stack else None, marked[pos:]))
    return pieces


def _locate_in_order(prompt: str, parts: list[Part]) -> list[tuple[int | None, str]]:
    """Fallback after a failed step 4: find each text in order, the rest is template."""
    pieces: list[tuple[int | None, str]] = []
    pos = 0
    for index, part in enumerate(parts):
        at = prompt.find(part.text, pos)
        if at < 0:
            continue
        if at > pos:
            pieces.append((None, prompt[pos:at]))
        pieces.append((index, part.text))
        pos = at + len(part.text)
    if pos < len(prompt):
        pieces.append((None, prompt[pos:]))
    return pieces


def render_context(
    engine: Engine,
    template: str,
    messages: list[dict[str, Any]],
    *,
    call_id: str | None,
    special_tokens: list[str] | tuple[str, ...] = (),
    **template_vars: Any,
) -> RenderedContext:
    """Render the prompt to send, and attribute each of its tokens to one segment.

    `messages` carry their content as a list of `Part`; every other key is passed as is.
    """
    # A 1-char token cannot be broken by an inserted character: the loop would never end.
    special_tokens = [t for t in special_tokens if len(t) >= 2]
    special = (
        re.compile("|".join(re.escape(t) for t in sorted(special_tokens, key=len, reverse=True)))
        if special_tokens
        else None
    )

    parts: list[Part] = []
    plain: list[dict[str, Any]] = []
    marked: list[dict[str, Any]] = []
    for message in messages:
        plain_texts: list[str] = []
        marked_texts: list[str] = []
        for part in message["content"]:
            part = _neutralize(part, special)
            if not part.text:
                continue  # step 3: an empty text gets no sentinels and no segment
            marked_texts.append(f"{_START}{len(parts)}{_MID}{part.text}{_END}")
            plain_texts.append(part.text)
            parts.append(part)
        plain.append({**message, "content": PART_SEPARATOR.join(plain_texts)})
        marked.append({**message, "content": PART_SEPARATOR.join(marked_texts)})

    prompt = render_template(template, plain, **template_vars)  # step 1
    marked_render = render_template(template, marked, **template_vars)  # step 3

    if _MARKER.sub("", marked_render) == prompt:  # step 4
        pieces = _split_marked(marked_render)
    else:
        get_journal().emit(
            "harness_error",
            {
                "message_fr": "Attribution approximative : le rendu d'attribution diffère du "
                "prompt envoyé.",
                "cause": "Le gabarit transforme le texte des messages (contrôle 4 d'AD-4).",
                "effect_fr": "Le prompt envoyé est inchangé ; le texte non localisé est compté "
                "dans le gabarit.",
            },
        )
        pieces = _locate_in_order(prompt, parts)

    prefix = call_id or "preview"
    segments = [
        Segment(
            id=f"{prefix}.{n}",
            kind=SegmentKind.TEMPLATE if owner is None else parts[owner].kind,
            brick=None if owner is None else parts[owner].brick,
            component=None if owner is None else parts[owner].component,
            text=text,
        )
        for n, (owner, text) in enumerate(pieces, start=1)
    ]

    ids = engine.tokenize(prompt)  # step 6
    token_bytes = engine.token_pieces(ids)
    if b"".join(token_bytes) != prompt.encode("utf-8"):
        get_journal().emit(
            "harness_error",
            {
                "message_fr": "Contrôle des tokens en échec : les octets des tokens ne "
                "recomposent pas le prompt.",
                "cause": "Le découpage du tokenizer ne correspond pas au texte (contrôle 6 "
                "d'AD-4).",
                "effect_fr": "Le total de tokens reste exact ; leur répartition par segment "
                "peut être décalée.",
            },
        )
    if segments:
        segment_ends = list(accumulate(len(s.text.encode("utf-8")) for s in segments))
        offset = 0
        for piece in token_bytes:
            index = min(bisect.bisect_right(segment_ends, offset), len(segments) - 1)
            segments[index].tokens += 1
            offset += len(piece)

    return RenderedContext(prompt=prompt, ids=ids, segments=segments)
