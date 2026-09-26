"""The global memory of the `global_memory` brick: `memory.json` in the data folder (AD-20).

The session alone reads and writes it, through `MemoryWrite` effects (AD-23); this module
holds its format, its texts from `content/memory/memory.yaml` (AD-19) and the pure helpers.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, TypeAdapter

from wavestack import config
from wavestack.session.effects import MemoryWrite

MAX_ENTRIES = 20  # H3: keeps the system message within a 4 096-token window
MAX_CHARS = 300

Source = Literal["model", "user", "demo"]


class MemoryEntry(BaseModel):
    """One entry of `memory.json` (AD-20)."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    created_at: str
    source: Source


_ENTRIES = TypeAdapter(list[MemoryEntry])


class RememberText(BaseModel):
    """The harness meta-tool of the brick (AD-25)."""

    label_fr: str = Field(min_length=1)
    description: str = Field(min_length=1)  # seen by the model
    text: str = Field(min_length=1)  # the `text` parameter's description


class MemoryContent(BaseModel):
    """`content/memory/memory.yaml`."""

    file_label_fr: str = Field(min_length=1)  # the `file.memory` node of the schema
    intro: str = Field(min_length=1)  # seen by the model, before the entries
    remember: RememberText
    demo: list[str] = Field(min_length=1, max_length=MAX_ENTRIES)


def load_memory_content() -> MemoryContent:
    """Raises on a missing or invalid file (the session traces it)."""
    path = config.content_dir() / "memory" / "memory.yaml"
    return MemoryContent.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def read_memory(path: Path) -> list[MemoryEntry] | None:
    """`None` when the file does not exist. Raises on an unreadable or invalid file."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return _ENTRIES.validate_python(json.loads(text))


def write_memory(path: Path, entries: Iterable[MemoryEntry]) -> None:
    """An atomic replace (temporary file, then `os.replace`). Raises OSError on failure."""
    data = [entry.model_dump() for entry in entries]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def check_text(text: str | None) -> str:
    """The text of an entry, stripped. Raises `ValueError` with the French reason."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Le texte à retenir est vide : rien n'est écrit.")
    if len(text) > MAX_CHARS:
        raise ValueError(
            f"Le texte à retenir fait {len(text)} caractères, pour {MAX_CHARS} au plus : "
            "rien n'est écrit."
        )
    return text


def same_text(a: str, b: str) -> bool:
    """H10: a duplicate, ignoring case and edge blanks."""
    return a.strip().casefold() == b.strip().casefold()


def new_entry_id() -> str:
    return f"m{secrets.token_hex(4)}"


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def demo_entries(texts: Iterable[str], created_at: str) -> list[MemoryEntry]:
    return [
        MemoryEntry(id=f"demo{i}", text=text, created_at=created_at, source="demo")
        for i, text in enumerate(texts, start=1)
    ]


def apply_writes(
    entries: list[MemoryEntry], writes: Iterable[MemoryWrite], source: Source, created_at: str
) -> list[MemoryEntry]:
    """The entries once `writes` are applied in order, on a copy. `replace` keeps the id
    and the creation date. Raises `KeyError` for an unknown id."""
    result = list(entries)
    for write in writes:
        if write.op == "add":
            result.append(
                MemoryEntry(
                    id=write.entry_id, text=write.text, created_at=created_at, source=source
                )
            )
            continue
        at = next((i for i, e in enumerate(result) if e.id == write.entry_id), None)
        if at is None:
            raise KeyError(write.entry_id)
        if write.op == "replace":
            result[at] = result[at].model_copy(update={"text": write.text, "source": source})
        else:
            del result[at]
    return result
