"""Story 29, the « LLM nu » screen: the candidates of one token, read from the logits the
in-process engine drew it from (AD-5: the last position only, never `logits_all`).

llama.cpp's chain (`Llama._init_sampler`) applies top-k, top-p and min-p to the raw logits,
then the temperature to the tokens kept, then draws. Hence three figures per candidate:
- `p`: the model's own probability (softmax at temperature 1, over the whole vocabulary);
- `kept`: whether top-k, then top-p (cumulated over the probabilities renormalized among the
  tokens top-k kept), then min-p left it in the draw;
- `p_sampled`: its real chance to be drawn, softmax of `logits / T` over the tokens kept;
  at T = 0 the draw is greedy: 1 for the most probable, 0 for the others.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


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
