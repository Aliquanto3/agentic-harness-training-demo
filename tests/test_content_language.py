"""Languages (3/5, AD-19): the pedagogical content in the session's language. Each loader of
the scope is given the session's language, never `settings.json`'s; `read_file` reads the
translated demonstration file, file by file, confined to the French folder."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from fake_engine import FakeEngine, booted_session
from pydantic import SecretStr
from test_bricks import _client
from test_cloud import SENTINEL, Provider
from test_tools import QWEN, call
from test_turn import _run

from wavestack import config
from wavestack.bricks.contract import load_brick_content
from wavestack.cloud import active_model, load_cloud_content
from wavestack.compression.port import load_compression_content
from wavestack.context.segments import SegmentKind, load_labels
from wavestack.hooks import DEMO_HOOKS
from wavestack.models import catalog
from wavestack.scenarios import load_scenarios
from wavestack.session.app_session import AppSession
from wavestack.tools.native import read_file
from wavestack.tools.registry import ToolError
from wavestack.trace.journal import get_journal

CONTENT = config.content_dir()
LANGS = config.LANGUAGES
TRANSLATED = ("en", "de")
WINDOW = 16384
SECRET = "confidentiel/budget_projet.txt"
BLOCKED = "Bloqué par le hook garde-fou"  # H1's refusal stays French until story 5


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


def _dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture
def marked(tmp_path, monkeypatch) -> Path:
    """A copy of `content/` whose `en` and `de` files of the scope are the French ones with
    a marker (`[en] `, `[de] `) before one text of each: what a loader read says its language,
    whatever the shipped translations say."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    for lang in TRANSLATED:
        mark, root = _mark(lang), content / "i18n" / lang
        data = _load(CONTENT / "scenarios.yaml")
        data["program"][0]["title_text"] = mark + data["program"][0]["title_text"]
        data["scenarios"]["native_tools"]["title_text"] = mark + "native_tools"
        _dump(root / "scenarios.yaml", data)
        data = _load(CONTENT / "cloud.yaml")
        data["banner_text"] = mark + data["banner_text"]
        data["no_key_text"] = mark + data["no_key_text"]
        _dump(root / "cloud.yaml", data)
        data = _load(CONTENT / "labels" / "segment_kinds.yaml")
        data["kinds"]["user_message"] = mark + data["kinds"]["user_message"]
        _dump(root / "labels" / "segment_kinds.yaml", data)
        data = _load(CONTENT / "models" / "publishers.yaml")
        data["legend_text"] = mark + data["legend_text"]
        data["hosting_text"]["network"] = mark + data["hosting_text"]["network"]
        _dump(root / "models" / "publishers.yaml", data)
        data = _load(CONTENT / "compression.yaml")
        data["limits_text"] = mark + data["limits_text"]
        _dump(root / "compression.yaml", data)
        data = _load(CONTENT / "bricks" / "tools.yaml")
        data["label_text"] = mark + data["label_text"]
        _dump(root / "bricks" / "tools.yaml", data)
        demo = root / "demo_files"
        for french in (CONTENT / "demo_files").rglob("*"):
            if french.is_file():
                rel = french.relative_to(CONTENT / "demo_files")
                (demo / rel).parent.mkdir(parents=True, exist_ok=True)
                (demo / rel).write_text(mark + french.read_text(encoding="utf-8"), "utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    return content


def _known() -> dict[str, set[str]]:
    """Every id `scenarios.yaml` names, known."""
    data = _load(CONTENT / "scenarios.yaml")
    fields = ("bricks", "tools", "mcp_servers", "skills", "hooks")
    return {f: {i for s in data["scenarios"].values() for i in s.get(f) or []} for f in fields}


def _expected(lang: str, french: str) -> str:
    return french if lang == "fr" else _mark(lang) + french


def _french(rel: str) -> str:
    return (CONTENT / "demo_files" / rel).read_text(encoding="utf-8")


# ---------- each loader of the scope reads its argument, never the setting ----------


@pytest.mark.parametrize("lang", LANGS)
def test_each_loader_reads_its_language_not_the_setting(marked, lang):
    config.save_setting("language", _other(lang))
    french_scenarios = _load(CONTENT / "scenarios.yaml")

    program = load_scenarios(_known(), lang)
    assert program.program[0].title_text == _expected(
        lang, french_scenarios["program"][0]["title_text"]
    )
    assert load_cloud_content(lang).banner_text == _expected(
        lang, _load(CONTENT / "cloud.yaml")["banner_text"]
    )
    assert load_labels(lang).kinds[SegmentKind.USER_MESSAGE] == _expected(
        lang, "Message de l'utilisateur"
    )
    publishers, error = catalog.load_publishers(lang)
    assert error is None
    assert publishers.legend_text == _expected(
        lang, _load(CONTENT / "models" / "publishers.yaml")["legend_text"]
    )
    assert load_compression_content(lang).limits_text == _expected(
        lang, _load(CONTENT / "compression.yaml")["limits_text"]
    )
    assert load_brick_content("tools", lang).label_text == _expected(
        lang, _load(CONTENT / "bricks" / "tools.yaml")["label_text"]
    )
    assert read_file("recette_crepes.txt", lang) == _expected(lang, _french("recette_crepes.txt"))


@pytest.mark.parametrize("lang", LANGS)
def test_the_models_catalog_speaks_the_language_it_is_given(marked, lang):
    config.save_setting("language", _other(lang))
    cfg = config.load_config()
    payload = catalog.models_payload([], cfg, lang=lang)
    network = _expected(lang, "Réseau")
    assert payload["legend_text"].startswith(_expected(lang, "Légende"))
    assert payload["groups"] and all(
        g["label_text"].startswith(f"{network} · ") for g in payload["groups"]
    )


# ---------- read_file (matrix) ----------


@pytest.mark.parametrize("lang", LANGS)
def test_the_listing_is_the_french_folders_in_every_language(marked, lang):
    """Matrix « Liste »: the same names in the three languages."""
    assert read_file(".", lang) == read_file(".", "fr")
    assert "confidentiel/budget_projet.txt" in read_file(".", lang)


def test_an_untranslated_demo_file_is_read_in_french(marked):
    """Matrix « Fichier non traduit »: the fallback is file by file."""
    (marked / "i18n" / "en" / "demo_files" / "notes_reunion.txt").unlink()
    assert read_file("notes_reunion.txt", "en") == _french("notes_reunion.txt")
    assert read_file("recette_crepes.txt", "en").startswith(_mark("en"))


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("path", ["../x", "../README.md", "../i18n/de/demo_files/guide.md"])
def test_an_escape_is_refused_in_every_language(marked, lang, path):
    """Matrix « Évasion »: the confinement is the French folder's."""
    with pytest.raises(ToolError, match="sort du dossier de démonstration"):
        read_file(path, lang)


def test_a_file_only_translated_is_not_readable(marked):
    """The translated folder adds no file: the listing and the confinement are French."""
    (marked / "i18n" / "de" / "demo_files" / "extra.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ToolError, match="Fichier absent"):
        read_file("extra.txt", "de")


def _session(lang: str, outputs: list[str], hooks=None) -> AppSession:
    engine = FakeEngine(outputs=outputs, template=QWEN.decode("utf-8"), architecture="qwen35")
    if hooks is None:
        return booted_session(engine, window=WINDOW, values={"language": lang})
    session = AppSession(
        config.Config(
            values={"language": lang, "context": {"window": WINDOW, "near_limit_ratio": 0.8}}
        ),
        engine_factory=lambda path, n_ctx: engine,
        hooks=hooks,
    )
    session.boot("fake.gguf").result()
    return session


@pytest.mark.parametrize("lang", LANGS)
def test_a_turn_reads_the_demo_file_of_the_sessions_language(marked, lang):
    """Matrix « Lecture traduite »: `read_file` bound to the session's language."""
    config.save_setting("language", _other(lang))  # the setting is not what is read
    session = _session(lang, [call("read_file", path="recette_crepes.txt"), "Voilà."])
    session.set_brick("tools", True)
    (ended,) = _run(session, "Lis la recette.")["tool_ended"]
    assert ended["status"] == "ok"
    assert ended["result"] == _expected(lang, _french("recette_crepes.txt"))
    session.close()


@pytest.mark.parametrize("lang", LANGS)
def test_h1_refuses_the_confidential_folder_in_every_language(marked, lang):
    """Matrix « Garde-fou »: `confidentiel/` refused whatever folder would be read."""
    session = _session(lang, [call("read_file", path=SECRET), "Non."], hooks=DEMO_HOOKS)
    session.set_brick("tools", True)
    session.set_brick("hooks", True)
    events = _run(session, "Quel est le budget ?")
    blocks = [d for d in events["hook_decided"] if d["decision"] == "block"]
    assert blocks and blocks[0]["detail_text"].startswith(BLOCKED)
    assert "tool_ended" not in events
    session.close()


def test_the_bound_read_file_follows_a_change_of_language(marked):
    session = _session("fr", ["Voilà."])
    spec = session._registry.get("read_file")
    assert spec.run(path="recette_crepes.txt") == _french("recette_crepes.txt")
    session.set_language("de")
    assert session._registry.get("read_file").run(path="recette_crepes.txt").startswith("[de] ")
    session.close()


# ---------- the session: programme, cloud, labels ----------


def _scenario_payloads(mark: int) -> list[dict]:
    return [e.payload for e in get_journal().events_since(mark) if e.kind == "scenario_changed"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_programme_is_read_in_the_sessions_language(marked, lang):
    config.save_setting("language", _other(lang))
    mark = get_journal().last_seq()
    session = _session(lang, ["Voilà."])
    program = _scenario_payloads(mark)[-1]["program"]
    titles = {s["id"]: s["title_text"] for m in program["modules"] for s in m["scenarios"]}
    assert titles["native_tools"] == ("Outils natifs" if lang == "fr" else f"[{lang}] native_tools")
    session.close()


def _cloud() -> AppSession:
    """A French session with Groq loaded (no request: booting a cloud model sends none)."""
    cfg = config.load_config()
    entry = cfg.cloud_model("groq")
    config.write_api_key(entry.id, entry.host, SecretStr(SENTINEL))
    session = AppSession(cfg, cloud_factory=Provider().factory)
    session.boot_cloud(entry).result()
    session.join()
    return session


def test_set_language_reads_the_programme_the_cloud_and_the_labels_again(marked):
    """Matrix « Changement de langue »: `fr` → `en`, a cloud model loaded."""
    session = _cloud()
    assert not session.active_model()["banner_text"].startswith("[")
    assert session._labels.kinds[SegmentKind.USER_MESSAGE] == "Message de l'utilisateur"
    mark = get_journal().last_seq()

    session.set_language("en")

    assert session._cloud_content.banner_text.startswith("[en] ")
    assert session.active_model()["banner_text"].startswith("[en] ")
    assert session._labels.kinds[SegmentKind.USER_MESSAGE] == "[en] Message de l'utilisateur"
    program = _scenario_payloads(mark)[-1]["program"]
    assert program["modules"][0]["title_text"].startswith("[en] ")
    session.close()


def test_the_active_model_of_a_cloud_choice_is_in_the_language():
    entry = config.load_config().cloud_model("groq")
    french = active_model(entry, "fr")["banner_text"]
    assert active_model(entry, "en")["banner_text"]  # never bare for an existing language
    assert french == active_model(entry)["banner_text"]


def test_an_invalid_translated_programme_falls_back_on_french(marked):
    """Matrix « Traduction invalide »: `harness_error`, then the French programme."""
    (marked / "i18n" / "de" / "scenarios.yaml").write_text("program: 3\n", encoding="utf-8")
    mark = get_journal().last_seq()
    session = _session("de", ["Voilà."])
    events = get_journal().events_since(mark)
    errors = [e.payload["message_text"] for e in events if e.kind == "harness_error"]
    assert errors == ["Un fichier traduit (de) sous content/i18n/de/ est invalide."]
    program = _scenario_payloads(mark)[-1]["program"]
    titles = {s["id"]: s["title_text"] for m in program["modules"] for s in m["scenarios"]}
    assert titles["native_tools"] == "Outils natifs"
    session.close()


def test_an_invalid_translated_publishers_file_gives_the_french_table(marked):
    (marked / "i18n" / "de" / "models" / "publishers.yaml").write_text(": :\n", "utf-8")
    content, error = catalog.load_publishers("de")
    french, _ = catalog.load_publishers("fr")
    assert content == french and content.publishers
    assert "content/i18n/de/models/publishers.yaml" in error


# ---------- /api/diagnostic ----------


@pytest.mark.parametrize("lang", LANGS)
def test_the_diagnostic_gives_the_sessions_language_to_the_catalog_and_cloud(marked, lang):
    config.save_setting("language", _other(lang))
    session = _session(lang, ["Voilà."])
    body = _client(session).get("/api/diagnostic").json()
    assert body["models"]["legend_text"].startswith(_expected(lang, "Légende"))
    rows = {row["id"]: row for row in body["cloud"]["models"]}
    no_key = _load(CONTENT / "cloud.yaml")["no_key_text"]
    assert any(
        (row.get("disabled_text") or "").startswith(_expected(lang, no_key[:10]))
        for row in rows.values()
    )
    session.close()
