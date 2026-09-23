"""AD-18: `static/tokens.css` must mirror DESIGN.md's frontmatter tokens exactly.

Parses both files independently (no shared code with the generator) so a
drift in either one fails this test.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from wavestack import config

_DESIGN_MD_MATCHES = list(
    (config.repo_root() / "_bmad-output" / "planning-artifacts" / "ux-designs").glob("*/DESIGN.md")
)
assert len(_DESIGN_MD_MATCHES) == 1, f"expected exactly one DESIGN.md, found {_DESIGN_MD_MATCHES}"
DESIGN_MD = _DESIGN_MD_MATCHES[0]
TOKENS_CSS = (
    Path(__file__).resolve().parents[1] / "src" / "wavestack" / "web" / "static" / "tokens.css"
)

_ATTR_TO_CSS = {
    "fontFamily": "font-family",
    "fontSize": "font-size",
    "fontWeight": "font-weight",
    "lineHeight": "line-height",
    "letterSpacing": "letter-spacing",
}


def _design_frontmatter() -> dict:
    text = DESIGN_MD.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "DESIGN.md must start with a YAML frontmatter block."
    return yaml.safe_load(match.group(1))


def _expected_tokens(frontmatter: dict) -> dict[str, str]:
    expected: dict[str, str] = {}
    for key, value in frontmatter["colors"].items():
        expected[f"--color-{key}"] = str(value)
    for key, attrs in frontmatter["typography"].items():
        for attr, value in attrs.items():
            expected[f"--typography-{key}-{_ATTR_TO_CSS[attr]}"] = str(value)
    for key, value in frontmatter["rounded"].items():
        expected[f"--rounded-{key}"] = str(value)
    for key, value in frontmatter["spacing"].items():
        expected[f"--spacing-{key}"] = str(value)
    return expected


def _css_custom_properties() -> dict[str, str]:
    text = TOKENS_CSS.read_text(encoding="utf-8")
    return {name: value.strip() for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", text)}


def test_tokens_css_matches_design_frontmatter():
    frontmatter = _design_frontmatter()
    expected = _expected_tokens(frontmatter)
    actual = _css_custom_properties()

    missing = expected.keys() - actual.keys()
    assert not missing, f"tokens.css is missing: {sorted(missing)}"

    mismatched = {
        name: (expected[name], actual[name])
        for name in expected
        if expected[name].strip("'\"") != actual[name].strip("'\"")
    }
    assert not mismatched, f"tokens.css values differ from DESIGN.md: {mismatched}"
