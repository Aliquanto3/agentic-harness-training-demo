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


# ---------- story 4 of the deferred leftovers (E122): `prefill` ----------


def test_a_prefilled_prefix_is_extended_by_the_next_completion(engine):
    prefix = engine.tokenize("<|im_start|>system\nTu es bref.<|im_end|>\n<|im_start|>user")

    assert engine.prefill(prefix, CancelToken()) == len(prefix)
    assert engine.cached_ids() == prefix

    rest = engine.tokenize("\nBonjour<|im_end|>\n<|im_start|>assistant\n")
    complete(engine, prefix + rest)
    assert engine.last_evaluated == len(rest)
    # A prefill whose ids are all in cache already touches nothing: the cache stays longer.
    assert engine.prefill(prefix, CancelToken()) == 0
    longer = engine.cached_ids()
    assert longer[: len(prefix)] == prefix and len(longer) > len(prefix)


def test_a_prefill_cancelled_after_its_first_batch_keeps_what_it_evaluated(engine, monkeypatch):
    from wavestack.models import engine as engine_module

    monkeypatch.setattr(engine_module, "PREFILL_BATCH", 4)
    ids = engine.tokenize("<|im_start|>system\nContexte principal, long de deux lots.<|im_end|>\n")
    assert len(ids) > 8

    class AfterFirstBatch(CancelToken):
        reads = 0

        @property
        def cancelled(self) -> bool:  # read before each batch: false once, then true
            self.reads += 1
            return self.reads > 1

    assert engine.prefill(ids, AfterFirstBatch()) == 4
    assert engine.cached_ids() == ids[:4]

    complete(engine, ids)
    assert engine.last_evaluated == len(ids) - 4
