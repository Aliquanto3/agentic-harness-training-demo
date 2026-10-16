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


@pytest.mark.parametrize(
    "name",
    ["CON", "con.txt", "NUL", "COM1", "CON:x", "nul:x", "x/CON:y", "CONIN$", "conin$.txt"]
    + ["a.txt:stream", "col.txt"],
)
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


# ---------- the tools (review): called in-process, with a fake capture ----------


def _text(result) -> str:
    return result.content[0].text


def test_create_path_writes_a_file_and_a_folder_inside_the_sandbox():
    from wavestack.mcp import local_server

    assert not local_server.create_path("notes", kind="folder").is_error
    result = local_server.create_path("notes/a.txt", content="bonjour")

    assert not result.is_error and "notes/a.txt" in _text(result)
    assert (sandbox.sandbox_dir() / "notes" / "a.txt").read_text(encoding="utf-8") == "bonjour"


@pytest.mark.parametrize("name", ["../evil.txt", "CON", "a.txt:stream", " "])
def test_create_path_answers_an_mcp_error_and_writes_nothing(name):
    from wavestack.mcp import local_server

    result = local_server.create_path(name, content="x")

    assert result.is_error
    assert list(sandbox.sandbox_dir().iterdir()) == []


def test_create_path_refuses_overwriting_a_directory_or_a_file_and_too_much_content():
    from wavestack.mcp import local_server

    assert local_server.create_path(".", content="x").is_error  # the sandbox itself
    assert not local_server.create_path("a.txt", content="1").is_error
    assert local_server.create_path("a.txt", content="2").is_error
    assert local_server.create_path("a.txt.", content="2").is_error  # same file on Windows
    big = "x" * (local_server.MAX_CONTENT_BYTES + 1)
    assert local_server.create_path("big.txt", content=big).is_error
    assert (sandbox.sandbox_dir() / "a.txt").read_text(encoding="utf-8") == "1"
    assert not (sandbox.sandbox_dir() / "big.txt").exists()


class _FakeShot:
    """Stands for `mss.mss()`: no real screen is ever captured in a test."""

    monitors = [{}, {"left": 0, "top": 0, "width": 2, "height": 1}]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def grab(self, monitor):
        return type("Shot", (), {"rgb": b"\x00" * 6, "size": (2, 1)})()


def test_take_screenshot_saves_a_png_and_answers_only_its_path_and_size(monkeypatch):
    from wavestack.mcp import local_server

    monkeypatch.setattr(local_server.mss, "mss", _FakeShot)
    monkeypatch.setattr(local_server, "MAX_SCREENSHOTS", 2)

    for _ in range(3):
        result = local_server.take_screenshot()

    shots = sorted((sandbox.sandbox_dir() / "screenshots").glob("*.png"))
    assert len(shots) == 2  # the oldest is purged
    assert shots[-1].read_bytes().startswith(b"\x89PNG")
    text = _text(result)
    assert f"screenshots/{shots[-1].name}" in text and str(shots[-1].stat().st_size) in text
    assert len(result.content) == 1 and "PNG" not in text
