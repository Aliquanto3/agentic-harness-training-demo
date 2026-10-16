"""CAP-1: the local MCP server's sandbox, under the data directory (story 2).

Constraint: a path that resolves outside the sandbox is refused, whatever the escape
(`..`, an absolute path elsewhere, a symlink or a junction leading out), with a test.
Known limit: the check precedes the write, so a local actor who swaps a folder for a
junction in between could still redirect it (TOCTOU); the sandbox guards against the
model, not against a process already running on the workstation.
"""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath

from wavestack import config

# Windows reserved device names (any extension): `PureWindowsPath` parses them on every
# platform, since the demo targets a Windows workstation (AD-20).
_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    "conin$",
    "conout$",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
_DRIVE = re.compile(r"^[A-Za-z]:")


class SandboxError(ValueError):
    """A requested path escapes the sandbox, or names a reserved Windows device. `key` is
    its message under `mcp.sandbox.` (`content/messages.yaml`), `part` the culprit."""

    def __init__(self, key: str, part: str = "") -> None:
        super().__init__(f"{key}: {part}")
        self.key = key
        self.part = part


def sandbox_dir() -> Path:
    """The sandbox directory, created on first use (story 2's constraint: under `data_dir()`),
    resolved so that paths below it compare (8.3 names, junctions, redirected profile)."""
    path = config.data_dir() / "mcp_sandbox"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def resolve(name: str) -> Path:
    """`name` resolved inside the sandbox. Raises `SandboxError` when it escapes it once
    resolved (a symlink or a junction followed), when a path component is a reserved
    Windows name, whatever its extension, or when it holds a `:` past a drive letter (an
    NTFS stream or a device such as `CON:`)."""
    if not name or not name.strip():
        raise SandboxError("empty")
    if ":" in _DRIVE.sub("", name, count=1):
        raise SandboxError("reserved", name)
    for part in PureWindowsPath(name).parts:
        if part.split(".")[0].rstrip(" ").lower() in _RESERVED:
            raise SandboxError("reserved", part)
    base = sandbox_dir()
    candidate = (base / name).resolve()
    if candidate != base and not candidate.is_relative_to(base):
        raise SandboxError("outside", name)
    return candidate
