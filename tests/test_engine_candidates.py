"""Story 29, increment 4: `LlamaCppEngine`'s sampling, tokens and candidates on the synthetic
`tiny-llama.gguf` (no real model; the default suite)."""

from __future__ import annotations

from pathlib import Path

import pytest

from wavestack.models.engine import CancelToken, LlamaCppEngine, Sampling

TINY = Path(__file__).parent / "fixtures" / "tiny-llama.gguf"


@pytest.fixture
def engine():
    engine = LlamaCppEngine(str(TINY), n_ctx=256)
    yield engine
    engine.close()


def _fragments(engine: LlamaCppEngine, sampling: Sampling) -> list:
    ids = engine.tokenize("<|im_start|>user\nBonjour<|im_end|>\n")
    return list(engine.complete(ids, [], 4, CancelToken(), sampling=sampling, candidates=5))


def test_top_k_one_keeps_only_the_token_drawn(engine):
    fragments = _fragments(engine, Sampling(1.0, 1, 1.0, 0.0))
    tokens = [f for f in fragments if f.stop_reason is None]
    assert tokens
    for fragment in tokens:
        assert fragment.token_id is not None and fragment.piece is not None
        rows = fragment.candidates
        assert rows and rows[0]["chosen"] and rows[0]["token_id"] == fragment.token_id
        assert rows[0]["p_sampled"] == 1.0 and rows[0]["kept"]
        assert all(not r["kept"] and not r["chosen"] for r in rows[1:])
        assert sum(r["p"] for r in rows) <= 1.0 + 1e-6


def test_greedy_draws_the_most_probable(engine):
    fragments = _fragments(engine, Sampling(0.0, 40, 0.95, 0.05))
    for fragment in (f for f in fragments if f.stop_reason is None):
        rows = fragment.candidates
        assert rows[0]["chosen"] and rows[0]["token_id"] == fragment.token_id
        assert rows[0]["p_sampled"] == 1.0


def test_dimensions_of_the_loaded_model(engine):
    dims = engine.dimensions()
    assert dims["vocab_size"] and dims["embedding_length"] and dims["layer_count"]
