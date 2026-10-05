"""Lot 3 of 2026-10-04: the cards of « Diagnostic et modèles » (`catalog.group_sources`), one
test per row of the spec's I/O matrix, the quantization read in a header, and the
publishers' logos shipped with the page.

Synthetic GGUF headers (`gguf_writer`) and candidates built by hand: no model loaded, no
network.
"""

from __future__ import annotations

import os
import re
import struct
from pathlib import Path

import pytest
import yaml
from fake_engine import CHATML
from gguf_writer import write_gguf

from wavestack import config
from wavestack.models import catalog
from wavestack.models.discovery import ModelCandidate

GIB = 1024**3
STATIC = config.repo_root() / "src" / "wavestack" / "web" / "static"
LOGOS = STATIC / "logos"


@pytest.fixture(autouse=True)
def _fresh_publishers():
    catalog.load_publishers.cache_clear()
    yield
    catalog.load_publishers.cache_clear()


def _gguf(path: Path, padding: int = 0, **meta) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = {k.replace("__", "."): v for k, v in meta.items()}
    fields.setdefault("tokenizer.chat_template", CHATML)
    if padding:
        fields["wavestack.padding"] = "x" * padding  # other bytes, the same model
    return write_gguf(path, fields)


QWEN3 = {
    "general__architecture": "qwen3",
    "general__basename": "Qwen3",
    "general__finetune": "Instruct",
    "general__version": "2507",
    "general__size_label": "4B",
    "general__name": "Qwen3 4B Instruct 2507",
    "general__file_type": 15,  # Q4_K_M
}


def _file(path: Path, source: str = "hf_cache") -> ModelCandidate:
    return ModelCandidate(
        source=source,
        status="found",
        path=str(path),
        name=path.name,
        size_bytes=path.stat().st_size,
    )


def _ollama_served(blob: Path | None, quantization: str | None = "Q4_K_M") -> ModelCandidate:
    return ModelCandidate(
        source="server",
        status="server",
        server_url="http://127.0.0.1:11434",
        name="qwen3:4b",
        engine="ollama",
        ref="ollama/qwen3:4b",
        provider="Ollama",
        gguf_path=None if blob is None else str(blob),
        publisher_hint="qwen3",
        params_label="4B",
        size_bytes=None if blob is None else blob.stat().st_size,
        quantization=quantization,
    )


def _groups(candidates: list[ModelCandidate], cfg: config.Config | None = None) -> list[dict]:
    cfg = cfg or config.Config(values={"cloud": {"models": []}})
    return catalog.models_payload(candidates, cfg)["groups"]


def _cards(candidates: list[ModelCandidate]) -> list[dict]:
    return [card for group in _groups(candidates) for card in group["cards"]]


# ---------- the quantization ----------


@pytest.mark.parametrize(
    ("value", "text"),
    [(15, "Q4_K_M"), (7, "Q8_0"), (1, "F16"), (32, "BF16"), (38, "MXFP4"), (15 | 1024, "Q4_K_M")],
)
def test_file_type_names_the_quantization(value, text):
    assert catalog.file_type_text(value) == text


@pytest.mark.parametrize("value", [None, 4, 99, "15", True, 2.0])
def test_unknown_file_type_says_nothing(value):
    assert catalog.file_type_text(value) is None


def test_a_file_and_an_ollama_model_say_their_quantization(tmp_path):
    path = _gguf(tmp_path / "hf" / "Qwen3-4B-Q4_K_M.gguf", **QWEN3)
    blob = _gguf(tmp_path / "blobs" / "sha256-1", **{**QWEN3, "general__file_type": 7})
    entries = catalog.local_entries([_file(path), _ollama_served(blob)], config.load_config())
    # Ollama says its quantization (`details.quantization_level`), before the header's.
    assert [e.quantization_text for e in entries] == ["Q4_K_M", "Q4_K_M"]
    assert [e.gguf_path for e in entries] == [str(path), str(blob)]
    assert entries[0].origin_text == "Fichier GGUF · Hugging Face"
    assert entries[1].origin_text == "Ollama · serveur local déjà lancé"


# ---------- the matrix ----------


def test_rule_1_an_ollama_blob_and_the_model_ollama_serves_from_it(tmp_path):
    blob = _gguf(tmp_path / "blobs" / "sha256-1", general__architecture="qwen3")
    blob_file = ModelCandidate(
        source="ollama", status="found", path=str(blob), name="qwen3:4b", size_bytes=10
    )
    [card] = _cards([blob_file, _ollama_served(blob, quantization=None)])
    assert card["source_values"] == [f"file:{blob}", "server:ollama/qwen3:4b"]
    assert card["origin_text"] == "2 sources · dossier d'Ollama, Ollama"
    assert card["id"] == f"card:file:{blob}"  # its first source's


def test_rule_1_two_paths_to_one_file(tmp_path):
    path = _gguf(tmp_path / "models" / "a.gguf", general__architecture="qwen3")
    other = f"{path.parent}{os.sep}.{os.sep}{path.name}"  # another spelling, the same file
    candidates = [_file(path, "models_dir"), _file(Path(other), "explicit")]
    candidates[1].path = other
    [card] = _cards(candidates)
    assert len(card["source_values"]) == 2
    assert card["name"] == "a"  # no `general.name`: the file's name without « .gguf »


def test_rule_2_an_identical_copy(tmp_path):
    meta = {k: v for k, v in QWEN3.items() if k != "general__version"}  # rule 3 out of play
    first = _gguf(tmp_path / "hf" / "Qwen3-4B.gguf", **meta)
    copy = _gguf(tmp_path / "lmstudio" / "Qwen3-4B.gguf", **meta)
    [card] = _cards([_file(first), _file(copy, "lm_studio")])
    assert card["origin_text"] == "2 sources · Hugging Face, LM Studio"
    assert card["size_text"] == catalog.size_fr(None, first.stat().st_size)  # one size


def test_rule_2_needs_the_same_variant(tmp_path):
    """Same bytes, architecture, base name and size, another `general.finetune`: two cards."""
    meta = {k: v for k, v in QWEN3.items() if k != "general__version"}
    first = _gguf(tmp_path / "hf" / "Qwen3-4B.gguf", **meta)  # « Instruct »
    other = _gguf(
        tmp_path / "lmstudio" / "Qwen3-4B.gguf", **{**meta, "general__finetune": "Thinking"}
    )
    assert first.stat().st_size == other.stat().st_size
    assert len(_cards([_file(first), _file(other, "lm_studio")])) == 2


def test_rule_2_needs_the_same_bytes(tmp_path):
    meta = {k: v for k, v in QWEN3.items() if k != "general__version"}
    first = _gguf(tmp_path / "hf" / "Qwen3-4B.gguf", **meta)
    other = _gguf(tmp_path / "lmstudio" / "Qwen3-4B.gguf", padding=8, **meta)
    assert len(_cards([_file(first), _file(other, "lm_studio")])) == 2


def test_rule_3_a_file_and_an_ollama_model_of_the_same_quantization(tmp_path):
    path = _gguf(tmp_path / "hf" / "Qwen3-4B-Instruct-2507-Q4_K_M.gguf", **QWEN3)
    # Ollama's blob: other bytes, no `file_type`; its quantization is Ollama's.
    blob_meta = {k: v for k, v in QWEN3.items() if k != "general__file_type"}
    blob = _gguf(tmp_path / "blobs" / "sha256-2", padding=64, **blob_meta)
    [card] = _cards([_file(path), _ollama_served(blob, quantization="q4_k_m")])
    assert card["source_values"] == [f"file:{path}", "server:ollama/qwen3:4b"]
    assert card["name"] == "Qwen3 4B Instruct 2507"  # `general.name`
    assert card["quantization_text"] == "Q4_K_M"
    assert card["params_text"] == "4 B"


def test_different_quantizations_are_two_cards_each_saying_its_own(tmp_path):
    q4 = _gguf(tmp_path / "hf" / "Qwen3-4B-Q4_K_M.gguf", **QWEN3)
    q8 = _gguf(tmp_path / "hf" / "Qwen3-4B-Q8_0.gguf", **{**QWEN3, "general__file_type": 7})
    cards = _cards([_file(q4), _file(q8)])
    assert [c["name"] for c in cards] == [
        "Qwen3 4B Instruct 2507 · Q4_K_M",
        "Qwen3 4B Instruct 2507 · Q8_0",
    ]


def test_a_field_missing_on_one_side_keeps_two_cards(tmp_path):
    path = _gguf(tmp_path / "hf" / "a.gguf", **QWEN3)
    meta = {k: v for k, v in QWEN3.items() if k not in ("general__version", "general__file_type")}
    blob = _gguf(tmp_path / "blobs" / "sha256-3", padding=64, **meta)
    assert len(_cards([_file(path), _ollama_served(blob)])) == 2


def test_never_a_local_and_a_cloud_model(tmp_path):
    from test_reasoning import _preset

    path = _gguf(tmp_path / "hf" / "mistral-small-latest.gguf", general__architecture="llama")
    cloud = _preset("mistral").model_dump(exclude_none=True)
    cfg = config.Config(values={"cloud": {"models": [cloud]}})
    groups = _groups([_file(path)], cfg)
    cards = [(g["hosting"], c["source_values"]) for g in groups for c in g["cards"]]
    assert cards == [("local", [f"file:{path}"]), ("network", [f"cloud:{cloud['id']}"])]


def test_a_cards_sources_join_the_group_of_its_first_source(tmp_path):
    """The page and the picker group alike: the second source, Gemma by its own header,
    goes to the first one's publisher, Qwen, in `models` as in `cards`."""
    path = _gguf(tmp_path / "hf" / "a.gguf", **QWEN3)
    blob_meta = {**QWEN3, "general__architecture": "gemma3"}
    del blob_meta["general__file_type"]
    blob = _gguf(tmp_path / "blobs" / "sha256-4", padding=64, **blob_meta)
    served = _ollama_served(blob)
    served.publisher_hint = "gemma3"
    [group] = _groups([_file(path), served])
    assert group["publisher_id"] == "qwen" and group["logo"] == "qwen.png"
    assert [m["value"] for m in group["models"]] == [f"file:{path}", "server:ollama/qwen3:4b"]
    assert {m["publisher_id"] for m in group["models"]} == {"qwen"}
    assert {m["card_id"] for m in group["models"]} == {f"card:file:{path}"}


def test_the_payload_of_a_card(tmp_path):
    path = _gguf(tmp_path / "hf" / "Qwen3-4B.gguf", **QWEN3)
    blob = _gguf(tmp_path / "blobs" / "sha256-5", padding=200_000, **QWEN3)
    [group] = _groups([_file(path), _ollama_served(blob)])
    [card] = group["cards"]
    assert set(card) >= {"id", "name", "size_bytes_min", "size_text", "source_values"}
    assert card["size_bytes_min"] == path.stat().st_size
    # Two sizes written alike (« 1 Mo »): one size, without « ≈ » (a file is among them).
    assert card["size_text"] == catalog.size_fr(None, path.stat().st_size) == "1 Mo"
    served = next(m for m in group["models"] if m["kind"] == "server")
    assert served["bytes_text"].startswith("≈ ")  # a served model's size, its server's
    assert group["publisher_text"] == "Qwen (Alibaba)"


def test_the_card_sizes():
    def entry(kind: str, size: int) -> catalog.ModelEntry:
        return catalog.ModelEntry.model_construct(kind=kind, size_bytes=size)

    assert catalog._card_size([entry("file", int(2.5 * GIB))], "fr")[1] == "2,5 Go"
    assert catalog._card_size([entry("server", int(2.7 * GIB))], "fr")[1] == "≈ 2,7 Go"
    both = [entry("file", int(2.4 * GIB)), entry("server", int(2.5 * GIB))]
    assert catalog._card_size(both, "fr") == (int(2.4 * GIB), "2,4 à 2,5 Go")
    assert catalog._card_size(both, "en")[1] == "2.4 to 2.5 GB"
    assert catalog._card_size([], "fr") == (None, None)


# ---------- the logos (static/logos, publishers.yaml) ----------


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path.name
    return struct.unpack(">II", data[16:24])


@pytest.mark.parametrize("lang", ["fr", "en", "de"])
def test_every_logo_of_the_publishers_is_shipped(lang):
    path = config.content_dir() / (
        "models/publishers.yaml" if lang == "fr" else f"i18n/{lang}/models/publishers.yaml"
    )
    publishers = yaml.safe_load(path.read_text(encoding="utf-8"))["publishers"]
    logos = {p["id"]: p.get("logo") for p in publishers}
    assert {i for i, logo in logos.items() if not logo} == {"lfm", "minicpm"}  # the initial
    assert logos["granite"] == "ibm.png" and logos["llama"] == "meta.png"  # Anaël, 2026-10-04
    for logo in filter(None, logos.values()):
        assert (LOGOS / logo).is_file(), logo


def test_every_shipped_logo_is_referenced_small_and_traced():
    shipped = sorted(p.name for p in LOGOS.glob("*.png"))
    publishers = yaml.safe_load(catalog.publishers_path().read_text(encoding="utf-8"))
    assert shipped == sorted({p["logo"] for p in publishers["publishers"] if p.get("logo")})
    sources = (LOGOS / "SOURCES.md").read_text(encoding="utf-8")
    assert "formation interne, à vérifier avant usage client" in sources
    for name in shipped:
        assert max(_png_size(LOGOS / name)) == 128, name
        assert f"`{name}`" in sources, name
    # Served from the page's own folder, never from the network.
    page = (STATIC / "diagnostic.html").read_text(encoding="utf-8")
    assert "`/static/logos/${group.logo}`" in page
    assert not re.search(r"https?://(?!127\.0\.0\.1)", page.split("<script", 1)[1])


def test_a_logo_outside_the_folder_makes_the_file_invalid(tmp_path, monkeypatch):
    text = catalog.publishers_path().read_text(encoding="utf-8")
    broken = tmp_path / "publishers.yaml"
    broken.write_text(text.replace("logo: qwen.png", "logo: ../app.js"), encoding="utf-8")
    monkeypatch.setattr(catalog, "publishers_path", lambda lang="fr": broken)
    content, error = catalog.load_publishers()
    assert content.publishers == [] and "logo" in error


def test_logos_reach_the_entries_and_the_groups(tmp_path):
    path = _gguf(tmp_path / "hf" / "a.gguf", **QWEN3)
    other = _gguf(tmp_path / "hf" / "b.gguf", general__architecture="lfm2", general__name="LFM2")
    groups = {g["publisher_id"]: g for g in _groups([_file(path), _file(other)])}
    assert groups["qwen"]["logo"] == "qwen.png"
    assert groups["qwen"]["models"][0]["logo"] == "qwen.png"
    assert groups["lfm"]["logo"] is None  # the page shows its initial
