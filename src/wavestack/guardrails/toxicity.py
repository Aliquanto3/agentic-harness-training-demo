"""Toxicity guardrail (CAP-5): `gravitee-io/distilbert-multilingual-toxicity-classifier`, the
ONNX quantized export, run by `onnxruntime` with a fast tokenizer — no torch.

shortcut: the documented fallback, `textdetox/bert-multilingual-toxicity-classifier`, has no
ONNX export on the Hub (only a 680 MB PyTorch `safetensors` file), which would need torch and
blow the brick's 1.5 GB RAM budget alone. Until a quantized ONNX build exists, a failed
download or load leaves the guardrail in `error` status (its message says why) instead of a
second model (upgrade: re-check the Hub for an ONNX textdetox export).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from wavestack import config
from wavestack.config import ModelFile
from wavestack.guardrails.contract import Classification, Entity
from wavestack.models.download import DownloadError, download_files, missing_files
from wavestack.models.engine import CancelToken

_REPO = (
    "https://huggingface.co/gravitee-io/distilbert-multilingual-toxicity-classifier/resolve/main/"
)
# Sizes checked by hand on 2026-10-16 (story 4): a real `GET`, not redistributed in the repo.
FILES = (
    ModelFile(url=_REPO + "model.quant.onnx", path="model.quant.onnx", size=135582999),
    ModelFile(url=_REPO + "tokenizer.json", path="tokenizer.json", size=2919627),
)
THRESHOLD = 0.5
TOXIC_LABEL = 1  # config.json: id2label.1 == "toxic"


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
        self._session = ort.InferenceSession(
            str(dest / "model.quant.onnx"), providers=["CPUExecutionProvider"]
        )

    def classify(self, text: str) -> Classification:
        self.ensure_loaded()
        encoded = self._tokenizer.encode(text)
        ids = np.array([encoded.ids], dtype=np.int64)
        mask = np.array([encoded.attention_mask], dtype=np.int64)
        inputs = {i.name: v for i, v in zip(self._session.get_inputs(), [ids, mask], strict=False)}
        logits = self._session.run(None, inputs)[0][0]
        probs = np.exp(logits) / np.exp(logits).sum()
        score = float(probs[TOXIC_LABEL])
        return Classification(detected=score >= THRESHOLD, score=score, threshold=THRESHOLD)

    def mask(self, text: str, entities: tuple[Entity, ...]) -> str:
        return text  # toxicity never masks: "signaler" only annotates

    def unload(self) -> None:
        self._session = None
        self._tokenizer = None


__all__ = ["ToxicityGuardrail", "DownloadError"]
