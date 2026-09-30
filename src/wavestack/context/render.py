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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from itertools import accumulate
from typing import Any

from jinja2 import nodes
from jinja2.exceptions import TemplateError
from jinja2.ext import Extension, loopcontrols
from jinja2.sandbox import ImmutableSandboxedEnvironment

from wavestack.context.segments import Joined, Part, Segment, SegmentKind
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


# Private markers of `reasoning_wrap`'s probe renders (never in a real text: step 2).
_PROBE_REASONING, _PROBE_TEXT = "\ue010", "\ue011"


@cache
def reasoning_wrap(template: str) -> tuple[str, str] | None:
    """AD-4, append only over the conversation (local mode): what `template` writes before
    an assistant message's reasoning and between reasoning and text in the turn itself
    (Qwen3.5: `"<think>\n"`, `"\n</think>\n\n"`), returned only when the template omits
    that block for a past message and keeps a content already wrapped as it is, with
    `reasoning_content = ""`. The session then renders a past answer as it was produced.
    `None` otherwise (the template keeps the past reasoning, or has none), or when a probe
    render fails."""
    question = {"role": "user", "content": "Q"}
    answer = {"role": "assistant", "content": _PROBE_TEXT, "reasoning_content": _PROBE_REASONING}
    later = {"role": "user", "content": "R"}
    try:
        in_turn = render_template(template, [question, answer], add_generation_prompt=False)
        past = render_template(template, [question, answer, later])
        at_reasoning, at_text = in_turn.find(_PROBE_REASONING), in_turn.find(_PROBE_TEXT)
        past_text = past.find(_PROBE_TEXT)
        if _PROBE_REASONING in past or not 0 <= at_reasoning < at_text or past_text < 0:
            return None
        head = past[:past_text]  # the message's header, up to its content
        if not in_turn[:at_reasoning].startswith(head):
            return None
        before = in_turn[len(head) : at_reasoning]
        middle = in_turn[at_reasoning + len(_PROBE_REASONING) : at_text]
        if not before and not middle:
            return None
        wrapped = f"{before}{_PROBE_REASONING}{middle}{_PROBE_TEXT}"
        kept = render_template(
            template, [question, answer | {"content": wrapped, "reasoning_content": ""}, later]
        )
    except Exception:  # noqa: BLE001 - a template the probes do not suit: nothing changes
        return None
    return (before, middle) if head + wrapped in kept else None


# ---------- attribution ----------


@dataclass
class RenderedContext:
    prompt: str
    ids: list[int]
    segments: list[Segment]
    # Story 32: the leading segments the previous call of the same context read already in
    # the turn (`seen_prefix`), set by the session; the gauge's `seen_segments`.
    seen: int = 0


def _neutralize(part: Part, special: re.Pattern[str] | None) -> Part:
    """Step 2: strip outer blanks and private-use chars, break special-token strings. A
    `template` part is a literal of the harness (the reasoning block of `reasoning_wrap`):
    left intact, blanks and special tokens included."""
    if part.kind == SegmentKind.TEMPLATE:
        return part
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
                "message_text": (
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


def _merge_groups(
    pieces: list[tuple[int | None, str]], parts: list[Part]
) -> list[tuple[int | None, str, list[int]]]:
    """A template piece enclosed between two texts of one group joins it, and a group's
    consecutive pieces form one segment (one `tool_catalog` per tool, one piece per call).
    Each segment keeps the indexes of the parts it holds."""

    def group(owner: int | None) -> str | None:
        return None if owner is None else parts[owner].group

    merged: list[list[Any]] = []  # [owner, text, group, owners]
    for i, (owner, text) in enumerate(pieces):
        held = [] if owner is None else [owner]
        if owner is None and 0 < i < len(pieces) - 1:
            before, after = pieces[i - 1][0], pieces[i + 1][0]
            if group(before) is not None and group(before) == group(after):
                owner = before
        if merged and group(owner) is not None and merged[-1][2] == group(owner):
            merged[-1][1] += text
            merged[-1][3] += held
        else:
            merged.append([owner, text, group(owner), held])
    return [(owner, text, owners) for owner, text, _, owners in merged]


def _special_pattern(special_tokens: list[str] | tuple[str, ...]) -> re.Pattern[str] | None:
    # A 1-char token cannot be broken by an inserted character: the loop would never end.
    tokens = [t for t in special_tokens if len(t) >= 2]
    if not tokens:
        return None
    return re.compile("|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)))


def _attribute(
    render: Callable[[list[dict[str, Any]], Any], str],
    messages: list[dict[str, Any]],
    tools: Any,
    special: re.Pattern[str] | None,
    call_id: str | None,
) -> tuple[str, list[tuple[Segment, list[Part]]]]:
    """Steps 1 to 5 around a renderer `(messages, tools) -> str`, called twice: the text
    sent, and its ordered, disjoint segments (tokens not counted yet), each with the parts
    whose texts it holds.

    `messages` carry their content as a list of `Part` (or `Joined`); a message without
    `content` keeps none. Any other value, in a message (`tool_calls`) or in `tools`, may
    itself be a `Part` at any depth: its text is attributed the same way (step 3: sentinels
    on the strings of a definition). A `Joined` is one string whose parts are attributed
    each on its own.
    """
    parts: list[Part] = []

    def add(part: Part) -> tuple[str, str]:
        part = _neutralize(part, special)
        if not part.text:
            return "", ""  # step 3: an empty text gets no sentinels and no segment
        parts.append(part)
        return part.text, f"{_START}{len(parts) - 1}{_MID}{part.text}{_END}"

    def prepare(value: Any) -> tuple[Any, Any]:
        """(plain, marked) copies of `value`, every nested `Part` replaced by its text."""
        if isinstance(value, Part):
            return add(value)
        if isinstance(value, Joined):
            texts = [add(part) for part in value.parts]
            return value.sep.join(p for p, _ in texts if p), value.sep.join(
                m for _, m in texts if m
            )
        if isinstance(value, dict):
            pairs = {key: prepare(item) for key, item in value.items()}
            return {k: p for k, (p, _) in pairs.items()}, {k: m for k, (_, m) in pairs.items()}
        if isinstance(value, list):
            pairs_list = [prepare(item) for item in value]
            return [p for p, _ in pairs_list], [m for _, m in pairs_list]
        return value, value

    plain_tools, marked_tools = prepare(
        tools
    )  # before the messages: the template renders them first
    plain: list[dict[str, Any]] = []
    marked: list[dict[str, Any]] = []
    for message in messages:
        # A `Part` or a `Joined` each; chat mode omits an empty `content` (AD-4). A content
        # made of blocks (a reasoning sent back as `thinking`, AD-4) is prepared as any value.
        parted = "content" in message and all(
            isinstance(part, (Part, Joined)) for part in message["content"]
        )
        texts = [prepare(part) for part in message["content"]] if parted else None
        rest = {key: value for key, value in message.items() if key != "content" or not parted}
        plain_rest, marked_rest = prepare(rest)
        if texts is not None:  # in the message's own key order (the chat body keeps it)
            plain_rest["content"] = PART_SEPARATOR.join(p for p, _ in texts if p)
            marked_rest["content"] = PART_SEPARATOR.join(m for _, m in texts if m)
        plain.append({key: plain_rest[key] for key in message})
        marked.append({key: marked_rest[key] for key in message})

    prompt = render(plain, plain_tools)  # step 1
    marked_render = render(marked, marked_tools)  # step 3

    if _MARKER.sub("", marked_render) == prompt:  # step 4
        pieces = _split_marked(marked_render)
    else:
        get_journal().emit(
            "harness_error",
            {
                "message_text": "Attribution approximative : le rendu d'attribution diffère du "
                "prompt envoyé.",
                "cause": "Le gabarit transforme le texte des messages (contrôle 4 d'AD-4).",
                "effect_text": "Le prompt envoyé est inchangé ; le texte non localisé est compté "
                "dans le gabarit.",
            },
        )
        pieces = _locate_in_order(prompt, parts)

    prefix = call_id or "preview"
    segments = [
        (
            Segment(
                id=f"{prefix}.{n}",
                kind=SegmentKind.TEMPLATE if owner is None else parts[owner].kind,
                brick=None if owner is None else parts[owner].brick,
                component=None if owner is None else parts[owner].component,
                text=text,
                compressed_from=None if owner is None else parts[owner].compressed_from,
            ),
            [parts[i] for i in owners],
        )
        for n, (owner, text, owners) in enumerate(_merge_groups(pieces, parts), start=1)
    ]
    return prompt, segments


def render_context(
    engine: Engine,
    template: str,
    messages: list[dict[str, Any]],
    *,
    call_id: str | None,
    special_tokens: list[str] | tuple[str, ...] = (),
    tools: list[dict[str, Any]] | None = None,
    **template_vars: Any,
) -> RenderedContext:
    """Render the prompt to send through the model's template, and attribute each of its
    tokens to one segment (steps 1 to 6)."""

    def render(plain: list[dict[str, Any]], plain_tools: Any) -> str:
        return render_template(template, plain, tools=plain_tools, **template_vars)

    prompt, pairs = _attribute(render, messages, tools, _special_pattern(special_tokens), call_id)
    segments = [segment for segment, _ in pairs]

    ids = engine.tokenize(prompt)  # step 6
    token_bytes = engine.token_pieces(ids)
    if b"".join(token_bytes) != prompt.encode("utf-8"):
        get_journal().emit(
            "harness_error",
            {
                "message_text": "Contrôle des tokens en échec : les octets des tokens ne "
                "recomposent pas le prompt.",
                "cause": "Le découpage du tokenizer ne correspond pas au texte (contrôle 6 "
                "d'AD-4).",
                "effect_text": "Le total de tokens reste exact ; leur répartition par segment "
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


# ---------- chat mode (AD-4, `openai_chat`) ----------


@dataclass
class RenderedChat:
    """The exact body sent, and its segments, each with the tokens estimated from the
    characters of its original texts (`estimates`, the provider's segment excluded)."""

    body: str
    segments: list[Segment]
    estimates: list[int]
    # Story 32: as `RenderedContext.seen`; kept here so that `context_reconciled` carries the
    # `seen_segments` of its `context_rendered`.
    seen: int = 0

    @property
    def raw_total(self) -> int:
        return sum(self.estimates)


def render_chat_body(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    call_id: str | None,
    fields: dict[str, Any],
    markers: list[str] | tuple[str, ...],
    estimate: Callable[[str], int],
    provider_label_text: str,
) -> RenderedChat:
    """AD-4, chat mode: `context` alone writes the whole body, serialized once, cut into
    segments by the sentinel method (the JSON syntax is `template`, 0 token). `fields`:
    `model`, then what follows `messages` and `tools` (`stream`, output limit,
    `stream_options`, reasoning parameters). A last `template` segment without text,
    « chez le fournisseur », carries the gap once a total is known (`with_total`)."""
    model = {"model": fields["model"]}
    tail = {key: value for key, value in fields.items() if key != "model"}

    def render(plain: list[dict[str, Any]], plain_tools: Any) -> str:
        body = {**model, "messages": plain, **({"tools": plain_tools} if plain_tools else {})}
        return json.dumps({**body, **tail}, ensure_ascii=False, separators=(",", ":"))

    body, pairs = _attribute(render, messages, tools, _special_pattern(markers), call_id)
    estimates = [
        0
        if segment.kind == SegmentKind.TEMPLATE and not held
        else estimate("".join(part.text for part in held))
        for segment, held in pairs
    ]
    segments = [
        segment.model_copy(update={"tokens": tokens, "estimated": True})
        for (segment, _), tokens in zip(pairs, estimates, strict=True)
    ]
    segments.append(
        Segment(
            id=f"{call_id or 'preview'}.{len(segments) + 1}",
            kind=SegmentKind.TEMPLATE,
            text="",
            estimated=True,
            label_text=provider_label_text,
        )
    )
    return RenderedChat(body=body, segments=segments, estimates=estimates)


def distribute(estimates: list[int], total: int) -> tuple[list[int], int]:
    """AD-4: `gap = total − Σ estimates` goes to the provider's segment when positive;
    otherwise the estimates shrink in proportion (largest remainders) and the gap is 0.
    300 + 100 with a total of 360 gives 270 + 90 + 0."""
    whole = sum(estimates)
    if total >= whole:
        return list(estimates), total - whole
    scaled = [e * total / whole for e in estimates]
    shares = [int(x) for x in scaled]
    by_remainder = sorted(range(len(scaled)), key=lambda i: scaled[i] - shares[i], reverse=True)
    for i in by_remainder[: total - sum(shares)]:
        shares[i] += 1
    return shares, 0


def with_total(rendered: RenderedChat, total: int) -> list[Segment]:
    """The segments once `total` is known (before the call: estimates × ratio; after:
    `usage.prompt_tokens`): the per-segment sum equals it."""
    shares, gap = distribute(rendered.estimates, total)
    return [
        segment.model_copy(update={"tokens": tokens})
        for segment, tokens in zip(rendered.segments, [*shares, gap], strict=True)
    ]
