"""CAP-1: the local MCP server's sandbox, under the data directory (story 2).

Constraint: a path that resolves outside the sandbox is refused, whatever the escape
(`..`, an absolute path elsewhere, a symlink or a junction leading out), with a test.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

from wavestack import config

# Windows reserved device names (any extension): `PureWindowsPath` parses them on every
# platform, since the demo targets a Windows workstation (AD-20).
_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class SandboxError(ValueError):
    """A requested path escapes the sandbox, or names a reserved Windows device."""


def sandbox_dir() -> Path:
    """The sandbox directory, created on first use (story 2's constraint: under `data_dir()`)."""
    path = config.data_dir() / "mcp_sandbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve(name: str) -> Path:
    """`name` resolved inside the sandbox. Raises `SandboxError` when it escapes it once
    resolved (a symlink or a junction followed), or when a path component is a reserved
    Windows name, whatever its extension."""
    if not name or not name.strip():
        raise SandboxError("chemin vide")
    for part in PureWindowsPath(name).parts:
        if part.split(".")[0].rstrip(" ").lower() in _RESERVED:
            raise SandboxError(f"nom réservé Windows : {part}")
    base = sandbox_dir()
    candidate = (base / name).resolve()
    resolved_base = base.resolve()
    if candidate != resolved_base and not candidate.is_relative_to(resolved_base):
        raise SandboxError(f"chemin hors du bac à sable : {name}")
    return candidate
