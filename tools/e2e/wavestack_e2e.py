"""WaveStack for the end-to-end tests: `wavestack.cli`, with the fake embedding model and
the slowed-down `fake_b` of `launch_app.py` (story 17).

No real embedding model is downloadable here: the RAG brick loads `tests/fake_embedder.py`
(a hashed bag of words) instead of llama.cpp. Everything else is the real application,
network guard first (`wavestack.cli` installs it when imported).

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

from wavestack.models import embedding  # noqa: E402

embedding.open_embedder = lambda model: FakeEmbedder(model_id=model.id)

if os.environ.get("WAVESTACK_E2E_NO_HEADROOM") == "1":
    # Story 20 (`run_e2e.py --no-headroom`): as a machine without the `compression` extra.
    from wavestack.compression import headroom_adapter  # noqa: E402

    _find_spec = headroom_adapter._find_spec
    headroom_adapter._find_spec = lambda name: None if name == "headroom" else _find_spec(name)

if __name__ == "__main__":
    raise SystemExit(cli.main())
