"""Lot A: `LlamaCppEngine`'s cache and state on the synthetic `tiny-llama.gguf` (AD-4, AD-11).

The prompt tokens evaluated are read on the engine's side (llama.cpp's counters), not
deduced by the harness: the suite checks the real reuse of the cache without a real model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from wavestack.models.engine import CancelToken, LlamaCppEngine

TINY = Path(__file__).parent / "fixtures" / "tiny-llama.gguf"


@pytest.fixture
def engine():
    engine = LlamaCppEngine(str(TINY), n_ctx=256)
    yield engine
    engine.close()


def complete(engine: LlamaCppEngine, ids: list[int]) -> None:
    list(engine.complete(ids, [], 4, CancelToken()))


def test_a_prompt_that_extends_the_cache_evaluates_its_new_tokens_only(engine):
    first = engine.tokenize("<|im_start|>user\nBonjour, comment vas-tu ?<|im_end|>\n")
    assert engine.last_evaluated is None and engine.cached_ids() == []

    complete(engine, first)

    assert engine.last_evaluated == len(first)
    cached = engine.cached_ids()
    assert cached[: len(first)] == first  # then the output, but its last token sampled
    added = engine.tokenize("<|im_start|>user\nEt ensuite ?<|im_end|>\n")
    complete(engine, cached + added)
    assert engine.last_evaluated == len(added)


def test_a_restored_state_is_extended_after_a_divergent_prompt(engine):
    complete(engine, engine.tokenize("<|im_start|>system\nContexte principal.<|im_end|>\n"))
    main = engine.cached_ids()

    saved = engine.snapshot()
    assert saved is not None and saved.size_bytes > 0
    complete(engine, engine.tokenize("<|im_start|>system\nSous-agent.<|im_end|>\n"))
    assert engine.cached_ids()[: len(main)] != main  # the other context took the cache
    assert engine.restore(saved) is True

    assert engine.cached_ids() == main
    added = engine.tokenize("<|im_start|>user\nSuite.<|im_end|>\n")
    complete(engine, main + added)
    assert engine.last_evaluated == len(added)
