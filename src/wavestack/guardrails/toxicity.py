"""Toxicity guardrail (CAP-5): `gravitee-io/distilbert-multilingual-toxicity-classifier`, the
ONNX quantized export, run by `onnxruntime` with a fast tokenizer — no torch.

shortcut: the documented fallback, `textdetox/bert-multilingual-toxicity-classifier`, has no
ONNX export on the Hub (only a 680 MB PyTorch `safetensors` file), which would need torch and
blow the brick's 1.5 GB RAM budget alone. Until a quantized ONNX build exists, a failed
download or load leaves the guardrail in `error` status (its message says why) instead of a
second model (upgrade: re-check the Hub for an ONNX textdetox export).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from wavestack import config
from wavestack.config import ModelFile
from wavestack.guardrails.contract import Classification, Entity
from wavestack.models.download import DownloadError, download_files, missing_files
from wavestack.models.engine import CancelToken

# Pinned revision, sizes and sha256 checked on 2026-10-16, like the models of `wavestack.toml`.
_REPO = (
    "https://huggingface.co/gravitee-io/distilbert-multilingual-toxicity-classifier/resolve/"
    "865ad1b453a49e4a7f2471fc40b727ececd28314/"
)
FILES = (
    ModelFile(
        url=_REPO + "model.quant.onnx",
        path="model.quant.onnx",
        size=135582999,
        sha256="c8169782758fe097c6cf036ddc48f6ff7b3c861764d6124c20d8b31bc0ba93d7",
    ),
    ModelFile(
        url=_REPO + "tokenizer.json",
        path="tokenizer.json",
        size=2919627,
        sha256="c2c0e4d392f08c2c2eb950156eb26e4e5ddd15b557faa45ed6a0decaf45b5f98",
    ),
)
THRESHOLD = 0.5
TOXIC_LABEL = 1  # config.json: id2label.1 == "toxic"
# Measured on 2026-10-16: one insult after ~200 tokens of neutral text, or even inside a
# 64-token window, scores under 0.05, and tokenizer.json drops everything past 256 tokens.
# So each sentence is scored alone (overlapping 256-token windows for a very long one), the
# worst one wins; padding is off so a short sentence costs a short run.
_SENTENCES = re.compile(r"(?<=[.!?…])\s+|\n+")
_WINDOW = 256
_STRIDE = 32


def _dest() -> Path:
    return config.models_dir() / "guardrails" / "toxicity"


class ToxicityGuardrail:
    """Lazy: nothing is loaded (no RAM, no disk check) before the first `classify`."""

    def __init__(self) -> None:
        self._session = None
        self._tokenizer = None

    @property
    def loaded(self) -> bool:
        return self._session is not None

    def ensure_loaded(self) -> None:
        if self.loaded:
            return
        import onnxruntime as ort
        from tokenizers import Tokenizer

        dest = _dest()
        if missing_files(FILES, dest):
            download_files(FILES, dest, CancelToken(), lambda done, total: None)
        self._tokenizer = Tokenizer.from_file(str(dest / "tokenizer.json"))
        self._tokenizer.enable_truncation(max_length=_WINDOW, stride=_STRIDE)
        self._tokenizer.no_padding()
        self._session = ort.InferenceSession(
            str(dest / "model.quant.onnx"), providers=["CPUExecutionProvider"]
        )

    def classify(self, text: str) -> Classification:
        self.ensure_loaded()
        sentences = [s for s in _SENTENCES.split(text) if s.strip()] or [text]
        names = [i.name for i in self._session.get_inputs()]
        score = 0.0
        # The ONNX export has a fixed batch size of 1: one run per window, the worst one wins.
        windows = (w for e in self._tokenizer.encode_batch(sentences) for w in (e, *e.overflowing))
        for window in windows:
            ids = np.array([window.ids], dtype=np.int64)
            mask = np.array([window.attention_mask], dtype=np.int64)
            inputs = dict(zip(names, [ids, mask], strict=False))
            logits = self._session.run(None, inputs)[0][0]
            probs = np.exp(logits) / np.exp(logits).sum()
            score = max(score, float(probs[TOXIC_LABEL]))
        return Classification(detected=score >= THRESHOLD, score=score, threshold=THRESHOLD)

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        return text  # toxicity never masks: "signaler" only annotates

    def unload(self) -> None:
        self._session = None
        self._tokenizer = None


__all__ = ["ToxicityGuardrail", "DownloadError"]
