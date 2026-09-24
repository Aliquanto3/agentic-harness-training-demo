from __future__ import annotations

import os
from pathlib import Path

import pytest

from wavestack.models import probe


def test_probe_missing_file_reports_reason():
    result = probe.probe_file("/does/not/exist.gguf")
    assert result.ok is False
    assert result.reason


def test_record_success_and_probed_entry_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake bytes")
    stat = model_file.stat()

    result = probe.ProbeResult(
        ok=True,
        path=str(model_file),
        architecture="qwen3",
        has_chat_template=True,
        rss_bytes=123,
        size_bytes=stat.st_size,
        mtime=stat.st_mtime,
    )

    assert probe.probed_entry(str(model_file)) is None
    probe.record_success(result)
    assert probe.probed_entry(str(model_file)) is not None


def test_probed_entry_none_when_file_changed(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake bytes")
    stat = model_file.stat()

    probe.record_success(
        probe.ProbeResult(
            ok=True, path=str(model_file), size_bytes=stat.st_size, mtime=stat.st_mtime
        )
    )

    model_file.write_bytes(b"changed content, different size")
    assert probe.probed_entry(str(model_file)) is None


def test_failed_entry_valid_until_file_or_llama_cpp_changes(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.3.0")
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake bytes")
    path = str(model_file)

    assert probe.failed_entry(path) is None
    probe.record_failure(path, "Fichier corrompu.")
    assert probe.failed_entry(path)["reason"] == "Fichier corrompu."

    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.4.0")
    assert probe.failed_entry(path) is None  # upgrade: probe again
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.3.0")
    model_file.write_bytes(b"changed content, different size")
    assert probe.failed_entry(path) is None


def test_failure_not_recorded_without_llama_cpp_or_file(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake bytes")
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: None)
    probe.record_failure(str(model_file), "llama-cpp-python non installé.")
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.3.0")
    probe.record_failure(str(tmp_path / "gone.gguf"), "Fichier introuvable.")
    assert "failed_probes" not in probe.config.read_settings()


def test_success_clears_the_remembered_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.3.0")
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake bytes")
    stat = model_file.stat()
    probe.record_failure(str(model_file), "Fichier corrompu.")

    probe.record_success(
        probe.ProbeResult(
            ok=True, path=str(model_file), size_bytes=stat.st_size, mtime=stat.st_mtime
        )
    )
    assert probe.failed_entry(str(model_file)) is None


@pytest.mark.model
def test_probe_real_gguf_loads_successfully():
    gguf_path = os.environ.get("WAVESTACK_TEST_GGUF")
    if not gguf_path or not Path(gguf_path).is_file():
        pytest.skip("WAVESTACK_TEST_GGUF not set to a real GGUF file")

    result = probe.probe_file(gguf_path)
    assert result.ok is True
    assert result.rss_bytes and result.rss_bytes > 0
