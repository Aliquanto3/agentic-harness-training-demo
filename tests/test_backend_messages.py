"""Languages (5/5, AD-19): the texts the backend writes, `content/messages.yaml` and its
translations, produced by `msg(key, lang)` in the session's language."""

from __future__ import annotations

import ast
import json
import re
import shutil
from datetime import datetime

import pytest
from fake_engine import FakeEngine, booted_session
from test_tools import QWEN, _segments, call
from test_turn import _run

from wavestack import config, messages
from wavestack.messages import KeyedError, Message, MessageError, msg
from wavestack.tools import native
from wavestack.trace.journal import get_journal

CONTENT = config.content_dir()
LANGS = config.LANGUAGES
KEYS = sorted(messages.load_messages("fr"))


@pytest.fixture
def _fresh_content_caches():
    """A test that changes the language or the content leaves nothing cached in it (the
    catalogue's own tests read the shipped files once: no clearing between them)."""
    config.clear_content_caches()
    yield
    config.clear_content_caches()


# Every test but the catalogue's key by key reads the content afresh.
fresh = pytest.mark.usefixtures("_fresh_content_caches")


def _fake(text: str | dict[str, str]) -> dict[str, object]:
    kw: dict[str, object] = {name: f"<{name}>" for name in messages.variables(text)}
    if isinstance(text, dict):
        kw["count"] = 2
    return kw


def _session(language: str, outputs: list[str], *, contrary: bool = True):
    """A session in `language`, `settings.json` holding another language (matrix « Réglage
    contraire »): what the session says never comes from the setting."""
    if contrary:
        config.save_setting("language", "fr" if language != "fr" else "de")
    engine = FakeEngine(outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35")
    return booted_session(engine, window=16384, values={"language": language})


def _french_values() -> set[str]:
    """Every French text of the catalogue (both forms of a plural), `{…}` cut out: none
    may appear in what a German or English session writes."""
    values = set()
    for text in messages.load_messages("fr").values():
        for form in text.values() if isinstance(text, dict) else (text,):
            values |= {p.strip() for p in messages._VARIABLE.split(form) if len(p.strip()) > 12}
    return values


def _no_french(text: str) -> None:
    left = [v for v in _french_values() if v in text]
    assert not left, left


# ---------- the catalogue ----------


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key", KEYS)
def test_every_key_renders_in_every_language(key, lang):
    text = messages.load_messages(lang)[key]
    rendered = msg(key, lang, **_fake(text))
    assert rendered.strip() and "{" not in rendered.replace("{text}", "")


@fresh
def test_an_unknown_key_or_a_missing_variable_is_an_error():
    with pytest.raises(MessageError):
        msg("session.no_such_key", "fr")
    with pytest.raises(MessageError):
        msg("session.translation_invalid.message", "de")


@fresh
def test_plurals_follow_the_language():
    assert messages.plural_form(0, "fr") == "one" and messages.plural_form(1, "fr") == "one"
    assert messages.plural_form(0, "en") == "other" and messages.plural_form(1, "de") == "one"
    assert messages.plural_form(2, "fr") == "other"


@fresh
def test_a_keyed_error_is_french_as_a_string_and_rendered_on_demand():
    error = KeyedError("mcp.glossary.unknown_term", term="x", known="a, b")
    assert str(error) == msg("mcp.glossary.unknown_term", "fr", term="x", known="a, b")
    assert error.render("de").startswith("Begriff nicht im Glossar")
    nested = Message("common.verbatim", text=Message("tools.datetime.weekdays.monday"))
    assert nested.render("en") == "Monday" and str(nested) == "lundi"
    assert KeyedError.verbatim("Connection refused").render("de") == "Connection refused"


def test_a_said_text_follows_a_change_of_language():
    """A text said before a change of language (the startup diagnostic's) is rendered again
    in the language asked; in its own language it is the same object."""
    monday = messages.Said(Message("tools.datetime.weekdays.monday"), "fr")
    assert messages.in_language({"checks": [monday]}, "en") == {"checks": ["Monday"]}
    assert messages.in_language(monday, "fr") is monday


@fresh
def test_a_missing_translated_key_gives_the_french_text(tmp_path, monkeypatch):
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "en" / "messages.yaml").write_text(
        "tools:\n  datetime:\n    weekdays:\n      monday: Monday\n", encoding="utf-8"
    )
    monkeypatch.setattr(config, "content_dir", lambda: content)
    config.clear_content_caches()
    assert msg("tools.datetime.weekdays.monday", "en") == "Monday"
    assert msg("tools.datetime.weekdays.friday", "en") == "vendredi"


@fresh
def test_a_translation_with_other_variables_is_invalid(tmp_path, monkeypatch):
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "de" / "messages.yaml").write_text(
        "mcp:\n  glossary:\n    unknown_term: 'Unbekannt: {word}'\n", encoding="utf-8"
    )
    monkeypatch.setattr(config, "content_dir", lambda: content)
    config.clear_content_caches()
    with pytest.raises(messages.MessagesError):
        messages.load_messages("de")
    french = msg("mcp.glossary.unknown_term", "fr", term="x", known="y")
    assert msg("mcp.glossary.unknown_term", "de", term="x", known="y") == french


# ---------- the matrix, Python side ----------


@fresh
def test_get_datetime_names_the_day_in_the_sessions_language():
    """Matrix « get_datetime »: « Mittwoch 2026-09-30T… » in `de`."""
    wednesday = datetime(2026, 9, 30, 10, 12).astimezone()
    assert native.weekday(wednesday, "de") == "Mittwoch"
    assert native.weekday(wednesday, "en") == "Wednesday"
    assert native.weekday(wednesday, "fr") == "mercredi"
    session = _session("de", [call("get_datetime"), "Fertig."])
    session.set_brick("tools", True)
    (result,) = _run(session, "Welcher Tag ist heute?")["tool_ended"]
    day = result["result"].split(" ")[0]
    assert day in {msg(f"tools.datetime.weekdays.{d}", "de") for d in native._WEEKDAYS}
    session.close()


@fresh
def test_the_glossary_answers_in_its_language(monkeypatch):
    """Matrix « Glossaire »: the local MCP server's unknown term, in English."""
    from wavestack.mcp import local_server

    monkeypatch.setattr(local_server, "LANGUAGE", "en")
    result = local_server.define_term("nowhere")
    assert result.is_error
    assert result.content[0].text.startswith("Term not in the glossary: “nowhere”.")


@fresh
def test_an_invalid_translated_file_is_traced_in_the_sessions_language(tmp_path, monkeypatch):
    """Matrix « Fichier traduit invalide »: a German `harness_error`, then the French file."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "de" / "tools.yaml").write_text("tools: {}\n", encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    mark = get_journal().last_seq()
    session = _session("de", ["Fertig."])
    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert [(e["message_text"], e["effect_text"]) for e in errors] == [
        (
            "Eine übersetzte Datei (de) unter content/i18n/de/ ist ungültig.",
            msg("session.translation_invalid.effect", "de"),
        )
    ]
    session.close()


@fresh
def test_an_invalid_translated_catalogue_is_traced_once_in_french(tmp_path, monkeypatch):
    """Matrix « messages.yaml traduit invalide »: one `harness_error`, in French (the
    English catalogue is unreadable), then the French messages."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "en" / "messages.yaml").write_text("session: []\n", encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    mark = get_journal().last_seq()
    session = _session("en", ["Done."])
    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert [e["message_text"] for e in errors] == [
        "Un fichier traduit (en) sous content/i18n/en/ est invalide."
    ]
    assert msg("tools.datetime.weekdays.monday", "en") == "lundi"
    session.close()


# ---------- the matrix in English and German (story 7 of 2026-09-30) ----------

TRANSLATED = [lang for lang in LANGS if lang != config.DEFAULT_LANGUAGE]


def _prefix(key: str, lang: str) -> str:
    """The text of `key` up to its first variable: what a rendered message starts with."""
    text = messages.load_messages(lang)[key]
    return messages._VARIABLE.split(text)[0]


@fresh
@pytest.mark.parametrize("lang", TRANSLATED)
def test_a_tool_error_reaches_the_model_in_the_sessions_language(lang):
    """Matrix « Erreur d'outil lue par le modèle »: `read_file` on a missing file, its error
    prefix included, in the session's language (`settings.json` holding another)."""
    session = _session(lang, [call("read_file", path="absent.txt"), "Done."])
    session.set_brick("tools", True)
    events = _run(session, "Read absent.txt")
    (result,) = _segments(events["context_rendered"][1], "tool_result")
    assert result["text"].startswith(_prefix("tools.error", lang))
    _no_french(result["text"])
    session.close()


@fresh
@pytest.mark.parametrize("lang", TRANSLATED)
def test_a_malformed_call_is_refused_in_the_sessions_language(lang):
    """Matrix « Appel mal formé »: an unknown argument, « Error: … Fix the call or answer
    without a tool. » in English."""
    session = _session(lang, [call("calculator", expression="1+1", oops=1), "Done."])
    session.set_brick("tools", True)
    events = _run(session, "1 + 1?")
    (result,) = _segments(events["context_rendered"][1], "tool_result")
    reject = messages.load_messages(lang)["tools.reject"]
    head, tail = messages._VARIABLE.split(reject)[0], messages._VARIABLE.split(reject)[-1]
    assert result["text"].startswith(head) and result["text"].endswith(tail.rstrip())
    assert "oops" in result["text"]
    _no_french(result["text"])
    session.close()


@fresh
@pytest.mark.parametrize("lang", TRANSLATED)
def test_the_truncation_mark_is_in_the_sessions_language(lang):
    """Matrix « Troncature »: the mark the model reads, in the session's language, the
    bound holding with its length."""
    session = _session(lang, ["Done."])
    text = "\n".join(f"line {i:04d} " + "x" * 40 for i in range(400))
    bounded, cut = session._bound_result(text)
    assert cut is not None
    assert _prefix("tools.truncated", lang) in bounded
    assert session._count_tokens(bounded)[0] <= session.cfg.tool_result_max_tokens
    _no_french(bounded)
    session.close()


@fresh
@pytest.mark.parametrize("lang", TRANSLATED)
def test_h1_refuses_in_the_sessions_language(lang):
    """Matrix « Refus H1 »: the confidential file refused in the context, in German."""
    session = _session(lang, [call("read_file", path="confidentiel/budget_projet.txt"), "Ok."])
    session.set_brick("tools", True)
    session.set_brick("hooks", True)
    events = _run(session, "Budget?")
    (refusal,) = _segments(events["context_rendered"][1], "tool_result")
    assert (refusal["brick"], refusal["component"]) == ("hooks", "hooks.h1")
    _no_french(refusal["text"])
    session.close()


@fresh
@pytest.mark.parametrize("lang", TRANSLATED)
def test_the_cards_reasons_are_in_the_sessions_language(lang):
    """Matrix « Carte indisponible »: every brick's reason and status, in the session's
    language (the RAG without its index, the cloud without a key…)."""
    mark = get_journal().last_seq()
    session = _session(lang, ["Done."])
    cards = [e.payload for e in get_journal().events_since(mark) if e.kind == "bricks_changed"]
    assert cards
    assert any(brick.get("reason_text") for brick in cards[-1]["bricks"])
    _no_french(json.dumps(cards[-1], ensure_ascii=False))
    session.close()


# ---------- the static check: no French literal left in the perimeter ----------

SRC = config.repo_root() / "src" / "wavestack"
_FRENCH = re.compile(r"[àâçéèêëîïôûùüÿœÀÂÇÉÈÊËÎÏÔÛÙÜŸŒ«»]")
# The modules whose texts reach the model or the user (commit by commit).
PERIMETER = (
    "tools/executor.py",
    "tools/parser.py",
    "tools/native.py",
    "tools/network.py",
    "tools/registry.py",
    "mcp/connection.py",
    "mcp/local_server.py",
    "hooks.py",
    "memory.py",
    "messages.py",
    "ui_texts.py",
    # Commit 3: the texts the user sees.
    "session/app_session.py",
    "session/diagnostic.py",
    "cli.py",
    "web/app.py",
    "config.py",
    "cloud.py",
    "greenops.py",
    "context/render.py",
    "context/window.py",
    "compression/headroom_adapter.py",
    "models/capabilities.py",
    "models/catalog.py",
    "models/discovery.py",
    "models/download.py",
    "models/embedding.py",
    "models/engine.py",
    "models/gguf_meta.py",
    "models/load_registry.py",
    "models/cloud_api.py",
    "models/anthropic_messages.py",  # native providers 3/5
    "models/openai_responses.py",  # native providers 4/5
    "models/cloud_base.py",
    "models/openai_chat.py",
    "models/probe.py",
    "models/reranker.py",
    "models/servers.py",
    "net/guard.py",
    "net/factory.py",
    "rag/lab.py",
    "mcp/lab.py",  # story 6 (2026-09-30)
    "rag/index.py",
    "rag/retriever.py",
    "rag/corpus.py",
    "session/llm_lab.py",
)
# Literals kept on purpose, by module: `(module, a piece of the literal)`, each justified.
EXCEPTIONS = {
    # H3's date, written by `date_fr` in the content's language (story 1).
    ("hooks.py", "février"),
    ("hooks.py", "août"),
    ("hooks.py", "décembre"),
    # An internal exception, mapped to `mcp.error.closed` by `describe_error`.
    ("mcp/connection.py", "connexion fermée"),
    # Validation of `memory.json` and `memory.yaml`: file validation, never translated.
    ("memory.py", "entrée"),
    ("memory.py", "caractères au plus"),
    # Validation of `ui.yaml` and `messages.yaml`: file validation, never translated.
    ("ui_texts.py", "clé"),
    ("ui_texts.py", "texte non vide"),
    ("ui_texts.py", "même forme"),
    ("messages.py", "même forme"),
    ("messages.py", "mêmes variables"),
    # Languages (1/5): why the language cannot change, French then the current language.
    ("session/app_session.py", "Vider"),
    # The French catalogue itself unreadable: no key to render it with.
    ("session/app_session.py", "content/messages.yaml est absent"),
    ("session/app_session.py", "ne peuvent pas s'afficher"),
    # Each language written in itself, for the selector (story 1).
    ("config.py", "Français"),
    # Validation of wavestack.toml and settings.json: file validation, never translated.
    ("config.py", "L'en-tête"),
    ("config.py", "entrée"),
    ("config.py", "tracé en clair"),
    ("config.py", "posé par l'adaptateur"),  # `extra_headers` (native providers 1/5)
    # Validation of `publishers.yaml` and `rag_lab.yaml`: content validation.
    ("models/catalog.py", "expression régulière invalide"),
    ("models/catalog.py", "est réservé à « Autres éditeurs »"),
    ("models/catalog.py", "l'identifiant « "),
    ("models/catalog.py", " » : "),
    ("rag/lab.py", "il faut exactement"),
    # A last-resort model name, also its `ref`: an identifier, not a text.
    ("models/catalog.py", "modèle"),
    ("models/servers.py", "modèle"),
    # Internal errors, always caught, never shown.
    ("models/engine.py", "copie de l'état llama.cpp"),
    ("models/gguf_meta.py", "chaîne trop longue"),
    ("models/gguf_meta.py", "en-tête GGUF illisible"),
    ("models/reranker.py", "reranking arrêté"),
    # The neutral prompt the probe gives the model, and its mojibake marks: data.
    ("models/probe.py", "Le harnais prépare le contexte"),
    ("models/probe.py", "Ã"),
    ("models/probe.py", "Â"),
    ("models/probe.py", "â€"),
    ("models/probe.py", "00c3"),
    # The value traced in place of a masked header (`test_net_factory`).
    ("net/factory.py", "[masqué]"),
    # A sentence-end pattern, not a text.
    ("rag/corpus.py", "…»"),
    # The warm-up call's text, given to Headroom, never shown.
    ("compression/headroom_adapter.py", "Résultat à compresser"),
}


def _skipped(tree: ast.AST) -> set[int]:
    """The docstrings and the `log.*` calls' strings: never translated."""
    skipped = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            first = body[0] if body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skipped.add(id(first.value))
        func = getattr(node, "func", None)
        if isinstance(node, ast.Call) and isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id in ("log", "logger"):
                skipped |= {id(n) for n in ast.walk(node)}
    return skipped


def _french_literals(module: str) -> list[str]:
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    skipped = _skipped(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skipped
        and _FRENCH.search(node.value)
        and not any(m == module and piece in node.value for m, piece in EXCEPTIONS)
    ]


@pytest.mark.parametrize("module", PERIMETER)
def test_no_french_literal_is_left_in_the_perimeter(module):
    assert _french_literals(module) == []
