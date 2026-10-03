"""Story 25: the model table (`models/catalog.py`), one test per row of the I/O matrix (CAP-34,
CAP-35, AD-1, AD-6, AD-9, AD-19).

Synthetic GGUF headers (`gguf_writer`), candidates built by hand or by discovery with a
simulated server, cloud entries from the configuration: no model loaded, no network.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest
import yaml
from fake_engine import CHATML, FakeEngine, booted_session
from gguf_writer import write_gguf
from test_cloud import Provider
from test_reasoning import TEXT, _card, _cloud, _preset
from test_tools import QWEN
from test_web_app import _build, _client

from wavestack import config
from wavestack.context.window import window_for
from wavestack.models import catalog, gguf_meta
from wavestack.models.capabilities import (
    capabilities_for,
    cloud_capabilities,
    reasoning_mode,
    tools_summary,
)
from wavestack.models.discovery import ModelCandidate
from wavestack.models.engine import EngineMetadata

QWEN_TEMPLATE = QWEN.decode("utf-8")
# ChatML with `<tool_call>` and `enable_thinking`, without `<function=`: the hermes parser.
HERMES_THINKING = (
    "{% if enable_thinking %}<think>{% endif %}<|im_start|>{{ m }}<|im_end|><tool_call>"
)
THINK_ONLY = CHATML + "<think>"  # `<think>` without a reasoning variable
INTROUVABLE = (
    "Fichier GGUF du modèle introuvable dans le dossier d'Ollama (/x) : WaveStack ne peut pas "
    "lire son tokenizer."
)


@pytest.fixture(autouse=True)
def _fresh_publishers():
    catalog.load_publishers.cache_clear()
    yield
    catalog.load_publishers.cache_clear()


def _gguf(path: Path, **meta) -> Path:
    return write_gguf(path, {k.replace("__", "."): v for k, v in meta.items()})


def _qwen_file(tmp_path: Path, name: str = "Qwen3.5-2B-Q4_K_M.gguf", size: str = "2B") -> Path:
    return _gguf(
        tmp_path / name,
        general__architecture="qwen35",
        general__size_label=size,
        general__basename="Qwen3.5",
        qwen35__context_length=262144,
        tokenizer__chat_template=HERMES_THINKING,
    )


def _file(path: Path) -> ModelCandidate:
    return ModelCandidate(
        source="models_dir",
        status="found",
        path=str(path),
        name=path.name,
        size_bytes=path.stat().st_size,
    )


def _ollama_missing() -> ModelCandidate:
    return ModelCandidate(
        source="server",
        status="incompatible",
        server_url="http://127.0.0.1:11434",
        name="faux-ollama:latest",
        engine="ollama",
        ref="ollama/faux-ollama:latest",
        provider="Ollama",
        reason=INTROUVABLE,
        publisher_hint="qwen3",
        params_label="0.6B",
        size_bytes=1_000_000_000,
    )


def _llama_server(gguf_path: str | None = "/modeles/faux-llama-server.gguf") -> ModelCandidate:
    return ModelCandidate(
        source="server",
        status="server",
        server_url="http://127.0.0.1:8080",
        name="faux-llama-server.gguf",
        engine="llama_server",
        ref="llama_server/faux-llama-server.gguf",
        provider="llama-server",
        gguf_path=gguf_path,
        size_bytes=1_500_000_000,
        server_template=QWEN_TEMPLATE,
        native_context=32768,
        server_context=8192,
    )


def _entry(candidate: ModelCandidate) -> catalog.ModelEntry:
    [entry] = catalog.local_entries([candidate], config.load_config())
    return entry


def _cloud_entry(**update) -> catalog.ModelEntry:
    base = _preset("mistral").model_copy(update=update)
    cfg = config.Config(values={"cloud": {"models": [base.model_dump(exclude_none=True)]}})
    [entry] = catalog.cloud_entries(cfg)
    return entry


# ---------- the I/O matrix ----------


def test_qwen_file(tmp_path):
    entry = _entry(_file(_qwen_file(tmp_path)))
    assert entry.value == f"file:{tmp_path / 'Qwen3.5-2B-Q4_K_M.gguf'}"
    assert entry.label_text == "Local · fichier · Qwen3.5-2B-Q4_K_M.gguf · 2B"
    assert (entry.publisher_id, entry.publisher_text) == ("qwen", "Qwen (Alibaba)")
    assert (entry.params_b, entry.params_label) == (2.0, "2B")
    assert (entry.tools, entry.tools_text) == (True, "oui (hermes)")
    assert (entry.reasoning, entry.reasoning_text) == ("toggle", "activable")
    # AD-9: min(configured 4 096, native 262 144).
    assert (entry.window, entry.native_context, entry.window_text) == (
        4096,
        262144,
        "4 096 tokens",
    )
    assert entry.usable and entry.disabled_text is None and entry.hosting == "local"
    [group] = catalog.group_models([entry])
    assert group.label_text == "Sur ce poste · Qwen (Alibaba)"


def test_ollama_without_a_readable_blob():
    entry = _entry(_ollama_missing())
    assert entry.label_text == "Local · Ollama · faux-ollama:latest · 0.6B"
    assert entry.publisher_text == "Qwen (Alibaba)" and entry.params_b == 0.6
    assert not entry.usable and "introuvable" in entry.disabled_text
    assert (entry.tools, entry.tools_text, entry.reasoning_text) == (None, "inconnu", "inconnu")
    assert "introuvable" in entry.reason_text and "introuvable" in entry.tools_reason_text
    assert entry.window is None and entry.window_text == "—"


def test_ollama_blob_read_in_its_header(tmp_path):
    blob = _qwen_file(tmp_path, "sha256-abc", "4B")
    candidate = _ollama_missing().model_copy(
        update={"status": "server", "reason": None, "gguf_path": str(blob)}
    )
    entry = _entry(candidate)
    # The header's size label comes first; the capabilities are its template's.
    assert entry.params_label == "4B" and entry.reasoning == "toggle" and entry.usable


def test_llama_server_capabilities_from_props():
    entry = _entry(_llama_server())
    assert entry.label_text == "Local · llama-server · faux-llama-server.gguf"
    assert entry.value == "server:llama_server/faux-llama-server.gguf"
    assert entry.publisher_text == "Qwen (Alibaba)"  # the family of `capabilities_for`
    assert entry.params_label is None and entry.size_bytes == 1_500_000_000
    assert entry.size_text == "1,4\u00a0Go"
    assert entry.hosting_label_text == "Sur ce poste · llama-server"
    assert entry.window_reason_text == "fenêtre configurée ; contexte natif : 32\u202f768 tokens"
    # min(configured 4 096, native 32 768, a slot's 8 192).
    assert (entry.window, entry.native_context) == (4096, 32768)
    assert (entry.tools, entry.tools_text) == (True, "oui (qwen3_coder)")
    assert entry.reasoning == "toggle"


def test_llama_server_slot_context_bounds_the_window():
    entry = _entry(_llama_server().model_copy(update={"server_context": 2048}))
    assert entry.window == 2048


def test_llama_server_header_gives_publisher_and_size_never_capabilities(tmp_path):
    path = _gguf(
        tmp_path / "gemma-3-1b-it-Q4_K_M.gguf",
        general__architecture="gemma3",
        general__size_label="1B",
        tokenizer__chat_template=CHATML,  # would give « jamais » if it were read
    )
    entry = _entry(_llama_server(str(path)))
    assert (entry.publisher_text, entry.params_label) == ("Gemma (Google)", "1B")
    assert entry.reasoning == "toggle"  # `/props`' template, as the adapter


def test_llama_server_unreadable_header_by_family_then_name():
    no_template = _llama_server().model_copy(update={"server_template": None})
    entry = _entry(no_template)
    assert entry.publisher_text == "Autres éditeurs"  # « llama-server »: not Llama
    # AD-6: no template, the load fails: never choosable.
    assert not entry.usable and "tokenizer.chat_template" in entry.disabled_text
    named = no_template.model_copy(update={"name": "Llama-3.2-3B-Instruct-Q4_K_M.gguf"})
    assert _entry(named).publisher_text == "Llama (Meta)"
    assert _entry(named).params_label == "3B"


def test_cloud_that_always_reasons():
    entry = _cloud_entry(
        model="openai/gpt-oss-120b", reasoning=config.CloudReasoning(format="field", always=True)
    )
    assert (entry.reasoning, entry.reasoning_text) == ("always", "toujours")
    assert (entry.tools, entry.tools_text) == (True, "oui (déclaré)")
    assert entry.label_text == "RÉSEAU · Mistral AI · openai/gpt-oss-120b · 120B"
    assert entry.publisher_text == "gpt-oss (OpenAI)" and entry.hosting == "network"


def test_cloud_without_declarations():
    entry = _cloud_entry(reasoning=None, tools=False)
    assert (entry.reasoning_text, entry.tools_text) == ("jamais", "non")
    assert "non déclaré" in entry.reason_text and "non déclaré" in entry.tools_reason_text
    assert entry.publisher_text == "Mistral (Mistral AI)"
    assert entry.params_label is None and entry.size_text == "—"
    assert entry.hosting_text.startswith("Mistral AI, France")


def test_prices_per_million_tokens_for_the_cloud_and_a_dash_for_local(tmp_path):
    """FinOps: « 0,30 $ / 2,50 $ » (input / output) with its date; « — » without prices."""
    prices = {e.ref: e for e in catalog.cloud_entries(config.load_config())}
    assert prices["gemini"].price_text == "0,30 $ / 2,50 $"
    assert prices["groq"].price_text == prices["mistral"].price_text == "0,15 $ / 0,60 $"
    reason = prices["gemini"].price_reason_text
    assert reason == (
        "par million de tokens (entrée / sortie), relevé le 29/09/2026 ; le coût de chaque "
        "appel en est une estimation"
    )
    assert _entry(_file(_qwen_file(tmp_path))).price_text == "—"
    unpriced = _cloud_entry(pricing=None)
    assert unpriced.price_text == "—" and unpriced.price_reason_text == "prix non déclaré"
    odd = config.CloudPricing(
        input_usd_per_mtok=0.075, output_usd_per_mtok=12, checked="2026-09-29"
    )
    assert _cloud_entry(pricing=odd).price_text == "0,075 $ / 12,00 $"


def test_cloud_window_as_the_session():
    entry = _cloud_entry(tpm=6000)  # min(configured 4 096, context, tpm // 2 = 3 000)
    assert (entry.window, entry.native_context) == (3000, 131072)


def test_cloud_disabled_by_its_row():
    base = _preset("mistral")
    cfg = config.Config(values={"cloud": {"models": [base.model_dump(exclude_none=True)]}})
    rows = [{"id": "mistral", "disabled_text": "Désactivé : saisissez d'abord la clé API."}]
    [entry] = catalog.cloud_entries(cfg, rows)
    assert not entry.usable and entry.disabled_text.startswith("Désactivé")


def test_think_tags_without_a_variable_is_unknown(tmp_path):
    path = _gguf(
        tmp_path / "mystere.gguf",
        general__architecture="mystere",
        tokenizer__chat_template=THINK_ONLY,
    )
    entry = _entry(_file(path))
    assert entry.reasoning == "unknown"
    assert entry.reason_text == (
        "raisonne peut-être de lui-même, WaveStack ne sait ni l'allumer ni l'éteindre"
    )
    assert (entry.tools, entry.tools_text) == (False, "non")
    assert entry.tools_reason_text == "aucun format d'appel connu pour cette famille de modèle"


def test_without_template_is_unknown_with_the_incompatible_reason(tmp_path):
    path = _gguf(tmp_path / "sans-gabarit.gguf", general__architecture="llama")
    entry = _entry(_file(path))
    assert entry.reasoning == "unknown" and entry.tools is None
    assert "tokenizer.chat_template" in entry.reason_text
    assert entry.usable is False and entry.disabled_text == entry.reason_text
    assert entry.window is None


def test_relative_file_path_is_read(tmp_path, monkeypatch):
    """An explicit path, or a relative data dir: the header is read from the working dir."""
    _qwen_file(tmp_path)
    monkeypatch.chdir(tmp_path)
    candidate = ModelCandidate(
        source="explicit", status="found", path="Qwen3.5-2B-Q4_K_M.gguf", name="x.gguf"
    )
    entry = _entry(candidate)
    assert (entry.publisher_text, entry.reasoning, entry.params_label) == (
        "Qwen (Alibaba)",
        "toggle",
        "2B",
    )
    assert entry.size_bytes and entry.value == "file:Qwen3.5-2B-Q4_K_M.gguf"


def test_unreadable_header_is_unknown(tmp_path):
    path = tmp_path / "pas-un-gguf.gguf"
    path.write_bytes(b"not a gguf")
    entry = _entry(_file(path))
    assert entry.reasoning == "unknown" and "illisible" in entry.reason_text
    assert entry.usable and entry.publisher_text == "Autres éditeurs"


def test_plain_template_never_reasons(tmp_path):
    path = _gguf(
        tmp_path / "Llama-3.2-3B-Instruct.gguf",
        general__architecture="llama",
        general__basename="Llama-3.2",
        tokenizer__chat_template=CHATML,
    )
    entry = _entry(_file(path))
    assert (entry.reasoning, entry.publisher_text, entry.params_label) == (
        "never",
        "Llama (Meta)",
        "3B",
    )
    assert entry.tools is False


def test_sort_by_parameters_then_bytes_then_name():
    def entry(name: str, params: str | None, size: int | None) -> catalog.ModelEntry:
        candidate = _ollama_missing().model_copy(
            update={
                "name": name,
                "ref": f"ollama/{name}",
                "params_label": params,
                "size_bytes": size,
            }
        )
        return _entry(candidate)

    entries = [
        entry("quatre", "4B", None),
        entry("zeta", None, None),
        entry("zero-six", "0.6B", 9_000_000_000),
        entry("sans-taille", None, 1_500_000_000),
        entry("Alpha", None, None),
    ]
    [group] = catalog.group_models(entries)
    assert [m.name for m in group.models] == ["zero-six", "quatre", "sans-taille", "Alpha", "zeta"]


def test_groups_local_first_publishers_in_order_others_last(tmp_path):
    gemma = _gguf(tmp_path / "gemma.gguf", general__architecture="gemma3")
    unknown = _gguf(tmp_path / "inconnu.gguf", general__architecture="mystere")
    cfg = config.load_config()
    local = catalog.local_entries([_file(unknown), _file(gemma), _ollama_missing()], cfg)
    cloud = catalog.cloud_entries(cfg)
    labels = [g.label_text for g in catalog.group_models(local + cloud)]
    assert labels == [
        "Sur ce poste · Qwen (Alibaba)",
        "Sur ce poste · Gemma (Google)",
        "Sur ce poste · Autres éditeurs",
        "Réseau · Gemma (Google)",
        "Réseau · Gemini (Google)",
        "Réseau · Mistral (Mistral AI)",
        "Réseau · gpt-oss (OpenAI)",
        "Réseau · Claude (Anthropic)",
    ]


def test_the_gemini_preset_is_its_own_network_group_and_toggles_its_reasoning():
    """The Gemini preset: « RÉSEAU · Google AI Studio · gemini-3.5-flash-lite » under
    « Réseau · Gemini (Google) », reasoning « activable », unavailable without a key."""
    cfg = config.load_config()
    rows = [{"id": "gemini", "disabled_text": "Aucune clé API : saisissez-la au diagnostic."}]
    entries = catalog.cloud_entries(cfg, rows)
    [gemini] = [e for e in entries if e.ref == "gemini"]
    assert gemini.label_text == "RÉSEAU · Google AI Studio · gemini-3.5-flash-lite"
    assert gemini.publisher_text == "Gemini (Google)" and gemini.reasoning == "toggle"
    assert gemini.params_label is None and gemini.tools is True
    assert not gemini.usable and gemini.disabled_text == rows[0]["disabled_text"]
    groups = {g.label_text: g for g in catalog.group_models(entries)}
    assert [m.ref for m in groups["Réseau · Gemini (Google)"].models] == ["gemini"]


def test_files_deduplicated_by_path(tmp_path):
    path = _qwen_file(tmp_path)
    twice = [_file(path), _file(path).model_copy(update={"source": "hf_cache"})]
    failed = _file(path).model_copy(update={"status": "incompatible", "source": "lm_studio"})
    tensor = _file(path).model_copy(
        update={"status": "incompatible", "path": "/autre", "reason": "Format de tenseur."}
    )
    entries = catalog.local_entries([*twice, failed, tensor], config.load_config())
    # Once per path, the usable listing kept; an incompatible file listed, greyed, with why.
    assert [(e.ref, e.usable) for e in entries] == [(str(path), True), ("/autre", False)]
    assert entries[1].disabled_text == "Format de tenseur." == entries[1].reason_text
    assert entries[1].reasoning == "unknown"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2B", 2.0),
        ("0.6B", 0.6),
        ("270M", 0.27),
        ("8x7B", 56.0),
        ("30B-A3B", 30.0),
        ("openai/gpt-oss-120b", 120.0),
        ("llama3.2:3b", 3.0),
        ("Qwen3.5-2B-Q4_K_M.gguf", 2.0),
        ("mistral-small-latest", None),
        ("Q4_K_M", None),
        ("3.5", None),
        ("Qwen3.5", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_params(text, expected):
    result = catalog.parse_params(text)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_size_text():
    assert catalog.size_fr("2B", int(1.3 * 1024**3)) == "2\u00a0B · 1,3\u00a0Go"
    assert catalog.size_fr(None, None) == "—"
    assert catalog.size_fr("0.6B", None) == "0,6\u00a0B"
    assert catalog.size_fr("8x7B", None) == "8x7\u00a0B"
    assert catalog.size_fr(None, 45 * 1024**2) == "45\u00a0Mo"  # below 0,1 Go
    assert catalog.size_fr(None, 10) == "1\u00a0Mo"
    assert catalog.size_fr(None, int(0.1 * 1024**3) + 1) == "0,1\u00a0Go"


# ---------- publishers ----------


@pytest.mark.parametrize(
    ("architectures", "names", "expected"),
    [
        (["qwen35"], [], "qwen"),
        (["qwen3moe"], [], "qwen"),
        (["llama"], ["Llama-3.2-3B-Instruct"], "llama"),
        (["llama"], ["Mistral-7B-Instruct-v0.3"], "mistral"),  # `llama` says nothing
        (["llama"], ["SmolLM2-1.7B"], "smollm"),
        (["smollm3"], [], "smollm"),
        (["qwen2"], ["deepseek-r1:1.5b"], "deepseek"),  # its name before its base's family
        (["deepseek2"], [], "deepseek"),
        (["qwen2"], ["qwen2.5:1.5b"], "qwen"),
        (["gemma3"], [], "gemma"),
        (["granitehybrid"], [], "granite"),
        (["phi3"], [], "phi"),
        (["mistral3"], [], "mistral"),
        (["lfm2"], [], "lfm"),
        (["nemotron_h"], [], "nemotron"),
        (["gpt-oss"], [], "gpt_oss"),
        (["minicpm"], [], "minicpm"),
        ([], ["gemma-3-270m-it"], "gemma"),
        ([], ["granite-4.0-h-micro"], "granite"),
        ([], ["Phi-4-mini-instruct"], "phi"),
        ([], ["ministral-8b-latest"], "mistral"),
        ([], ["magistral-small"], "mistral"),
        ([], ["devstral-small"], "mistral"),
        ([], ["codestral-latest"], "mistral"),
        ([], ["LFM2-1.2B"], "lfm"),
        ([], ["NVIDIA-Nemotron-Nano-9B-v2"], "nemotron"),
        ([], ["openai/gpt-oss-120b"], "gpt_oss"),
        ([], ["MiniCPM4-0.5B"], "minicpm"),
        ([], ["llama3.2:3b"], "llama"),
        ([], ["faux-llama-server.gguf"], "other"),  # the server, never Llama
        ([], ["wavestack-fake"], "other"),
        (["unknown", "openai_chat"], ["qwen3:0.6b"], "qwen"),  # families that say nothing
    ],
)
def test_publisher_for(architectures, names, expected):
    assert catalog.publisher_for(architectures, names).id == expected


def test_unknown_publisher_is_last_of_its_hosting():
    mistral = _preset("mistral").model_dump(exclude_none=True)
    fake = {**mistral, "id": "fake", "model": "wavestack-fake"}
    cfg = config.Config(values={"cloud": {"models": [fake, mistral]}})
    groups = catalog.group_models(catalog.cloud_entries(cfg) + [_entry(_ollama_missing())])
    assert [g.label_text for g in groups] == [
        "Sur ce poste · Qwen (Alibaba)",
        "Réseau · Mistral (Mistral AI)",
        "Réseau · Autres éditeurs",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "publishers: [{id: x, label_text: X, names: ['(']}]",  # a wrong regex
        "legend_text: Légende\n",  # keys missing
        "- pas: un objet\n",
        ": : :\n",
    ],
)
def test_invalid_publishers_file_puts_every_model_in_others(tmp_path, monkeypatch, text):
    path = tmp_path / "publishers.yaml"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(catalog, "publishers_path", lambda lang="fr": path)
    content, error = catalog.load_publishers()
    assert error.startswith("Fichier content/models/publishers.yaml invalide")
    assert content.publishers == []

    payload = catalog.models_payload([_ollama_missing()], config.load_config())
    assert payload["publishers_error_text"] == error
    assert {g["publisher_id"] for g in payload["groups"]} == {"other"}
    assert [g["label_text"] for g in payload["groups"]] == [
        "Sur ce poste · Autres éditeurs",
        "Réseau · Autres éditeurs",
    ]


@pytest.mark.parametrize(
    ("change", "cause"),
    [
        (lambda ps: ps.append({**ps[0], "label_text": "Autre Qwen"}), "en double : qwen"),
        (lambda ps: ps.append({"id": "other", "label_text": "X"}), "« other » est réservé"),
    ],
)
def test_publisher_ids_are_distinct_and_never_other(tmp_path, monkeypatch, change, cause):
    """Two publishers with one id, or the id of « Autres éditeurs », would merge groups."""
    data = yaml.safe_load(catalog.publishers_path().read_text(encoding="utf-8"))
    change(data["publishers"])
    path = tmp_path / "publishers.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(catalog, "publishers_path", lambda lang="fr": path)
    content, error = catalog.load_publishers()
    assert content.publishers == [] and cause in error


def test_shipped_publishers_file_is_valid():
    content, error = catalog.load_publishers()
    assert error is None
    assert [p.label_text for p in content.publishers] == [
        "Qwen (Alibaba)",
        "Llama (Meta)",
        "Gemma (Google)",
        "Gemini (Google)",
        "Granite (IBM)",
        "Phi (Microsoft)",
        "Mistral (Mistral AI)",
        "LFM (Liquid AI)",
        "Nemotron (NVIDIA)",
        "gpt-oss (OpenAI)",
        "Claude (Anthropic)",
        "MiniCPM (OpenBMB)",
        "DeepSeek (DeepSeek AI)",
        "SmolLM (Hugging Face)",
    ]
    assert "où tourne le modèle" in content.legend_text and "qui le sert" in content.legend_text
    assert content.other_text == "Autres éditeurs"


# ---------- the header, read once ----------


def test_header_read_once_per_path_size_and_mtime(tmp_path, monkeypatch):
    path = _qwen_file(tmp_path)
    reads = []
    real = gguf_meta.try_read_metadata
    monkeypatch.setattr(gguf_meta, "try_read_metadata", lambda p: reads.append(p) or real(p))

    first = catalog.header_metadata(str(path))
    assert catalog.header_metadata(str(path)) is first
    assert len(reads) == 1
    assert first[0].architecture == "qwen35" and first[1]["general.size_label"] == "2B"

    _qwen_file(tmp_path, size="4B")  # rewritten: another size or modification time
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert catalog.header_metadata(str(path))[1]["general.size_label"] == "4B"
    assert len(reads) == 2
    assert catalog.header_metadata(str(tmp_path / "absent.gguf")) is None


def test_header_path_is_the_file_the_entry_reads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    relative = ModelCandidate(source="models_dir", path="m.gguf", name="m", status="found")
    assert catalog.header_path(relative) == str(tmp_path / "m.gguf")
    assert catalog.header_path(_llama_server("relatif.gguf")) is None  # not this disk's
    absolute = str(tmp_path / "served.gguf")
    assert catalog.header_path(_llama_server(absolute)) == absolute
    assert catalog.header_path(_llama_server(None)) is None


def test_warm_headers_reads_each_file_once_off_the_request(tmp_path, monkeypatch):
    """R1: the search's candidates read in the background, each file once (two tags of one
    blob too); the table then reads nothing."""
    path = _qwen_file(tmp_path)
    reads = []
    real = gguf_meta.try_read_metadata
    monkeypatch.setattr(gguf_meta, "try_read_metadata", lambda p: reads.append(p) or real(p))

    catalog.warm_headers([_file(path), _file(path), _ollama_missing()]).join(timeout=10)
    assert reads == [str(path)]
    catalog.local_entries([_file(path)], config.load_config())
    assert reads == [str(path)]


def test_a_request_during_the_warm_up_waits_instead_of_reading_again(tmp_path, monkeypatch):
    """R1: two threads asking for the same cold header: one reads, the other waits for it
    (on the PC pro, two concurrent requests each read every header, 21 s)."""
    path = str(_qwen_file(tmp_path))
    reads = []
    started, release = threading.Event(), threading.Event()
    real = gguf_meta.try_read_metadata

    def slow(p):  # noqa: ANN001, ANN202
        reads.append(p)
        started.set()
        release.wait(timeout=10)
        return real(p)

    class _Spy:
        """`_READ_LOCK`, saying when a second thread is about to wait on it."""

        def __init__(self, lock) -> None:  # noqa: ANN001
            self.lock, self.entered, self.second = lock, 0, threading.Event()

        def __enter__(self):  # noqa: ANN204
            self.entered += 1
            if self.entered == 2:
                self.second.set()
            return self.lock.__enter__()

        def __exit__(self, *exc):  # noqa: ANN002, ANN204
            return self.lock.__exit__(*exc)

    spy = _Spy(catalog._READ_LOCK)
    monkeypatch.setattr(catalog, "_READ_LOCK", spy)
    monkeypatch.setattr(gguf_meta, "try_read_metadata", slow)
    results = []
    first = threading.Thread(target=lambda: results.append(catalog.header_metadata(path)))
    first.start()
    assert started.wait(timeout=10)
    second = threading.Thread(target=lambda: results.append(catalog.header_metadata(path)))
    second.start()
    assert spy.second.wait(timeout=10)  # the cache still cold: it waits for the first read
    release.set()
    first.join(timeout=10)
    second.join(timeout=10)
    assert reads == [path]
    assert results[0] is results[1] and results[0][0].architecture == "qwen35"


def test_a_failing_warm_up_is_logged_and_leaves_the_reads_to_the_request(
    tmp_path, monkeypatch, caplog
):
    path = _qwen_file(tmp_path)
    real = catalog.header_metadata

    def broken(p):  # noqa: ANN001, ANN202
        raise RuntimeError("panne")

    monkeypatch.setattr(catalog, "header_metadata", broken)
    catalog.warm_headers([_file(path)]).join(timeout=10)
    assert "Préchauffage des en-têtes GGUF interrompu" in caplog.text
    monkeypatch.setattr(catalog, "header_metadata", real)
    assert _entry(_file(path)).params_label == "2B"


def test_payload_timings_detail_each_step_and_the_slow_candidates():
    timings = catalog.PayloadTimings()
    for step in ("load_publishers", "local_entries", "cloud_entries", "group_models"):
        timings.lap(step)
    timings.candidate("gemma3:1b", 0.482, 0.001)
    timings.candidate("qwen3.5:4b", 1.335, 0.007)
    timings.candidate("en cache", 0.0, 0.0002)  # under 1 ms: left out
    text = timings.summary()
    assert text.startswith("load_publishers ")
    assert "local_entries " in text and "cloud_entries " in text and "group_models " in text
    assert "(headers 1817 ms ; qwen3.5:4b 1335 + 7 ms ; gemma3:1b 482 + 1 ms)" in text
    assert "en cache" not in text


# ---------- one truth: the table says what the cards say after the load ----------


def _meta(template: str | None, architecture: str | None) -> EngineMetadata:
    return EngineMetadata(architecture, template, None, "", "<|im_end|>", ())


@pytest.mark.parametrize(
    ("template", "architecture", "window", "mode"),
    [
        (QWEN_TEMPLATE, "qwen35", 4096, "toggle"),
        (QWEN_TEMPLATE, "qwen35", 1024, "never"),  # AD-9: no room past the reasoning reserve
        (CHATML, "fake", 4096, "never"),
        (THINK_ONLY, "fake", 4096, "unknown"),
        (QWEN_TEMPLATE.replace("enable_thinking", "autre_variable"), "qwen35", 4096, "unknown"),
    ],
)
def test_local_mode_matches_the_reasoning_card(template, architecture, window, mode):
    engine = FakeEngine(template=template, architecture=architecture)
    caps = capabilities_for(engine.metadata())
    found, reason = reasoning_mode(caps, window)
    assert found == mode
    session = booted_session(engine, window=window)
    card = _card()
    assert (found == "toggle") == (card["available"] and not card["always_text"])
    assert (found == "always") == bool(card["always_text"])
    if window <= 1536:
        assert not card["available"] and card["reason_text"] == reason
    session.close()


@pytest.mark.parametrize(
    ("preset", "update", "mode"),
    [
        ("groq", {}, "always"),
        ("mistral", {}, "toggle"),
        ("mistral", {"reasoning": None}, "never"),
    ],
)
def test_cloud_mode_matches_the_reasoning_card(preset, update, mode):
    entry = _preset(preset).model_copy(update=update)
    assert reasoning_mode(cloud_capabilities(entry))[0] == mode
    session = _cloud(entry, Provider(TEXT))
    card = _card()
    assert (mode == "toggle") == (card["available"] and not card["always_text"])
    assert (mode == "always") == bool(card["always_text"])
    session.close()


def test_tools_summary_follows_the_parser():
    assert tools_summary(None) == (None, "inconnu", "capacités non lues")
    assert tools_summary(capabilities_for(_meta(QWEN_TEMPLATE, "qwen35")))[:2] == (
        True,
        "oui (qwen3_coder)",
    )
    no = cloud_capabilities(_preset("mistral").model_copy(update={"tools": False}))
    assert tools_summary(no) == (False, "non", "non déclaré dans la configuration (tools)")


def test_window_for_is_the_session_rule():
    meta = EngineMetadata(None, CHATML, 32768, "", "", (), server_context=2048)
    assert window_for(meta, 4096) == (2048, "server")
    assert window_for(_meta(CHATML, "x"), 4096) == (4096, "configured")
    native = EngineMetadata("x", CHATML, 1024, "", "", ())
    assert window_for(native, 4096) == (1024, "native")


# ---------- the servers' answers kept, and the API ----------


def test_api_diagnostic_carries_the_models(monkeypatch, tmp_path):
    app = _build(monkeypatch, tmp_path)
    body = _client(app).get("/api/diagnostic").json()
    models = body["models"]
    assert "où tourne le modèle" in models["legend_text"]
    assert models["publishers_error_text"] is None
    assert [g["label_text"] for g in models["groups"]] == [
        "Réseau · Gemma (Google)",
        "Réseau · Gemini (Google)",
        "Réseau · Mistral (Mistral AI)",
        "Réseau · gpt-oss (OpenAI)",
        "Réseau · Claude (Anthropic)",
    ]
    groq = models["groups"][3]["models"][0]
    assert (groq["value"], groq["reasoning"], groq["params_label"]) == (
        "cloud:groq",
        "always",
        "120B",
    )
    assert groq["window"] == 4000  # tpm // 2 (AD-9)


def test_api_diagnostic_with_an_invalid_publishers_file(monkeypatch, tmp_path):
    path = tmp_path / "publishers.yaml"
    path.write_text("publishers: [{id: x, label_text: X, names: ['[']}]", encoding="utf-8")
    monkeypatch.setattr(catalog, "publishers_path", lambda lang="fr": path)
    response = _client(_build(monkeypatch, tmp_path)).get("/api/diagnostic")
    assert response.status_code == 200
    models = response.json()["models"]
    assert {g["label_text"] for g in models["groups"]} == {"Réseau · Autres éditeurs"}
    assert "content/models/publishers.yaml" in models["publishers_error_text"]


def test_local_entries_read_the_window_configured_now(tmp_path):
    """Story 26: the table shows the window the session holds, not the launch's."""
    candidate = _file(_qwen_file(tmp_path))
    cfg = config.Config(values={"context": {"window": 4096}})
    [launch] = catalog.local_entries([candidate], cfg)
    [chosen] = catalog.local_entries([candidate], cfg, window=8192)
    assert (launch.window, chosen.window) == (4096, 8192)
