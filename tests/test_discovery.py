from __future__ import annotations

import json
from pathlib import Path

import pytest

from wavestack import config
from wavestack.models import discovery


def test_explicit_missing_path_is_incompatible(tmp_path):
    missing = tmp_path / "nope.gguf"
    candidates = discovery.discover(explicit_path=missing)
    explicit = [c for c in candidates if c.source == "explicit"]
    assert explicit and explicit[0].status == "incompatible"


def test_explicit_existing_path_is_found(tmp_path):
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"not a real gguf")
    candidates = discovery.discover(explicit_path=model_file)
    explicit = [c for c in candidates if c.source == "explicit"]
    assert explicit and explicit[0].status == "found"
    assert explicit[0].path == str(model_file)


def test_models_dir_candidate_is_found(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path))
    models_dir = config.models_dir()
    models_dir.mkdir(parents=True)
    (models_dir / "local.gguf").write_bytes(b"fake")

    candidates = discovery.discover()

    matches = [c for c in candidates if c.source == "models_dir"]
    assert len(matches) == 1
    assert matches[0].status == "found"


def test_file_candidates_carry_their_size(monkeypatch, tmp_path):
    """Story 25: the model table sorts by the file's bytes when no size label says it."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path))
    config.models_dir().mkdir(parents=True)
    (config.models_dir() / "local.gguf").write_bytes(b"12345")

    [candidate] = [c for c in discovery.discover() if c.source == "models_dir"]

    assert candidate.size_bytes == 5
    dumped = candidate.model_dump()
    assert dumped["size_bytes"] == 5 and "server_template" not in dumped


def test_no_candidates_when_nothing_present(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hf-empty"))
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "ollama-empty"))
    monkeypatch.setattr(discovery, "_lm_studio_dirs", lambda: [tmp_path / "lmstudio-empty"])
    monkeypatch.setattr(discovery, "_server_candidates", lambda cfg: [])

    assert discovery.discover() == []


def test_ollama_manifest_layers_classified(monkeypatch, tmp_path):
    ollama_root = tmp_path / "ollama"
    manifests_dir = ollama_root / "manifests" / "registry.ollama.ai" / "library" / "demo"
    manifests_dir.mkdir(parents=True)
    blobs_dir = ollama_root / "blobs"
    blobs_dir.mkdir(parents=True)

    model_digest = "sha256:aaaa"
    (blobs_dir / "sha256-aaaa").write_bytes(b"fake gguf bytes")

    manifest = {
        "layers": [
            {"mediaType": "application/vnd.ollama.image.model", "digest": model_digest},
            {"mediaType": "application/vnd.ollama.image.tensor", "digest": "sha256:bbbb"},
        ]
    }
    (manifests_dir / "latest").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setenv("OLLAMA_MODELS", str(ollama_root))
    candidates = discovery._ollama_candidates()

    found = [c for c in candidates if c.status == "found"]
    incompatible = [c for c in candidates if c.status == "incompatible"]
    assert len(found) == 1
    assert found[0].path == str(blobs_dir / "sha256-aaaa")
    assert len(incompatible) == 1
    assert incompatible[0].reason


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("registry.ollama.ai/library/qwen3.5/9b", "qwen3.5:9b"),
        ("registry.ollama.ai/user/model/tag", "user/model:tag"),
        ("hf.co/org/repo/tag", "hf.co/org/repo:tag"),
    ],
)
def test_ollama_name_matches_ollama_list(relative, expected):
    manifests = Path("manifests")
    assert discovery._ollama_name(manifests / relative, manifests) == expected
