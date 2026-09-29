from __future__ import annotations

import os
from pathlib import Path

import pytest
from gguf_writer import write_gguf

from wavestack.models import gguf_meta, probe


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


# ---------- lot E: the probe after an evaluation (E2), its French reason (E6) ----------

TINY = str(Path(__file__).parent / "fixtures" / "tiny-llama.gguf")


def test_probe_of_tiny_llama_evaluates_a_full_batch_at_the_window(monkeypatch, tmp_path):
    """E2: loaded at the window, one full batch (llama-cpp-python's 512) evaluated, the RSS
    read after it: `probe_version = 2`, `rss_eval_tokens`, and a complete entry."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))

    result = probe.probe_file(TINY, window=4096)

    assert result.ok and result.probe_version == probe.PROBE_VERSION == 2
    assert result.rss_eval_tokens == 512 and result.rss_bytes and result.rss_bytes > 0
    assert result.probe_window == 4096  # the context the probe created
    assert result.kv_bytes_per_token == 2 * 4 * (8 + 8)  # 1 layer, 4 KV heads of 32 / 4
    small = probe.probe_file(TINY, window=64)
    assert (small.rss_eval_tokens, small.probe_window) == (63, 64)  # never past the window
    probe.record_success(result)
    entry = probe.probed_entry(TINY)
    assert (entry["probe_version"], entry["probe_window"], entry["rss_eval_tokens"]) == (
        2,
        4096,
        512,
    )
    assert probe.measured(TINY)


def test_old_or_incomplete_entries_are_not_measured(monkeypatch, tmp_path):
    """E2: only a complete entry of the current probe counts; a `null` KV the probe wrote
    (a GGUF that does not say it) is complete, a missing key is not."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    model_file = tmp_path / "model.gguf"
    model_file.write_bytes(b"fake bytes")
    path, stat = str(model_file), model_file.stat()
    complete = {"rss_bytes": 10, "probe_version": 2, "probe_window": 4096, "rss_eval_tokens": 512}

    def record(**fields) -> bool:  # noqa: ANN003
        probe.record_success(
            probe.ProbeResult(
                ok=True, path=path, size_bytes=stat.st_size, mtime=stat.st_mtime, **fields
            )
        )
        return probe.measured(path)

    assert record(rss_bytes=10, kv_bytes_per_token=128) is False  # story 17: no version
    assert record(**{**complete, "probe_version": 1}) is False
    assert record(**{**complete, "rss_bytes": None}) is False
    assert record(**{**complete, "rss_eval_tokens": None}) is False
    assert record(**{**complete, "probe_window": None}) is False
    assert record(**complete) is True  # KV `null`: written by the probe, complete
    probed = probe.config.read_settings()["probed_models"]
    del probed[path]["kv_bytes_per_token"]
    probe.config.save_setting("probed_models", probed)
    assert probe.measured(path) is False  # an entry without the key: probed again


def test_incompatible_file_reason_is_french_with_the_raw_detail(tmp_path):
    """E6: llama.cpp's message is the detail, never the reason."""
    bad = tmp_path / "abime.gguf"
    bad.write_bytes(b"GGUF" + b"\0" * 32)

    result = probe.probe_file(str(bad))

    assert result.ok is False
    assert result.reason == probe.incompatible_fr()
    assert "ne sait pas charger ce fichier" in result.reason
    assert "Choisissez un autre modèle, ou servez-le avec Ollama ou llama-server." in result.reason
    assert "Failed to load model" in (result.detail or "")
    assert "Failed" not in result.reason and result.transient is False


@pytest.mark.parametrize(
    ("step", "error"),
    [
        ("context", ValueError("Failed to create llama_context")),
        ("context", MemoryError()),
        ("tokenize", RuntimeError("tokenize en panne")),
        ("eval", RuntimeError("llama_decode returned -3")),
    ],
)
def test_memory_or_eval_failures_are_transient(monkeypatch, tmp_path, step, error):
    """Lot E: only llama.cpp refusing the file itself is an incompatibility; the context's
    memory, the tokenizer or the evaluation failing says nothing about the file."""
    import sys
    import types

    model_file = tmp_path / "m.gguf"
    model_file.write_bytes(b"GGUF")

    class _Llama:
        metadata: dict = {}
        n_batch = 512

        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            if step == "context":
                raise error

        def tokenize(self, text: bytes, add_bos: bool, special: bool) -> list[int]:
            if step == "tokenize":
                raise error
            return [1, 2, 3]

        def eval(self, tokens: list[int]) -> None:
            raise error

        def close(self) -> None:
            pass

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=_Llama))

    result = probe.probe_file(str(model_file))

    assert result.ok is False and result.transient is True
    assert result.reason == probe.transient_fr() and "mémoire ou de temps" in result.reason
    assert result.detail


def test_failures_written_before_lot_e_are_probed_again(monkeypatch, tmp_path):
    """Lot E: a `failed_probes` entry without `probe_version = 2` (its reason may be
    llama.cpp's English message) is ignored."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(probe, "_llama_cpp_version", lambda: "0.3.35")
    model_file = tmp_path / "blob"
    model_file.write_bytes(b"fake bytes")
    path = str(model_file)
    probe.record_failure(path, probe.incompatible_fr())
    assert probe.failed_entry(path)["probe_version"] == 2

    failed = probe.config.read_settings()["failed_probes"]
    failed[path] = {k: v for k, v in failed[path].items() if k != "probe_version"}
    failed[path]["reason"] = "Chargement impossible : Failed to load model from file: blob"
    probe.config.save_setting("failed_probes", failed)
    assert probe.failed_entry(path) is None


@pytest.mark.parametrize(("platform", "factor"), [("linux", 1024), ("darwin", 1)])
def test_os_peak_rss_units(monkeypatch, platform, factor):
    """`ru_maxrss`: kB on Linux, bytes on macOS."""
    import sys
    import types

    usage = types.SimpleNamespace(ru_maxrss=2048)
    fake = types.SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda who: usage)
    monkeypatch.setitem(sys.modules, "resource", fake)
    monkeypatch.setattr(probe.sys, "platform", platform)

    assert probe._os_peak_rss() == 2048 * factor


def test_probe_arguments_window_then_path():
    assert probe._args(["m.gguf"]) == ("m.gguf", probe.DEFAULT_WINDOW)
    assert probe._args(["--window", "2048", "m.gguf"]) == ("m.gguf", 2048)
    assert probe._args(["--window", "x", "m.gguf"]) is None
    assert probe._args(["--window", "0", "m.gguf"]) is None
    assert probe._args([]) is None


def test_gguf_kv_is_read_without_the_weights(monkeypatch, tmp_path):
    """E1: the KV of a GGUF llama-server loaded, from its header read in Python."""
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path / "data"))
    assert probe.gguf_kv_bytes_per_token(TINY) == 128
    assert probe.gguf_kv_bytes_per_token(str(tmp_path / "absent.gguf")) is None
    assert probe.gguf_kv_bytes_per_token(None) is None
    not_gguf = tmp_path / "notes.txt"
    not_gguf.write_text("pas un GGUF", encoding="utf-8")
    assert probe.gguf_kv_bytes_per_token(str(not_gguf)) is None
    hybrid = write_gguf(tmp_path / "hybride.gguf", HYBRID)
    assert probe.gguf_kv_bytes_per_token(str(hybrid)) == 2 * (2 + 2) * (256 + 256)


# A hybrid layout (Qwen3.5): KV heads per layer, 0 on the linear-attention layers.
HYBRID = {
    "general.architecture": "qwen35",
    "qwen35.block_count": 8,
    "qwen35.attention.head_count": 16,
    "qwen35.attention.head_count_kv": [0, 0, 0, 2, 0, 0, 0, 2],
    "qwen35.attention.key_length": 256,
    "qwen35.attention.value_length": 256,
    "tokenizer.ggml.tokens": ["a"] * 5000,  # a long array: skipped
}


def test_gguf_header_reader_on_tiny_llama_and_a_hybrid_layout(tmp_path):
    """The pure-Python header reader: real lists, where llama-cpp-python shows text."""
    tiny = gguf_meta.read_metadata(TINY)
    assert tiny["general.architecture"] == "llama" and tiny["llama.block_count"] == 1
    assert tiny["llama.attention.head_count_kv"] == 4
    assert isinstance(tiny["tokenizer.ggml.tokens"], list)  # 259 tokens, kept
    assert tiny["tokenizer.chat_template"].startswith("{% for message in messages %}")

    meta = gguf_meta.read_metadata(write_gguf(tmp_path / "h.gguf", HYBRID))
    assert meta["qwen35.attention.head_count_kv"] == [0, 0, 0, 2, 0, 0, 0, 2]
    assert meta["tokenizer.ggml.tokens"] is None  # longer than MAX_ARRAY
    assert probe.kv_bytes_per_token(meta) == 2 * 4 * 512

    (tmp_path / "v1.gguf").write_bytes(b"GGUF" + b"\x01\0\0\0" + b"\0" * 16)
    for bad in ("v1.gguf", "absent.gguf"):
        assert gguf_meta.try_read_metadata(tmp_path / bad) is None
    truncated = (tmp_path / "h.gguf").read_bytes()[:60]
    (tmp_path / "cut.gguf").write_bytes(truncated)
    assert gguf_meta.try_read_metadata(tmp_path / "cut.gguf") is None
