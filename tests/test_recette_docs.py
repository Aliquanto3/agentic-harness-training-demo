"""Lot K (A6): the llama-server install procedure of the acceptance-test documents.

`releases/latest` of ggml-org/llama.cpp may name a release without the Windows archive (v0.5.0
on 2026-09-29): the procedure reads the last ten releases and takes the first that has it.
"""

from __future__ import annotations

import re

import pytest

from wavestack import config

ARTIFACTS = config.repo_root() / "_bmad-output"
CAHIER = ARTIFACTS / "implementation-artifacts" / "cahier-recette-nuit-2026-09-28.html"
STORY_28 = (
    ARTIFACTS
    / "specs"
    / "spec-agentic-harness-training-demo"
    / "stories"
    / "28-guide-de-test-et-cahier-de-recette-corriges.md"
)
# An archive of the application may leave the BMAD documents out.
pytestmark = pytest.mark.skipif(
    not (CAHIER.exists() and STORY_28.exists()), reason="documents de recette absents"
)
ARCHIVE = r"'^llama-b\d+-bin-win-cpu-x64\.zip$'"


def _block(html: str, block_id: str) -> str:
    found = re.search(rf'<script type="text/plain" id="{block_id}">(.*?)</script>', html, re.S)
    assert found, block_id
    return found.group(1)


def test_install_block_takes_the_first_release_with_the_windows_archive():
    html = CAHIER.read_text(encoding="utf-8")
    install = _block(html, "cmd-llama-install")

    assert "releases/latest" not in install
    assert "/releases?per_page=10" in install
    assert f"$_.assets.name -match {ARCHIVE} }} | Select-Object -First 1" in install
    assert '$tag = "b11239"' in _block(html, "cmd-llama-fallback")  # the fallback stays


def test_story_28_procedure_no_longer_reads_releases_latest():
    text = STORY_28.read_text(encoding="utf-8")
    procedure = text.split("**Procédure llama-server**")[1].split("```", 2)[1]

    assert "releases/latest" not in procedure and "/releases?per_page=10" in procedure
    assert "lot K, point 8" in text.split("## Spec Change Log")[1].split("##")[0]


# Story 28 rewrote the README, the palier 2 guide and its cahier from the older procedure: the
# same correction there, and the three procedures stay word for word the same.
IMPLEMENTATION = ARTIFACTS / "implementation-artifacts"
PALIER_2 = {
    "README": config.repo_root() / "README.md",
    "guide": IMPLEMENTATION / "guide-test-pc-palier-2.md",
    "cahier": IMPLEMENTATION / "cahier-recette-palier-2.html",
}


def _install_procedure(path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index("$px = @{}   # erreur 407")
    return text[start : text.index("Expand-Archive", start)]


@pytest.mark.skipif(
    not all(path.exists() for path in PALIER_2.values()), reason="documents de recette absents"
)
def test_palier_2_procedures_take_the_first_release_with_the_windows_archive():
    procedures = {name: _install_procedure(path) for name, path in PALIER_2.items()}

    for name, install in procedures.items():
        assert "releases/latest" not in install, name
        assert "/releases?per_page=10" in install, name
        assert f"$_.assets.name -match {ARCHIVE} }} | Select-Object -First 1" in install, name
    assert procedures["guide"] == procedures["README"] == procedures["cahier"]
