"""Writes two synthetic BERT GGUFs of a few KB for the reranker's tests (story 16).

- `tiny-bert-rank.gguf`: a reranker, pooling `RANK` declared, with its classification head
  (`cls`, `cls.output`); random weights, so its scores mean nothing, but llama-cpp-python
  loads it, tokenizes a pair and gives one figure per pair, as bge-reranker does.
- `tiny-bert-cls.gguf`: the same without the head, pooling `CLS` declared: an embedding
  model, which the adapter must refuse.

A WordPiece vocabulary of the letters, digits and a few French characters, BOS/EOS/SEP
added to a pair as XLM-RoBERTa does. The files are committed; to write them again (the
`gguf` package is not a project dependency):

    uv run --with gguf python tests/fixtures/make_tiny_rerank_gguf.py
"""

from __future__ import annotations

import string
import sys
from pathlib import Path

import numpy as np
from gguf import GGUFWriter, LlamaFileType, PoolingType, TokenType

N_EMBD, N_FF, N_HEAD, N_CTX = 16, 32, 2, 128


def tokens() -> list[str]:
    special = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]"]
    chars = list(string.ascii_lowercase + string.digits + "éèêàçùôîâû'?:,.-")
    return special + chars + ["##" + c for c in chars]


def write(path: Path, rank: bool) -> None:
    rng = np.random.default_rng(16 if rank else 15)
    toks = tokens()
    w = GGUFWriter(str(path), "bert")
    w.add_name("tiny-bert-rank" if rank else "tiny-bert-cls")
    w.add_context_length(N_CTX)
    w.add_embedding_length(N_EMBD)
    w.add_feed_forward_length(N_FF)
    w.add_block_count(1)
    w.add_head_count(N_HEAD)
    w.add_layer_norm_eps(1e-12)
    w.add_causal_attention(False)
    w.add_pooling_type(PoolingType.RANK if rank else PoolingType.CLS)
    w.add_file_type(LlamaFileType.ALL_F32)
    w.add_tokenizer_model("bert")
    w.add_token_list(toks)
    w.add_token_types([TokenType.CONTROL] * 5 + [TokenType.NORMAL] * (len(toks) - 5))
    w.add_token_type_count(2)
    w.add_pad_token_id(0)
    w.add_unk_token_id(1)
    w.add_bos_token_id(2)
    w.add_eos_token_id(3)
    w.add_sep_token_id(3)
    w.add_mask_token_id(4)
    w.add_add_bos_token(True)
    w.add_add_eos_token(True)

    def t(name: str, *shape: int) -> None:
        w.add_tensor(name, (rng.standard_normal(shape) * 0.1).astype(np.float32))

    def const(name: str, n: int, value: float) -> None:
        w.add_tensor(name, np.full(n, value, dtype=np.float32))

    t("token_embd.weight", len(toks), N_EMBD)
    t("token_types.weight", 2, N_EMBD)
    t("position_embd.weight", N_CTX, N_EMBD)
    const("token_embd_norm.weight", N_EMBD, 1.0)
    const("token_embd_norm.bias", N_EMBD, 0.0)
    for p in ("attn_q", "attn_k", "attn_v", "attn_output"):
        t(f"blk.0.{p}.weight", N_EMBD, N_EMBD)
        const(f"blk.0.{p}.bias", N_EMBD, 0.0)
    const("blk.0.attn_output_norm.weight", N_EMBD, 1.0)
    const("blk.0.attn_output_norm.bias", N_EMBD, 0.0)
    t("blk.0.ffn_up.weight", N_FF, N_EMBD)
    const("blk.0.ffn_up.bias", N_FF, 0.0)
    t("blk.0.ffn_down.weight", N_EMBD, N_FF)
    const("blk.0.ffn_down.bias", N_EMBD, 0.0)
    const("blk.0.layer_output_norm.weight", N_EMBD, 1.0)
    const("blk.0.layer_output_norm.bias", N_EMBD, 0.0)
    if rank:
        t("cls.weight", N_EMBD, N_EMBD)
        const("cls.bias", N_EMBD, 0.0)
        t("cls.output.weight", 1, N_EMBD)
        const("cls.output.bias", 1, 0.0)
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    write(out / "tiny-bert-rank.gguf", rank=True)
    write(out / "tiny-bert-cls.gguf", rank=False)
