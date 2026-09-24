"""AD-4 non-regression: the Qwen3.5 template render, and checks 4 and 6 on a real GGUF."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from wavestack.context.render import render_context, render_template
from wavestack.context.segments import Part, SegmentKind
from wavestack.models.capabilities import capabilities_for
from wavestack.trace.journal import get_journal

FIXTURES = Path(__file__).parent / "fixtures"
QWEN_TEMPLATE = FIXTURES / "qwen3_5_chat_template.jinja"
# Expected render, produced independently (transformers `apply_chat_template`), never by WaveStack.
QWEN_REFERENCE = FIXTURES / "qwen3_5_reference_render.txt"

MESSAGES = [
    {"role": "system", "content": "Tu es l'assistant de la démo. Réponds en français."},
    {"role": "user", "content": "Quelle heure est-il à Montréal ? C'est l'été."},
]
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Donne l'heure d'une ville, par exemple « Montréal ».",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "Nom de la ville"}},
                "required": ["city"],
            },
        },
    }
]


def test_qwen3_5_render_matches_reference():
    if not (QWEN_TEMPLATE.is_file() and QWEN_REFERENCE.is_file()):
        pytest.skip("Qwen3.5 template fixture and its reference render are not fetched yet.")
    rendered = render_template(
        QWEN_TEMPLATE.read_bytes().decode("utf-8"),
        MESSAGES,
        tools=TOOLS,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    assert rendered == QWEN_REFERENCE.read_bytes().decode("utf-8")


@pytest.mark.model
def test_real_gguf_passes_checks_4_and_6():
    """Set WAVESTACK_TEST_GGUF to a local GGUF path; skipped otherwise."""
    from wavestack.models.engine import LlamaCppEngine

    path = os.environ.get("WAVESTACK_TEST_GGUF")
    if not path or not Path(path).is_file():
        pytest.skip("WAVESTACK_TEST_GGUF does not point to a GGUF file.")
    engine = LlamaCppEngine(path, n_ctx=4096)
    try:
        meta = engine.metadata()
        caps = capabilities_for(meta)
        assert caps.incompatible_reason is None
        # Accents, apostrophe, and a 128-space run: whitespace-run tokens can exceed the
        # 32-byte piece buffer, which exercises its resize in `token_pieces`.
        message = "Résumé de l'été : « déjà-vu »," + " " * 128 + "fin."
        template_vars = {caps.reasoning_variable: False} if caps.reasoning_variable else {}
        mark = get_journal().last_seq()
        rendered = render_context(
            engine,
            caps.chat_template or "",
            [{"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, message)]}],
            call_id="t0.main.c1",
            special_tokens=meta.special_tokens,
            bos_token=meta.bos_token,
            eos_token=meta.eos_token,
            add_generation_prompt=True,
            **template_vars,
        )
        errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
        assert errors == []  # checks 4 and 6 both passed
        assert b"".join(engine.token_pieces(rendered.ids)) == rendered.prompt.encode("utf-8")
        assert sum(s.tokens for s in rendered.segments) == len(rendered.ids)
        assert [s.text for s in rendered.segments if s.kind == SegmentKind.USER_MESSAGE] == [
            message
        ]
    finally:
        engine.close()
