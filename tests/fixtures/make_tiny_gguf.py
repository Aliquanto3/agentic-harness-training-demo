"""Writes `tiny-llama.gguf`, a synthetic model of a few KB for the default test suite.

A `llama` architecture with one layer and random weights (it answers noise), a byte-level
BPE vocabulary (the 256 bytes, one merge « on », then `<|im_start|>` and `<|im_end|>` as
control tokens), a ChatML template, and a native context of 256. Enough for llama-cpp-python
to load it fully (`LlamaCppEngine`) or `vocab_only` (`VocabTokenizer`), tokenize, give
token pieces and generate a few tokens.

The file is committed; to write it again (the `gguf` package is not a project dependency):

    uv run --with gguf python tests/fixtures/make_tiny_gguf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from gguf import GGUFWriter, TokenType

N_EMBD, N_FF, N_HEAD, N_CTX = 32, 64, 4, 256
SPECIAL = ["<|im_start|>", "<|im_end|>"]
TEMPLATE = (
    "{% for message in messages %}"
    "{{ '<|im_start|>' + message.role + '\\n' + message.content + '<|im_end|>\\n' }}"
    "{% endfor %}"
    "{% if add_generation_prompt %}{{ '<|im_start|>assistant\\n' }}{% endif %}"
)


def byte_tokens() -> list[str]:
    """GPT-2's byte-to-unicode table: the text of each of the 256 byte tokens."""
    visible = list(range(ord("!"), ord("~") + 1))
    visible += list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    chars, n = {}, 0
    for b in range(256):
        if b in visible:
            chars[b] = chr(b)
        else:
            chars[b] = chr(256 + n)
            n += 1
    return [chars[b] for b in range(256)]


def main(path: Path, architecture: str = "llama") -> None:
    rng = np.random.default_rng(18)
    tokens = byte_tokens() + ["on"] + SPECIAL  # « on »: the one merge (llama.cpp needs one)
    types = [TokenType.NORMAL] * 257 + [TokenType.CONTROL] * len(SPECIAL)
    writer = GGUFWriter(str(path), architecture)
    writer.add_name("tiny-llama")
    writer.add_context_length(N_CTX)
    writer.add_embedding_length(N_EMBD)
    writer.add_block_count(1)
    writer.add_feed_forward_length(N_FF)
    writer.add_head_count(N_HEAD)
    writer.add_head_count_kv(N_HEAD)
    writer.add_layer_norm_rms_eps(1e-5)
    writer.add_rope_dimension_count(N_EMBD // N_HEAD)
    writer.add_tokenizer_model("gpt2")
    writer.add_tokenizer_pre("default")
    writer.add_token_list(tokens)
    writer.add_token_types(types)
    writer.add_token_merges(["o n"])
    writer.add_eos_token_id(len(tokens) - 1)  # <|im_end|>
    writer.add_add_bos_token(False)
    writer.add_chat_template(TEMPLATE)

    def weights(*shape: int) -> np.ndarray:
        return (rng.standard_normal(shape) * 0.02).astype(np.float16)

    ones = np.ones(N_EMBD, dtype=np.float32)
    writer.add_tensor("token_embd.weight", weights(len(tokens), N_EMBD))
    writer.add_tensor("output_norm.weight", ones)
    writer.add_tensor("blk.0.attn_norm.weight", ones)
    for name in ("attn_q", "attn_k", "attn_v", "attn_output"):
        writer.add_tensor(f"blk.0.{name}.weight", weights(N_EMBD, N_EMBD))
    writer.add_tensor("blk.0.ffn_norm.weight", ones)
    writer.add_tensor("blk.0.ffn_gate.weight", weights(N_FF, N_EMBD))
    writer.add_tensor("blk.0.ffn_up.weight", weights(N_FF, N_EMBD))
    writer.add_tensor("blk.0.ffn_down.weight", weights(N_EMBD, N_FF))
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("tiny-llama.gguf")
    main(out, *(sys.argv[2:3]))
