"""Languages (2/5, AD-19): the interface's texts, `content/ui.yaml` and its translations,
served by `GET /api/ui_texts` and read by `t()` of `i18n.js`."""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import pytest
import yaml
from test_bricks import _client
from test_i18n import _session

from wavestack import config
from wavestack.trace.journal import get_journal
from wavestack.ui_texts import UiTextsError, load_ui_texts

CONTENT = config.content_dir()
STATIC = config.repo_root() / "src" / "wavestack" / "web" / "static"
TRANSLATED = ("en", "de")
_VARIABLE = re.compile(r"\{(\w+)\}")
_KEY = r"[a-z0-9_.]+"
# Languages (4/5): a section per page, and `common` for the shared texts.
SECTIONS = {"common", "main", "llm", "rag", "mcp", "diagnostic", "models"}  # story 6: mcp
# Each page and its scripts (its inline `<script type="module">` included).
# Story 2 (2026-09-30): each loads site-nav.js, the shared bar's menu.
PAGES = {
    "index.html": ("main", ("app.js", "site-nav.js")),
    "llm.html": ("llm", ("llm.js", "site-nav.js")),
    "rag.html": ("rag", ("rag.js", "site-nav.js")),
    "mcp.html": ("mcp", ("mcp.js", "site-nav.js")),  # story 6 (2026-09-30)
    "diagnostic.html": ("diagnostic", ("site-nav.js",)),
    "models.html": ("models", ("site-nav.js",)),
}


@pytest.fixture(autouse=True)
def _fresh_caches():
    config.clear_content_caches()
    yield
    config.clear_content_caches()


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _leaves(tree: dict, prefix: str = "") -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            found |= _leaves(value, f"{prefix}{key}.")
        else:
            found[prefix + key] = value
    return found


def _node(tree: dict, key: str):
    value = tree
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


FRENCH = _read(CONTENT / "ui.yaml")


# ---------- the catalogue ----------


def test_french_catalogue_has_the_sections_and_valid_keys():
    assert set(FRENCH) == SECTIONS
    for key, value in _leaves(FRENCH).items():
        assert re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z0-9_]+)*", key), key
        assert isinstance(value, str) and value.strip(), key


def test_plurals_come_in_pairs():
    def walk(tree: dict, path: str) -> None:
        for key, value in tree.items():
            if isinstance(value, dict):
                if {"one", "other"} & set(value):
                    assert set(value) == {"one", "other"}, f"{path}{key}"
                else:
                    walk(value, f"{path}{key}.")

    walk(FRENCH, "")


@pytest.mark.parametrize("lang", TRANSLATED)
def test_translation_mirrors_the_french_catalogue(lang):
    """Parity: the same keys, the same variables per key (hence the `.one` / `.other` pairs)."""
    translated = _leaves(_read(CONTENT / "i18n" / lang / "ui.yaml"))
    french = _leaves(FRENCH)
    assert set(translated) == set(french), sorted(set(translated) ^ set(french))[:20]
    for key, value in translated.items():
        assert value.strip(), key
        vars_fr, vars_tr = set(_VARIABLE.findall(french[key])), set(_VARIABLE.findall(value))
        if key.endswith(".one"):  # « l'entrée », « the entry »: the count may be implicit
            assert vars_tr <= vars_fr | {"count"}, key
        else:
            assert vars_tr == vars_fr, key


@pytest.mark.parametrize("lang", TRANSLATED)
def test_translation_quotes_as_its_language(lang):
    """English quotes with “…”, German with „…“: never the French « »."""
    french_quotes = [
        key
        for key, value in _leaves(_read(CONTENT / "i18n" / lang / "ui.yaml")).items()
        if "«" in value or "»" in value
    ]
    assert not french_quotes


def test_german_uses_the_formal_register():
    german = " ".join(_leaves(_read(CONTENT / "i18n" / "de" / "ui.yaml")).values())
    assert not re.search(r"\b(du|dich|dir|dein\w*)\b", german, re.I)


# ---------- the page's keys ----------


def _script(page: str, scripts: tuple[str, ...]) -> str:
    """The page's scripts: its files and its inline modules."""
    inline = re.findall(r'<script type="module">(.*?)</script>', page, re.S)
    files = [(STATIC / name).read_text(encoding="utf-8") for name in scripts]
    return "\n".join([*files, *inline])


@pytest.mark.parametrize("name", sorted(PAGES))
def test_every_key_of_the_page_is_in_french_and_the_html_says_it(name):
    page = (STATIC / name).read_text(encoding="utf-8")
    own, scripts = PAGES[name]
    script = _script(page, scripts)
    keys = set(re.findall(rf'\bt\(\s*"({_KEY})"', script))
    # Every key of its section written as a string, a ternary's included
    # (`t(a ? "main.x" : "main.y")`).
    keys |= set(re.findall(rf'"((?:common|{own})\.[a-z0-9_.]+)"', script))
    keys |= {f"common.count.{n}" for n in re.findall(r'plural\([^()]*?, "(\w+)"\)', script)}
    sections = set(re.findall(rf'section\("({_KEY})"\)', script))
    missing = [k for k in sorted(keys) if not isinstance(_node(FRENCH, k), (str, dict))]
    missing += [s for s in sorted(sections) if not isinstance(_node(FRENCH, s), dict)]
    assert not missing, missing

    # The HTML keeps its French: the text of a `data-i18n` element, and each translated
    # attribute, equals the French value of its key.
    tags = re.findall(r"<(\w+)((?:\s+[\w-]+(?:=\"[^\"]*\")?)*)\s*/?>([^<]*)", page)
    checked = 0
    for _, attributes, text in tags:
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', attributes))
        if "data-i18n" in attrs:
            assert _node(FRENCH, attrs["data-i18n"]) == html.unescape(text.strip()), attrs
            checked += 1
        for data, attribute in (
            ("data-i18n-title", "title"),
            ("data-i18n-aria-label", "aria-label"),
            ("data-i18n-placeholder", "placeholder"),
        ):
            if data in attrs:
                assert _node(FRENCH, attrs[data]) == html.unescape(attrs[attribute]), attrs
                checked += 1
    assert checked > (60 if name == "index.html" else 8), checked


def test_every_page_loads_i18n_js_after_theme_js():
    for name in ("index", "llm", "rag", "mcp", "diagnostic", "models"):
        page = (STATIC / f"{name}.html").read_text(encoding="utf-8")
        theme = page.index('<script src="/static/theme.js"></script>')
        module = page.index('<script type="module" src="/static/i18n.js"></script>')
        assert theme < module < page.index("</head>"), name


def test_app_js_has_no_french_number_format_left():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '"fr-FR"' not in script and "toLocale" not in script
    assert "LANGUAGE_TEXTS" not in script


@pytest.mark.parametrize("name", sorted(PAGES))
def test_no_page_formats_numbers_in_french_by_hand(name):
    """Languages (4/5): every format through `numberFormat` and `dateTimeFormat`."""
    script = _script((STATIC / name).read_text(encoding="utf-8"), PAGES[name][1])
    assert '"fr-FR"' not in script and "toLocale" not in script
    assert '.replace(".", ",")' not in script


@pytest.mark.parametrize("name", sorted(PAGES))
def test_each_page_awaits_the_texts_and_shares_the_navigation(name):
    """Story 2 (2026-09-30): the shared bar of every page, its links named by their address
    (`applyTexts`), their French the catalogue's, the brand aside; its menu's keys in
    `common`."""
    page = (STATIC / name).read_text(encoding="utf-8")
    # The page's own script (site-nav.js waits for the texts on every page).
    script = _script(page, tuple(f for f in PAGES[name][1] if f != "site-nav.js"))
    assert re.search(r"await (textsReady|ready);", script), name
    nav = page[page.index('<nav class="site-nav"') : page.index("</nav>")]
    assert page.index('<nav class="site-nav"') == page.index("<nav"), name
    assert 'data-i18n-aria-label="common.links.pages" data-i18n-links>' in nav
    assert 'data-i18n-aria-label="common.theme.name"' in nav
    assert 'data-i18n="common.display.menu"' in nav and 'data-i18n="common.display.theme"' in nav
    links = re.findall(r'<a href="/(\w*)"( class="site-nav-brand")?[^>]*>([^<]+)</a>', nav)
    assert [(href, text) for href, brand, text in links if brand] == [("", "WaveStack")], name
    named = [(href or "home", text) for href, brand, text in links if not brand]
    assert [href for href, _ in named] == ["home", "llm", "rag", "mcp", "diagnostic", "models"], (
        name
    )
    for link, text in named:
        assert FRENCH["common"]["links"][link] == text, (name, link)


def test_i18n_names_the_links_by_their_address_the_brand_aside():
    script = (STATIC / "i18n.js").read_text(encoding="utf-8")
    names = re.search(r"const LINK_NAMES = \{([^}]*)\}", script).group(1)
    assert dict(re.findall(r'"(/\w*)": "(\w+)"', names)) == {
        "/": "home",
        "/diagnostic": "diagnostic",
        "/models": "models",
        "/llm": "llm",
        "/rag": "rag",
        "/mcp": "mcp",
    }
    assert ":not(.site-nav-brand)" in script
    homes = {
        lang: _read(CONTENT / "i18n" / lang / "ui.yaml")["common"]["links"]["home"]
        for lang in TRANSLATED
    }
    assert (FRENCH["common"]["links"]["home"], homes) == (
        "Atelier",
        {"en": "Workshop", "de": "Werkstatt"},
    )


def test_the_models_table_headers_are_the_catalogues_in_order():
    page = (STATIC / "models.html").read_text(encoding="utf-8")
    order = re.search(r"const COLUMN_ORDER = \[([^\]]+)\]", page).group(1)
    columns = [FRENCH["models"]["columns"][k] for k in re.findall(r'"(\w+)"', order)]
    head = page[page.index("<thead>") : page.index("</thead>")]
    assert re.findall(r'<th scope="col">([^<]+)</th>', head) == columns


# ---------- the loader ----------


def test_the_translation_is_filled_with_french(tmp_path, monkeypatch):
    """Matrix « Clé absente de la traduction »: the French value of that key."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    german = _read(content / "i18n" / "de" / "ui.yaml")
    del german["common"]["language"]["failed"]
    (content / "i18n" / "de" / "ui.yaml").write_text(
        yaml.safe_dump(german, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setattr(config, "content_dir", lambda: content)
    texts = load_ui_texts("de")
    assert texts["common"]["language"]["failed"] == FRENCH["common"]["language"]["failed"]
    assert texts["common"]["language"]["name"] == "Sprache"


@pytest.mark.parametrize(
    "broken",
    [
        "common: {}\n",  # an empty section
        "common:\n  language:\n    name: ''\n",  # an empty text
        "common:\n  unknown_key: 'x'\n",  # a key French lacks
        "common:\n  language: 'x'\n",  # a text where French has a section
        "- a list\n",
    ],
)
def test_an_invalid_translation_is_refused(tmp_path, monkeypatch, broken):
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "de" / "ui.yaml").write_text(broken, encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    with pytest.raises(UiTextsError):
        load_ui_texts("de")
    assert load_ui_texts("fr") == FRENCH


# ---------- the route ----------


@pytest.mark.parametrize("lang", ["fr", *TRANSLATED])
def test_the_route_serves_the_sessions_language(lang):
    _, session = _session(language=lang)
    body = _client(session).get("/api/ui_texts").json()
    assert body["language"] == lang
    assert set(body["texts"]) == SECTIONS
    assert set(_leaves(body["texts"])) == set(_leaves(FRENCH))
    expected = _read(config.content_file("ui.yaml", lang))["common"]["language"]["name"]
    assert body["texts"]["common"]["language"]["name"] == expected
    assert (expected == "Langue") == (lang == "fr")
    session.close()


def test_the_route_follows_a_change_of_language():
    _, session = _session()
    client = _client(session)
    assert client.get("/api/ui_texts").json()["texts"]["common"]["language"]["name"] == "Langue"
    session.set_language("de")
    body = client.get("/api/ui_texts").json()
    assert body["language"] == "de" and body["texts"]["common"]["language"]["name"] == "Sprache"
    session.close()


def test_an_invalid_translation_gives_an_error_then_french(tmp_path, monkeypatch):
    """Matrix « Traduction invalide »: `harness_error`, then the French catalogue."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "de" / "ui.yaml").write_text("common: {}\n", encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    _, session = _session(language="de")
    mark = get_journal().last_seq()
    body = _client(session).get("/api/ui_texts").json()
    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert [e["message_text"] for e in errors] == [
        "Eine übersetzte Datei (de) unter content/i18n/de/ ist ungültig."
    ]
    assert body["language"] == "de" and body["texts"] == FRENCH
    session.close()


def test_a_broken_french_catalogue_leaves_the_html(tmp_path, monkeypatch):
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "ui.yaml").write_text("common: []\n", encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    _, session = _session()
    mark = get_journal().last_seq()
    body = _client(session).get("/api/ui_texts").json()
    assert body == {"language": "fr", "texts": {}}
    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert [e["message_text"] for e in errors] == [
        "Le fichier content/ui.yaml est absent ou invalide."
    ]
    session.close()
