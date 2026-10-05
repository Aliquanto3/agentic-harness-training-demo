"""Story 29, the « LLM nu » screen: the candidates of one token, read from the logits the
in-process engine drew it from (AD-5: the last position only, never `logits_all`).

llama.cpp's chain (`Llama._init_sampler`) applies top-k, top-p and min-p to the raw logits,
then the temperature to the tokens kept, then draws. Hence three figures per candidate:
- `p`: the model's own probability (softmax at temperature 1, over the whole vocabulary);
- `kept`: whether top-k, then top-p (cumulated over the probabilities renormalized among the
  tokens top-k kept), then min-p left it in the draw;
- `p_sampled`: its real chance to be drawn, softmax of `logits / T` over the tokens kept;
  at T = 0 the draw is greedy: 1 for the most probable, 0 for the others.

llama-cpp-python 0.3.35's `generate` leaves the penalties neutral (`repeat_penalty` 1,
`frequency_penalty` and `presence_penalty` 0) and `typical_p` at 1 (no effect): the raw
logits read here are those top-k sees (checked for story 5 of 2026-09-30).

Story 5 of 2026-09-30 (the live distribution): the in-process engine also reads, for each
token, the `TOP` most probable tokens' `p` and `tail = 1 - sum(p)` (`top_from_logits`), which
the session keeps in memory for the last generation; `distribution` redraws their `kept`
and `p_sampled` for any sampling, the same chain, without the logits (AD-1: the server
computes, never the page).
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Callable, Sequence
from typing import Any

TOP = 100  # the most probable tokens kept in memory per token of the last generation


def piece_text(piece: bytes) -> str:
    """A token's text: its UTF-8 bytes decoded, or, when they are only part of a character,
    the bytes themselves: « ⟨F0 9F⟩ »."""
    try:
        return piece.decode("utf-8")
    except UnicodeDecodeError:
        return "⟨" + " ".join(f"{b:02X}" for b in piece) + "⟩"


def candidates_from_logits(
    logits: Sequence[float] | Any,
    sampling: Any,
    chosen_id: int,
    n: int = 5,
) -> list[dict[str, Any]]:
    """The `n` most probable tokens, then the token drawn when it is not among them:
    `{token_id, p, kept, p_sampled, chosen}` each (the text is the engine's to add).
    `sampling`: `temperature`, `top_k`, `top_p`, `min_p` (`engine.Sampling`)."""
    import numpy as np  # installed with llama-cpp-python; imported on the in-process path only

    values = np.asarray(logits, dtype=np.float64)
    vocab = values.shape[0]
    top = values.max()
    weights = np.exp(values - top)
    p = weights / weights.sum()  # the model's own probabilities, temperature 1

    # llama.cpp's order: the logits sorted, top-k, then top-p on the renormalized, then min-p.
    k = max(1, min(int(sampling.top_k) if sampling.top_k > 0 else vocab, vocab))
    width = min(vocab, max(k, n))
    head = np.argpartition(-values, width - 1)[:width] if width < vocab else np.arange(vocab)
    head = head[np.argsort(-values[head], kind="stable")]
    kept_ids = head[:k]
    kept_p = weights[kept_ids] / weights[kept_ids].sum()
    if sampling.top_p < 1.0:
        cumulated = np.cumsum(kept_p)
        last = int(np.searchsorted(cumulated, sampling.top_p, side="left"))
        kept_ids = kept_ids[: min(last + 1, len(kept_ids))]
    if sampling.min_p > 0.0:
        floor = values[kept_ids[0]] + np.log(sampling.min_p)  # p_i / p_max >= min_p
        kept_ids = kept_ids[values[kept_ids] >= floor]
    kept = set(int(t) for t in kept_ids)

    if sampling.temperature <= 0.0:
        sampled = {int(kept_ids[0]): 1.0}
    else:
        scaled = values[kept_ids] / sampling.temperature
        scaled = np.exp(scaled - scaled.max())
        scaled /= scaled.sum()
        sampled = {int(t): float(q) for t, q in zip(kept_ids, scaled, strict=True)}

    shown = [int(t) for t in head[:n]]
    if chosen_id not in shown:
        shown.append(int(chosen_id))
    return [
        {
            "token_id": token,
            "p": float(p[token]),
            "kept": token in kept,
            "p_sampled": sampled.get(token, 0.0),
            "chosen": token == chosen_id,
        }
        for token in shown
    ]


def top_from_logits(
    logits: Sequence[float] | Any, n: int = TOP
) -> tuple[list[int], list[float], float]:
    """The `n` most probable token ids, most probable first, their probability at temperature
    1 (softmax over the whole vocabulary) and `tail`, the mass of all the others (`1 - sum`)."""
    import numpy as np  # installed with llama-cpp-python; imported on the in-process path only

    values = np.asarray(logits, dtype=np.float64)
    vocab = values.shape[0]
    weights = np.exp(values - values.max())
    p = weights / weights.sum()
    width = min(vocab, max(1, n))
    head = np.argpartition(-values, width - 1)[:width] if width < vocab else np.arange(vocab)
    head = head[np.argsort(-values[head], kind="stable")]
    top = [float(p[t]) for t in head]
    return [int(t) for t in head], top, max(0.0, 1.0 - sum(top))


def read_logits(
    logits: Sequence[float] | Any,
    sampling: Any,
    chosen_id: int,
    n: int,
    pieces: Callable[[list[int]], list[bytes]],
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any]]:
    """What an engine reads from one token's logits, shared by `LlamaCppEngine` and the tests'
    fake: its `n` candidates with their text (`candidates_from_logits`), and the `TOP` most
    probable tokens for the session's memory, `{p, texts, tail}` (story 5 of 2026-09-30)."""
    rows = candidates_from_logits(logits, sampling, chosen_id, n)
    ids, probs, tail = top_from_logits(logits)
    texts = [piece_text(p) for p in pieces([r["token_id"] for r in rows] + ids)]
    shown = tuple(
        {"token_id": r["token_id"], "text": t}
        | {k: r[k] for k in ("p", "kept", "p_sampled", "chosen")}
        for r, t in zip(rows, texts[: len(rows)], strict=True)
    )
    return shown, {"p": probs, "texts": texts[len(rows) :], "tail": tail}


def _cuts(values: list[float], tail: float, sampling: Any) -> tuple[int, int, int]:
    """How many of `values` (non-negative, most probable first) are still in the draw after
    top-k, then top-p, then min-p, in llama.cpp's order (`distribution`'s rules)."""
    count = len(values)
    k = int(sampling.top_k)
    if 0 < k <= count:
        kept_n, base = k, sum(values[:k])
    else:  # top-k off (or wider than what was read): the whole vocabulary stays
        kept_n, base = count, sum(values) + max(0.0, float(tail))
    after_k = kept_n
    if sampling.top_p < 1.0 and base > 0:
        cumulated: list[float] = []
        total = 0.0
        for v in values[:kept_n]:
            total += v / base
            cumulated.append(total)
        kept_n = min(bisect_left(cumulated, sampling.top_p) + 1, kept_n)
    after_p = kept_n
    if sampling.min_p > 0.0:
        floor = values[0] * sampling.min_p  # p_i / p_max >= min_p
        kept_n = max(1, sum(1 for v in values[:kept_n] if v >= floor))
    return after_k, after_p, kept_n


def dropped_by(top_p_values: Sequence[float], tail: float, sampling: Any) -> list[str | None]:
    """Lot 6 of 2026-10-04: which setting leaves each of `distribution`'s tokens out of the
    draw, `"top-k"`, `"top-p"` or `"min-p"` (the first of the chain), `None` when it stays;
    the same cuts as `distribution`, so that the page writes « écarté (top-p) » without
    computing anything (AD-1)."""
    values = [max(0.0, float(v)) for v in top_p_values]
    if not values:
        return []
    after_k, after_p, kept_n = _cuts(values, tail, sampling)
    return [
        None if i < kept_n else "top-k" if i >= after_k else "top-p" if i >= after_p else "min-p"
        for i in range(len(values))
    ]


def distribution(top_p_values: Sequence[float], tail: float, sampling: Any) -> list[dict[str, Any]]:
    """`kept` and `p_sampled` of the most probable tokens (`top_p_values`: their `p` at
    temperature 1, most probable first; `tail`: the mass of the rest of the vocabulary) for
    `sampling`, in llama.cpp's order, as `candidates_from_logits`:
    - top-k keeps the first k (0: all of them);
    - top-p, on the probabilities renormalized among those top-k kept, keeps up to the first
      whose cumulated sum reaches p (top-k off: over the whole vocabulary, the tail included);
    - min-p keeps those with p >= min-p x the most probable's; at least one stays;
    - T = 0: the first at 1, the others at 0; else softmax of `log p / T` over the kept.
    The draw is renormalized among these tokens only, never the tail's: an approximation, the
    page says so. `{p, kept, p_sampled}` each, in the same order."""
    values = [max(0.0, float(v)) for v in top_p_values]
    if not values:
        return []
    kept_n = _cuts(values, tail, sampling)[2]

    sampled = [1.0] + [0.0] * (kept_n - 1)  # T = 0: greedy
    if sampling.temperature > 0.0:
        scaled = [
            math.log(v) / sampling.temperature if v > 0 else -math.inf for v in values[:kept_n]
        ]
        top = max(scaled)
        if top > -math.inf:  # else every probability read is 0: the first one only
            weights = [math.exp(x - top) for x in scaled]
            total = sum(weights)
            sampled = [w / total for w in weights]
    return [
        {"p": v, "kept": i < kept_n, "p_sampled": sampled[i] if i < kept_n else 0.0}
        for i, v in enumerate(values)
    ]


def draw_index(rows: Sequence[dict[str, Any]], rng: Any) -> int:
    """Correction F of 2026-10-05: the index of one of `distribution`'s rows drawn among
    the kept ones only, each with its `p_sampled` as weight (`rng.random()`, a
    `random.Random`): the same chances as the bars the page draws. The first kept row when
    every weight is 0 (T = 0 already gives it 1); `ValueError` when no row is kept."""
    kept = [(i, max(0.0, float(r["p_sampled"]))) for i, r in enumerate(rows) if r["kept"]]
    if not kept:
        raise ValueError("no kept row to draw from")
    total = sum(w for _, w in kept)
    if total <= 0.0:
        return kept[0][0]
    point = rng.random() * total
    cumulated = 0.0
    for index, weight in kept:
        cumulated += weight
        if point < cumulated:
            return index
    # Rounding left `point` at the very top: the last kept row with a weight.
    return next(i for i, w in reversed(kept) if w > 0.0)
