"""Pure logic of the story 12 bench (`tools/bench/story12_bench.py`).

Nothing here imports headroom, llama-cpp, fastembed or huggingface_hub, and
nothing leaves the machine: the heavy paths are replaced by injected fakes.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_PATH = Path(__file__).resolve().parents[1] / "tools" / "bench" / "story12_bench.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("story12_bench", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["story12_bench"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("story12_bench", None)


# -- dataset and metrics ---------------------------------------------------


def test_dataset_has_one_gold_document_per_query(bench):
    assert bench.check_dataset() == []
    assert len(bench.QUERIES) == len(bench.DOCUMENTS) == 10


def test_headroom_samples_carry_their_marker(bench):
    samples = bench.headroom_samples()
    assert [s["id"] for s in samples] == [
        "json_tool_result",
        "log_tool_result",
        "prose_rag_excerpt",
    ]
    for sample in samples:
        assert sample["marker"] in sample["text"]


def test_dependency_closure_reads_installed_licences(bench):
    closure = bench.dependency_closure("psutil")
    assert [d["name"].lower() for d in closure] == ["psutil"]
    assert closure[0]["class"] == "ok"
    assert bench.dependency_closure("not-installed-package") == []


def test_ranks_recall_and_mrr(bench):
    docs = ["a", "b", "c"]
    scores = [[0.9, 0.1, 0.2], [0.8, 0.1, 0.5], [0.3, 0.2, 0.1]]
    ranks = bench.ranks_of_gold(scores, docs, ["a", "c", "c"])
    assert ranks == [1, 2, 3]
    assert bench.recall_at(ranks, 1) == 0.333
    assert bench.recall_at(ranks, 3) == 1.0
    assert bench.mrr(ranks) == round((1 + 1 / 2 + 1 / 3) / 3, 3)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("MIT", "ok"),
        ("Apache-2.0", "ok"),
        ("BSD License", "ok"),
        ("MPL-2.0 AND MIT", "ok"),
        ("Python Software Foundation License", "ok"),
        ("CC-BY-NC-4.0", "forbidden"),
        ("GNU General Public License v3 (GPLv3)", "forbidden"),
        ("AGPL-3.0-only", "forbidden"),
        ("Business Source License 1.1", "forbidden"),
        ("BUSL-1.1", "forbidden"),
        ("BSL 1.1", "forbidden"),
        ("BSL-1.0", "ok"),  # SPDX: the Boost licence
        (
            "Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause"
            " AND BSL-1.0 AND MIT",
            "ok",
        ),  # torch 2.14, read on the target PC (V2 S6 bench, 2026-10-03)
        ("gemma", "forbidden"),
        ("LGPL-3.0-or-later", "unknown"),
        ("?", "unknown"),
    ],
)
def test_classify_license(bench, text, expected):
    assert bench.classify_license(text) == expected


# -- network observations --------------------------------------------------


def test_attempts_summary_drops_loopback_and_duplicates(bench):
    attempts = [
        ["socket.getaddrinfo", "openaipublic.blob.core.windows.net"],
        ["socket.getaddrinfo", "openaipublic.blob.core.windows.net"],
        ["socket.connect", "127.0.0.1"],
        ["socket.getaddrinfo", "localhost"],
        ["socket.connect", "57.150.192.193"],
    ]
    assert bench.summarize_attempts(attempts) == [
        "57.150.192.193",
        "openaipublic.blob.core.windows.net",
    ]


def test_blocked_attempt_is_found_behind_the_library_exception(bench):
    from wavestack.net.guard import NetworkBlocked

    try:
        try:
            raise NetworkBlocked("Hôte réseau non autorisé : openaipublic.blob.core.windows.net")
        except NetworkBlocked as exc:
            raise ConnectionError("tiktoken download failed") from exc
    except ConnectionError as wrapped:
        assert "openaipublic.blob.core.windows.net" in bench._blocked_host(wrapped)
    assert bench._blocked_host(ValueError("unrelated")) is None


def test_strace_parser_keeps_remote_inet_connects_only(bench):
    log = "\n".join(
        [
            '101 connect(3, {sa_family=AF_UNIX, sun_path="/var/run/nscd/socket"}, 110) = -1',
            '101 connect(3, {sa_family=AF_INET, sin_port=htons(53), sin_addr=inet_addr("8.8.8.8")}'
            ", 16) = 0",
            '101 connect(4, {sa_family=AF_INET, sin_port=htons(443), sin_addr=inet_addr("57.1.2.3")'
            "}, 16) = 0",
            '101 connect(5, {sa_family=AF_INET, sin_port=htons(8420), sin_addr=inet_addr("127.0.0.1'
            '")}, 16) = 0',
            "101 connect(6, {sa_family=AF_INET6, sin6_port=htons(443), sin6_flowinfo=htonl(0), "
            'inet_pton(AF_INET6, "2001:db8::1", &sin6_addr), sin6_scope_id=0}, 28) = 0',
        ]
    )
    assert bench.parse_strace_connects(log) == ["2001:db8::1:443", "57.1.2.3:443", "8.8.8.8:53"]


# -- Headroom verdict ------------------------------------------------------


def _passing_report() -> dict:
    samples = [
        {"id": "json_tool_result", "tokens_before": 7556, "tokens_after": 2825},
        {"id": "prose_rag_excerpt", "tokens_before": 624, "tokens_after": 624},
    ]
    return {
        # The naive variant is informational: its blocked attempts never decide.
        "naive": {"attempts": [["socket.getaddrinfo", "openaipublic.blob.core.windows.net"]]},
        "configured": {
            "attempts": [["socket.getaddrinfo", "localhost"]],
            "native_connects": [],
            "heavy_modules_loaded": [],
            "rss_added_mb": 130,
            "rss_peak_mb": 154,
            "samples": samples,
        },
        "netns": True,
        "closure": [
            {"name": "headroom-ai", "version": "0.38.0", "license": "Apache-2.0", "class": "ok"},
            {"name": "litellm", "version": "1.102.1", "license": "MIT", "class": "ok"},
        ],
    }


def _criterion(verdict: dict, criterion_id: str) -> dict:
    return next(c for c in verdict["criteria"] if c["id"] == criterion_id)


def test_headroom_configured_and_clean_is_retained(bench):
    verdict = bench.headroom_verdict(_passing_report())
    assert verdict["retained"] is True
    assert [c["id"] for c in verdict["criteria"]] == [
        "network",
        "no_torch",
        "budget",
        "license",
        "adoption",
    ]


@pytest.mark.parametrize(
    ("change", "failing"),
    [
        (
            lambda r: r["configured"]["attempts"].append(["socket.getaddrinfo", "pypi.org"]),
            "network",
        ),
        (lambda r: r["configured"].update(native_connects=["1.2.3.4:443"]), "network"),
        (lambda r: r["configured"].update(heavy_modules_loaded=["torch"]), "no_torch"),
        (
            lambda r: r["closure"].append(
                {"name": "torch", "version": "2.12", "license": "BSD", "class": "ok"}
            ),
            "no_torch",
        ),
        (lambda r: r["configured"].update(rss_added_mb=301), "budget"),
        (
            lambda r: r["closure"].append(
                {"name": "x", "version": "1", "license": "BSL-1.1", "class": "forbidden"}
            ),
            "license",
        ),
        (lambda r: r["configured"]["samples"].append({"id": "x", "error": "boom"}), "adoption"),
        (lambda r: r.update(netns=False), "adoption"),
    ],
)
def test_headroom_verdict_fails_on_each_criterion(bench, change, failing):
    report = _passing_report()
    change(report)
    verdict = bench.headroom_verdict(report)
    assert verdict["retained"] is False
    assert _criterion(verdict, failing)["ok"] is False


def test_headroom_without_strace_or_netns_says_so(bench):
    report = _passing_report()
    report["configured"]["native_connects"] = None
    report["netns"] = None
    verdict = bench.headroom_verdict(report)
    assert verdict["retained"] is True
    assert "strace absent" in _criterion(verdict, "network")["detail"]
    assert "non disponible" in _criterion(verdict, "adoption")["detail"]


def _stub_child(bench, monkeypatch, rss: list[int], peaks: list[int]) -> None:
    """No audit hook nor guard added to the pytest process; RSS and peaks in sequence (the
    last value repeats)."""
    monkeypatch.setattr(bench, "_record_and_guard", lambda allowed_hosts: ([], "factice"))

    def reader(values: list[int]):
        return lambda: values.pop(0) if len(values) > 1 else values[0]

    monkeypatch.setattr(bench, "_rss_mb", reader(rss))
    monkeypatch.setattr(bench, "_peak_rss_mb", reader(peaks))


def test_headroom_child_counts_with_the_adapter_model_in_both_variants(bench, monkeypatch):
    from wavestack.compression import headroom_adapter

    seen: list[tuple] = []

    def compress(messages, **kwargs):
        seen.append((kwargs.get("model"), kwargs.get("kompress_model")))
        return SimpleNamespace(
            messages=messages,
            tokens_before=10,
            tokens_after=5,
            transforms_applied=["factice"],
        )

    monkeypatch.setitem(sys.modules, "headroom", SimpleNamespace(compress=compress))
    monkeypatch.setattr(bench.time, "sleep", lambda seconds: None)
    for variant, kompress in (("naive", None), ("configured", "disabled")):
        seen.clear()
        # RSS before import, after import, after compression; peak at the baseline, then after.
        _stub_child(bench, monkeypatch, rss=[25, 28, 97], peaks=[30, 124])
        out = bench._headroom_child(variant)
        assert out["counting_model"] == bench.COUNTING_MODEL
        assert seen and set(seen) == {(bench.COUNTING_MODEL, kompress)}
        assert out["rss_added_mb"] == 124 - 30  # the peak minus the baseline, as the embed bench
    assert bench.COUNTING_MODEL == headroom_adapter.COUNTING_MODEL == "gpt-4"


def test_headroom_missing_prints_the_uv_command(bench, monkeypatch, capsys):
    monkeypatch.setattr(bench.importlib.util, "find_spec", lambda name: None)
    assert bench.main(["headroom"]) == 2
    out = capsys.readouterr().out
    assert "uv run --with headroom-ai==0.38.0" in out
    assert "aucune dépendance n'est ajoutée au projet" in out


# -- embedding and reranking -----------------------------------------------


def _measured(bench, candidate_id: str, **values) -> dict:
    c = bench.candidate(candidate_id)
    row = {"id": c.id, "role": c.role, "backend": c.backend, "size_mb": c.size_mb}
    row.update(status="measured", recall_at_1=0.9, mrr=0.93, rss_added_mb=200)
    row.update(values)
    return row


def _no_fastembed(name):
    return None if name == "fastembed" else object()


def test_embed_without_models_is_provisional_and_runs_nothing(bench, tmp_path):
    def runner(c, models_dir):
        raise AssertionError(f"no child should run for {c.id}")

    report = bench.run_embed(tmp_path, runner=runner, find_spec=_no_fastembed)
    statuses = {r["id"]: r["status"] for r in report["results"]}
    assert statuses["granite107m_q8"].startswith("absent")
    assert statuses["fe_minilm_multi"] == "non mesuré (fastembed absent)"
    verdict = report["verdict"]
    assert verdict["embedding"] == {
        "id": "granite107m_q8",
        "status": "provisoire, mesure sur PC cible à faire",
        "measured": False,
    }
    assert verdict["reranker"]["id"] == "bgererank_m3_q4km"
    assert verdict["reranker"]["measured"] is False


def test_embed_main_without_models_prints_the_provisional_verdict(bench, tmp_path, capsys):
    assert bench.main(["embed", "--models-dir", str(tmp_path), "--only", "granite107m_q8"]) == 0
    out = capsys.readouterr().out
    assert "granite107m_q8 — provisoire, mesure sur PC cible à faire" in out
    assert "Apache-2.0" in out


def test_embed_download_measures_each_candidate_and_survives_a_failure(
    bench, tmp_path, monkeypatch
):
    # A dummy candidate that fails to load: no real candidate is known to fail (lot F).
    dummy = dataclasses.replace(
        bench.candidate("granite107m_q8"),
        id="factice_q8",
        repo="factice/factice-GGUF",
        filename="factice-Q8_0.gguf",
        size_mb=50,
    )
    monkeypatch.setattr(bench, "CANDIDATES", [*bench.CANDIDATES, dummy])
    downloaded = []

    def downloader(models_dir, selected):
        for c in selected:
            if c.backend == "llama_cpp":
                path = bench.model_path(models_dir, c)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"GGUF")
                downloaded.append(c.id)
        return {"guard": "wavestack.net.guard", "hosts": ["huggingface.co"], "errors": {}}

    def runner(c, models_dir):
        if c.id == "factice_q8":
            raise RuntimeError("chargement impossible")
        if c.id == "qwen3emb06_q8":
            return {"fatal": "code -11"}
        values = {"bgererank_m3_q4km": {"mrr": 0.97}, "bgem3_q4km": {"mrr": 0.99}}
        return _measured(bench, c.id, **values.get(c.id, {}))

    report = bench.run_embed(
        tmp_path, download=True, runner=runner, downloader=downloader, find_spec=_no_fastembed
    )
    assert "granite107m_q8" in downloaded and "factice_q8" in downloaded
    rows = {r["id"]: r for r in report["results"]}
    assert rows["factice_q8"]["status"] == "erreur"
    assert "chargement impossible" in rows["factice_q8"]["error"]
    assert rows["qwen3emb06_q8"]["status"] == "erreur"
    assert rows["bgem3_q4km"]["status"] == "measured"
    verdict = report["verdict"]
    # Smallest passing GGUF wins, even when a bigger one scores higher.
    assert verdict["embedding"] == {"id": "granite107m_q8", "status": "mesuré", "measured": True}
    assert verdict["reranker"] == {"id": "bgererank_m3_q4km", "status": "mesuré", "measured": True}


def test_embed_verdict_falls_back_to_fastembed(bench):
    results = [
        _measured(bench, "granite107m_q8", recall_at_1=0.5),
        _measured(bench, "bgem3_q4km", rss_added_mb=900),
        _measured(bench, "fe_minilm_multi", mrr=0.8),
        _measured(bench, "bgererank_m3_q4km", mrr=0.7),
        _measured(bench, "fe_mmarco_rerank", mrr=0.85),
    ]
    verdict = bench.embed_verdict(results)
    assert verdict["embedding"]["id"] == "fe_minilm_multi"
    assert verdict["embedding"]["status"] == "repli fastembed"
    # The GGUF reranker loses MRR against the chosen embedding: fastembed takes over.
    assert verdict["reranker"]["id"] == "fe_mmarco_rerank"


def test_embed_verdict_when_nothing_passes(bench):
    verdict = bench.embed_verdict([_measured(bench, "granite107m_q8", recall_at_1=0.1)])
    assert verdict["embedding"]["id"] is None
    assert verdict["embedding"]["measured"] is True
    assert verdict["reranker"]["status"] == "provisoire, mesure sur PC cible à faire"


def test_e5small_is_no_longer_a_candidate_and_says_why(bench):
    assert "e5small_q8" not in {c.id for c in bench.CANDIDATES}
    reasons = dict(bench.EXCLUDED)
    assert "llama-cpp-python 0.3.35" in reasons["cstr/multilingual-e5-small-GGUF"]


# -- added RSS: the peak, model loaded (lot F) -------------------------------


def _perfect_scores(bench) -> list[list[float]]:
    return [[1.0 if doc == gold else 0.0 for doc in bench.DOCUMENTS] for _, gold in bench.QUERIES]


def test_added_rss_is_the_peak_minus_the_baseline_not_the_rss_after_close(bench):
    stats = {
        "rss_before_load_mb": 100,
        "peak_before_load_mb": 90,
        "rss_after_load_mb": 480,
        "rss_loaded_mb": 510,
        "rss_peak_mb": 528,
    }
    scores = _perfect_scores(bench)
    row = bench.measured_result(scores, stats, rss_after_run_mb=104)  # after close(): +4
    assert row["rss_added_mb"] == 428
    assert row["rss_after_run_mb"] == 104 and row["recall_at_1"] == 1.0
    # The high-water mark never goes down: one already higher at the baseline is the base.
    row = bench.measured_result(scores, dict(stats, peak_before_load_mb=150), 104)
    assert row["rss_added_mb"] == 378
    # No high-water mark on this system: the largest RSS read with the model loaded.
    row = bench.measured_result(scores, dict(stats, rss_peak_mb=None), rss_after_run_mb=104)
    assert row["rss_added_mb"] == 410


class _FakeLlama:
    """Enough of `llama_cpp.Llama` for both llama.cpp runners; records its instances."""

    made: list[_FakeLlama] = []

    def __init__(self, **_kwargs) -> None:
        self.closed = False
        self.metadata = {}
        self._ctx = SimpleNamespace(kv_cache_clear=lambda: None, decode=lambda b: None, ctx=None)
        self._batch = SimpleNamespace(reset=lambda: None, add_sequence=lambda *a: None)
        self._model = SimpleNamespace(model=None)
        _FakeLlama.made.append(self)

    def tokenize(self, text, add_bos=True, special=False):
        return [1, 2, 3]

    def n_embd(self) -> int:
        return 2

    def pooling_type(self) -> int:
        return 2

    def close(self) -> None:
        self.closed = True


def _fake_llama_cpp() -> SimpleNamespace:
    _FakeLlama.made = []
    return SimpleNamespace(
        Llama=_FakeLlama,
        LLAMA_POOLING_TYPE_CLS=2,
        LLAMA_POOLING_TYPE_MEAN=1,
        LLAMA_POOLING_TYPE_LAST=3,
        LLAMA_POOLING_TYPE_RANK=4,
        llama_get_embeddings_seq=lambda ctx, seq: [1.0, 0.0],
        llama_model_get_vocab=lambda model: None,
        llama_vocab_bos=lambda vocab: 0,
        llama_vocab_eos=lambda vocab: 2,
        llama_vocab_sep=lambda vocab: 2,
    )


@pytest.mark.parametrize("candidate_id", ["granite107m_q8", "bgererank_m3_q4km"])
def test_embed_child_reports_the_peak_not_the_rss_after_close(
    bench, monkeypatch, tmp_path, candidate_id
):
    monkeypatch.setitem(sys.modules, "llama_cpp", _fake_llama_cpp())
    monkeypatch.setattr(bench, "model_path", lambda models_dir, c: tmp_path / "x.gguf")
    # RSS: 100 at the baseline, 480 after load, 510 loaded after the run, 104 after close().
    # High-water mark: 120 at the baseline (reached by the imports), 528 afterwards.
    _stub_child(bench, monkeypatch, rss=[100, 480, 510, 104], peaks=[120, 528])

    out = bench._embed_child(candidate_id, tmp_path)

    assert _FakeLlama.made and _FakeLlama.made[-1].closed
    assert out["status"] == "measured" and out["attempts"] == []
    assert out["rss_before_load_mb"] == 100 and out["peak_before_load_mb"] == 120
    assert out["rss_loaded_mb"] == 510 and out["rss_peak_mb"] == 528
    assert out["rss_after_run_mb"] == 104
    assert out["rss_added_mb"] == 528 - 120


def test_embed_child_fastembed_reports_the_peak(bench, monkeypatch, tmp_path):
    model = SimpleNamespace(
        passage_embed=lambda docs: [[1.0, 0.0] for _ in docs],
        query_embed=lambda queries: [[1.0, 0.0] for _ in queries],
    )
    monkeypatch.setitem(sys.modules, "fastembed", SimpleNamespace())
    monkeypatch.setattr(bench, "_fastembed_model", lambda c, models_dir, local_only: model)
    _stub_child(bench, monkeypatch, rss=[100, 300, 320, 320], peaks=[100, 350])

    out = bench._embed_child("fe_minilm_multi", tmp_path)

    assert out["status"] == "measured" and out["rss_loaded_mb"] == 320
    assert out["rss_added_mb"] == 250


def test_embed_verdict_with_the_target_pc_peaks_keeps_the_recommended_models(bench):
    # Peaks measured on the target PC (2026-09-27), with the thresholds set before them.
    results = [
        _measured(bench, "granite107m_q8", rss_added_mb=428),
        _measured(bench, "bgem3_q4km", rss_added_mb=731, mrr=0.99),
        _measured(bench, "qwen3emb06_q8", rss_added_mb=900, mrr=0.99),
        _measured(bench, "bgererank_m3_q4km", rss_added_mb=736, mrr=0.97),
    ]
    rows = {r["id"]: r for r in results}
    assert not bench._passes(rows["bgem3_q4km"], bench.EMBED_RSS_BUDGET_MB, None)
    assert not bench._passes(rows["qwen3emb06_q8"], bench.EMBED_RSS_BUDGET_MB, None)
    assert bench._passes(rows["bgererank_m3_q4km"], bench.RERANK_RSS_BUDGET_MB, 0.93)
    verdict = bench.embed_verdict(results)
    assert verdict["embedding"]["id"] == bench.RECOMMENDED["embedding"]
    assert verdict["reranker"]["id"] == bench.RECOMMENDED["reranker"]


def test_embed_report_says_how_the_added_rss_was_measured(bench, tmp_path):
    report = bench.run_embed(tmp_path, find_spec=_no_fastembed)
    assert report["rss_added_method"] == "pic"


def test_embed_only_with_an_unknown_or_removed_id_stops_and_says_why(bench, tmp_path, capsys):
    argv = ["embed", "--models-dir", str(tmp_path), "--only", "granite107m_q8", "e5small_q8"]
    assert bench.main(argv) == 2
    out = capsys.readouterr().out
    assert "Candidat inconnu : e5small_q8" in out and "retiré" in out
    assert "granite107m_q8" in out and "Verdict" not in out
    assert bench.main(["embed", "--models-dir", str(tmp_path), "--only", "nimporte"]) == 2
    assert "Candidat inconnu : nimporte" in capsys.readouterr().out


# -- story 1e: the download hands the confiscated proxy back ---------------


@pytest.mark.parametrize(
    ("strip_proxy", "expected"), [(False, "http://127.0.0.1:9000"), (True, None)]
)
def test_record_and_guard_hands_the_proxy_back_for_downloads_only(strip_proxy, expected):
    """The real `_record_and_guard`, in a child process (its guard cannot be uninstalled)."""
    child = (
        "import importlib.util, json, sys, urllib.request\n"
        f"spec = importlib.util.spec_from_file_location('story12_bench', {str(_PATH)!r})\n"
        "bench = importlib.util.module_from_spec(spec)\n"
        "sys.modules['story12_bench'] = bench\n"
        "spec.loader.exec_module(bench)\n"
        f"bench._record_and_guard(allowed_hosts=[], strip_proxy={strip_proxy})\n"
        "print(json.dumps(urllib.request.getproxies().get('https')))\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    env["HTTPS_PROXY"] = "http://127.0.0.1:9000"
    result = subprocess.run(
        [sys.executable, "-c", child], capture_output=True, text=True, env=env, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == expected
