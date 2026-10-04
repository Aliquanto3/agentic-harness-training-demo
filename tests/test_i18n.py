"""Languages (1/5, AD-19): French by default, English and German overlaid under
`content/i18n/{lang}/`; the language changes only on an empty conversation."""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import get_args

import pytest
import yaml
from fake_engine import FakeEngine, booted_session
from test_bricks import HEADERS, _client
from test_mcp import enable, loop, mcp_session, wait_for  # noqa: F401 - fixture
from test_tools import QWEN, _segments, call
from test_turn import _run

from wavestack import config, messages
from wavestack import hooks as hooks_module
from wavestack import memory as memory_file
from wavestack.bricks.contract import load_brick_content, load_default_system_prompt
from wavestack.cloud import load_cloud_content
from wavestack.compression.port import load_compression_content
from wavestack.context.segments import load_labels
from wavestack.hooks import date_fr, date_text, load_hooks_content
from wavestack.mcp import lab as mcp_lab
from wavestack.mcp.connection import McpConnection
from wavestack.mcp.servers import LOCAL, McpServer, load_local_tools, load_mcp_content
from wavestack.models.catalog import load_publishers
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import load_rag_content
from wavestack.scenarios import load_scenarios
from wavestack.session import app_session as app_session_module
from wavestack.session import llm_lab
from wavestack.session.app_session import SendRefused
from wavestack.skills import load_skills_content
from wavestack.subagent import load_subagent_content
from wavestack.tools.registry import load_tools_content
from wavestack.trace.catalog import LanguageChangedPayload
from wavestack.trace.journal import get_journal
from wavestack.ui_texts import load_ui_texts
from wavestack.web.app import LanguageIntention

CONTENT = config.content_dir()
TRANSLATED = ("en", "de")
SKILLS = (
    "budget_review",
    "caveman",
    "explain_like_ten",
    "meeting_minutes",
    "pirate",
    "working_days",
)
HOOKS = ["h1", "h2", "h3", "h5"]
# The defaults sent to the model, translated by this story (spec « Always »).
LLM_DEFAULTS = (
    "prompts/system.md",
    "prompts/subagent.md",
    "tools.yaml",
    "hooks.yaml",
    "memory/memory.yaml",
    "skills.yaml",
    *(f"skills/{s}/SKILL.md" for s in SKILLS),
    "subagent.yaml",
    "mcp.yaml",
    "mcp_local/glossary.yaml",
    "mcp_local/tools.yaml",
    "rag.yaml",
    "cloud.yaml",  # languages (3/5): the cloud test's prompt and tool
)
# Languages (3/5): the pedagogical content, translated with the same ids.
BRICKS = sorted(p.stem for p in (CONTENT / "bricks").glob("*.yaml"))
DEMO_FILES = sorted(
    p.relative_to(CONTENT / "demo_files").as_posix()
    for p in (CONTENT / "demo_files").rglob("*")
    if p.is_file()
)
PEDAGOGICAL = (
    *(f"bricks/{b}.yaml" for b in BRICKS),
    "scenarios.yaml",
    "cloud.yaml",
    "compression.yaml",
    "labels/segment_kinds.yaml",
    "models/publishers.yaml",
    *(f"demo_files/{f}" for f in DEMO_FILES),
)
# Languages (4/5): the workshops and the RAG corpus, translated under the same names.
CORPUS = sorted(p.name for p in (CONTENT / "corpus").glob("*.md"))
# Story 6 (2026-09-30): the MCP workshop too.
WORKSHOPS = ("llm_lab.yaml", "rag_lab.yaml", "mcp_lab.yaml", *(f"corpus/{c}" for c in CORPUS))
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?")
PROMPTS = {
    "fr": "Tu es l'assistant de démonstration de WaveStack. Réponds en français",
    "en": "You are WaveStack's demonstration assistant. Answer in English",
    "de": "Du bist der Demo-Assistent von WaveStack. Antworte auf Deutsch",
}
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


@pytest.fixture(autouse=True)
def _fresh_content_caches():
    """A test that changes the language leaves no content cached in it."""
    config.clear_content_caches()
    yield
    config.clear_content_caches()


def _translations() -> list[tuple[str, str]]:
    return sorted(
        (lang, path.relative_to(CONTENT / "i18n" / lang).as_posix())
        for lang in TRANSLATED
        for path in (CONTENT / "i18n" / lang).rglob("*")
        if path.is_file()
    )


def _placeholders(path: Path) -> set[str]:
    """The template keys of a file's text, its YAML comments aside."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    return set(_PLACEHOLDER.findall("\n".join(x for x in lines if not x.lstrip().startswith("#"))))


def _yaml(rel: str, lang: str) -> dict:
    return yaml.safe_load(config.content_file(rel, lang).read_text(encoding="utf-8"))


def _known_ids() -> dict[str, set[str]]:
    """Every id the French `scenarios.yaml` names, known (its own check is test_program's)."""
    data = _yaml("scenarios.yaml", "fr")
    fields = ("bricks", "tools", "mcp_servers", "skills", "hooks")
    return {f: {i for s in data["scenarios"].values() for i in s.get(f) or []} for f in fields}


def _shape(blocks: list) -> list:
    """A brick's explanation, as paragraphs and list lengths."""
    return [len(b) if isinstance(b, list) else "p" for b in blocks]


def _demo_names(text: str) -> set[str]:
    return {f for f in DEMO_FILES if f.rsplit("/", 1)[-1] in text}


# ---------- parity: every translated file ----------


def test_every_default_sent_to_the_model_is_translated():
    for lang in TRANSLATED:
        for rel in LLM_DEFAULTS:
            assert (CONTENT / "i18n" / lang / rel).is_file(), f"{lang}: {rel} manque"
    assert not (CONTENT / "i18n" / "en" / "skills" / "caveman" / "NOTICE.md").exists()


def test_every_pedagogical_file_is_translated():
    """Languages (3/5): the bricks, the scenarios, the cloud, compression, segment and
    publisher texts, and the demonstration files."""
    for lang in TRANSLATED:
        for rel in PEDAGOGICAL:
            assert (CONTENT / "i18n" / lang / rel).is_file(), f"{lang}: {rel} manque"


def test_every_workshop_and_corpus_file_is_translated():
    """Languages (4/5): the two workshops and the same set of corpus files."""
    for lang in TRANSLATED:
        for rel in WORKSHOPS:
            assert (CONTENT / "i18n" / lang / rel).is_file(), f"{lang}: {rel} manque"
        translated = sorted(p.name for p in (CONTENT / "i18n" / lang / "corpus").glob("*"))
        assert translated == CORPUS


@pytest.mark.parametrize(("lang", "rel"), _translations())
def test_translated_file_mirrors_the_french_one(lang, rel):
    """Same tree and name as a French file, same template keys, validated by the French
    file's model with the same identifiers."""
    french, translated = CONTENT / rel, CONTENT / "i18n" / lang / rel
    assert french.is_file(), f"{rel} n'existe pas en français"
    assert config.content_file(rel, lang) == translated
    # Languages (2/5, 5/5): `ui.yaml` and `messages.yaml` are compared key by key.
    if rel not in ("ui.yaml", "messages.yaml"):
        assert _placeholders(translated) == _placeholders(french)
    assert translated.read_text(encoding="utf-8") != french.read_text(encoding="utf-8")

    if rel in ("prompts/system.md", "prompts/subagent.md"):
        assert translated.read_text(encoding="utf-8").strip()
    elif rel == "tools.yaml":
        fr, tr = load_tools_content("fr"), load_tools_content(lang)
        assert tr.tools.keys() == fr.tools.keys()
        for name, text in fr.tools.items():
            assert tr.tools[name].parameters.keys() == text.parameters.keys()
            assert [p.args for p in tr.tools[name].presets] == [p.args for p in text.presets]
            assert (tr.tools[name].sends_text is None) == (text.sends_text is None)
    elif rel == "hooks.yaml":
        fr, tr = load_hooks_content(HOOKS, "fr"), load_hooks_content(HOOKS, lang)
        assert (tr.hooks.keys(), tr.points.keys()) == (fr.hooks.keys(), fr.points.keys())
        assert tr.language == lang
    elif rel == "memory/memory.yaml":
        fr, tr = memory_file.load_memory_content("fr"), memory_file.load_memory_content(lang)
        assert len(tr.demo) == len(fr.demo)  # the entries' ids: demo1…demoN
    elif rel == "skills.yaml" or rel.startswith("skills/"):
        fr, tr = load_skills_content(SKILLS, "fr"), load_skills_content(SKILLS, lang)
        assert {i: s.name for i, s in tr.skills.items()} == {i: i for i in SKILLS}
        assert tr.skills.keys() == fr.skills.keys()
    elif rel == "subagent.yaml":
        fr, tr = load_subagent_content("fr"), load_subagent_content(lang)
        assert [p.args.keys() for p in tr.presets] == [p.args.keys() for p in fr.presets]
    elif rel == "mcp.yaml":
        fr, tr = load_mcp_content("fr"), load_mcp_content(lang)
        assert tr.servers.keys() == fr.servers.keys()
        assert tr.call_presets.keys() == fr.call_presets.keys()
        for name, presets in fr.call_presets.items():
            assert [p.args.keys() for p in tr.call_presets[name]] == [
                p.args.keys() for p in presets
            ]
    elif rel == "mcp_local/glossary.yaml":
        fr, tr = _yaml(rel, "fr")["terms"], _yaml(rel, lang)["terms"]
        assert len(tr) == len(fr) and all(str(v).strip() for v in tr.values())
    elif rel == "mcp_local/tools.yaml":
        fr, tr = load_local_tools("fr"), load_local_tools(lang)
        assert tr.list_terms != fr.list_terms and tr.define_term != fr.define_term
    elif rel == "ui.yaml":  # languages (2/5): its parity key by key is in test_ui_texts
        fr, tr = load_ui_texts("fr"), load_ui_texts(lang)
        assert tr["common"]["language"] != fr["common"]["language"]
    elif rel == "messages.yaml":  # languages (5/5): the same keys, the same variables
        fr, tr = messages.load_messages("fr"), messages.load_messages(lang)
        raw = messages.flatten(_yaml(rel, lang))
        # Story 7 of 2026-09-30: complete, every key of the French catalogue translated.
        assert raw.keys() == fr.keys(), sorted(fr.keys() ^ raw.keys())[:20]
        for key, text in raw.items():
            assert messages.variables(text) == messages.variables(fr[key]), key
        assert (
            tr["session.translation_invalid.message"] != fr["session.translation_invalid.message"]
        )
    elif rel == "rag.yaml":  # languages (4/5): the same documents, their titles translated
        fr, tr = load_rag_content("fr"), load_rag_content(lang)
        assert [(d.id, d.file) for d in tr.documents] == [(d.id, d.file) for d in fr.documents]
        assert not {d.title_text for d in tr.documents} & {d.title_text for d in fr.documents}
        assert tr.intro_text != fr.intro_text
        assert "French" not in tr.intro_text and "Französisch" not in tr.intro_text
    elif rel == "llm_lab.yaml":  # languages (4/5)
        fr, tr = llm_lab.load_lab_content("fr"), llm_lab.load_lab_content(lang)
        assert tr.title_text != fr.title_text
        assert tr.model_dump().keys() == fr.model_dump().keys()
    elif rel == "rag_lab.yaml":  # languages (4/5): the same stages, options and settings
        fr, tr = rag_lab.load_lab_content("fr"), rag_lab.load_lab_content(lang)
        assert tr.title_text != fr.title_text
        assert (tr.stages.keys(), tr.params.keys()) == (fr.stages.keys(), fr.params.keys())
        assert {k: v.keys() for k, v in tr.options.items()} == {
            k: v.keys() for k, v in fr.options.items()
        }
    elif rel == "mcp_lab.yaml":  # story 6 (2026-09-30): the same transports and methods
        fr, tr = mcp_lab.load_lab_content("fr"), mcp_lab.load_lab_content(lang)
        assert tr.title_text != fr.title_text and tr.intro_text != fr.intro_text
        assert tr.model_dump().keys() == fr.model_dump().keys()
        assert (tr.transports.keys(), tr.methods.keys()) == (
            fr.transports.keys(),
            fr.methods.keys(),
        )
    elif rel.startswith("corpus/"):  # languages (4/5): the same sections, about as long
        fr_text = french.read_text(encoding="utf-8")
        tr_text = translated.read_text(encoding="utf-8")
        headings = [x.split(" ")[0] for x in fr_text.splitlines() if x.startswith("#")]
        assert [x.split(" ")[0] for x in tr_text.splitlines() if x.startswith("#")] == headings
        assert tr_text.count("<!--") == fr_text.count("<!--")
        ratio = len(tr_text) / len(fr_text)
        assert 0.6 <= ratio <= 1.4, ratio
    elif rel.startswith("bricks/"):  # languages (3/5)
        brick_id = rel.removeprefix("bricks/").removesuffix(".yaml")
        fr, tr = load_brick_content(brick_id, "fr"), load_brick_content(brick_id, lang)
        assert _shape(tr.explanation_text) == _shape(fr.explanation_text)
        assert (tr.outbound_text is None) == (fr.outbound_text is None)
    elif rel == "scenarios.yaml":
        fr = load_scenarios(_known_ids(), "fr")
        tr = load_scenarios(_known_ids(), lang)
        assert [(m.duration_min, m.scenarios) for m in tr.program] == [
            (m.duration_min, m.scenarios) for m in fr.program
        ]
        assert tr.transverse == fr.transverse and tr.scenarios.keys() == fr.scenarios.keys()
        texts = {"title_text", "description_text", "prompts"}
        for scenario_id, french_scenario in fr.scenarios.items():
            scenario = tr.scenarios[scenario_id]
            assert scenario.model_dump(exclude=texts) == french_scenario.model_dump(exclude=texts)
            assert len(scenario.prompts) == len(french_scenario.prompts), scenario_id
            pairs = [
                (french_scenario.description_text, scenario.description_text),
                *zip(french_scenario.prompts, scenario.prompts, strict=True),
            ]
            for fr_text, tr_text in pairs:  # a demo file named in French is named here too
                assert _demo_names(tr_text) >= _demo_names(fr_text), (scenario_id, tr_text)
    elif rel == "cloud.yaml":
        fr, tr = load_cloud_content("fr"), load_cloud_content(lang)
        assert tr.training_text.keys() == fr.training_text.keys()
        assert (tr.test.tool.name, tr.test.tool_reply) == (fr.test.tool.name, fr.test.tool_reply)
        assert tr.test.prompt != fr.test.prompt
    elif rel == "compression.yaml":
        fr, tr = load_compression_content("fr"), load_compression_content(lang)
        assert tr.limits_text != fr.limits_text
    elif rel == "labels/segment_kinds.yaml":
        fr, tr = load_labels("fr"), load_labels(lang)
        assert (tr.kinds.keys(), tr.groups.keys()) == (fr.kinds.keys(), fr.groups.keys())
    elif rel == "models/publishers.yaml":
        (fr, fr_error), (tr, tr_error) = load_publishers("fr"), load_publishers(lang)
        assert fr_error is None and tr_error is None
        fixed = {"id", "architectures", "names", "names_first"}
        assert [p.model_dump(include=fixed) for p in tr.publishers] == [
            p.model_dump(include=fixed) for p in fr.publishers
        ]
    elif rel.startswith("demo_files/"):  # the same name, its text translated
        fr_lines = french.read_text(encoding="utf-8").splitlines()
        tr_lines = translated.read_text(encoding="utf-8").splitlines()
        if rel.endswith(".log"):  # the same lines, stamps and format
            assert len(tr_lines) == len(fr_lines)
            for a, b in zip(fr_lines, tr_lines, strict=True):
                assert _TIMESTAMP.findall(b) == _TIMESTAMP.findall(a), b
                assert b.count("|") == a.count("|"), b
        elif rel.endswith(".md"):  # the same sections
            assert [x.split(" ")[0] for x in tr_lines if x.startswith("#")] == [
                x.split(" ")[0] for x in fr_lines if x.startswith("#")
            ]
        ratio = sum(map(len, tr_lines)) / sum(map(len, fr_lines))
        assert 0.6 < ratio < 1.6, ratio
    else:
        pytest.fail(f"{rel} : aucun contrôle de parité")


# ---------- resolution ----------


def test_content_file_falls_back_on_french():
    assert config.content_file("tools.yaml", "fr") == CONTENT / "tools.yaml"
    assert config.content_file("tools.yaml", "en") == CONTENT / "i18n" / "en" / "tools.yaml"
    # Languages (4/5): the workshops are translated too.
    assert config.content_file("llm_lab.yaml", "de") == CONTENT / "i18n" / "de" / "llm_lab.yaml"
    assert config.content_file("tools.yaml", "it") == CONTENT / "tools.yaml"  # unknown language


def test_language_setting_is_bounded_and_read_by_content_file():
    assert config.load_config().language == "fr"
    assert config.content_file("tools.yaml") == CONTENT / "tools.yaml"
    config.save_setting("language", "de")
    assert config.load_config().language == config.current_language() == "de"
    assert config.content_file("tools.yaml") == CONTENT / "i18n" / "de" / "tools.yaml"
    config.save_setting("language", "it")
    assert config.load_config().language == config.current_language() == "fr"
    assert config.Config(values={"language": 3}).language == "fr"


def test_the_local_mcp_server_is_started_in_the_sessions_language():
    no_loop = None  # `_transport` of the local server reads no loop
    server = McpServer(LOCAL, None)
    connection = McpConnection(server, no_loop, connect_timeout=1, call_timeout=1)
    assert connection._transport(None).args[-1] == "fr"
    config.save_setting("language", "de")  # the setting is not what the process gets
    connection = McpConnection(server, no_loop, connect_timeout=1, call_timeout=1, language="en")
    assert connection._transport(None).args == ["-m", "wavestack.mcp.local_server", "en"]


def test_the_demo_files_are_the_same_in_every_language():
    """Languages (3/5): the same files under the same names, `confidentiel/` included."""
    for lang in TRANSLATED:
        demo = CONTENT / "i18n" / lang / "demo_files"
        names = sorted(p.relative_to(demo).as_posix() for p in demo.rglob("*") if p.is_file())
        assert names == DEMO_FILES, lang


def test_every_per_language_table_has_exactly_the_languages():
    languages = set(config.LANGUAGES)
    assert set(config.LANGUAGE_LABELS) == languages
    assert set(hooks_module._WEEKDAYS) | {"fr"} == languages == set(hooks_module._MONTHS) | {"fr"}
    assert set(app_session_module._LANGUAGE_LOCKED) == languages
    assert set(get_args(LanguageIntention.model_fields["language"].annotation)) == languages
    assert set(get_args(LanguageChangedPayload.model_fields["language"].annotation)) == languages
    static = config.repo_root() / "src" / "wavestack" / "web" / "static"
    # Story 2 (2026-09-30): the picker is in « Affichage ▾ » of the shared bar, on every page.
    for name in ("index", "llm", "rag", "diagnostic", "models"):
        html = (static / f"{name}.html").read_text(encoding="utf-8")
        picker = re.search(r'<select id="language-picker".*?</select>', html, re.S).group(0)
        options = re.findall(r'<option value="(\w+)" lang="\w+">([^<]+)</option>', picker)
        assert options == list(config.LANGUAGE_LABELS.items()), name
        assert 'id="display-menu"' in html and 'src="/static/site-nav.js"' in html, name
    # Languages (2/5): the picker's texts, once `LANGUAGE_TEXTS` of app.js, are in
    # `common.language` of each language's ui.yaml.
    names = {lang: load_ui_texts(lang)["common"]["language"]["name"] for lang in config.LANGUAGES}
    assert names == {"fr": "Langue", "en": "Language", "de": "Sprache"}


def test_h3_speaks_the_language_of_the_file_it_read(tmp_path, monkeypatch):
    """A missing German `hooks.yaml`: the French sentence, with a French date."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "de" / "hooks.yaml").unlink()
    monkeypatch.setattr(config, "content_dir", lambda: content)
    assert load_hooks_content(HOOKS, "de").language == "fr"
    assert load_hooks_content(HOOKS, "en").language == "en"


def test_an_unreadable_settings_file_means_french(monkeypatch):
    def unreadable():
        raise PermissionError("settings.json verrouillé")

    monkeypatch.setattr(config, "read_settings", unreadable)
    assert config.current_language() == "fr"


# ---------- the intention ----------


def _session(**values):
    engine = FakeEngine(outputs=["Voilà."], template=QWEN.decode("utf-8"), architecture="qwen35")
    return engine, booted_session(engine, window=16384, values=values)


def _post(client, language):
    return client.post("/api/intentions/language", json={"language": language}, headers=HEADERS)


def test_english_then_a_turn_sends_only_english_defaults():
    """Matrix « Passage à l'anglais » and the first acceptance criterion."""
    _, session = _session()
    client = _client(session)
    state = client.get("/api/state").json()
    assert (state["language"], state["language_locked"]) == ("fr", False)
    assert [x["label"] for x in state["languages"]] == ["Français", "English", "Deutsch"]
    mark = get_journal().last_seq()

    response = _post(client, "en")

    assert response.status_code == 200
    assert config.read_settings()["language"] == "en"
    kinds = [e.kind for e in get_journal().events_since(mark)]
    assert "language_changed" in kinds
    after = kinds[kinds.index("language_changed") :]
    assert {"bricks_changed", "scenario_changed", "memory_changed"} <= set(after)
    changed = [e.payload for e in get_journal().events_since(mark) if e.kind == "language_changed"]
    assert changed == [{"language": "en"}]
    assert client.get("/api/state").json()["language"] == "en"

    session.set_brick("system_prompt", True)
    session.set_brick("tools", True)
    ctx = _run(session, "What time is it?")["context_rendered"][0]
    prompt = [s["text"] for s in _segments(ctx, "system_prompt")]
    assert prompt == [load_default_system_prompt("en")] and prompt[0].startswith(PROMPTS["en"])
    catalog = "".join(s["text"] for s in _segments(ctx, "tool_catalog"))
    assert "Gives the workstation's local day, date and time." in catalog
    for text in ("Donne le jour", "Calcule exactement", "Lit un fichier", "Réponds en français"):
        assert text not in catalog
    assert session._registry.label("get_datetime") == "Time and date"
    session.close()


def test_a_conversation_locks_the_language():
    """Matrix « Conversation en cours »: 409, the reason, nothing written."""
    _, session = _session()
    client = _client(session)
    _run(session, "Bonjour")
    assert client.get("/api/state").json()["language_locked"] is True
    states = [e.payload for e in get_journal().all_events() if e.kind == "session_state"]
    assert states[-1]["language_locked"] is True and states[-1]["language"] == "fr"

    response = _post(client, "en")

    assert response.status_code == 409
    assert "conversation vide" in response.json()["detail"]
    assert "language" not in config.read_settings()
    session.clear_conversation()
    assert client.get("/api/state").json()["language_locked"] is False
    assert _post(client, "en").status_code == 200
    session.close()


def test_the_reason_is_also_in_the_current_language():
    _, session = _session(language="de")
    _run(session, "Hallo")
    with pytest.raises(SendRefused) as refused:
        session.set_language("en")
    assert "conversation vide" in refused.value.reason_text
    assert "leerer Unterhaltung" in refused.value.reason_text
    session.close()


def test_a_running_turn_refuses_the_change():
    """Matrix « Tour en cours »: 409 outside `idle`."""
    gate = threading.Event()
    engine = FakeEngine(outputs=["Voilà."], gate=gate)
    session = booted_session(engine)
    client = _client(session)
    session.send("Bonjour")
    try:
        assert session.state == "turn"
        assert _post(client, "en").status_code == 409
    finally:
        gate.set()
        session.join()
    assert "language" not in config.read_settings()
    session.close()


def test_an_unknown_language_is_refused():
    _, session = _session()
    assert _post(_client(session), "it").status_code == 422
    assert "language" not in config.read_settings()
    session.close()


def test_an_invalid_translation_falls_back_on_french(tmp_path, monkeypatch):
    """Matrix « Fichier traduit invalide »: `harness_error`, then French for that file."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "de" / "tools.yaml").write_text("tools: {}\n", encoding="utf-8")
    monkeypatch.setattr(config, "content_dir", lambda: content)
    mark = get_journal().last_seq()

    _, session = _session(language="de")

    errors = [e.payload for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert [e["message_text"] for e in errors] == [
        "Eine übersetzte Datei (de) unter content/i18n/de/ ist ungültig."
    ]
    assert session._tools_content.tools["get_datetime"].label_text == "Heure et date"  # French
    assert session._hooks_content.points["on_turn_end"] == "Ende der Runde"  # German
    assert "tools" not in session._content_errors
    session.close()


def test_an_untranslated_file_is_read_in_french(tmp_path, monkeypatch):
    """Matrix « Fichier non traduit »: no error."""
    content = tmp_path / "content"
    shutil.copytree(CONTENT, content)
    (content / "i18n" / "de" / "subagent.yaml").unlink()
    monkeypatch.setattr(config, "content_dir", lambda: content)
    mark = get_journal().last_seq()

    _, session = _session(language="de")

    assert [e for e in get_journal().events_since(mark) if e.kind == "harness_error"] == []
    assert session._subagent_content.phase_label_text == "Appel au sous-agent"
    assert session._subagent_content.prompt.startswith("Du bist ein Sub-Agent")  # translated .md
    session.close()


# ---------- what the change reloads ----------


def test_demo_memory_follows_the_language():
    """Matrix « Mémoire de démonstration »: a memory the user changed stays through the
    change; restored (« Réinitialiser »), it is the English demonstration."""
    _, session = _session()
    session.set_brick("global_memory", True)
    session.edit_memory("replace", "demo3", "Pascal aime le thé.")

    session.set_language("en")

    assert "Pascal aime le thé." in [e.text for e in session._memory]  # the user's, kept
    session.reset()
    session.join()
    written = json.loads(config.memory_path().read_text(encoding="utf-8"))
    assert [e["text"] for e in written] == [
        "The user's name is Pascal.",
        "Pascal is a cybersecurity consultant.",
        "Pascal is preparing a training course on AI agents.",
    ]
    assert [e.text for e in session._memory] == [e["text"] for e in written]
    assert session._registry.get("remember").description.startswith("Remembers a lasting")
    session.close()


def test_the_demonstration_memory_changes_language_with_the_session():
    """Never written (H5), it is rebuilt in the new language; written, it is written again."""
    _, session = _session()
    session.set_brick("global_memory", True)
    assert [e.text for e in session._memory][0] == "L'utilisateur s'appelle Pascal."
    session.set_language("de")
    assert [e.text for e in session._memory][0] == "Der Benutzer heißt Pascal."
    assert not config.memory_path().exists()  # still the demonstration, not written
    session.edit_memory("replace", "demo3", "Pascal trinkt Tee.")
    session.reset()  # written: the German demonstration
    session.join()
    session.set_language("en")
    assert [e.text for e in session._memory][0] == "The user's name is Pascal."
    assert "The user's name is Pascal." in config.memory_path().read_text(encoding="utf-8")
    session.close()


def test_a_german_turn_and_h3s_date():
    """Matrix « H3 en allemand »: a German turn, its date included."""
    assert (
        date_text(datetime(2026, 9, 24, 10, 12), "de")
        == "Donnerstag, 24. September 2026, 10:12 Uhr"
    )
    assert date_text(datetime(2026, 1, 5, 9, 5), "en") == "Monday 5 January 2026, 9:05"
    assert date_text(datetime(2026, 9, 24, 10, 12), "fr") == date_fr(datetime(2026, 9, 24, 10, 12))
    _, session = _session(language="de")
    for brick in ("system_prompt", "tools", "hooks"):
        session.set_brick(brick, True)
    ctx = _run(session, "Wie spät ist es?")["context_rendered"][0]
    assert [s["text"] for s in _segments(ctx, "system_prompt")][0].startswith(PROMPTS["de"])
    catalog = "".join(s["text"] for s in _segments(ctx, "tool_catalog"))
    assert "Gibt den Wochentag, das Datum und die Ortszeit" in catalog
    (injection,) = _segments(ctx, "hook_injection")
    assert injection["text"].startswith("Datum und Uhrzeit des Arbeitsplatzes: ")
    weekday = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
    assert any(f"{day}, " in injection["text"] for day in weekday)
    assert "Uhr. Regeln der Mission: Antworte auf Deutsch" in injection["text"]
    session.close()


def test_back_to_french_gives_the_same_context_byte_for_byte():
    """Matrix « Retour au français »: `fr` after `en`, the same context as before."""

    def context(session) -> str:
        for brick in ("system_prompt", "tools", "skills", "global_memory", "subagent"):
            session.set_brick(brick, True)
        ctx = _run(session, "Quelle heure est-il ?")["context_rendered"][0]
        session.clear_conversation()
        return "".join(s["text"] for s in ctx["segments"])

    _, fresh = _session()
    before = context(fresh)
    fresh.close()

    _, session = _session()
    session.set_language("en")
    english = context(session)
    session.set_language("fr")
    assert context(session) == before != english
    assert PROMPTS["en"] in english and PROMPTS["fr"] in before
    session.close()


def test_a_forced_tool_call_is_described_in_the_new_language():
    """The harness tools (`load_skill`, `remember`, `delegate`) are described again."""
    engine = FakeEngine(outputs=[call("load_skill", skill="pirate"), "Ahoy!"])
    engine.template, engine.architecture = QWEN.decode("utf-8"), "qwen35"
    session = booted_session(engine, window=16384)
    session.set_language("de")
    session.set_brick("skills", True)
    ctx = _run(session, "Sprich wie ein Pirat.")["context_rendered"][0]
    catalog = "".join(s["text"] for s in _segments(ctx, "tool_catalog"))
    assert "Lädt anhand seines Namens" in catalog and "Charge par son nom" not in catalog
    session.close()


def test_a_french_session_switched_to_german_speaks_german_everywhere():
    """Booted in French, then `de`: H3 (a date in `Uhr`), `delegate`, `load_tool_doc`, the
    RAG's intro and the sub-agent's prompt, all German."""
    _, session = _session()
    session.set_language("de")
    for brick in ("system_prompt", "tools", "hooks", "subagent"):
        session.set_brick(brick, True)
    ctx = _run(session, "Fasse den Harness-Leitfaden zusammen.")["context_rendered"][0]
    (injection,) = _segments(ctx, "hook_injection")
    date = r"Datum und Uhrzeit des Arbeitsplatzes: \w+, \d+\. \w+ \d{4}, \d+:\d{2} Uhr\."
    assert re.search(date, injection["text"])
    catalog = "".join(s["text"] for s in _segments(ctx, "tool_catalog"))
    assert "Übergibt eine Teilaufgabe an einen Sub-Agenten" in catalog
    assert session._registry.get("load_tool_doc").description.startswith(
        "Lädt die Dokumentation eines MCP-Tools"
    )
    assert session._rag_content.intro_text.startswith("Auszüge aus der internen Dokumentation")
    assert session._subagent_content.prompt.startswith("Du bist ein Sub-Agent")
    session.close()


def test_the_default_prompt_in_the_new_language_is_no_pending_change():
    _, session = _session()
    session.set_brick("system_prompt", True)
    _run(session, "Bonjour")
    session.clear_conversation()
    mark = get_journal().last_seq()
    session.set_language("en")
    bricks = [e.payload for e in get_journal().events_since(mark) if e.kind == "bricks_changed"]
    card = next(b for b in bricks[-1]["bricks"] if b["id"] == "system_prompt")
    assert card["wanted"] and not card["pending"]
    assert bricks[-1]["system_prompt"]["is_default"]
    states = [e.payload for e in get_journal().events_since(mark) if e.kind == "session_state"]
    assert states and states[-1]["language"] == "en"  # after `language_changed`
    session.close()


def test_a_skill_loaded_by_a_stopped_turn_locks_the_language():
    """No exchange in the history, but a skill in the context: locked."""
    engine = FakeEngine(outputs=[call("load_skill", skill="pirate"), "Arrr " * 200], delay=0.01)
    engine.template, engine.architecture = QWEN.decode("utf-8"), "qwen35"
    session = booted_session(engine, window=16384)
    session.set_brick("skills", True)
    client = _client(session)
    mark = get_journal().last_seq()
    session.send("Parle comme un pirate.")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not [
        e for e in get_journal().events_since(mark) if e.kind == "tool_ended"
    ]:
        time.sleep(0.02)
    session.stop()
    session.join()
    assert session.state == "idle" and session._history == []
    assert session._loaded_skills == {"pirate"}
    assert client.get("/api/state").json()["language_locked"] is True
    assert _post(client, "en").status_code == 409
    assert "language" not in config.read_settings()
    session.close()


def test_a_setting_that_cannot_be_written_refuses_the_change(monkeypatch):
    def unwritable(key, value):
        raise PermissionError(13, "Accès refusé")

    monkeypatch.setattr(config, "save_setting", unwritable)
    _, session = _session()
    response = _post(_client(session), "en")
    assert response.status_code == 409
    assert "n'a pas pu être enregistrée" in response.json()["detail"]
    assert session._language == "fr"
    assert session._tools_content.tools["get_datetime"].label_text == "Heure et date"
    session.close()


def test_the_real_local_server_answers_in_english_after_the_change(loop):  # noqa: F811
    """With `mcp` on, `en`: the local server is started again, its tools described in
    English, and `define_term` answers from the English glossary (a real child process)."""
    session = mcp_session(loop, [call("local__define_term", term="harness"), "Done."], window=16384)
    assert enable(session)["status"] == "ok"
    mark = get_journal().last_seq()

    session.set_language("en")

    ended = [p for p in wait_for(session, "mcp_connect_ended", mark) if p["server"] == "local"]
    assert ended and ended[-1]["status"] == "ok"
    events = _run(session, "What is a harness?")
    catalog = "".join(s["text"] for s in _segments(events["context_rendered"][0], "tool_catalog"))
    assert "Gives the definition of a notion of the WaveStack demonstrator" in catalog
    assert "Donne la définition" not in catalog
    (result,) = events["tool_ended"]
    assert result["status"] == "ok"
    assert result["result"].startswith("harness : All the code around the model")
    session.close()
