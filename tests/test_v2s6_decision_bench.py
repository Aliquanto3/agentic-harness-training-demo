"""Pure logic of the V2 story 6 bench (`tools/bench/v2s6_decision_bench.py`).

Nothing here imports onnxruntime, torch, gliformer or llama-cpp, downloads a model or
leaves the machine: the heavy paths are replaced by injected fakes.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_PATH = _ROOT / "tools" / "bench" / "v2s6_decision_bench.py"
_CANDIDATES_DOC = (
    _ROOT / "_bmad-output" / "specs" / "spec-wavestack-v2" / "decision-model-candidates.md"
)
_HEAVY = ("onnxruntime", "torch", "transformers", "gliformer", "fast_gliner")


@pytest.fixture(scope="module")
def bench():
    before = {m for m in _HEAVY if m in sys.modules}
    spec = importlib.util.spec_from_file_location("v2s6_decision_bench", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["v2s6_decision_bench"] = module
    spec.loader.exec_module(module)
    assert {m for m in _HEAVY if m in sys.modules} == before  # standard library only
    yield module
    sys.modules.pop("v2s6_decision_bench", None)


# -- prompts and tasks -----------------------------------------------------


def test_twenty_consistent_prompts_with_both_tasks(bench):
    assert bench.check_prompts() == []
    assert len(bench.PROMPTS) == 20
    costs = [p.cost for p in bench.PROMPTS]
    assert costs.count("simple") == costs.count("complexe") == 10
    assert set(bench.TASKS) == {"cost", "specialty"}
    assert 3 <= len(bench.TASKS["specialty"]) <= 4


def test_prompts_come_from_the_v1_scenarios(bench):
    scenarios = yaml.safe_load((_ROOT / "content" / "scenarios.yaml").read_text("utf-8"))
    for p in bench.PROMPTS:
        prompts = scenarios["scenarios"][p.scenario]["prompts"]
        assert prompts[p.index] == p.text, f"{p.id} ne correspond plus à content/scenarios.yaml"


def test_check_prompts_reports_unknown_labels(bench, monkeypatch):
    bad = bench.Prompt("bare_llm", 0, "x", "moyen", "general")
    monkeypatch.setattr(bench, "PROMPTS", [*bench.PROMPTS, bad])
    problems = bench.check_prompts()
    assert any("étiquette cost inconnue 'moyen'" in p for p in problems)
    assert any("même source" in p for p in problems)


# -- candidates and commands -----------------------------------------------


def _doc_rows() -> list[str]:
    text = _CANDIDATES_DOC.read_text("utf-8")
    table = text.split("## Candidats", 1)[1]
    rows = [line for line in table.splitlines() if line.startswith("| ")]
    return [row.split("|")[1].strip() for row in rows[1:]]  # header skipped


def test_every_row_of_the_candidates_doc_has_a_candidate(bench):
    rows = _doc_rows()
    assert len(rows) == 7
    for cell in rows:
        assert any(cell.startswith(c.doc_name) for c in bench.CANDIDATES), cell


def test_commands_one_per_candidate(bench):
    cmd = bench.command_for(bench.candidate("deberta_xsmall"))
    assert cmd.startswith(
        "uv run --with onnxruntime --with tokenizers --with huggingface-hub python "
        "tools/bench/v2s6_decision_bench.py"
    )
    assert "measure deberta_xsmall --download --slm $SLM" in cmd
    assert '--out "$OUT\\deberta_xsmall.json"' in cmd
    judge = bench.command_for(bench.candidate("slm_judge"))
    assert judge.startswith("uv run python") and "--download" not in judge
    nvidia = bench.command_for(bench.candidate("nvidia"))
    assert "--with torch --with transformers --with safetensors" in nvidia
    assert "decision10 --checked-on" in bench.command_for(bench.candidate("decision10"))
    assert bench.command_for(bench.candidate("arch_router")).startswith("(aucune")
    for c in bench.CANDIDATES:
        assert bench.command_for(c)  # every candidate has its line


def test_generative_candidates_are_never_measured(bench):
    for cid in ("llama_guard", "qwen3guard"):
        c = bench.candidate(cid)
        assert c.backend is None and c.office == "écarté"
        assert "seul modèle génératif" in c.office_reason


def test_list_prints_every_candidate(bench, capsys):
    assert bench.main(["list"]) == 0
    out = capsys.readouterr().out
    for c in bench.CANDIDATES:
        assert c.id in out


def test_measure_refuses_unknown_and_office_candidates(bench, capsys):
    assert bench.main(["measure", "foo"]) == 2
    assert "Candidat inconnu : foo" in capsys.readouterr().out
    assert bench.main(["measure", "llama_guard"]) == 2
    assert bench.main(["measure", "decision10"]) == 2


# -- decoding --------------------------------------------------------------


def test_softmax_and_entailment_index(bench):
    probs = bench.softmax([1.0, 2.0, 3.0])
    assert abs(sum(probs) - 1) < 1e-9 and probs[2] > probs[1] > probs[0]
    assert bench.softmax([]) == []
    assert bench.entailment_index({"0": "entailment", "1": "not_entailment"}) == 0
    assert bench.entailment_index({"0": "contradiction", "1": "neutral", "2": "ENTAILMENT"}) == 2
    with pytest.raises(ValueError):
        bench.entailment_index({"0": "positive"})


def test_pick_nli_label_takes_the_highest_entailment_logit(bench):
    logits = [[0.1, 2.0], [3.0, -1.0], [2.5, 0.0]]
    assert bench.pick_nli_label(["a", "b", "c"], logits, 0) == "b"
    assert bench.pick_nli_label(["a", "b", "c"], logits, 1) == "a"


_NVIDIA_CFG = {
    "target_sizes": {
        "task_type": 12,
        "creativity_scope": 3,
        "reasoning": 2,
        "contextual_knowledge": 2,
        "number_of_few_shots": 6,
        "domain_knowledge": 4,
        "no_label_reason": 1,
        "constraint_ct": 2,
    },
    "task_type_map": {
        str(i): name
        for i, name in enumerate(
            [
                "Brainstorming",
                "Chatbot",
                "Classification",
                "Closed QA",
                "Code Generation",
                "Extraction",
                "Open QA",
                "Other",
                "Rewrite",
                "Summarization",
                "Text Generation",
                "Unknown",
            ]
        )
    },
    "weights_map": {
        "creativity_scope": [2, 1, 0],
        "reasoning": [0, 1],
        "contextual_knowledge": [0, 1],
        "number_of_few_shots": [0, 1, 2, 3, 4, 5],
        "domain_knowledge": [3, 1, 2, 0],
        "no_label_reason": [0],
        "constraint_ct": [1, 0],
    },
    "divisor_map": {
        "creativity_scope": 2,
        "reasoning": 1,
        "contextual_knowledge": 1,
        "number_of_few_shots": 1,
        "domain_knowledge": 3,
        "no_label_reason": 1,
        "constraint_ct": 1,
    },
}


def test_nvidia_scores_follow_the_card(bench):
    flat = [[0.0] * n for n in _NVIDIA_CFG["target_sizes"].values()]
    scores = bench.nvidia_scores(flat, _NVIDIA_CFG)
    assert scores["task_type"] == "Brainstorming"
    assert scores["creativity_scope"] == 0.5 and scores["number_of_few_shots"] == 2.5
    assert scores["complexity"] == 0.6  # 0.95 x 0.5 + 0.05 x 2.5
    assert bench.nvidia_label(scores, "cost") == "complexe"

    peaked = [
        [0.0] * 4 + [50.0] + [0.0] * 7,  # Code Generation
        [0.0, 0.0, 50.0],
        [50.0, 0.0],
        [50.0, 0.0],
        [50.0] + [0.0] * 5,
        [0.0, 0.0, 0.0, 50.0],
        [0.0],
        [0.0, 50.0],
    ]
    scores = bench.nvidia_scores(peaked, _NVIDIA_CFG)
    assert scores["task_type"] == "Code Generation"
    assert scores["number_of_few_shots"] == 0 and scores["complexity"] == 0
    assert bench.nvidia_label(scores, "cost") == "simple"
    assert bench.nvidia_label(scores, "specialty") == "Code Generation"


@pytest.mark.parametrize(
    "predictions",
    [
        [{"class_name": "b", "score": 0.9}, {"class_name": "a", "score": 0.1}],
        [{"label": "b", "score": 0.9}, {"label": "a", "score": 0.1}],
        [("b", 0.9), ("a", 0.1)],
        [["b", 0.9], ["a", 0.1]],
        [[{"class_name": "a", "score": 0.1}, {"class_name": "b", "score": 0.9}]],
        [[("a", 0.1), ("b", 0.9)]],
        {"a": 0.1, "b": 0.9},
    ],
)
def test_top_label_reads_every_classify_shape(bench, predictions):
    assert bench.top_label(predictions, {"a": "key_a", "b": "key_b"}) == "key_b"


def test_top_label_without_prediction(bench):
    assert bench.top_label([], {}) == "aucune"
    assert bench.top_label([[]], {}) == "aucune"  # a batch of one text, nothing predicted
    assert bench.top_label([("autre", 1.0)], {"a": "key_a"}) == "autre"


def test_judge_grammar_and_prompt(bench):
    assert bench.gbnf_choice(["simple", "complexe"]) == 'root ::= "simple" | "complexe"'
    messages = bench.judge_messages("Quelle heure est-il ?", "specialty")
    assert [m["role"] for m in messages] == ["system", "user"]
    for key, crit in bench.TASKS["specialty"].items():
        assert f"- {key} : {crit.text}" in messages[0]["content"]
    assert messages[1]["content"] == "Quelle heure est-il ?"


# -- latency and agreement -------------------------------------------------


class _Clock:
    def __init__(self, step: float) -> None:
        self.t, self.step = 0.0, step

    def __call__(self) -> float:
        self.t += self.step
        return self.t


def test_run_decisions_times_each_decision_after_a_warmup(bench):
    calls = []

    def decide(text, task):
        calls.append((text, task))
        return next(p for p in bench.PROMPTS if p.text == text).expected(task)

    warmup, rows = bench.run_decisions(decide, clock=_Clock(0.25))
    assert len(calls) == 42 and len(rows) == 40
    assert [task for _, task in calls[:2]] == ["cost", "specialty"]  # each task warmed
    assert warmup == 250.0 and {r["ms"] for r in rows} == {250.0}
    summary = bench.summarize_decisions(rows)
    assert summary["decisions"] == 40
    assert summary["latency_median_ms"] == summary["latency_max_ms"] == 250.0
    assert summary["agreement"] == {"cost": "20/20", "specialty": "20/20"}


def test_agreement_without_object_for_fixed_labels(bench):
    rows = [{"task": "specialty", "label": "Open QA", "expected": "general", "ms": 1.0}]
    assert bench.agreement(rows, "specialty", fixed=True).startswith("sans objet")
    assert bench.summarize_decisions(rows, ("specialty",))["agreement"]["specialty"].startswith(
        "sans objet"
    )
    # A programmable model that answers nothing usable scores 0, it is not "sans objet".
    assert bench.agreement([dict(rows[0], label="aucune")], "specialty") == "0/1"
    rows = [
        {"task": "cost", "label": "simple", "expected": "simple", "ms": 1.0},
        {"task": "cost", "label": "simple", "expected": "complexe", "ms": 3.0},
    ]
    assert bench.agreement(rows, "cost") == "1/2"
    assert bench.summarize_decisions(rows)["latency_median_ms"] == 2.0


# -- packages, revisions, Decision 1.0 -------------------------------------


def test_commit_sha_and_added_packages(bench):
    assert bench.is_commit_sha("52fed1c818636b7cb8c4e4e3ae73189efeb78081")
    assert not bench.is_commit_sha("main") and not bench.is_commit_sha("")
    rows = [{"name": "huggingface_hub"}, {"name": "onnxruntime"}]
    marked = bench.added_packages(rows, {"huggingface-hub", "numpy"})
    assert [r["added"] for r in marked] == [False, True]


def test_decision10_discarded_without_measurement(bench):
    v = bench.decision10_verdict("2026-10-02", "https://example.org/usage")
    assert v["status"] == "écarté sans mesure"
    assert "2026-10-02" in v["reason"] and "génératifs" in v["reason"]
    v = bench.decision10_verdict("2026-10-02", "src", onnx="https://example.org/onnx")
    assert v["status"] == "à surveiller" and v["found"] == {"ONNX": "https://example.org/onnx"}
    blank = bench.decision10_verdict("2026-10-02", "src", gguf="  ", cpu="")
    assert blank["status"] == "écarté sans mesure"
    with pytest.raises(ValueError):
        bench.decision10_verdict("02/10/2026", "src")
    with pytest.raises(ValueError):
        bench.decision10_verdict("2026-10-02", " ")


def test_decision10_command(bench, capsys, tmp_path):
    assert bench.main(["decision10", "--checked-on", "hier", "--source", "x"]) == 2
    assert "Relevé incomplet" in capsys.readouterr().out
    out = tmp_path / "res" / "decision10.json"
    args = ["decision10", "--checked-on", "2026-10-02", "--source", "s", "--out", str(out)]
    assert bench.main(args) == 0
    saved = json.loads(out.read_text("utf-8"))
    assert saved["verdict"]["status"] == "écarté sans mesure"
    assert "measured_at" in saved and "platform" in saved


# -- verdicts --------------------------------------------------------------

_SHA = "a" * 40


def _measured(**overrides) -> dict:
    report = {
        "status": "measured",
        "target_pc": True,
        "platform": "Windows-11",
        "windows_release": "11",
        "admin": False,
        "rss_peak_mb": 2900,
        "rss_with_slm_mb": 2500,
        "rss_added_mb": 380,
        "latency_median_ms": 120.0,
        "latency_max_ms": 400.0,
        "decisions": 40,
        "attempts": [],
        "revisions": {"MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33": _SHA},
        "versions": {"onnxruntime": "1.23.0", "tokenizers": "0.23.2", "huggingface-hub": "1.33.0"},
        "packages": [
            {"name": "onnxruntime", "license": "MIT", "class": "ok", "added": True},
            {"name": "numpy", "license": "BSD", "class": "ok", "added": False},
        ],
        "torch_loaded": False,
    }
    report.update(overrides)
    return report


def _status(bench, cid, **overrides):
    return bench.decision_verdict(bench.candidate(cid), _measured(**overrides))


def test_verdict_retained_when_every_criterion_passes(bench):
    v = _status(bench, "deberta_xsmall")
    assert v["status"] == "retenu" and v["target_pc"] is True
    assert [c["id"] for c in v["criteria"]] == [
        "cpu_windows",
        "ram",
        "latency",
        "offline",
        "pinned",
        "license",
        "no_torch",
    ]
    assert all(c["ok"] for c in v["criteria"])


@pytest.mark.parametrize(
    "overrides",
    [
        {"rss_peak_mb": 4200},
        {"latency_median_ms": 1500.0},
        {"latency_max_ms": 3500.0},
        {"attempts": [["socket.getaddrinfo", "huggingface.co"]]},
        {"packages": [{"name": "x", "license": "AGPL-3.0", "class": "forbidden", "added": True}]},
    ],
)
def test_blocking_criteria_discard(bench, overrides):
    assert _status(bench, "deberta_xsmall", **overrides)["status"] == "écarté"


@pytest.mark.parametrize(
    "overrides",
    [
        {"torch_loaded": True, "heavy_modules_loaded": ["torch"]},
        {"revisions": {"MoritzLaurer/deberta-v3-xsmall-zeroshot-v1.1-all-33": "main"}},
        {"revisions": {}},
        {"versions": {"onnxruntime": None}},
        {"packages": [{"name": "y", "license": "LGPL-3.0", "class": "unknown", "added": True}]},
    ],
)
def test_soft_criteria_put_under_watch(bench, overrides):
    assert _status(bench, "deberta_xsmall", **overrides)["status"] == "à surveiller"


@pytest.mark.parametrize("overrides", [{"admin": True}, {"admin": None}, {"windows_release": "10"}])
def test_admin_session_or_other_windows_is_indicative(bench, overrides):
    v = _status(bench, "deberta_xsmall", **overrides)
    assert v["status"] == "retenu (indicatif : Windows 11 sans droits admin non vérifié)"
    assert v["criteria"][0]["ok"] is None


def test_unreadable_peak_is_not_a_discard(bench):
    v = _status(bench, "deberta_xsmall", rss_peak_mb=None)
    ram = next(c for c in v["criteria"] if c["id"] == "ram")
    assert ram["ok"] is None and v["status"] == "retenu"


def test_ram_detail_gives_the_margin_with_the_v1_rag(bench):
    v = _status(bench, "deberta_xsmall", v1_rag_rss_mb=1170)
    ram = next(c for c in v["criteria"] if c["id"] == "ram")
    assert "avec l'embedding et le reranker V1 (1170 Mo mesurés), 4070 Mo" in ram["detail"]


def test_network_blocked_while_loading_discards(bench):
    c = bench.candidate("gliformer")
    report = {"status": "erreur", "error": "boom", "blocked": "huggingface.co", "target_pc": True}
    v = bench.decision_verdict(c, report)
    assert v["status"] == "écarté" and "huggingface.co" in v["reason"]
    report = {"status": "erreur", "error": "boom", "attempts": [["socket.connect", "8.8.8.8"]]}
    v = bench.decision_verdict(c, report)
    assert v["status"] == "écarté (indicatif, hors PC cible)" and "8.8.8.8" in v["reason"]


def test_an_undeclared_model_licence_is_under_watch(bench):
    v = _status(bench, "gliformer_onnx")
    assert v["status"] == "à surveiller"
    licence = next(c for c in v["criteria"] if c["id"] == "license")
    assert licence["ok"] is False and "non déclarée" in licence["detail"]


def test_dev_container_measure_is_marked_indicative(bench):
    v = _status(bench, "deberta_xsmall", target_pc=False, platform="Linux-6")
    assert v["status"] == "retenu (indicatif, hors PC cible)"
    cpu = v["criteria"][0]
    assert cpu["ok"] is None and "hors PC cible" in cpu["detail"]


def test_slm_judge_is_the_fallback_reference(bench):
    v = _status(bench, "slm_judge", latency_median_ms=2500.0, latency_max_ms=9000.0, revisions={})
    assert v["status"] == "repli (référence)"
    bad = _status(bench, "slm_judge", attempts=[["socket.connect", "1.2.3.4"]], revisions={})
    assert bad["status"] == "à revoir"
    heavy = _status(bench, "slm_judge", rss_peak_mb=4300, revisions={})
    assert heavy["status"] == "à revoir" and "RAM" in heavy["reason"]


def test_not_measured_and_office_verdicts(bench):
    c = bench.candidate("deberta_base")
    v = bench.decision_verdict(c, {"status": "absent : x", "target_pc": True})
    assert v["status"] == "non mesuré" and v["criteria"] == []
    v = bench.decision_verdict(c, {"status": "erreur", "error": "boom"})
    assert v["reason"] == "erreur : boom"
    v = bench.decision_verdict(bench.candidate("arch_router"), {})
    assert v["status"] == "écarté" and "NFR-10" in v["reason"]


# -- SLM and measurement flow ----------------------------------------------


def test_resolve_slm(bench, tmp_path):
    path, error = bench.resolve_slm(str(tmp_path / "absent.gguf"), tmp_path)
    assert path is None and "introuvable" in error
    path, error = bench.resolve_slm(None, tmp_path)
    assert path is None and "Aucun GGUF" in error
    (tmp_path / "granite-embedding.gguf").write_bytes(b"x")
    (tmp_path / "Qwen3.5-2B-Q4_K_M.gguf").write_bytes(b"x")
    path, error = bench.resolve_slm(None, tmp_path)
    assert error is None and path.name == "Qwen3.5-2B-Q4_K_M.gguf"
    (tmp_path / "Qwen3.5-0.8B-Q8_0.gguf").write_bytes(b"x")
    path, error = bench.resolve_slm(None, tmp_path)
    assert path is None and "Plusieurs GGUF" in error and "0.8B" in error
    path, error = bench.resolve_slm(str(tmp_path / "Qwen3.5-0.8B-Q8_0.gguf"), tmp_path)
    assert error is None and path.name == "Qwen3.5-0.8B-Q8_0.gguf"


def test_measure_command_without_package_or_slm(bench, capsys, monkeypatch, tmp_path):
    if importlib.util.find_spec("onnxruntime") is None:  # the project never installs it
        assert bench.main(["measure", "deberta_xsmall"]) == 0
        out = capsys.readouterr().out
        assert "non mesuré (absent : onnxruntime" in out and "NON MESURÉ" in out
    monkeypatch.setattr(bench, "missing_modules", lambda c, find_spec=None: [])
    monkeypatch.setattr(bench, "_slm_search_dir", lambda: tmp_path)
    assert bench.main(["measure", "slm_judge"]) == 2
    assert "Aucun GGUF de SLM" in capsys.readouterr().out


def _machine():
    return {
        "platform": "Windows-11",
        "target_pc": True,
        "windows_release": "11",
        "admin": False,
        "measured_at": "2026-10-02T09:00",
    }


def _fake_snapshot(bench, models_dir, cand, skip=()):
    for repo, files in cand.repos:
        snap = bench.hf_cache(models_dir) / f"models--{repo.replace('/', '--')}" / "snapshots"
        for name in files:
            if name not in skip:
                (snap / _SHA / name).parent.mkdir(parents=True, exist_ok=True)
                (snap / _SHA / name).write_bytes(b"x")


def test_partial_snapshot_is_absent_with_the_download_errors(bench, tmp_path):
    c = bench.candidate("deberta_xsmall")
    _fake_snapshot(bench, tmp_path, c, skip=("onnx/model_quantized.onnx",))
    assert not bench.snapshot_present(tmp_path, *c.repos[0])

    def downloader(cand, models_dir):
        return {"hosts": ["huggingface.co"], "errors": {cand.repos[0][0]: "Timeout"}}

    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        download=True,
        runner=_fail,
        downloader=downloader,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
    )
    assert report["status"].startswith("absent ou incomplet")
    assert "Timeout" in report["status"]
    _fake_snapshot(bench, tmp_path, c)
    assert bench.snapshot_present(tmp_path, *c.repos[0])


def test_a_failing_downloader_is_reported(bench, tmp_path):
    def downloader(cand, models_dir):
        raise ImportError("huggingface_hub")

    report = bench.run_measure(
        bench.candidate("deberta_xsmall"),
        tmp_path,
        tmp_path / "slm.gguf",
        download=True,
        runner=_fail,
        downloader=downloader,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
    )
    assert "huggingface_hub" in report["download"]["errors"]["*"]
    assert report["verdict"]["status"] == "non mesuré"


class _FakeLlama:
    def __init__(self, model_path, n_ctx, verbose):
        self.n_ctx = n_ctx

    def create_completion(self, prompt, max_tokens):
        return {"choices": [{"text": "."}]}


def test_measure_child_report_feeds_the_verdict_and_the_printout(
    bench, monkeypatch, tmp_path, capsys
):
    """The glue between the child's report, `decision_verdict` and `print_measure`."""
    import types

    c = bench.candidate("deberta_xsmall")
    _fake_snapshot(bench, tmp_path, c)
    fake_llama = types.SimpleNamespace(Llama=_FakeLlama, __version__="0.3.35")
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama)
    monkeypatch.setattr(bench.s12, "_record_and_guard", lambda **kw: ([], "garde factice"))
    monkeypatch.setattr(bench.s12, "_rss_mb", lambda: 2500)
    monkeypatch.setattr(
        bench.s12,
        "_baseline_rss",
        lambda: {"rss_before_load_mb": 2500, "peak_before_load_mb": 2510},
    )
    monkeypatch.setattr(
        bench.s12, "_loaded_rss", lambda: {"rss_loaded_mb": 2800, "rss_peak_mb": 2900}
    )
    monkeypatch.setattr(bench, "_versions", lambda roots: {r: "1.0" for r in roots})

    def loader(cand, models_dir, slm_llm):
        assert slm_llm.n_ctx == 4096  # WaveStack's default window
        expected = {p.text: p for p in bench.PROMPTS}
        return (lambda text, task: expected[text].expected(task)), {
            "revisions": {cand.repos[0][0]: _SHA}
        }

    monkeypatch.setitem(bench.LOADERS, "nli_onnx", loader)
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=lambda cand, d, s: bench._measure_child(cand.id, d, s),
        downloader=_fail,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
    )
    assert report["status"] == "measured"
    assert report["rss_peak_mb"] == 2900 and report["rss_added_mb"] == 390
    assert report["agreement"] == {"cost": "20/20", "specialty": "20/20"}
    assert report["llama_cpp_version"] == "0.3.35" and report["v1_rag_rss_mb"] == 1170
    assert report["verdict"]["status"] == "retenu"
    bench.print_measure(report)
    out = capsys.readouterr().out
    assert "== Verdict : RETENU" in out and "coût 20/20" in out


def test_child_command_line_matches_its_parser(bench, monkeypatch, tmp_path, capsys):
    seen = {}
    monkeypatch.setattr(bench.s12, "_run_child", lambda cmd, env, timeout: seen.update(cmd=cmd))
    bench._default_runner(bench.candidate("slm_judge"), tmp_path, tmp_path / "slm.gguf")
    assert seen["cmd"][2] == "_measure-child"
    monkeypatch.setattr(bench, "_measure_child", lambda cid, d, s: {"id": cid, "slm": s.name})
    assert bench.main(seen["cmd"][2:]) == 0
    assert json.loads(capsys.readouterr().out) == {"id": "slm_judge", "slm": "slm.gguf"}


def test_write_out_survives_a_bad_path(bench, tmp_path, capsys):
    blocker = tmp_path / "fichier"
    blocker.write_text("x")
    bench._write_out(str(blocker / "sous" / "r.json"), {"a": 1})
    assert "écriture impossible" in capsys.readouterr().err
    bench._write_out(str(tmp_path / "ok" / "r.json"), {"a": 1})
    assert json.loads((tmp_path / "ok" / "r.json").read_text("utf-8")) == {"a": 1}


def test_settings_from_wavestack_toml(bench):
    settings = bench.wavestack_settings()
    assert bench.v1_rag_rss_mb(settings) == 1170  # story 12 on the target PC: 430 + 740
    assert bench.slm_n_ctx(settings) == 4096
    assert bench.v1_rag_rss_mb({}) is None and bench.slm_n_ctx({}) == bench.SLM_N_CTX


def _no_packages(roots):
    return []


def _fail(*args):
    raise AssertionError("ne doit pas être appelé")


def test_run_measure_without_measurement_package(bench, tmp_path):
    c = bench.candidate("deberta_xsmall")
    report = bench.run_measure(
        c,
        tmp_path,
        None,
        runner=_fail,
        downloader=_fail,
        find_spec=lambda name: None,
        packages=_no_packages,
        machine=_machine,
    )
    assert report["status"].startswith("non mesuré (absent : onnxruntime")
    assert "uv run --with onnxruntime" in report["status"]
    assert report["verdict"]["status"] == "non mesuré"


def test_run_measure_absent_model_then_download(bench, tmp_path):
    c = bench.candidate("deberta_xsmall")
    slm = tmp_path / "slm.gguf"
    common = dict(find_spec=lambda name: object(), packages=_no_packages, machine=_machine)
    report = bench.run_measure(c, tmp_path, slm, runner=_fail, downloader=_fail, **common)
    assert report["status"].startswith("absent ou incomplet : MoritzLaurer/")
    assert "--download" in report["status"]

    def downloader(cand, models_dir):
        _fake_snapshot(bench, models_dir, cand)
        return {"hosts": ["huggingface.co"], "errors": {}, "revisions": {}}

    def runner(cand, models_dir, slm_path):
        assert slm_path == slm
        return {k: v for k, v in _measured().items() if k not in ("status", "packages")}

    report = bench.run_measure(
        c, tmp_path, slm, download=True, runner=runner, downloader=downloader, **common
    )
    assert report["download"]["hosts"] == ["huggingface.co"]
    assert report["status"] == "measured"
    assert report["verdict"]["status"] == "retenu"
    assert report["command"] == bench.command_for(c)


def test_run_measure_child_failure(bench, tmp_path):
    c = bench.candidate("slm_judge")
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=lambda *a: {"error": "RuntimeError('chargement')", "blocked": None},
        downloader=_fail,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
    )
    assert report["status"] == "erreur" and "chargement" in report["error"]
    assert report["verdict"]["status"] == "non mesuré"


def test_shares_the_story12_helpers(bench):
    assert bench.s12.added_rss_mb(100, 120, 600) == 480
    assert re.search(r"story12_bench\.py$", bench.s12.__file__)
