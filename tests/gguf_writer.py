"""Writes a GGUF header (no tensor) for the tests: `write_gguf(path, metadata)`.

Integers are uint32 (a negative one int32), floats float32, booleans bool, strings UTF-8,
lists arrays of uint32 (or of strings). Enough for `wavestack.models.gguf_meta`.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any


def _string(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack("<Q", len(data)) + data


def _typed(value: Any) -> tuple[int, bytes]:
    if isinstance(value, bool):
        return 7, struct.pack("<?", value)
    if isinstance(value, int):
        return (5, struct.pack("<i", value)) if value < 0 else (4, struct.pack("<I", value))
    if isinstance(value, float):
        return 6, struct.pack("<f", value)
    if isinstance(value, str):
        return 8, _string(value)
    if isinstance(value, list):
        inner = 8 if value and isinstance(value[0], str) else 4
        items = b"".join(_typed(v)[1] for v in value)
        return 9, struct.pack("<IQ", inner, len(value)) + items
    raise TypeError(value)


def write_gguf(path: Path, metadata: dict[str, Any], version: int = 3) -> Path:
    body = b""
    for key, value in metadata.items():
        kind, data = _typed(value)
        body += _string(key) + struct.pack("<I", kind) + data
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", version, 0, len(metadata)) + body)
    return path
