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

import os
import sys
from pathlib import Path

from wavestack import cli  # installs the network guard before anything else

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import launch_app  # noqa: E402, F401 - story 17: slows the preparation of `fake_b`
from fake_embedder import FakeEmbedder  # noqa: E402
from fake_reranker import FakeReranker  # noqa: E402

from wavestack.models import embedding, reranker  # noqa: E402

RERANK_FAILURE_MARK = "[reranker-en-panne]"


class _E2EReranker(FakeReranker):
    """Restes différés, story 6 (E094): the fake reranker breaks down on a question that
    carries `RERANK_FAILURE_MARK`, as a reranker that raises while it scores (AD-16: the
    turn goes on, with the embedding's order)."""

    def score(self, query, passages, cancelled=None, progress=None):  # noqa: ANN001, ANN201
        if RERANK_FAILURE_MARK in query:
            raise RuntimeError("reranker en panne (e2e)")
        return super().score(query, passages, cancelled, progress)


QUOTA_MARK = b"[quota0]"


def _install_quota_trace() -> None:
    """Recette du 02/10 (R2): the fake provider listens on 127.0.0.1, which the factory never
    traces (AD-15). A request whose body carries `QUOTA_MARK` is traced all the same, here
    only, so its refusal reaches the journal as `outbound_response`; every other request of
    the fake model stays untraced (the data-flow counts of the other scenarios are kept)."""
    from wavestack.net import factory

    traced = factory._traced

    def traced_or_marked(request) -> bool:  # noqa: ANN001
        if traced(request):
            return True
        try:
            return QUOTA_MARK in request.content
        except Exception:  # noqa: BLE001 - a stream not read yet: not a marked model call
            return False

    factory._traced = traced_or_marked


_install_quota_trace()
embedding.open_embedder = lambda model: FakeEmbedder(model_id=model.id)
reranker.open_reranker = lambda model: _E2EReranker(model_id=model.id)  # story 16

if os.environ.get("WAVESTACK_E2E_NO_HEADROOM") == "1":
    # Story 20 (`run_e2e.py --no-headroom`): as a machine without the `compression` extra.
    from wavestack.compression import headroom_adapter  # noqa: E402

    _find_spec = headroom_adapter._find_spec
    headroom_adapter._find_spec = lambda name: None if name == "headroom" else _find_spec(name)

if os.environ.get("WAVESTACK_E2E_NO_RAG_ALT") == "1":
    # Story 30 (`run_e2e.py --no-rag-alt`): as a machine without the `rag-alt` extra.
    from wavestack.rag import lab  # noqa: E402

    _lab_find_spec = lab._find_spec
    lab._find_spec = lambda name: None if name in ("faiss", "lancedb") else _lab_find_spec(name)

if os.environ.get("WAVESTACK_E2E_NO_GREENOPS") == "1":
    # GreenOps (`run_e2e.py --no-greenops`): as a machine without the `greenops` extra.
    from wavestack import greenops  # noqa: E402

    _green_find_spec = greenops._find_spec
    greenops._find_spec = lambda name: None if name == "codecarbon" else _green_find_spec(name)

if __name__ == "__main__":
    raise SystemExit(cli.main())
