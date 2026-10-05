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


def test_fragments_carry_the_most_probable_tokens(engine):
    """Story 5 of 2026-09-30: with the candidates, each token's `top` (the session's memory
    of the live distribution): `{p, texts, tail}`, the most probable first, `tail` the rest;
    the token that stops the generation carries it too."""
    from wavestack.models.candidates import TOP

    width = min(TOP, engine.dimensions()["vocab_size"])
    ids = engine.tokenize("<|im_start|>user\nBonjour<|im_end|>\n")
    fragments = list(
        engine.complete(
            ids, ["\n"], 8, CancelToken(), sampling=Sampling(1.0, 0, 1.0, 0.0), candidates=5
        )
    )
    tokens = [f for f in fragments if f.token_id is not None]
    assert tokens
    for fragment in tokens:
        top = fragment.top
        assert top is not None and set(top) == {"p", "texts", "tail"}
        assert len(top["p"]) == len(top["texts"]) == width
        assert top["p"] == sorted(top["p"], reverse=True)
        assert top["tail"] == pytest.approx(1 - sum(top["p"]), abs=1e-6)
    without = list(engine.complete(ids, [], 2, CancelToken(), sampling=Sampling(1.0, 0, 1.0, 0.0)))
    assert all(f.top is None for f in without)


def test_next_candidates_reads_the_next_token_without_drawing_one(engine):
    """Correction E of 2026-10-05: the OUTPUT's first load reads the candidates of the token
    after the ids, from the logits of their last position, nothing sampled: the same `top`
    as the first token a generation draws there, whatever the cache holds (empty, the ids
    and more, exactly the ids); `None` when cancelled first."""
    ids = engine.tokenize("<|im_start|>user\nBonjour<|im_end|>\n")
    fresh = engine.next_candidates(ids, CancelToken())
    assert fresh is not None and set(fresh) == {"p", "texts", "tail"}
    assert fresh["p"] == sorted(fresh["p"], reverse=True)
    assert fresh["tail"] == pytest.approx(1 - sum(fresh["p"]), abs=1e-6)
    drawn = list(
        engine.complete(
            ids, [], 2, CancelToken(), sampling=Sampling(1.0, 0, 1.0, 0.0), candidates=5
        )
    )
    first = next(f for f in drawn if f.token_id is not None)
    assert first.top["texts"] == fresh["texts"]
    assert first.top["p"] == pytest.approx(fresh["p"], abs=1e-5)
    for _ in range(2):  # the cache past the ids, then exactly on them: read again the same
        again = engine.next_candidates(ids, CancelToken())
        assert again["texts"] == fresh["texts"]
        assert again["p"] == pytest.approx(fresh["p"], abs=1e-5)
        assert engine.last_evaluated == 1  # only the last id evaluated again
    cancel = CancelToken()
    cancel.cancel()
    assert engine.next_candidates(engine.tokenize("Autre texte"), cancel) is None
    with pytest.raises(ValueError):
        engine.next_candidates([], CancelToken())
