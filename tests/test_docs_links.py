"""The README stays a short onboarding page, and the links between the docs all resolve.

Anchors follow GitHub's heading slugs. An anchor with two hyphens in a row is refused: GitLab
collapses them, so the same link would break once the repository moves there.
"""

from __future__ import annotations

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
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


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


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_relative_links_resolve(path):
    for target in _relative_links(path):
        file_part, _, anchor = target.partition("#")
        dest = (path.parent / file_part).resolve() if file_part else path
        assert dest.exists(), f"{target} : fichier absent"
        if anchor:
            assert "--" not in anchor, f"{target} : ancre différente sous GitLab"
            assert anchor in _anchors(dest), f"{target} : ancre absente de {dest.name}"


def test_readme_is_a_short_onboarding_page():
    text = README.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 100
    assert "docs/assets/wavestack-demo.gif" in text
    for doc in ("docs/installation.md", "docs/guide.md", "docs/modeles.md", "CONTRIBUTING.md"):
        assert f"]({doc})" in text, doc
