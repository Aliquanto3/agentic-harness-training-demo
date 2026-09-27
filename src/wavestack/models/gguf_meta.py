"""A GGUF file's metadata, read in pure Python (lot E): the header's key/values, no tensor.

llama-cpp-python shows an array value as text (`"arr[i32,24]"`), so the per-layer
`head_count_kv` of a hybrid model (Qwen3.5) is lost; and opening a file llama.cpp may
refuse must never happen in WaveStack's own process (AD-16). This reader stops before the
tensors: magic, version, counts, then the typed key/values, arrays as real lists. Long
arrays (the tokenizer's vocabulary) are skipped, their value `None`.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, BinaryIO

MAGIC = b"GGUF"
MAX_KEYS = 100_000  # a header announcing more is not a GGUF this reader trusts
MAX_ARRAY = 4096  # longer arrays are skipped (vocabulary, merges): their value is `None`
MAX_STRING = 1 << 24

# GGUF value types: struct format of the scalars.
_SCALARS = {
    0: "<B",  # uint8
    1: "<b",  # int8
    2: "<H",  # uint16
    3: "<h",  # int16
    4: "<I",  # uint32
    5: "<i",  # int32
    6: "<f",  # float32
    7: "<?",  # bool
    10: "<Q",  # uint64
    11: "<q",  # int64
    12: "<d",  # float64
}
_STRING, _ARRAY = 8, 9


class GGUFError(ValueError):
    """Not a GGUF header this reader can read."""


def _read(f: BinaryIO, n: int) -> bytes:
    data = f.read(n)
    if len(data) != n:
        raise GGUFError("fin de fichier inattendue")
    return data


def _unpack(f: BinaryIO, fmt: str) -> Any:
    return struct.unpack(fmt, _read(f, struct.calcsize(fmt)))[0]


def _string(f: BinaryIO, keep: bool = True) -> str | None:
    length = _unpack(f, "<Q")
    if length > MAX_STRING:
        raise GGUFError("chaîne trop longue")
    if not keep:
        f.seek(length, 1)
        return None
    return _read(f, length).decode("utf-8", "replace")


def _value(f: BinaryIO, kind: int, keep: bool = True) -> Any:
    if kind in _SCALARS:
        fmt = _SCALARS[kind]
        if not keep:
            f.seek(struct.calcsize(fmt), 1)
            return None
        return _unpack(f, fmt)
    if kind == _STRING:
        return _string(f, keep)
    if kind == _ARRAY:
        inner = _unpack(f, "<I")
        count = _unpack(f, "<Q")
        keep = keep and count <= MAX_ARRAY
        if inner in _SCALARS and not keep:  # fixed size: one seek
            f.seek(struct.calcsize(_SCALARS[inner]) * count, 1)
            return None
        values = [_value(f, inner, keep) for _ in range(count)]
        return values if keep else None
    raise GGUFError(f"type de valeur inconnu : {kind}")


def read_metadata(path: str | Path) -> dict[str, Any]:
    """The key/values of the GGUF header of `path` (versions 2 and 3). Raises `OSError` or
    `GGUFError`."""
    with open(path, "rb") as f:
        if f.read(4) != MAGIC:
            raise GGUFError("pas un fichier GGUF")
        version = _unpack(f, "<I")
        if version not in (2, 3):
            raise GGUFError(f"version GGUF non lue : {version}")
        _unpack(f, "<Q")  # tensor count
        n_keys = _unpack(f, "<Q")
        if n_keys > MAX_KEYS:
            raise GGUFError("en-tête GGUF illisible")
        meta: dict[str, Any] = {}
        for _ in range(n_keys):
            key = _string(f) or ""
            meta[key] = _value(f, _unpack(f, "<I"))
        return meta


def try_read_metadata(path: str | Path | None) -> dict[str, Any] | None:
    """`read_metadata`, or `None` when the file is absent or not a readable GGUF."""
    if not path:
        return None
    try:
        return read_metadata(path)
    except (OSError, GGUFError, UnicodeDecodeError, struct.error):
        return None
