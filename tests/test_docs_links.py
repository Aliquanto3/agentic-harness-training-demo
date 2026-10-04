"""The README stays a short onboarding page, and the links between the docs all resolve.

Anchors follow GitHub's heading slugs. An anchor with two hyphens in a row is refused: GitLab
collapses them, so the same link would break once the repository moves there.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from wavestack import config

ROOT = config.repo_root()
README = ROOT / "README.md"
DOCS = [
    README,
    ROOT / "CONTRIBUTING.md",
    *sorted((ROOT / "docs").glob("*.md")),
    ROOT / "tools" / "demo" / "README.md",
]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^[ \t]*```.*?^[ \t]*```", re.MULTILINE | re.DOTALL)  # list items indent


def _text(path: Path) -> str:
    return FENCE.sub("", path.read_text(encoding="utf-8"))


def _slug(heading: str) -> str:
    text = re.sub(r"[`*]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    return {_slug(m) for m in re.findall(r"^#{1,6} (.+)$", _text(path), re.MULTILINE)}


def _relative_links(path: Path) -> list[str]:
    return [t for t in LINK.findall(_text(path)) if not re.match(r"[a-z]+:", t)]


def _exists_with_exact_case(dest: Path) -> bool:
    """Windows and macOS ignore case, GitHub and GitLab do not: check every segment's spelling."""
    if not dest.exists():
        return False
    folder = ROOT
    for part in dest.relative_to(ROOT).parts:
        if part not in os.listdir(folder):
            return False
        folder = folder / part
    return True


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_resolve(path):
    for target in _relative_links(path):
        file_part, _, anchor = target.partition("#")
        # normpath, not resolve(): on Windows, resolve() would return the file's real case
        dest = Path(os.path.normpath(path.parent / file_part)) if file_part else path
        assert _exists_with_exact_case(dest), f"{target} : fichier absent (casse comprise)"
        if anchor and dest.suffix == ".md":
            assert "--" not in anchor, f"{target} : ancre différente sous GitLab"
            assert anchor in _anchors(dest), f"{target} : ancre absente de {dest.name}"


def test_readme_is_a_short_onboarding_page():
    text = README.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 100
    assert "docs/assets/wavestack-demo.gif" in text
    for doc in ("docs/installation.md", "docs/guide.md", "docs/modeles.md", "CONTRIBUTING.md"):
        assert f"]({doc})" in text, doc
