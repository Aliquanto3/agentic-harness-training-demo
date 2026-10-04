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
    """The `:root` block: every light colour (story 31: not the `-dark` twins, which the dark
    blocks carry under the light names), then the type ramp, the radii and the spacing."""
    expected: dict[str, str] = {}
    for key, value in frontmatter["colors"].items():
        if not key.endswith(_DARK):
            expected[f"--color-{key}"] = str(value)
    for key, attrs in frontmatter["typography"].items():
        for attr, value in attrs.items():
            expected[f"--typography-{key}-{_ATTR_TO_CSS[attr]}"] = str(value)
    for key, value in frontmatter["rounded"].items():
        expected[f"--rounded-{key}"] = str(value)
    for key, value in frontmatter["spacing"].items():
        expected[f"--spacing-{key}"] = str(value)
    return expected


# ---------- story 31: tokens.css in three blocks, the light theme, then the dark one twice ---

_DARK = "-dark"
_BLOCKS = {
    "root": re.compile(r"^:root\s*\{(.*?)^\}", re.S | re.M),
    "dark": re.compile(r'^:root\[data-theme="dark"\]\s*\{(.*?)^\}', re.S | re.M),
    "media": re.compile(
        r"^@media \(prefers-color-scheme: dark\)\s*\{\s*"
        r":root:not\(\[data-theme\]\)\s*\{(.*?)\}\s*^\}",
        re.S | re.M,
    ),
}


def _tokens_blocks() -> dict[str, str]:
    """The body of each block of tokens.css; nothing else is declared there (a fourth block, or
    a declaration outside them, would redefine a token behind the test's back)."""
    text = re.sub(r"/\*.*?\*/", "", TOKENS_CSS.read_text(encoding="utf-8"), flags=re.S)
    blocks = {}
    rest = text
    for name, pattern in _BLOCKS.items():
        found = pattern.findall(text)
        assert len(found) == 1, f"tokens.css: {len(found)} bloc(s) {name}, un seul attendu"
        blocks[name] = found[0]
        rest = pattern.sub("", rest)
    assert not rest.strip(), f"tokens.css declares outside its three blocks: {rest.strip()[:80]}"
    return blocks


def _declarations(block: str) -> dict[str, str]:
    return {name: value.strip() for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)}


def _color_scheme(block: str) -> str | None:
    match = re.search(r"(?<![\w-])color-scheme\s*:\s*([^;]+);", block)
    return match.group(1).strip() if match else None


def _css_custom_properties() -> dict[str, str]:
    """The `:root` block's custom properties (the light theme, the ramp, radii, spacing)."""
    return _declarations(_tokens_blocks()["root"])


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


def _twin_gaps(colors: dict) -> list[str]:
    """Story 31: what breaks « every colour X has its X-dark, and every X-dark its X »."""
    light = {k for k in colors if not k.endswith(_DARK)}
    dark = {k.removesuffix(_DARK) for k in colors if k.endswith(_DARK)}
    return [f"{k}-dark manque" for k in sorted(light - dark)] + [
        f"{k}-dark sans {k}" for k in sorted(dark - light)
    ]


def test_every_color_has_its_dark_twin_and_back():
    gaps = _twin_gaps(_design_frontmatter()["colors"])
    assert not gaps, gaps


def test_removing_one_dark_twin_is_caught():
    """The coverage check itself: any single `X-dark` taken out is reported."""
    colors = _design_frontmatter()["colors"]
    for twin in [k for k in colors if k.endswith(_DARK)]:
        mutated = {k: v for k, v in colors.items() if k != twin}
        assert _twin_gaps(mutated) == [f"{twin.removesuffix(_DARK)}-dark manque"], twin


def _dark_expected(colors: dict) -> dict[str, str]:
    return {
        f"--color-{k}": str(colors[f"{k}{_DARK}"]).upper()
        for k in colors
        if not k.endswith(_DARK) and f"{k}{_DARK}" in colors
    }


def test_dark_block_redefines_every_color_with_its_twin():
    """`:root[data-theme="dark"]` = exactly `{--color-X: X-dark}`, for every colour; nothing
    else (no `--color-X-dark` of its own, no other token)."""
    colors = _design_frontmatter()["colors"]
    dark = {n: v.upper() for n, v in _declarations(_tokens_blocks()["dark"]).items()}
    assert dark == _dark_expected(colors)
    light = [k for k in colors if not k.endswith(_DARK)]
    assert len(dark) == len(light), "one declaration per colour"


def test_media_block_is_the_dark_block():
    """« Système » on a dark workstation: the very same declarations, without the attribute."""
    blocks = _tokens_blocks()
    assert _declarations(blocks["media"]) == _declarations(blocks["dark"])


def test_color_scheme_follows_the_theme():
    blocks = _tokens_blocks()
    assert _color_scheme(blocks["root"]) == "light"
    assert _color_scheme(blocks["dark"]) == "dark"
    assert _color_scheme(blocks["media"]) == "dark"


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


# ---------- story 31: the contrasts of both palettes ----------


def _palette(colors: dict, dark: bool) -> dict[str, str]:
    """The light colours, or their `-dark` twins under the light names."""
    return {
        k: str(colors[f"{k}{_DARK}"] if dark else v)
        for k, v in colors.items()
        if not k.endswith(_DARK)
    }


_TEXT_BACKGROUNDS = [
    "surface",
    "surface-raised",
    "primary-soft",
    "accent-soft",
    "warning-soft",
    "danger-soft",
    *(f"discipline-{n}-soft" for n in ("prompt", "context", "harness", "network", "neutral")),
    "produced-soft",
    "reasoning-soft",
]
_VIVID = [
    "hosting-network",
    "warning",
    "discipline-network",
    "discipline-neutral",
    "state-active",
    "accent",
    "danger",
    "state-error",
]

# (foreground, background, WCAG AA threshold), checked in both palettes (DESIGN.md > Colors >
# Thème sombre): 4.5 for text, 3 for a stroke that carries meaning. `_PAIRS` above stays.
_THEME_PAIRS = [
    *((fg, bg, 4.5) for fg in ("ink", "ink-soft") for bg in _TEXT_BACKGROUNDS),
    ("primary", "surface-raised", 4.5),
    ("primary-deep", "primary-soft", 4.5),
    ("on-primary", "primary", 4.5),
    ("on-ink", "ink-fill", 4.5),
    ("on-ink-soft", "ink-fill", 4.5),
    *(("on-discipline", f"discipline-{n}", 4.5) for n in ("prompt", "context", "harness")),
    *(("on-vivid", bg, 4.5) for bg in _VIVID),
    *(
        (f"discipline-{n}", bg, 3.0)
        for n in ("prompt", "context", "harness", "neutral")
        for bg in ("surface", "surface-raised")
    ),
    *((fg, bg, 4.5) for fg in _JSON_FLOORS for bg in _JSON_BACKGROUNDS),
    # Non-text, 3:1: a control's on-ink-soft border on the ink-fill bar; the edge of an ink-fill
    # piece (top bar, bubble, tile, plate) on the page and on a pane.
    ("on-ink-soft", "ink-fill", 3.0),
    ("ink-fill-edge", "surface", 3.0),
    ("ink-fill-edge", "surface-raised", 3.0),
]

# Dark only: the light palette already fails them, as documented (red text on white 3.7:1,
# the pale segments on cream).
_DARK_ONLY_PAIRS = [
    ("danger", "surface-raised", 4.5),
    *(
        (f"segment-{s}", "segment-free", 3.0)
        for s in (
            "system-prompt",
            "global-memory",
            "tool-descriptions",
            "history",
            "rag",
            "tool-results",
            "message",
        )
    ),
]

# The dark figures of the DESIGN.md table, rounded to 0.1.
_DARK_RATIOS = {
    ("primary", "surface-raised"): 5.7,
    ("primary-deep", "primary-soft"): 8.4,
    ("on-primary", "primary"): 6.7,
    ("on-ink", "ink-fill"): 12.5,
    ("on-ink-soft", "ink-fill"): 8.0,
    ("on-discipline", "discipline-prompt"): 6.7,
    ("on-discipline", "discipline-context"): 7.8,
    ("on-discipline", "discipline-harness"): 6.2,
    ("danger", "surface-raised"): 6.0,
}

# The dark floors of the DESIGN.md table: the lowest ratio of each group, rounded to 0.1.
_DARK_FLOORS = [
    (
        "ink et encre douce sur un fond de texte",
        6.2,
        [(fg, bg) for fg in ("ink", "ink-soft") for bg in _TEXT_BACKGROUNDS],
    ),
    ("on-vivid sur un fond vif", 5.8, [("on-vivid", bg) for bg in _VIVID]),
    (
        "disciplines sur surface et surface-raised",
        4.9,
        [
            (f"discipline-{n}", bg)
            for n in ("prompt", "context", "harness", "neutral")
            for bg in ("surface", "surface-raised")
        ],
    ),
    (
        "encre sur les fonds produits",
        7.4,
        [(fg, bg) for fg in ("ink", "ink-soft") for bg in ("produced-soft", "reasoning-soft")],
    ),
    (
        "couleurs JSON sur leurs fonds",
        6.6,
        [(fg, bg) for fg in _JSON_FLOORS for bg in _JSON_BACKGROUNDS],
    ),
    (
        "segments sur l'espace libre",
        4.1,
        [(fg, bg) for fg, bg, threshold in _DARK_ONLY_PAIRS if threshold == 3.0],
    ),
    (
        "bord d'ink-fill sur la page",
        3.5,
        [("ink-fill-edge", "surface"), ("ink-fill-edge", "surface-raised")],
    ),
]


def test_both_palettes_meet_wcag_aa():
    colors = _design_frontmatter()["colors"]
    failures = []
    for dark in (False, True):
        palette = _palette(colors, dark)
        theme = "sombre" if dark else "clair"
        for fg, bg, threshold in _THEME_PAIRS + (_DARK_ONLY_PAIRS if dark else []):
            ratio = _contrast(palette[fg], palette[bg])
            expected = _DARK_RATIOS.get((fg, bg)) if dark else None
            if ratio < threshold or (expected is not None and round(ratio, 1) != expected):
                failures.append(f"{theme} : {fg} sur {bg} : {ratio:.2f} (seuil {threshold})")
    dark = _palette(colors, True)
    for what, floor, pairs in _DARK_FLOORS:
        lowest = min(_contrast(dark[fg], dark[bg]) for fg, bg in pairs)
        if round(lowest, 1) < floor:
            failures.append(f"sombre : {what} à {lowest:.2f} (< {floor})")
    # The JSON colours stay distinct from the disciplines in the dark palette too.
    disciplines = {v for k, v in dark.items() if k.startswith("discipline-")}
    failures += [
        f"sombre : {fg} = une discipline" for fg in _JSON_FLOORS if dark[fg] in disciplines
    ]
    assert not failures, failures


def test_role_tokens_keep_the_light_theme():
    """The role tokens split from an existing one take, in light, the value their role had
    before the story: the light theme does not move. `warning-soft` and `danger-soft` are new
    values (the diagnostic page's backgrounds, formerly written in the page)."""
    colors = _design_frontmatter()["colors"]
    assert colors["ink-fill"] == colors["ink"]
    assert colors["ink-fill-edge"] == colors["ink-fill"]
    assert colors["on-discipline"] == colors["on-ink"]
    assert colors["on-vivid"] == colors["ink"]


# ---------- colours only through tokens.css, in every page of static/ (stories 33, 25, 31) ---

_COMMENTS = {
    ".css": re.compile(r"/\*.*?\*/", re.S),
    # Block comments, then line comments not preceded by `:` (a URL keeps its `//`).
    ".js": re.compile(r"/\*.*?\*/|(?<![:\\])//[^\n]*", re.S),
    # A page with its style and script inline (story 25); its entities (`&#9680;`) too.
    ".html": re.compile(r"<!--.*?-->|/\*.*?\*/|(?<![:\\])//[^\n]*|&#\w+;", re.S),
}
_HARD_COLOR = re.compile(
    r"#[0-9a-fA-F]{3,8}\b(?![-\w])|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\("
)

# The CSS named colours (CSS Color 4), matched only as a value: in a declaration of a
# stylesheet, a `<style>` or a `style=""`, or assigned to a colour property in a script.
_NAMED_COLORS = (
    "aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue "
    "blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk "
    "crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki "
    "darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen "
    "darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue "
    "dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite "
    "gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki "
    "lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan "
    "lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen "
    "lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen "
    "magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen "
    "mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream "
    "mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid "
    "palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum "
    "powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown "
    "seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen "
    "steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow "
    "yellowgreen"
).split()
_NAMED = "|".join(_NAMED_COLORS)
_CSS_DECLARATION = re.compile(r"(?<![\w-])[\w-]+\s*:\s*([^;{}]*)")
_CSS_STRING = re.compile(r"\"[^\"]*\"|'[^']*'")
_CSS_NAMED = re.compile(rf"(?<![\w-])(?:{_NAMED})(?![\w-])", re.I)
_JS_NAMED = re.compile(
    rf"\b(?:color|background(?:Color)?|fill|stroke|border(?:Color)?|outline(?:Color)?)\b"
    rf"[\"']?\s*[:=,]\s*[\"'`]\s*(?:{_NAMED})\b",
    re.I,
)
_HTML_CSS = re.compile(r"<style\b[^>]*>(.*?)</style>|\bstyle=\"([^\"]*)\"", re.S)
# `color-mix(` only between tokens: once its `var(--…)`, its `in <space>` and its
# percentages taken out, nothing but punctuation remains.
_COLOR_MIX = re.compile(r"color-mix\(((?:[^()]|\([^()]*\))*)\)", re.I)
_MIX_ALLOWED = re.compile(r"var\(--[\w-]+\)|\bin\s+[\w-]+|\d+(?:\.\d+)?%|[\s,]|transparent")


def _css_of(path: Path, text: str) -> str:
    if path.suffix == ".css":
        return text
    if path.suffix == ".html":
        return "\n".join(a or b for a, b in _HTML_CSS.findall(text))
    return ""


def _named_color_offenders(path: Path, text: str) -> list[str]:
    offenders = []
    for value in _CSS_DECLARATION.findall(_css_of(path, text)):
        value = _CSS_STRING.sub("", value)
        offenders += [
            f"{path.name}: {m.group(0)!r} in {value.strip()[:60]}"
            for m in _CSS_NAMED.finditer(value)
        ]
        for mix in _COLOR_MIX.findall(value):
            if _MIX_ALLOWED.sub("", mix):
                offenders.append(f"{path.name}: color-mix with a literal colour: {mix[:60]}")
    if path.suffix in {".js", ".html"}:
        offenders += [f"{path.name}: {m.group(0)!r}" for m in _JS_NAMED.finditer(text)]
    return offenders


def _static_sources() -> list[Path]:
    """Every page, stylesheet and script of static/ but tokens.css, the only home of colours;
    a page added later (stories 29, 30) is covered without touching this test."""
    return sorted(
        path
        for path in STATIC_DIR.rglob("*")
        if path.suffix in _COMMENTS and path.name != "tokens.css"
    )


def test_static_files_write_no_color_outside_the_tokens():
    """Every colour goes through `tokens.css`, so the dark theme (story 31) only redefines the
    tokens. CSS id selectors (`#gauge-bar`) are not colours: a hex colour is 3 to 8 hex digits
    not followed by a name character."""
    sources = _static_sources()
    names = {path.name for path in sources}
    assert {"app.css", "app.js", "theme.js", "diagnostic.html", "pages.css"} <= names
    assert {"llm.html", "llm.css", "llm.js"} <= names  # story 29: the « LLM nu » screen
    assert {"rag.html", "rag.css", "rag.js"} <= names  # story 30: the RAG workshop
    assert {"mcp.html", "mcp.css", "mcp.js"} <= names  # story 6 (2026-09-30): MCP workshop
    offenders = []
    for path in sources:
        text = _COMMENTS[path.suffix].sub("", path.read_text(encoding="utf-8"))
        for line in text.splitlines():
            for match in _HARD_COLOR.finditer(line):
                offenders.append(f"{path.name}: {match.group(0)!r} in {line.strip()[:80]}")
            if "invert(" in line:
                offenders.append(f"{path.name}: a filter inverts the colours: {line.strip()[:80]}")
        offenders += _named_color_offenders(path, text)
    assert not offenders, offenders


def test_the_color_guard_catches_named_colours_and_colour_functions():
    """The guard itself: named colours as values, the colour functions and a `color-mix(` with
    a literal colour are caught; `white-space`, a class name, a token mix are not."""
    css = Path("x.css")
    caught = [
        ".a { color: white; }",
        ".a { border: 1px solid Red; }",
        ".a { background: color-mix(in srgb, var(--color-ink) 50%, black); }",
        ".a { outline-color: color-mix(in oklab, var(--color-ink), currentColor); }",
    ]
    for text in caught:
        assert _named_color_offenders(css, text), text
    for fn in ("hwb(", "lab(", "lch(", "oklab(", "oklch(", "rgb(", "hsla("):
        assert _HARD_COLOR.search(f"color: {fn}0 0 0)"), fn
    assert _named_color_offenders(Path("x.js"), 'el.style.color = "white";')
    assert _named_color_offenders(Path("x.html"), '<p style="background: navy">x</p>')
    fine = [
        ".a { white-space: nowrap; color: var(--color-ink); }",
        '.white-card { content: "black"; grid-template-areas: "tile icon"; }',
        ".a { background: color-mix(in srgb, var(--color-ink) 40%, transparent); }",
    ]
    for text in fine:
        assert not _named_color_offenders(css, text), text
    assert not _HARD_COLOR.search("const label = labelFor(x);")


_THEME_SCRIPT = '<script src="/static/theme.js"></script>'


def test_every_page_loads_the_tokens_and_the_theme_script_first():
    """Story 31: each page reads its colours from tokens.css, and sets `data-theme` before its
    first render: a classic script (neither a module nor deferred) in `<head>`, before the
    first stylesheet."""
    pages = sorted(STATIC_DIR.glob("*.html"))
    assert {p.name for p in pages} >= {
        "index.html",
        "diagnostic.html",
        "llm.html",
        "rag.html",
        "mcp.html",
    }
    for page in pages:
        text = page.read_text(encoding="utf-8")
        head = text[: text.index("</head>")]
        assert '<link rel="stylesheet" href="/static/tokens.css"' in head, page.name
        assert head.count(_THEME_SCRIPT) == 1, page.name
        scripts = re.findall(r"<script\b[^>]*\bsrc=\"/static/theme\.js\"[^>]*>", text)
        assert scripts == ['<script src="/static/theme.js">'], (page.name, scripts)
        first_sheet = head.index('<link rel="stylesheet"')
        assert head.index(_THEME_SCRIPT) < first_sheet, page.name
        assert re.search(r"<select\b[^>]*\bdata-theme-picker\b", text), page.name


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


# ---------- story 3 of 2026-09-30: /diagnostic sized by the tokens (lot 3: /models merged) --

_FONT_DECLARATION = re.compile(r"\b(font(?:-size)?)\s*:\s*([^;}]+)")


def test_diagnostic_and_models_pages_size_their_text_by_the_tokens():
    """No `rem` nor `em` left (the old diagnostic's 1.4rem, 0.9rem…), every font and font
    size from the type ramp; their shared styles (table, badges, buttons, fields) in
    pages.css, scoped to the annex pages."""
    offenders = []
    for name in ("diagnostic.html",):
        page = (STATIC_DIR / name).read_text(encoding="utf-8")
        assert '<body class="annex-page">' in page, name
        css = _COMMENTS[".css"].sub("", "\n".join(re.findall(r"<style>(.*?)</style>", page, re.S)))
        offenders += [f"{name}: {m.group(0)}" for m in re.finditer(r"\d(?:\.\d+)?r?em\b", css)]
        for prop, value in _FONT_DECLARATION.findall(css):
            if "var(--typography-" not in value and value.strip() not in {"inherit"}:
                offenders.append(f"{name}: {prop}: {value.strip()}")
    assert not offenders, offenders
    shared = (STATIC_DIR / "pages.css").read_text(encoding="utf-8")
    for rule in (
        ".annex-page .hosting-tag-network {",
        ".annex-page .button-primary {",
        ".annex-page .button-secondary {",
        ".annex-page .field-input {",
        # Lot 3 of 2026-10-04: the cards of « Diagnostic et modèles ».
        ".annex-page .model-grid {",
        ".annex-page .model-card {",
        ".annex-page .model-logo {",
        ".annex-page .state-pill {",
        ".annex-page .checks-panel {",
        ".annex-page .models-filters {",
    ):
        assert rule in shared, rule
