"""Prompt Guard 2 injection guardrail (CAP-5, story 13): `gravitee-io`'s ONNX quantized
export of `meta-llama/Llama-Prompt-Guard-2-22M`, run by `onnxruntime` — no torch, the same
choice and the same reason as `toxicity.py` (torch CPU would blow the brick's 1.5 Go budget).
Both `onnxruntime` and `tokenizers` are already required by the `guardrails` extra: Prompt
Guard needs no dependency of its own.

Decision (22M, not 86M): the 22M variant's quantized ONNX (~70 Mo) comfortably fits beside
toxicity and pii inside the 1.5 Go budget; the 86M variant's English-only accuracy gain
(guardrails.md) is not worth measuring the extra RAM for a demo guardrail on this poste —
upgrade: offer it as a second choice if a future story needs that gain.

Decision (token always required): `gravitee-io/Llama-Prompt-Guard-2-22M-onnx` itself reports
`gated: false` on the Hub (checked 2026-10-16) — its files can be fetched without a token.
WaveStack still requires one (CAP-5): the weights are still a Llama 4 Community licensed
derivative, and the point of the story is the user's own licence acceptance, not a mirror's
current leniency, which could tighten at any time. The token is sent as `Authorization:
Bearer …` on every request to this host; masked before it ever reaches the journal, the
trace or a log (`net.factory`'s header allow-list, AD-15), never written to the repository
(`config.hf_token_path()`, outside it, erasable).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

from wavestack import config
from wavestack.config import ModelFile
from wavestack.guardrails.contract import Classification, Entity, NotInstalled
from wavestack.messages import Message
from wavestack.models.download import DownloadError, download_files, missing_files
from wavestack.models.engine import CancelToken

# Pinned revision, sizes and sha256 checked on 2026-10-16 (gravitee-io's conversion repo has
# no pinned revision tag: `main`, like its README documents). `tokenizer.json` is a plain git
# file (no LFS, no declared sha256 on the Hub): size-checked only, like a declared-empty
# `sha256` anywhere else in this codebase.
_REPO = "https://huggingface.co/gravitee-io/Llama-Prompt-Guard-2-22M-onnx/resolve/main/"
FILES = (
    ModelFile(url=_REPO + "tokenizer.json", path="tokenizer.json", size=8649291),
    ModelFile(
        url=_REPO + "model.quant.onnx",
        path="model.quant.onnx",
        size=72542430,
        sha256="38c3f03e30a4d5d229aeb7bf638e778322f8179d0ed0d4953eb22f88d8e0cf6b",
    ),
)
THRESHOLD = 0.5
MALICIOUS_LABEL = 1  # config.json: id2label.1 == "MALICIOUS"
_WINDOW = 512  # config.json: max_position_embeddings


def _dest() -> Path:
    return config.models_dir() / "guardrails" / "injection"


class PromptGuardGuardrail:
    """Lazy, like `ToxicityGuardrail`: nothing loaded, no token read, before `classify` or an
    explicit `ensure_loaded` (the brick's « Installer », story 13)."""

    def __init__(self) -> None:
        self._session = None
        self._tokenizer = None

    @property
    def loaded(self) -> bool:
        return self._session is not None

    def ensure_loaded(self, on_progress: Callable[[int, int], None] | None = None) -> None:
        if self.loaded:
            return
        token = config.hf_token()
        if token is None:
            raise NotInstalled(str(Message("guardrails.injection.no_token")))
        import onnxruntime as ort
        from tokenizers import Tokenizer

        dest = _dest()
        if missing_files(FILES, dest):
            headers = {"Authorization": f"Bearer {token.get_secret_value()}"}
            download_files(
                FILES,
                dest,
                CancelToken(),
                on_progress or (lambda done, total: None),
                headers=headers,
            )
        self._tokenizer = Tokenizer.from_file(str(dest / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=_WINDOW)
        self._tokenizer.no_padding()
        self._session = ort.InferenceSession(
            str(dest / "model.quant.onnx"), providers=["CPUExecutionProvider"]
        )

    def classify(self, text: str) -> Classification:
        self.ensure_loaded()
        names = [i.name for i in self._session.get_inputs()]
        enc = self._tokenizer.encode(text)
        ids = np.array([enc.ids], dtype=np.int64)
        mask = np.array([enc.attention_mask], dtype=np.int64)
        logits = self._session.run(None, dict(zip(names, [ids, mask], strict=False)))[0][0]
        probs = np.exp(logits) / np.exp(logits).sum()
        score = float(probs[MALICIOUS_LABEL])
        return Classification(detected=score >= THRESHOLD, score=score, threshold=THRESHOLD)

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        return text  # injection is never masked: "signaler" only annotates, as toxicity does

    def unload(self) -> None:
        self._session = None
        self._tokenizer = None


__all__ = ["PromptGuardGuardrail", "DownloadError"]
