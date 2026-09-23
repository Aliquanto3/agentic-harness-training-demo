from __future__ import annotations

import os
from pathlib import Path

import pytest

from wavestack.models import probe


def test_probe_missing_file_reports_reason():
    result = probe.probe_file("/does/not/exist.gguf")
    assert result.ok is False
    assert result.reason


def test_record_success_and_already_probed_roundtrip(monkeypatch, tmp_path):
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

    assert probe.already_probed(str(model_file)) is False
    probe.record_success(result)
    assert probe.already_probed(str(model_file)) is True


def test_already_probed_false_when_file_changed(monkeypatch, tmp_path):
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
    assert probe.already_probed(str(model_file)) is False


@pytest.mark.model
def test_probe_real_gguf_loads_successfully():
    gguf_path = os.environ.get("WAVESTACK_TEST_GGUF")
    if not gguf_path or not Path(gguf_path).is_file():
        pytest.skip("WAVESTACK_TEST_GGUF not set to a real GGUF file")

    result = probe.probe_file(gguf_path)
    assert result.ok is True
    assert result.rss_bytes and result.rss_bytes > 0
