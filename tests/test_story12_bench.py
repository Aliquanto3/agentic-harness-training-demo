"""Pure logic of the story 12 bench (`tools/bench/story12_bench.py`).

Nothing here imports headroom, llama-cpp, fastembed or huggingface_hub, and
nothing leaves the machine: the heavy paths are replaced by injected fakes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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


def test_embed_download_measures_each_candidate_and_survives_a_failure(bench, tmp_path):
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
        if c.id == "e5small_q8":
            raise RuntimeError("chargement impossible")
        if c.id == "qwen3emb06_q8":
            return {"fatal": "code -11"}
        values = {"bgererank_m3_q4km": {"mrr": 0.97}, "bgem3_q4km": {"mrr": 0.99}}
        return _measured(bench, c.id, **values.get(c.id, {}))

    report = bench.run_embed(
        tmp_path, download=True, runner=runner, downloader=downloader, find_spec=_no_fastembed
    )
    assert "granite107m_q8" in downloaded
    rows = {r["id"]: r for r in report["results"]}
    assert rows["e5small_q8"]["status"] == "erreur"
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
