from __future__ import annotations

import json

from wavestack import config


def test_data_dir_honors_env_override(monkeypatch, tmp_path):
    override = tmp_path / "custom-data"
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(override))
    assert config.data_dir() == override


def test_models_dir_and_settings_path_are_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path))
    assert config.models_dir() == tmp_path / "models"
    assert config.settings_path() == tmp_path / "settings.json"


def test_settings_json_overrides_wavestack_toml(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path))
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "settings.json").write_text(
        json.dumps({"server": {"port": 9999}}), encoding="utf-8"
    )
    cfg = config.load_config()
    assert cfg.port == 9999
    # Untouched defaults from wavestack.toml still come through.
    assert "huggingface.co" in cfg.allowed_hosts


def test_hf_token_file_first_then_env_then_none(monkeypatch, tmp_path):
    """Story 13: the file `write_hf_token` writes, else `HF_TOKEN`, else `None` — never the
    repository, always under `data_dir()` (erasable by deleting the file)."""
    from pydantic import SecretStr

    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert config.hf_token() is None

    monkeypatch.setenv("HF_TOKEN", "hf_env_token")
    assert config.hf_token().get_secret_value() == "hf_env_token"

    config.write_hf_token(SecretStr("hf_file_token"))
    assert config.hf_token().get_secret_value() == "hf_file_token"  # the file wins over HF_TOKEN
    assert config.hf_token_path() == tmp_path / "hf_token.json"

    config.hf_token_path().unlink()
    assert config.hf_token().get_secret_value() == "hf_env_token"  # erased: back to the env var


def test_default_config_has_expected_defaults():
    cfg = config.load_config()
    assert cfg.context_window == 4096
    assert cfg.connectivity_probe_host


def test_save_setting_keeps_the_other_keys(monkeypatch, tmp_path):
    from wavestack.models import probe

    monkeypatch.setenv("WAVESTACK_DATA_DIR", str(tmp_path))
    result = probe.ProbeResult(ok=True, path="m.gguf", architecture="qwen35")

    config.save_setting("selected_model", "a.gguf")
    probe.record_success(result)
    assert config.read_settings()["selected_model"] == "a.gguf"
    assert "m.gguf" in config.read_settings()["probed_models"]

    config.save_setting("selected_model", "b.gguf")
    assert config.read_settings()["selected_model"] == "b.gguf"
    assert "m.gguf" in config.read_settings()["probed_models"]
