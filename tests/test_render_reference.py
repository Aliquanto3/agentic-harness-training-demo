"""AD-4 non-regression: the Qwen3.5 template render, and checks 4 and 6 on a real GGUF."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from wavestack.context.render import render_context, render_template
from wavestack.context.segments import Joined, Part, SegmentKind
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

        # AD-25: `load_tool_doc` with two servers, one `tool_catalog` segment per line.
        catalog = SegmentKind.TOOL_CATALOG
        lines = [
            Part(catalog, "- local__define_term : Donne la définition d'une notion.", "mcp",
                 "mcp.local", "local__define_term"),
            Part(catalog, "- datagouv__search_datasets : Cherche des jeux « publics »…", "mcp",
                 "mcp.datagouv", "datagouv__search_datasets"),
        ]  # fmt: skip
        intro = Part(catalog, "Charge une documentation :", "mcp", "core.harness", "load_tool_doc")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": Part(catalog, "load_tool_doc", "mcp", "core.harness", "load_tool_doc"),
                    "parameters": {"type": "object", "properties": {"tool": {"type": "string"}}},
                    "description": Joined((intro, *lines), sep="\n"),
                },
            }
        ]
        mark = get_journal().last_seq()
        rendered = render_context(
            engine,
            caps.chat_template or "",
            [{"role": "user", "content": [Part(SegmentKind.USER_MESSAGE, "Bonjour")]}],
            call_id="t0.main.c2",
            special_tokens=meta.special_tokens,
            tools=tools,
            bos_token=meta.bos_token,
            eos_token=meta.eos_token,
            add_generation_prompt=True,
            **template_vars,
        )
        errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
        assert errors == []
        assert sum(s.tokens for s in rendered.segments) == len(rendered.ids)
        found = [(s.component, s.text) for s in rendered.segments if s.kind == catalog]
        assert found[1:] == [(p.component, p.text) for p in lines]
    finally:
        engine.close()


@pytest.mark.model
def test_real_gguf_reuses_its_cache_between_two_turns():
    """Lot A (A5, AD-4): two turns of `native_tools` on the real model; the second turn's
    first call evaluates, as llama.cpp counts them, only the tokens after the first turn's
    last call and its output. Set WAVESTACK_TEST_GGUF; skipped otherwise."""
    from wavestack import config
    from wavestack.session.app_session import AppSession

    path = os.environ.get("WAVESTACK_TEST_GGUF")
    if not path or not Path(path).is_file():
        pytest.skip("WAVESTACK_TEST_GGUF does not point to a GGUF file.")
    session = AppSession(config.Config(values={"context": {"window": 4096}}))
    try:
        assert session.boot(path).result() != "error"
        session.launch_scenario("native_tools")
        session.join()
        turns = []
        for message in ("Quelle heure est-il ?", "Et quel jour sommes-nous ?"):
            mark = get_journal().last_seq()
            session.send(message)
            session.join()
            events = [e for e in get_journal().events_since(mark) if e.context_id == "main"]
            assert [e.payload["status"] for e in events if e.kind == "turn_ended"] == ["completed"]
            turns.append(events)
        last = [e.payload for e in turns[0] if e.kind == "model_call_ended"][-1]
        second = [e.payload for e in turns[1] if e.kind == "model_call_ended"][0]
        assert [e for e in turns[1] if e.kind == "prefix_not_reused"] == []
        # llama.cpp keeps the output but its last token sampled (±1 by how the call ended).
        new = second["prompt_tokens"] - (last["prompt_tokens"] + last["output_tokens"])
        assert abs(second["evaluated_tokens"] - new) <= 1
    finally:
        session.close()


@pytest.mark.model
def test_real_gguf_state_restored_after_a_divergent_prompt():
    """Lot A (N2, AD-11): the main context's state saved, a sub-agent's prompt evaluated in
    its place, the state restored: a prompt extending the main context evaluates its new
    tokens only, on the real (hybrid, for Qwen3.5) model. Set WAVESTACK_TEST_GGUF."""
    from wavestack.models.engine import CancelToken, LlamaCppEngine

    path = os.environ.get("WAVESTACK_TEST_GGUF")
    if not path or not Path(path).is_file():
        pytest.skip("WAVESTACK_TEST_GGUF does not point to a GGUF file.")
    engine = LlamaCppEngine(path, n_ctx=4096)
    try:

        def complete(ids: list[int]) -> None:
            list(engine.complete(ids, [], 8, CancelToken()))

        complete(engine.tokenize("<|im_start|>system\nContexte principal.<|im_end|>\n"))
        main = engine.cached_ids()
        saved = engine.snapshot()
        assert saved is not None and saved.size_bytes > 0
        complete(engine.tokenize("<|im_start|>system\nSous-agent.<|im_end|>\n"))
        assert engine.restore(saved) is True
        assert engine.cached_ids() == main
        added = engine.tokenize("<|im_start|>user\nSuite.<|im_end|>\n")
        complete(main + added)
        assert abs(engine.last_evaluated - len(added)) <= 1
    finally:
        engine.close()
