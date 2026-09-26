"""The load registry (AD-8, NFR-2): every model load goes through it, one generative slot.

It holds what each loaded component was granted and refuses, in figures, a load that would
take WaveStack past its memory budget: `RSS measured − cost of the slot's current holder +
cost of the newcomer > budget`. The check comes before any release, so a refusal leaves the
active model loaded (AD-3). Later stories add their non-generative slots (embedding,
reranking) next to `generative`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from wavestack.config import CloudModel
from wavestack.models import probe

GENERATIVE = "generative"
_GIB = 1024**3


@dataclass(frozen=True)
class ModelChoice:
    """A model to load (AD-3): a GGUF file (`ref`: its path), a model an already-running
    local server serves (`ref`: `ollama/{name}` or `llama_server/{file}`, `server`: its
    discovery candidate, story 18) or a declared cloud model (`ref`: its `id`, `entry`: its
    declaration)."""

    kind: str  # file | server | cloud
    ref: str
    entry: CloudModel | None = None
    # The candidate's readable name (discovery): an Ollama `model:tag`, else the file name.
    name: str | None = field(default=None, compare=False)
    # `kind = server`: the `discovery.ModelCandidate` (engine, address, GGUF of `ollama_raw`).
    server: Any = field(default=None, compare=False)

    @classmethod
    def served(cls, candidate: Any) -> ModelChoice:
        """The choice of a served-model candidate (`discovery.ModelCandidate`, story 18)."""
        return cls("server", candidate.ref, name=candidate.name, server=candidate)

    @property
    def provider(self) -> str | None:
        """A served model's server: « Ollama » or « llama-server »."""
        return getattr(self.server, "provider", None) if self.server is not None else None

    @property
    def label(self) -> str:
        """The model's name everywhere (indicator, schema, messages): the cloud `model`, an
        Ollama `model:tag`, else the file name without `.gguf` (never a `sha256-…` blob)."""
        if self.entry is not None:
            return self.entry.model
        if self.name and not self.name.lower().endswith(".gguf"):
            return self.name
        return Path(self.ref).stem

    @property
    def file_name(self) -> str:
        """What « Chargement du modèle … » names: the candidate's name, else the file's."""
        return self.name or Path(self.ref).name

    def same_as(self, other: ModelChoice | None) -> bool:
        return other is not None and (self.kind, self.ref) == (other.kind, other.ref)


def process_rss() -> int:
    """WaveStack's resident memory: this process and its children, recursively."""
    process = psutil.Process()
    total = process.memory_info().rss
    for child in process.children(recursive=True):
        try:
            total += child.memory_info().rss
        except psutil.Error:
            continue  # a child gone meanwhile
    return total


def _go(n: int) -> str:
    """Bytes in Go, one decimal, French decimal comma: « 3,1 Go »."""
    return f"{n / _GIB:.1f}".replace(".", ",") + " Go"


@dataclass
class _Grant:
    label: str
    cost: int


class LoadRegistry:
    """AD-8: the loaded components and their granted cost, by slot."""

    def __init__(
        self,
        budget_bytes: int,
        margin_bytes: int,
        rss_fn: Callable[[], int] = process_rss,
    ) -> None:
        self.budget_bytes = budget_bytes
        self.margin_bytes = margin_bytes
        self._rss = rss_fn
        self._slots: dict[str, _Grant] = {}

    def file_cost(self, path: str, window: int) -> int:
        """A GGUF's estimated cost: the probe's measured RSS or the file's size, whichever is
        larger; plus its KV cache at `window` tokens (0 when the probe did not read it); plus
        the margin."""
        entry = probe.probed_entry(path) or {}
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = 0
        # The probe's measure, but never less than the file: mmap'd weights may not all be
        # resident when the probe measures them.
        weights = max(int(entry.get("rss_bytes") or 0), size)
        kv = (entry.get("kv_bytes_per_token") or 0) * max(window, 0)
        return int(weights) + int(kv) + self.margin_bytes

    def check(self, label: str, cost_bytes: int, slot: str = GENERATIVE) -> str | None:
        """The French refusal when loading `label` into `slot` would exceed the budget, else
        `None`. A zero cost (a cloud model) is never refused: it only frees memory."""
        if cost_bytes <= 0:
            return None
        held = self._slots.get(slot)
        without = max(0, self._rss() - (held.cost if held else 0))
        if without + cost_bytes <= self.budget_bytes:
            return None
        stays = f" {held.label} reste actif." if held else ""
        return (
            f"Changement refusé : {label} demande environ {_go(cost_bytes)} ; WaveStack occupe "
            f"{_go(without)} sans le modèle actif, pour un budget de {_go(self.budget_bytes)}."
            f"{stays} Choisissez un modèle plus petit."
        )

    def grant(self, label: str, cost_bytes: int, slot: str = GENERATIVE) -> None:
        """`label` is loaded in `slot`: one holder per slot (the generative one: AD-8)."""
        self._slots[slot] = _Grant(label, cost_bytes)

    def release(self, slot: str = GENERATIVE) -> None:
        self._slots.pop(slot, None)

    def holder(self, slot: str = GENERATIVE) -> str | None:
        grant = self._slots.get(slot)
        return grant.label if grant else None
