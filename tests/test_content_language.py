"""Languages (3/5, AD-19): the pedagogical content in the session's language. Each loader of
the scope is given the session's language, never `settings.json`'s; `read_file` reads the
translated demonstration file, file by file, confined to the French folder."""

from __future__ import annotations

import re
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
from wavestack.cloud import fill as cloud_fill
from wavestack.compression.port import load_compression_content
from wavestack.context.segments import SegmentKind, load_labels
from wavestack.hooks import DEMO_HOOKS
from wavestack.messages import msg
from wavestack.models import catalog
from wavestack.models.discovery import ModelCandidate
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
        data["hosting_text"]["local"] = mark + data["hosting_text"]["local"]
        for engine in ("file", "ollama"):
            data["served_by_text"][engine] = mark + data["served_by_text"][engine]
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


@pytest.mark.parametrize("lang", LANGS)
def test_the_local_models_speak_the_language_they_are_given(marked, tmp_path, lang):
    """A file and an Ollama model: their hosting label and their group's, in `lang`."""
    gguf = tmp_path / "x.gguf"
    gguf.write_bytes(b"not a gguf")
    candidates = [
        ModelCandidate(source="models_dir", status="found", path=str(gguf), name=gguf.name),
        ModelCandidate(
            source="server",
            status="incompatible",
            server_url="http://127.0.0.1:11434",
            name="faux-ollama:latest",
            engine="ollama",
            ref="ollama/faux-ollama:latest",
            provider="Ollama",
            reason="Fichier GGUF introuvable.",
            publisher_hint="qwen3",
        ),
    ]
    config.save_setting("language", _other(lang))
    payload = catalog.models_payload(candidates, config.load_config(), lang=lang)
    local = [g for g in payload["groups"] if g["hosting"] == "local"]
    entries = {m["kind"]: m for g in local for m in g["models"]}
    here = _expected(lang, "Sur ce poste")
    assert entries["file"]["hosting_label_text"] == f"{here} · {_expected(lang, 'fichier')}"
    assert entries["server"]["hosting_label_text"] == f"{here} · {_expected(lang, 'Ollama')}"
    assert local and all(g["label_text"].startswith(f"{here} · ") for g in local)


# ---------- read_file (matrix) ----------


@pytest.mark.parametrize("lang", LANGS)
def test_the_listing_is_the_french_folders_in_every_language(marked, lang):
    """Matrix « Liste »: the same names in the three languages (its heading in the
    language, story 7 of 2026-09-30)."""
    assert read_file(".", lang).splitlines()[1:] == read_file(".", "fr").splitlines()[1:]
    assert (
        read_file(".", lang).splitlines()[0]
        == msg("tools.read_file.listing", lang, files="").splitlines()[0]
    )
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
    blocked = msg("hooks.h1.blocked", lang, path=SECRET)  # in the session's language
    assert blocks and blocks[0]["detail_text"] == blocked
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
    english = _load(CONTENT / "i18n" / "en" / "cloud.yaml")["banner_text"]
    assert active_model(entry, "en")["banner_text"] == cloud_fill(
        english, entry, load_cloud_content("en")
    )
    assert active_model(entry, "en")["banner_text"] != french
    assert french == active_model(entry)["banner_text"]


def test_an_invalid_translated_cloud_file_gives_the_french_texts(marked):
    """An invalid `i18n/de/cloud.yaml`: the indicator and the diagnostic in French, the
    diagnostic's `harness_error` naming the translated folder."""
    (marked / "i18n" / "de" / "cloud.yaml").write_text(": :\n", encoding="utf-8")
    entry = config.load_config().cloud_model("groq")
    assert active_model(entry, "de")["banner_text"] == active_model(entry, "fr")["banner_text"]
    session = _session("de", ["Voilà."])
    mark = get_journal().last_seq()
    response = _client(session).get("/api/diagnostic")
    assert response.status_code == 200
    french = _load(CONTENT / "cloud.yaml")
    assert response.json()["cloud"]["key_hint_text"] == french["key_hint_text"]
    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert errors and all("content/i18n/de/" in e["message_text"] for e in errors)
    session.close()


def test_an_invalid_translated_programme_falls_back_on_french(marked):
    """Matrix « Traduction invalide »: `harness_error`, then the French programme."""
    (marked / "i18n" / "de" / "scenarios.yaml").write_text("program: 3\n", encoding="utf-8")
    mark = get_journal().last_seq()
    session = _session("de", ["Voilà."])
    events = get_journal().events_since(mark)
    errors = [e.payload["message_text"] for e in events if e.kind == "harness_error"]
    assert errors == ["Eine übersetzte Datei (de) unter content/i18n/de/ ist ungültig."]
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


# ---------- the shipped translations (languages 3/5, commit 2) ----------

BRICK_NAMES = {
    "en": {
        "reasoning": "Reasoning",
        "short_memory": "Short-term memory",
        "system_prompt": "System prompt",
        "global_memory": "Global memory",
        "tools": "Tools",
        "rag": "RAG",
        "mcp": "MCP",
        "skills": "Skills",
        "hooks": "Hooks",
        "subagent": "Sub-agent",
        "compression": "Compression",
    },
    "de": {
        "reasoning": "Denkprozess",
        "short_memory": "Kurzzeitgedächtnis",
        "system_prompt": "System-Prompt",
        "global_memory": "Globales Gedächtnis",
        "tools": "Tools",
        "rag": "RAG",
        "mcp": "MCP",
        "skills": "Skills",
        "hooks": "Hooks",
        "subagent": "Sub-Agent",
        "compression": "Kompression",
    },
}
# The quotation marks of each language: « … », “…”, „…“.
MARKS = {"fr": ("«", "»"), "en": ("“", "”"), "de": ("„", "“")}
QUOTED = {
    lang: rf"{re.escape(opening)}\s*(.*?)\s*{re.escape(closing)}"
    for lang, (opening, closing) in MARKS.items()
}
# The catalogues whose labels an instruction may cite, besides the bricks' and skills' names.
CATALOGUES = (
    "ui.yaml",
    "tools.yaml",
    "subagent.yaml",
    "mcp.yaml",
    "skills.yaml",
    "hooks.yaml",
    "rag.yaml",
    "compression.yaml",
    "labels/segment_kinds.yaml",
)
SKILL_IDS = sorted(p.name for p in (CONTENT / "skills").iterdir() if (p / "SKILL.md").is_file())
_HEAD = re.compile(r"\s*\(?≈?\s*\{")


def _q(text: str, lang: str) -> str:
    opening, closing = MARKS[lang]
    return f"{opening}{text}{closing}"


def _leaves(data: object) -> list[str]:
    if isinstance(data, dict):
        return [v for x in data.values() for v in _leaves(x)]
    if isinstance(data, list):
        return [v for x in data for v in _leaves(x)]
    return [data] if isinstance(data, str) else []


def _catalogue_values(lang: str) -> list[str]:
    from wavestack.skills import load_skills_content

    values = [v for rel in CATALOGUES for v in _leaves(_load(config.content_file(rel, lang)))]
    values += [load_brick_content(b, lang).label_text for b in BRICK_NAMES["en"]]
    values += [s.label_text for s in load_skills_content(SKILL_IDS, lang).skills.values()]
    return [" ".join(v.split()) for v in values]


def _is_label(quote: str, values: list[str]) -> bool:
    """A label of the catalogues: a value, a value's text before its variable, or the start of
    one at a word boundary; « <Forcer l'appel> · <tool> » is the button of a forced call."""
    base = quote.split(" · ")[0]
    for value in values:
        head = _HEAD.split(value)[0].rstrip(" ,:(≈")
        at_boundary = head.startswith(base) and not head[len(base) : len(base) + 1].isalnum()
        if base == value or at_boundary:
            return True
    return False


def _quoted(text: str, lang: str) -> list[str]:
    return [" ".join(q.split()) for q in re.findall(QUOTED[lang], text, re.S)]


@pytest.mark.parametrize("lang", TRANSLATED)
def test_the_bricks_have_their_names(lang):
    names = {b: load_brick_content(b, lang).label_text for b in BRICK_NAMES[lang]}
    assert names == BRICK_NAMES[lang]


@pytest.mark.parametrize("lang", TRANSLATED)
def test_the_skills_name_the_tools_brick_by_its_label(lang):
    """Story 1's skills cite the Tools brick by the name of `bricks/tools.yaml` of their
    language (a reprise of languages 1/5)."""
    label = load_brick_content("tools", lang).label_text
    cited = {"en": r'"([^"]+)" brick', "de": "Baustein „([^“]+)“"}[lang]
    names = []
    for skill in SKILL_IDS:
        text = config.content_file(f"skills/{skill}/SKILL.md", lang).read_text(encoding="utf-8")
        names += re.findall(cited, text)
    assert names and set(names) == {label}


@pytest.mark.parametrize("lang", TRANSLATED)
def test_every_label_an_instruction_cites_is_one_of_its_language(lang):
    """A label quoted in an `en` or `de` instruction is a label of that language's catalogues,
    as many as the French instruction quotes; its quotation marks are the language's."""
    french_values, values = _catalogue_values("fr"), _catalogue_values(lang)
    french = load_scenarios(_known(), "fr").scenarios
    for scenario_id, scenario in load_scenarios(_known(), lang).scenarios.items():
        text, french_text = scenario.description_text, french[scenario_id].description_text
        assert "«" not in text and "»" not in text, scenario_id
        quotes, french_quotes = _quoted(text, lang), _quoted(french_text, "fr")
        assert len(quotes) == len(french_quotes), (scenario_id, quotes)
        labels = [q for q in quotes if _is_label(q, values)]
        french_labels = [q for q in french_quotes if _is_label(q, french_values)]
        assert len(labels) == len(french_labels), (
            scenario_id,
            [q for q in quotes if q not in labels],
            [q for q in french_quotes if q not in french_labels],
        )


@pytest.mark.parametrize("lang", TRANSLATED)
def test_the_fallbacks_cite_the_labels_of_their_language(lang):
    """`test_program`'s checks of the forced actions (story 27, lot K), in `en` and `de`:
    each instruction cites the button, the preset and the replay of its language."""
    from wavestack.mcp.servers import load_mcp_content
    from wavestack.skills import load_skills_content
    from wavestack.tools.registry import load_tools_content
    from wavestack.ui_texts import load_ui_texts

    ui = load_ui_texts(lang)["main"]
    force, replay, clear = ui["force"]["labels"], ui["chat"]["replay_last"], ui["chat"]["clear"]
    scenario = load_scenarios(_known(), lang).scenarios
    mcp, french_mcp = load_mcp_content(lang).call_presets, load_mcp_content("fr").call_presets
    tools = load_tools_content(lang).tools["read_file"]
    french_tools = load_tools_content("fr").tools["read_file"]

    def preset(french_label: str) -> str:
        index = [p.label_text for p in french_tools.presets].index(french_label)
        return tools.presets[index].label_text

    for scenario_id, tool, index in (
        ("mcp_full", "local__define_term", 0),
        ("mcp_lazy", "local__define_term", 0),
        ("iam", "mslearn__microsoft_docs_search", 0),
        ("iam", "mslearn__microsoft_docs_search", 1),
        ("sovereignty", "datagouv__search_datasets", 0),
        ("sovereignty", "mslearn__microsoft_docs_search", 2),
    ):
        text = scenario[scenario_id].description_text
        assert mcp[tool][index].args.keys() == french_mcp[tool][index].args.keys()
        assert _q(f"{force['tools']} · {tool}", lang) in text, (scenario_id, tool)
        assert _q(mcp[tool][index].label_text, lang) in text, (scenario_id, index)
        assert _q(replay, lang) in text, scenario_id
    text = scenario["sovereignty"].description_text
    assert (
        text.index(_q(f"{force['tools']} · datagouv__search_datasets", lang))
        < text.index(_q(clear, lang))
        < text.index(_q(f"{force['tools']} · mslearn__microsoft_docs_search", lang))
    )
    assert _q(force["mcp"], lang) in scenario["mcp_lazy"].description_text
    skills = scenario["skills"]
    label = load_skills_content(["meeting_minutes"], lang).skills["meeting_minutes"].label_text
    assert _q(force["skills"], lang) in skills.description_text
    assert _q(label, lang) in skills.description_text
    assert "meeting_minutes" in skills.prompts[0] and "load_skill" in skills.prompts[0]
    for scenario_id, presets in (
        (
            "compression",
            ("Journal de sauvegarde (compression)", "Guide du harnais (prose, compression)"),
        ),
        ("soc", ("Alertes SIEM (SOC)", "Comptes à privilèges (SOC, confidentiel)")),
    ):
        text = scenario[scenario_id].description_text
        assert _q(force["tools"], lang) in text and _q(tools.label_text, lang) in text
        for french_label in presets:  # test_program's :216, in the language
            assert _q(preset(french_label), lang) in text, (scenario_id, french_label)
    assert "confidentiel" not in scenario["soc"].prompts[1]
    assert "alertes_siem.log" in scenario["soc"].prompts[0]


@pytest.mark.parametrize("lang", LANGS)
def test_a_scenario_is_played_in_the_sessions_language(lang):
    """Matrix « Scénario en allemand » (and in `en`, `fr`): title, instructions and prompts
    of the language's file, the Tools brick's explanation of its language."""
    session = _session(lang, ["Voilà."])
    mark = get_journal().last_seq()
    session.launch_scenario("native_tools")
    session.join()
    expected = _load(config.content_file("scenarios.yaml", lang))["scenarios"]["native_tools"]
    payload = _scenario_payloads(mark)[-1]
    assert payload["active"] == "native_tools"
    shown = {s["id"]: s for m in payload["program"]["modules"] for s in m["scenarios"]}
    entry = shown["native_tools"]
    assert entry["title_text"] == expected["title_text"]
    assert entry["prompts"] == expected["prompts"]
    assert " ".join(entry["description_text"].split()) == " ".join(
        expected["description_text"].split()
    )
    bricks = [e.payload for e in get_journal().events_since(mark) if e.kind == "bricks_changed"]
    card = next(b for b in bricks[-1]["bricks"] if b["id"] == "tools")
    assert card["explanation_text"] == load_brick_content("tools", lang).explanation_text
    assert card["label_text"] == BRICK_NAMES.get(lang, {"tools": "Outils"})["tools"]
    if lang != "fr":
        assert entry["title_text"] != "Outils natifs"
        assert card["explanation_text"] != load_brick_content("tools", "fr").explanation_text
    session.close()


@pytest.mark.parametrize("lang", LANGS)
def test_read_file_reads_the_shipped_translation(lang):
    """Matrix « Lecture traduite » and « Français inchangé »: each demonstration file of the
    language; in French, the French files as before."""
    for french in (CONTENT / "demo_files").rglob("*"):
        if french.is_file():
            rel = french.relative_to(CONTENT / "demo_files").as_posix()
            path = french if lang == "fr" else CONTENT / "i18n" / lang / "demo_files" / rel
            assert read_file(rel, lang) == path.read_text(encoding="utf-8"), rel
            if lang != "fr":
                assert read_file(rel, lang) != french.read_text(encoding="utf-8"), rel
