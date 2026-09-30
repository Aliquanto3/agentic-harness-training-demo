"""Languages (4/5, AD-19, AD-22): the workshops and the RAG in the session's language. Each
loader of the scope is given the session's language, never `settings.json`'s; the RAG brick
and the RAG workshop search the corpus and the index of that language (`rag_index.sqlite` in
French, `rag_index.{lang}.sqlite` otherwise), titles included.

The indexes are tiny, built with the real code of `rag/` and `FakeEmbedder`: no real model."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
import yaml
from fake_embedder import FakeEmbedder
from test_rag import COVERED, card, place_model, rag_config, rag_session, turn_events
from test_rag_lab import chains, lab_session, run, stage, wait_idle
from test_rag_rerank import place_reranker, rerank_config
from test_rag_review import _script, fake_factory

from wavestack import config
from wavestack.rag import index as rag_index
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import chunk_corpus, load_rag_content
from wavestack.session import llm_lab
from wavestack.trace.journal import get_journal

CONTENT = config.content_dir()
LANGS = config.LANGUAGES
TRANSLATED = ("en", "de")
MAX_CHARS = 700
_PARAGRAPH = re.compile(r"(^|\n\n)(?!<!--)(?=\S)")


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    """A test that reads another language leaves no content cached in it."""
    config.clear_content_caches()
    yield
    config.clear_content_caches()


def _other(lang: str) -> str:
    """A language that is not `lang`: the setting, contrary to the loader's argument."""
    return "de" if lang == "en" else "en"


def _mark(lang: str) -> str:
    return f"[{lang}] "


def _expected(lang: str, french: str) -> str:
    return french if lang == "fr" else _mark(lang) + french


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


@pytest.fixture
def marked(tmp_path, monkeypatch) -> Path:
    """A copy of `content/` whose `en` and `de` files of the scope are the French ones with a
    marker (`[en] `, `[de] `): before the workshops' titles, the documents' titles and each
    paragraph of the corpus. What a loader read says its language, whatever the shipped
    translations say."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    for lang in TRANSLATED:
        mark, root = _mark(lang), content / "i18n" / lang
        for name in ("llm_lab.yaml", "rag_lab.yaml"):
            data = _load(CONTENT / name)
            data["title_text"] = mark + data["title_text"]
            _dump(root / name, data)
        data = _load(CONTENT / "rag.yaml")
        for doc in data["documents"]:
            doc["title_text"] = mark + doc["title_text"]
        _dump(root / "rag.yaml", data)
        for french in (CONTENT / "corpus").glob("*.md"):
            text = _PARAGRAPH.sub(lambda m, k=mark: m.group(1) + k, french.read_text("utf-8"))
            (root / "corpus").mkdir(parents=True, exist_ok=True)
            (root / "corpus" / french.name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    return content


def _french_titles() -> set[str]:
    return {d.title_text for d in load_rag_content("fr").documents}


def _build(path: Path, lang: str) -> rag_index.IndexMeta:
    """A tiny index of `lang`'s corpus and titles, with `FakeEmbedder`."""
    return rag_index.build_index(
        load_rag_content(lang), FakeEmbedder(), path, chunk_max_chars=MAX_CHARS, lang=lang
    )


def _values(index: Path, lang: str) -> dict:
    return rag_config(index) | {"language": lang}


def _excerpts(events) -> list[str]:  # noqa: ANN001
    ctx = next(e.payload for e in events if e.kind == "context_rendered")
    rag = [s["text"] for s in ctx["segments"] if s["kind"] == "rag_excerpt"]
    return rag[1:]  # the intro first


# ---------- each loader reads its argument, never the setting ----------


@pytest.mark.parametrize("lang", LANGS)
def test_each_loader_reads_its_language_not_the_setting(marked, lang):
    config.save_setting("language", _other(lang))

    assert llm_lab.load_lab_content(lang).title_text == _expected(
        lang, _load(CONTENT / "llm_lab.yaml")["title_text"]
    )
    assert rag_lab.load_lab_content(lang).title_text == _expected(
        lang, _load(CONTENT / "rag_lab.yaml")["title_text"]
    )
    content = load_rag_content(lang)
    french = load_rag_content("fr")
    assert [d.id for d in content.documents] == [d.id for d in french.documents]
    assert [d.file for d in content.documents] == [d.file for d in french.documents]
    assert content.documents[0].title_text == _expected(lang, french.documents[0].title_text)
    chunks = chunk_corpus(content, MAX_CHARS, lang)
    assert {c.doc_id for c in chunks} == {d.id for d in content.documents}
    marked_chunks = [c for c in chunks if c.text.startswith("[")]
    assert (marked_chunks == []) == (lang == "fr")
    assert chunks[0].title_text == content.documents[0].title_text


def test_the_corpus_falls_back_to_french_file_by_file(marked):
    (marked / "i18n" / "de" / "corpus" / "teletravail.md").unlink()
    chunks = chunk_corpus(load_rag_content("de"), MAX_CHARS, "de")
    french = [
        c.text for c in chunk_corpus(load_rag_content("fr"), MAX_CHARS) if c.doc_id == "teletravail"
    ]
    assert [c.text for c in chunks if c.doc_id == "teletravail"] == french
    assert all(c.text.startswith("[de] ") for c in chunks if c.doc_id == "mots_de_passe")


@pytest.mark.parametrize("lang", LANGS)
def test_the_index_path_inserts_the_language_before_the_extension(lang, tmp_path):
    config.save_setting("language", _other(lang))
    cfg = config.Config(values={"rag": {"index_path": str(tmp_path / "idx.sqlite")}})
    name = "idx.sqlite" if lang == "fr" else f"idx.{lang}.sqlite"
    assert cfg.rag_index_path(lang) == tmp_path / name
    shipped = config.Config(values={}).rag_index_path(lang)
    assert shipped.parent == config.repo_root() / "data"
    assert shipped.name == ("rag_index.sqlite" if lang == "fr" else f"rag_index.{lang}.sqlite")


def test_french_chunks_are_those_of_the_shipped_index():
    """Matrix « Français inchangé »: the French corpus chunks as the shipped index was built."""
    meta = rag_index.read_meta(config.load_config().rag_index_path("fr"))
    chunks = chunk_corpus(load_rag_content("fr"), meta.chunk_max_chars, "fr")
    assert rag_index.corpus_digest(chunks) == meta.corpus_sha256
    assert chunks == chunk_corpus(load_rag_content("fr"), meta.chunk_max_chars)


# ---------- the RAG brick ----------


@pytest.mark.parametrize("lang", LANGS)
def test_a_rag_turn_places_the_excerpts_of_the_sessions_language(marked, tmp_path, lang):
    """Matrix « Tour RAG en allemand » (and « Français inchangé »): the excerpts and their
    titles come from the index of the session's language."""
    place_model()
    config.save_setting("language", _other(lang))
    index = tmp_path / "rag_index.sqlite"
    for built in LANGS:
        _build(config.Config(values=_values(index, lang)).rag_index_path(built), built)
    session, _ = rag_session(_values(index, lang))

    excerpts = _excerpts(turn_events(COVERED, session))

    assert len(excerpts) == 3
    titles = {d.title_text for d in load_rag_content(lang).documents}
    for position, text in enumerate(excerpts, start=1):
        head = text.split("\n", 1)[0]
        title = head.removeprefix(f"Extrait {position} — ").removesuffix(" :")
        assert title in titles
        assert (title in _french_titles()) == (lang == "fr")
        assert text.split("\n", 1)[1].startswith(_mark(lang)) == (lang != "fr")
    assert excerpts[0].startswith(f"Extrait 1 — {_expected(lang, 'Politique des mots de passe')}")
    session.close()


def test_a_missing_index_of_the_language_offers_its_build(marked, tmp_path):
    """Matrix « Index absent »: `en` without `rag_index.en.sqlite`, the French one there."""
    place_model()
    index = tmp_path / "rag_index.sqlite"
    _build(index, "fr")
    french_sha = rag_index.file_sha256(index)
    session, embedders = rag_session(_values(index, "en"))

    rag = card(session)
    target = tmp_path / "rag_index.en.sqlite"
    assert rag["available"] is False and "index absent" in rag["reason_text"]
    assert str(target) in rag["reason_text"] and "--lang en" in rag["reason_text"]
    assert rag["build_index"] == {"label_text": load_rag_content("en").build_label_text}

    session.build_rag_index()
    wait_idle(session)

    meta = rag_index.read_meta(target)
    chunks = chunk_corpus(load_rag_content("en"), MAX_CHARS, "en")
    assert meta.corpus_sha256 == rag_index.corpus_digest(chunks)
    assert {c.title_text for c in rag_index.read_chunks(target)} <= {
        d.title_text for d in load_rag_content("en").documents
    }
    assert rag_index.file_sha256(index) == french_sha
    assert card(session)["available"] is True
    session.close()


def test_a_change_of_language_reopens_the_new_languages_index(marked, tmp_path):
    """Matrix « Changement de langue »: `fr` → `de`, the RAG ready."""
    place_model()
    index = tmp_path / "rag_index.sqlite"
    _build(index, "fr")
    _build(tmp_path / "rag_index.de.sqlite", "de")
    session, embedders = rag_session(_values(index, "fr"))
    assert card(session)["available"] is True and len(embedders.made) == 1

    mark = get_journal().last_seq()
    session.set_language("de")
    session.join()
    session.join()

    assert embedders.made[0].closed and len(embedders.made) == 2
    assert card(session)["available"] is True
    schemas = [e for e in get_journal().events_since(mark) if e.kind == "architecture_changed"]
    nodes = {n["id"]: n for n in schemas[-1].payload["nodes"]}
    assert "rag_index.de.sqlite" in nodes["file.rag_index"]["detail_text"]
    excerpts = _excerpts(turn_events(COVERED, session))
    assert excerpts[0].startswith("Extrait 1 — [de] Politique des mots de passe :\n[de] ")
    session.close()


def test_a_change_of_language_to_a_missing_index_offers_its_build(marked, tmp_path):
    place_model()
    index = tmp_path / "rag_index.sqlite"
    _build(index, "fr")
    session, embedders = rag_session(_values(index, "fr"))

    session.set_language("en")
    session.join()

    rag = card(session)
    assert rag["available"] is False and "rag_index.en.sqlite" in rag["reason_text"]
    assert rag["build_index"] is not None
    assert embedders.made[0].closed and len(embedders.made) == 1
    session.close()


def test_an_index_of_another_language_is_stale(marked, tmp_path):
    """Matrix « Index d'une autre langue »: the French index copied under the German name."""
    place_model()
    index = tmp_path / "rag_index.sqlite"
    _build(index, "fr")
    shutil.copyfile(index, tmp_path / "rag_index.de.sqlite")
    session, embedders = rag_session(_values(index, "de"))

    rag = card(session)
    assert rag["available"] is False and "index périmé" in rag["reason_text"]
    assert rag["build_index"] is not None and embedders.made == []
    session.close()


# ---------- the workshops ----------


@pytest.mark.parametrize("lang", LANGS)
def test_the_rag_workshop_runs_in_the_sessions_language(marked, tmp_path, lang):
    """Matrix « Atelier RAG »: its texts, its excerpts and their titles in the language."""
    place_model()
    place_reranker()
    config.save_setting("language", _other(lang))
    index = tmp_path / "rag_index.sqlite"
    values = rerank_config(index) | {"language": lang}
    _build(config.Config(values=values).rag_index_path(lang), lang)
    session, _ = lab_session(values)

    state = session.rag_lab_state()
    assert state["content"]["title_text"] == _expected(
        lang, _load(CONTENT / "rag_lab.yaml")["title_text"]
    )
    assert state["catalog"] is not None
    events = run(session)
    context = next(
        e.payload
        for e in events
        if e.kind == "rag_lab_stage_ended" and e.payload["kind"] == "context"
    )
    assert context["status"] == "ok"
    titles = {d.title_text for d in load_rag_content(lang).documents}
    for position, item in enumerate(context["items"], start=1):
        assert item["title_text"] in titles
        assert (item["title_text"] in _french_titles()) == (lang == "fr")
        assert item["text"].startswith(f"Extrait {position} — {item['title_text']} :\n")
    session.close()


def test_the_rag_workshop_chunks_the_languages_corpus_without_the_brick_index(marked, tmp_path):
    """No `rag_index.de.sqlite`: the chunking falls back on the German corpus."""
    place_model()
    place_reranker()
    values = rerank_config(tmp_path / "rag_index.sqlite") | {"language": "de"}
    session, _ = lab_session(values)
    _, chain, _ = chains(session)
    stage(chain, "vector_store").option = "memory"  # the brick's index is absent
    events = run(session, pipelines=[chain])
    chunking = next(
        e.payload
        for e in events
        if e.kind == "rag_lab_stage_ended" and e.payload["kind"] == "chunking"
    )
    assert chunking["status"] == "ok", chunking["error_text"]
    assert session._rag_index_path() == tmp_path / "rag_index.de.sqlite"
    context = next(
        e.payload
        for e in events
        if e.kind == "rag_lab_stage_ended" and e.payload["kind"] == "context"
    )
    assert context["status"] == "ok" and context["items"]
    for item in context["items"]:  # the German corpus's chunks, not the French ones
        assert item["text"].split("\n", 1)[1].startswith(_mark("de")), item["text"][:80]
    session.close()


@pytest.mark.parametrize("name", ["llm_lab.yaml", "rag_lab.yaml"])
def test_an_invalid_translated_workshop_gives_the_french_page(marked, tmp_path, name):
    """Matrix « Atelier traduit invalide »: `harness_error`, then the French texts."""
    (marked / "i18n" / "en" / name).write_text("title_text: 3\n", encoding="utf-8")
    place_model()
    session, _ = rag_session(_values(tmp_path / "rag_index.sqlite", "en"), bricks=())
    mark = get_journal().last_seq()

    state = session.lab_state() if name == "llm_lab.yaml" else session.rag_lab_state()

    assert state["content"]["title_text"] == _load(CONTENT / name)["title_text"]
    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert errors and "content/i18n/en/" in errors[0]["message_text"]
    session.close()


# ---------- scripts/build_rag_index.py --lang ----------


def _script_settings(index: Path) -> None:
    values = {"rag": rag_config(index)["rag"], "language": "en"}  # contrary to `--lang`
    config.settings_path().parent.mkdir(parents=True, exist_ok=True)
    config.settings_path().write_text(json.dumps(values), encoding="utf-8")


@pytest.mark.parametrize("lang", LANGS)
def test_the_script_writes_the_index_of_its_language_only(marked, tmp_path, lang):
    """Matrix « Script »: `--lang` writes its index, titles of its language, nothing else."""
    index = tmp_path / "script.sqlite"
    _script_settings(index)
    place_model()
    cfg = config.load_config()
    others = {o: cfg.rag_index_path(o) for o in LANGS if o != lang}
    for other, path in others.items():
        _build(path, other)
    before = {o: rag_index.file_sha256(p) for o, p in others.items()}

    assert _script().main(["--lang", lang], embedder_factory=fake_factory) == 0

    target = cfg.rag_index_path(lang)
    titles = {c.title_text for c in rag_index.read_chunks(target)}
    assert titles == {d.title_text for d in load_rag_content(lang).documents}
    meta = rag_index.read_meta(target)
    chunks = chunk_corpus(load_rag_content(lang), MAX_CHARS, lang)
    assert meta.corpus_sha256 == rag_index.corpus_digest(chunks)
    assert {o: rag_index.file_sha256(p) for o, p in others.items()} == before


def test_the_script_defaults_to_french_whatever_the_setting(marked, tmp_path):
    index = tmp_path / "script.sqlite"
    _script_settings(index)  # `language: en` in settings.json
    place_model()

    assert _script().main([], embedder_factory=fake_factory) == 0

    assert index.is_file() and not (tmp_path / "script.en.sqlite").exists()
    assert {c.title_text for c in rag_index.read_chunks(index)} == _french_titles()


# ---------- the shipped translations and indexes (commit 3) ----------

# `data/rag_index.sqlite` as the story found it (baseline da6748d): never rebuilt.
FRENCH_INDEX_SHA256 = "7a27518b66d0d265d4daa7e2639b9e91f8d8777412bbd9e4d15b39b8b79d4175"
EXCERPT = {"fr": "Extrait 1 — ", "en": "Excerpt 1 — ", "de": "Auszug 1 — "}
QUESTIONS = {
    "en": "How many characters must a password have at least at Exemplia?",
    "de": "Wie viele Zeichen muss ein Passwort bei Exemplia mindestens haben?",
}


def test_the_french_index_is_the_one_the_story_found():
    path = config.repo_root() / "data" / "rag_index.sqlite"
    assert rag_index.file_sha256(path) == FRENCH_INDEX_SHA256, (
        "data/rag_index.sqlite a changé : s'il a été reconstruit exprès, mettez à jour "
        "FRENCH_INDEX_SHA256"
    )


@pytest.mark.parametrize("lang", TRANSLATED)
def test_the_shipped_index_of_a_language_is_fresh_for_the_declared_model(lang):
    """Acceptance: on a fresh install with the embedding model, the RAG brick in `lang` needs
    no build. Read from `meta` and the chunks, without the real model."""
    cfg = config.load_config()
    path = cfg.rag_index_path(lang)
    assert path == config.repo_root() / "data" / f"rag_index.{lang}.sqlite"
    meta = rag_index.read_meta(path)
    model, error = cfg.rag_embedding
    assert error is None and model is not None
    declared = model.load_file
    assert (meta.embedding_model_id, meta.dims) == (model.id, model.dims)
    assert meta.model_size == declared.size
    assert not declared.sha256 or meta.model_sha256 == declared.sha256.lower()
    assert meta.chunk_max_chars == cfg.rag_chunk_max_chars
    content = load_rag_content(lang)
    chunks = chunk_corpus(content, cfg.rag_chunk_max_chars, lang)
    assert meta.corpus_sha256 == rag_index.corpus_digest(chunks)
    titles = {c.title_text for c in rag_index.read_chunks(path)}
    assert titles == {d.title_text for d in content.documents}
    assert not titles & _french_titles()


@pytest.mark.parametrize("lang", TRANSLATED)
def test_a_rag_turn_in_a_translated_language_sends_its_excerpts(tmp_path, lang):
    """Matrix « Tour RAG en allemand », with the shipped translations: « Auszug 1 — » and a
    German title, no French title in the context."""
    place_model()
    index = tmp_path / "rag_index.sqlite"
    _build(config.Config(values=_values(index, lang)).rag_index_path(lang), lang)
    session, _ = rag_session(_values(index, lang))

    excerpts = _excerpts(turn_events(QUESTIONS[lang], session))

    titles = {d.title_text for d in load_rag_content(lang).documents}
    assert len(excerpts) == 3
    for position, text in enumerate(excerpts, start=1):
        head = text.split("\n", 1)[0]
        assert head.startswith(EXCERPT[lang].replace("1", str(position)))
        assert head.removeprefix(EXCERPT[lang].replace("1", str(position))).rstrip(":") in titles
    assert not any(title in "\n".join(excerpts) for title in _french_titles())
    session.close()
