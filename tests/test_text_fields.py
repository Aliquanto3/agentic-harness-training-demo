"""Languages (2/5): the data fields `*_fr` became `*_text`; what was written before is still
read (a `settings.json` of an earlier version, the shipped RAG index)."""

from __future__ import annotations

import json

from wavestack import config
from wavestack.rag import index as rag_index


def _write_settings(settings: dict) -> None:
    path = config.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")


def _cloud(model_id: str) -> config.CloudModel:
    model = config.load_config().cloud_model(model_id)
    assert model is not None
    return model


def test_a_former_settings_entry_is_read_with_its_fr_keys():
    _write_settings(
        {
            "cloud": {
                "models": [
                    {
                        "id": "old_entry",
                        "provider": "Ancien",
                        "base_url": "https://api.example.com/v1",
                        "model": "m",
                        "context": 8192,
                        "hosting_fr": "Ailleurs",
                        "notes_fr": "Des notes",
                        "training": "no",
                        "impacts": {"provider": "p", "model": "m", "note_fr": "Une note"},
                    }
                ]
            }
        }
    )
    cfg = config.load_config()
    assert cfg.cloud_models[1] == []
    model = cfg.cloud_model("old_entry")
    assert model is not None
    assert (model.hosting_text, model.notes_text) == ("Ailleurs", "Des notes")
    assert model.impacts is not None and model.impacts.note_text == "Une note"
    assert "hosting_text" in model.model_dump() and "hosting_fr" not in model.model_dump()


def test_a_former_fr_key_overrides_the_shipped_text_key():
    shipped = _cloud("groq").hosting_text
    _write_settings({"cloud": {"models": [{"id": "groq", "hosting_fr": "Mon hébergement"}]}})
    assert shipped != "Mon hébergement"
    assert _cloud("groq").hosting_text == "Mon hébergement"


def test_the_text_key_wins_over_the_former_one_in_the_same_entry():
    _write_settings(
        {"cloud": {"models": [{"id": "groq", "hosting_fr": "Ancien", "hosting_text": "Nouveau"}]}}
    )
    assert _cloud("groq").hosting_text == "Nouveau"


def test_a_former_fastembed_label_is_read():
    _write_settings({"rag_lab": {"fastembed": {"model_name": "a/b", "dims": 8, "label_fr": "F"}}})
    model, error = config.load_config().rag_lab_fastembed
    assert error is None and model is not None and model.label_text == "F"


def test_the_shipped_index_keeps_its_column_and_reads_as_title_text():
    path = config.repo_root() / "data" / "rag_index.sqlite"
    conn = rag_index.connect(path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(chunks)")]
    finally:
        conn.close()
    assert "title_fr" in columns  # the French index does not change by a byte
    chunks = rag_index.read_chunks(path)
    assert chunks and all(chunk.title_text for chunk in chunks)
    longest = rag_index.longest_chunks(path, 2)
    assert len(longest) == 2 and longest[0].title_text
