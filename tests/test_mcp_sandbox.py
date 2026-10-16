"""Story 2 (CAP-1): the local MCP server's sandbox under the data directory.

Constraint: any path that resolves outside the sandbox is refused.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from wavestack.mcp import sandbox


def test_a_relative_path_resolves_inside_the_sandbox():
    target = sandbox.resolve("notes/a.txt")

    assert target == sandbox.sandbox_dir() / "notes" / "a.txt"


def test_dot_dot_is_refused():
    with pytest.raises(sandbox.SandboxError):
        sandbox.resolve("../evil.txt")


def test_dot_dot_buried_in_a_longer_path_is_refused():
    with pytest.raises(sandbox.SandboxError):
        sandbox.resolve("notes/../../evil.txt")


def test_an_absolute_path_elsewhere_is_refused(tmp_path):
    with pytest.raises(sandbox.SandboxError):
        sandbox.resolve(str(tmp_path / "elsewhere.txt"))


@pytest.mark.parametrize("name", ["CON", "con.txt", "NUL", "COM1", "col.txt"])
def test_a_reserved_windows_name_is_refused_whatever_its_extension(name):
    if name == "col.txt":  # not reserved: a near-miss must still be accepted
        sandbox.resolve(name)
        return
    with pytest.raises(sandbox.SandboxError):
        sandbox.resolve(name)


@pytest.mark.skipif(sys.platform != "win32", reason="junction : NTFS seulement")
def test_a_junction_leading_out_of_the_sandbox_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    base = sandbox.sandbox_dir()
    link = base / "escape"
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
    )

    with pytest.raises(sandbox.SandboxError):
        sandbox.resolve("escape/evil.txt")
