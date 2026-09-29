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
STATIC_DIR = Path(__file__).resolve().parents[1] / "src" / "wavestack" / "web" / "static"
TOKENS_CSS = STATIC_DIR / "tokens.css"

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


def test_tokens_css_declares_no_orphan_token():
    orphans = _css_custom_properties().keys() - _expected_tokens(_design_frontmatter()).keys()
    assert not orphans, f"tokens.css declares tokens absent from DESIGN.md: {sorted(orphans)}"


def test_no_static_file_loads_google_fonts():
    offenders = [
        path.name
        for path in STATIC_DIR.rglob("*")
        if path.suffix in {".html", ".css", ".js"}
        and "fonts.googleapis.com" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"static files reference fonts.googleapis.com: {offenders}"


def test_every_font_url_exists():
    text = (STATIC_DIR / "fonts.css").read_text(encoding="utf-8")
    urls = re.findall(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", text)
    assert len(urls) == 5, urls
    missing = [url for url in urls if not (STATIC_DIR / url).is_file()]
    assert not missing, f"fonts.css points to missing files: {missing}"


# ---------- story 33: contrasts of the discipline tokens, colours only through tokens ----------


def _luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of `#RRGGBB`."""
    value = hex_color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    light, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


# (foreground, background, ratio of the design note rounded to 0.1, WCAG AA threshold): 4.5
# for text, 3 for a stroke that carries meaning.
_PAIRS = [
    ("on-ink", "ink", 19.7, 4.5),
    ("on-ink-soft", "ink", 12.7, 4.5),
    ("on-ink", "discipline-prompt", 9.3, 4.5),
    ("on-ink", "discipline-context", 5.2, 4.5),
    ("on-ink", "discipline-harness", 5.6, 4.5),
    ("ink", "discipline-network", 8.7, 4.5),
    *(
        ("ink-soft", f"discipline-{name}-soft", None, 4.5)
        for name in ("prompt", "context", "harness", "network", "neutral")
    ),
    *(
        (f"discipline-{name}", "surface-raised", None, 3.0)
        for name in ("prompt", "context", "harness", "neutral")
    ),
]


# Story 32: what the call produced and its reasoning, then the JSON trees' text colours, on
# both backgrounds, on `surface-raised` and on each discipline's soft background (a section).
_STORY32_TEXT = [
    ("ink", "produced-soft", 16.9),
    ("ink-soft", "produced-soft", 7.4),
    ("ink", "reasoning-soft", 17.1),
    ("ink-soft", "reasoning-soft", 7.5),
    ("on-ink", "ink", 19.7),  # the « Produit par le modèle » tag
]
_JSON_FLOORS = {"json-key": 8.7, "json-string": 7.6, "json-literal": 6.2}
_JSON_BACKGROUNDS = [
    "produced-soft",
    "reasoning-soft",
    "surface-raised",
    *(f"discipline-{n}-soft" for n in ("prompt", "context", "harness", "network", "neutral")),
]


def test_story32_tokens_meet_wcag_aa():
    colors = _design_frontmatter()["colors"]
    failures = []
    for fg, bg, expected in _STORY32_TEXT:
        ratio = _contrast(colors[fg], colors[bg])
        if ratio < 4.5 or round(ratio, 1) != expected:
            failures.append(f"{fg} sur {bg} : {ratio:.2f} (attendu {expected})")
    for fg, floor in _JSON_FLOORS.items():
        lowest = min(_contrast(colors[fg], colors[bg]) for bg in _JSON_BACKGROUNDS)
        if round(lowest, 1) < floor or lowest < 4.5:
            failures.append(f"{fg} : {lowest:.2f} au plus bas (< {floor})")
    # The JSON colours are text colours only: none reuses a discipline's.
    disciplines = {v for k, v in colors.items() if k.startswith("discipline-")}
    failures += [fg for fg in _JSON_FLOORS if colors[fg] in disciplines]
    assert not failures, failures


def test_discipline_tokens_meet_wcag_aa():
    colors = _design_frontmatter()["colors"]
    failures = []
    for fg, bg, expected, threshold in _PAIRS:
        ratio = _contrast(colors[fg], colors[bg])
        if ratio < threshold or (expected is not None and round(ratio, 1) != expected):
            failures.append(f"{fg} sur {bg} : {ratio:.2f} (attendu {expected}, seuil {threshold})")
    soft_floor = min(
        _contrast(colors["ink-soft"], colors[f"discipline-{n}-soft"])
        for n in ("prompt", "context", "harness", "network", "neutral")
    )
    if soft_floor < 7.2:
        failures.append(f"ink-soft sur un fond doux : {soft_floor:.2f} (< 7,2)")
    assert not failures, failures


_COMMENTS = {
    ".css": re.compile(r"/\*.*?\*/", re.S),
    # Block comments, then line comments not preceded by `:` (a URL keeps its `//`).
    ".js": re.compile(r"/\*.*?\*/|(?<![:\\])//[^\n]*", re.S),
    # Story 25: a page with its style and script inline.
    ".html": re.compile(r"<!--.*?-->|/\*.*?\*/|(?<![:\\])//[^\n]*", re.S),
}
_HARD_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b(?![-\w])|\b(?:rgba?|hsla?)\(")


def test_app_css_and_js_write_no_color_outside_the_tokens():
    """Every colour goes through `tokens.css`, so a second theme (story 31) only redefines the
    tokens. CSS id selectors (`#gauge-bar`) are not colours: a hex colour is 3 to 8 hex digits
    not followed by a name character. Story 25: the `/models` page too."""
    offenders = []
    for name in ("app.css", "app.js", "models.html", "pages.css"):
        path = STATIC_DIR / name
        text = _COMMENTS[path.suffix].sub("", path.read_text(encoding="utf-8"))
        for line in text.splitlines():
            for match in _HARD_COLOR.finditer(line):
                offenders.append(f"{name}: {match.group(0)!r} in {line.strip()[:80]}")
    assert not offenders, offenders


# ---------- story 34: the projection mode's ramp (app.css), 9/7 of tokens.css ----------

APP_CSS = STATIC_DIR / "app.css"


def _projection_block() -> dict[str, str]:
    text = APP_CSS.read_text(encoding="utf-8")
    match = re.search(r":root\.projection\s*\{(.*?)\}", text, re.S)
    assert match, "app.css must redefine the ramp under :root.projection"
    return {n: v.strip() for n, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group(1))}


def test_projection_sizes_are_the_ramp_times_nine_sevenths():
    base = _css_custom_properties()
    projection = _projection_block()
    sizes = {
        n: v for n, v in base.items() if n.startswith("--typography-") and n.endswith("-font-size")
    }
    assert sizes.keys() <= projection.keys(), "every font size of the ramp is redefined"
    for name, value in sizes.items():
        expected = round(int(value.removesuffix("px")) * 9 / 7)
        assert projection[name] == f"{expected}px", name


def test_projection_sizes_match_the_design_table():
    projection = _projection_block()
    text = DESIGN_MD.read_text(encoding="utf-8")
    rows = re.findall(r"^\| (`[^|]+`) \| (\d+) px \| (\d+) px", text, re.M)
    assert rows, "DESIGN.md > Typography holds the projection table"
    seen = set()
    for roles, base, big in rows:
        for role in re.findall(r"`([\w.-]+)`", roles):
            name = (
                f"--{role.replace('.', '-')}"
                if role.startswith("spacing.")
                else f"--typography-{role}-font-size"
            )
            assert projection.get(name) == f"{big}px", (role, projection.get(name), big)
            if not role.startswith("spacing."):
                assert _css_custom_properties()[name] == f"{base}px", role
            seen.add(name)
    font_sizes = {n for n in projection if n.endswith("-font-size")}
    assert font_sizes <= seen, f"missing from the DESIGN.md table: {sorted(font_sizes - seen)}"
