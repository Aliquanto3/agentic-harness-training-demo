"""WaveStack for the end-to-end tests: `wavestack.cli`, with the fake embedding and reranking
models and the slowed-down `fake_b` of `launch_app.py` (story 17).

No real embedding or reranking model is downloadable here: the RAG brick loads
`tests/fake_embedder.py` (a hashed bag of words) and its reranking sub-option
`tests/fake_reranker.py` (words shared with the question) instead of llama.cpp. Everything
else is the real application, network guard first (`wavestack.cli` installs it when
imported).

Run by `stack.py`: `python tools/e2e/wavestack_e2e.py --port N`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from wavestack import cli  # installs the network guard before anything else

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import launch_app  # noqa: E402, F401 - story 17: slows the preparation of `fake_b`
from fake_embedder import FakeEmbedder  # noqa: E402
from fake_reranker import FakeReranker  # noqa: E402

from wavestack.models import embedding, reranker  # noqa: E402

embedding.open_embedder = lambda model: FakeEmbedder(model_id=model.id)
reranker.open_reranker = lambda model: FakeReranker(model_id=model.id)  # story 16

if __name__ == "__main__":
    raise SystemExit(cli.main())
