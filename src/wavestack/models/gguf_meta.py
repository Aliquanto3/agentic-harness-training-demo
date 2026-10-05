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
_U64 = struct.Struct("<Q")
_SKIP_BLOCK = 1 << 20  # bytes read at once when skipping a long array of strings


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


def _skip_strings(f: BinaryIO, count: int) -> None:
    """Skip `count` strings (a vocabulary, its merges): their lengths walked in blocks read
    whole, not one read and one seek each (R1: about 500 000 per file, 3 times slower)."""
    buffer, offset = b"", 0
    for _ in range(count):
        if offset + 8 > len(buffer):
            if offset > len(buffer):  # the last string ends past the block
                f.seek(offset - len(buffer), 1)
                buffer, offset = b"", 0
            buffer, offset = buffer[offset:] + f.read(_SKIP_BLOCK), 0
            if len(buffer) < 8:
                raise GGUFError("fin de fichier inattendue")
        length = _U64.unpack_from(buffer, offset)[0]
        if length > MAX_STRING:
            raise GGUFError("chaîne trop longue")
        offset += 8 + length
    f.seek(offset - len(buffer), 1)  # back to the end of the last string


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
        if inner == _STRING and not keep:
            _skip_strings(f, count)
            return None
        values = [_value(f, inner, keep) for _ in range(count)]
        return values if keep else None
    raise GGUFError(f"type de valeur inconnu : {kind}")


def read_metadata(path: str | Path, stop_at: str | None = None) -> dict[str, Any]:
    """The key/values of the GGUF header of `path` (versions 2 and 3). Raises `OSError` or
    `GGUFError`. Lot 5c-1: `stop_at`, a key prefix (`tokenizer.`): the reading stops at the
    first key that starts with it, never read, nor anything after it (the header's head: the
    `general.*` and `{arch}.*` keys come before the tokenizer's)."""
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
            if stop_at is not None and key.startswith(stop_at):
                break
            meta[key] = _value(f, _unpack(f, "<I"))
        return meta


def try_read_metadata(path: str | Path | None, stop_at: str | None = None) -> dict[str, Any] | None:
    """`read_metadata`, or `None` when the file is absent or not a readable GGUF."""
    if not path:
        return None
    try:
        return read_metadata(path, stop_at)
    except (OSError, GGUFError, UnicodeDecodeError, struct.error):
        return None


# ---------- story 29: a model's sizes, for the « LLM nu » screen ----------


def positive_size(value: Any) -> int | None:
    """A positive integer, the largest of a list (a per-layer value); else `None`."""
    if isinstance(value, list):
        numbers = [v for v in (positive_size(v) for v in value) if v is not None]
        return max(numbers) if numbers else None
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value) if value > 0 else None


def dimensions_from_header(meta: dict[str, Any] | None) -> dict[str, int | None]:
    """A GGUF header's dimensions (`gguf_meta`): `{arch}.embedding_length`, `block_count`,
    `attention.head_count` (the largest when it is an array, one value per layer) and
    `context_length`; `None` for a key absent. The vocabulary is never read here: the
    header reader skips long arrays, the tokenizer says it."""
    meta = meta or {}
    arch = meta.get("general.architecture")
    arch = arch if isinstance(arch, str) and arch else None

    def key(name: str) -> int | None:
        return positive_size(meta.get(f"{arch}.{name}")) if arch else None

    return {
        "embedding_length": key("embedding_length"),
        "layer_count": key("block_count"),
        "head_count": key("attention.head_count"),
        "context_length": key("context_length"),
    }
