"""The load registry (AD-8, NFR-2): every model load goes through it, one generative slot.

It holds what each loaded component was granted and refuses, in figures, a load that would
take WaveStack past its memory budget: `RSS measured − cost of the slot's current holder +
cost of the newcomer > budget`. The check comes before any release, so a refusal leaves the
active model loaded (AD-3). Story 15 adds the `embedding` slot (the RAG's model), refused
with its own message; reranking will add its slot next to them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from wavestack.config import CloudModel
from wavestack.models import probe

GENERATIVE = "generative"
EMBEDDING = "embedding"  # story 15: the RAG brick's embedding model
_GIB = 1024**3
_MIB = 1024**2


@dataclass(frozen=True)
class ModelChoice:
    """A model to load (AD-3): a GGUF file (`ref`: its path) or a declared cloud model
    (`ref`: its `id`, `entry`: its declaration)."""

    kind: str  # file | cloud
    ref: str
    entry: CloudModel | None = None
    # The candidate's readable name (discovery): an Ollama `model:tag`, else the file name.
    name: str | None = field(default=None, compare=False)

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


def _mo(n: int) -> str:
    """Bytes in Mo, rounded, French thousands separator: « 1 234 »."""
    return f"{round(n / _MIB):,}".replace(",", "\u202f")


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

    def embedding_cost(self, measured_rss_mb: int | None, file_sizes: list[int]) -> int:
        """Story 15: the RSS story 12 measured when declared, else the files' size plus the
        margin."""
        if measured_rss_mb:
            return measured_rss_mb * _MIB
        return sum(file_sizes) + self.margin_bytes

    def check_component(self, label: str, cost_bytes: int, slot: str) -> str | None:
        """The French refusal, in figures, when loading `label` (a brick's component) into
        `slot` would exceed the budget, else `None`."""
        held = self._slots.get(slot)
        without = max(0, self._rss() - (held.cost if held else 0))
        if without + cost_bytes <= self.budget_bytes:
            return None
        return (
            f"Mémoire insuffisante pour charger {label} : WaveStack occupe {_mo(without)} Mo, "
            f"il en faut environ {_mo(cost_bytes)} de plus, au-delà du budget de "
            f"{_mo(self.budget_bytes)} Mo. Désactivez une brique ou relevez [memory] budget_mb "
            "dans settings.json."
        )

    def grant(self, label: str, cost_bytes: int, slot: str = GENERATIVE) -> None:
        """`label` is loaded in `slot`: one holder per slot (the generative one: AD-8)."""
        self._slots[slot] = _Grant(label, cost_bytes)

    def release(self, slot: str = GENERATIVE) -> None:
        self._slots.pop(slot, None)

    def holder(self, slot: str = GENERATIVE) -> str | None:
        grant = self._slots.get(slot)
        return grant.label if grant else None
