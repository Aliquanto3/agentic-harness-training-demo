"""Pure logic of the V2 story 6 bench (`tools/bench/v2s6_decision_bench.py`).

Nothing here imports onnxruntime, torch, gliformer or llama-cpp, downloads a model or
leaves the machine: the heavy paths are replaced by injected fakes.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
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
    assert len(rows) == 15
    for cell in rows:
        assert any(
            cell.startswith(c.doc_name) or cell.startswith(f"`{c.id}`") for c in bench.CANDIDATES
        ), cell


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


def test_commands_of_the_story7_candidates(bench):
    for cid in ("mdeberta", "minilm_multi"):
        c = bench.candidate(cid)
        assert c.backend == "nli_onnx" and c.tier == "2" and c.model_license == "MIT"
        assert bench.command_for(c) == (
            "uv run --with onnxruntime --with tokenizers --with huggingface-hub python "
            f'tools/bench/v2s6_decision_bench.py measure {cid} --download --slm $SLM --out "$OUT'
            f'\\{cid}.json"'
        )
    assert bench.candidate("mdeberta").onnx_file == "onnx/model_quantized.onnx"
    assert bench.candidate("minilm_multi").onnx_file == "onnx/model.onnx"
    d20 = bench.candidate("decision20")
    assert bench.command_for(d20) == (
        "uv run --with torch --with transformers --with safetensors --with huggingface-hub "
        "python tools/bench/v2s6_decision_bench.py measure decision20 --download --slm $SLM --out "
        '"$OUT\\decision20.json"'
    )
    assert d20.revision == "881bee413681d80ebeac86afcda8b4138dae516e"
    assert d20.full_snapshot and d20.trust_remote_code and d20.model_license == "Apache-2.0"
    assert set(d20.repos[0][1]) == {
        "MODEL_MANIFEST.json",
        "config.json",
        "modeling_decision2.py",
        "decision_head.safetensors",
        "backbone/model.safetensors",
    }


def test_list_shows_the_reviewed_commit_of_decision20(bench, capsys):
    assert bench.main(["list"]) == 0
    out = capsys.readouterr().out
    block = out.split("-- decision20", 1)[1].split("\n-- ", 1)[0]
    assert f"commit relu (téléchargement et mesure épinglés) : {bench.DECISION20_REVISION}" in block
    assert "measure decision20 --download" in block
    for cid in ("mdeberta", "minilm_multi"):
        assert f"measure {cid} --download" in out


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


class _Enc:
    def __init__(self, n: int) -> None:
        self.ids, self.attention_mask, self.type_ids = [n, n], [1, 1], [0, 1]


def test_onnx_feeds_keep_the_inputs_the_session_declares(bench):
    encs = [_Enc(1), _Enc(2)]
    deberta = bench.onnx_feeds(encs, {"input_ids", "attention_mask", "token_type_ids"})
    assert deberta == {
        "input_ids": [[1, 1], [2, 2]],
        "attention_mask": [[1, 1], [1, 1]],
        "token_type_ids": [[0, 1], [0, 1]],
    }
    # The quantized mDeBERTa ONNX and MiniLM (XLM-R) take no token_type_ids.
    xlmr = bench.onnx_feeds(encs, ["input_ids", "attention_mask"])
    assert set(xlmr) == {"input_ids", "attention_mask"}


def test_decision20_questions_carry_the_written_criteria(bench):
    for task, labels in bench.TASKS.items():
        questions = bench.decision20_questions(task)
        assert list(questions) == [task]
        q = questions[task]
        assert q["type"] == "choice"
        assert q["instructions"] == "Classe la demande de l'utilisateur selon les critères."
        assert q["criteria"] == {key: crit.text for key, crit in labels.items()}


@pytest.mark.parametrize(
    ("answer", "label"),
    [
        ({"choice": "securite"}, "securite"),
        ({"choice": "simple", "confidence": 0.9}, "simple"),
        ({"error": "max_length_exceeded"}, "erreur : max_length_exceeded"),
        ({"error": "invalid_question"}, "erreur : invalid_question"),
        ({"error": "invalid_model_output"}, "erreur : invalid_model_output"),
        ({}, "erreur : sans choix"),
        (None, "erreur : réponse inattendue NoneType"),
    ],
)
def test_decision20_label(bench, answer, label):
    assert bench.decision20_label(answer) == label


def test_snapshot_kwargs_pin_the_reviewed_commit(bench):
    files = ("config.json",)
    assert bench.snapshot_kwargs(bench.candidate("mdeberta"), files) == {
        "allow_patterns": ["config.json"]
    }
    assert bench.snapshot_kwargs(bench.candidate("decision20"), files) == {
        "revision": bench.DECISION20_REVISION
    }  # the whole repository: `verify_bundle` wants every file of MODEL_MANIFEST.json


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
    assert ram["ok"] is None and v["status"] == "à surveiller"  # nor a pass
    assert "(non vérifiable)" in v["reason"]


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


def _d20_measured(**overrides) -> dict:
    d20 = {
        "revisions": {"vllm-sr/Decision-2.0-Kai-0.6B": "881bee413681d80ebeac86afcda8b4138dae516e"},
        "versions": {
            "torch": "2.14.1",
            "transformers": "5.18.0",
            "safetensors": "0.8.0",
            "huggingface-hub": "1.33.0",
        },
    }
    return dict(d20, **overrides)


def test_decision20_is_at_best_under_watch_even_without_torch(bench):
    v = _status(bench, "decision20", **_d20_measured())  # torch_loaded False in the fake
    assert v["status"] == "à surveiller"
    pinned = next(c for c in v["criteria"] if c["id"] == "pinned")
    assert pinned["ok"] is False and "trust_remote_code" in pinned["detail"]
    assert bench.DECISION20_REVISION in pinned["detail"]
    assert [c["id"] for c in v["criteria"] if c["ok"] is False] == ["pinned"]
    heavy = _status(bench, "decision20", torch_loaded=True, **_d20_measured())
    assert heavy["status"] == "à surveiller"
    assert _status(bench, "decision20", rss_peak_mb=4500, **_d20_measured())["status"] == ("écarté")


def test_ram_ceiling_discards_without_latency(bench):
    report = {
        "status": "erreur",
        "error": "ram_ceiling",
        "rss_at_stop_mb": 4321,
        "attempts": [],
        "target_pc": True,
    }
    v = bench.decision_verdict(bench.candidate("decision20"), report)
    assert v["status"] == "écarté (RAM)" and "4321 Mo" in v["reason"]
    assert v["criteria"] == []
    v = bench.decision_verdict(bench.candidate("mdeberta"), dict(report, target_pc=False))
    assert v["status"] == "écarté (RAM) (indicatif, hors PC cible)"


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


def _fake_snapshot(bench, models_dir, cand, skip=(), sha=_SHA):
    for repo, files in cand.repos:
        snap = bench.hf_cache(models_dir) / f"models--{repo.replace('/', '--')}" / "snapshots"
        for name in files:
            if name not in skip:
                (snap / sha / name).parent.mkdir(parents=True, exist_ok=True)
                (snap / sha / name).write_bytes(b"x")


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


_FAIL_CALLS: list = []


def _fail(*args, **kwargs):
    _FAIL_CALLS.append(args)  # the bench catches exceptions: the call itself is recorded
    raise AssertionError("ne doit pas être appelé")


@pytest.fixture(autouse=True)
def _fail_never_called():
    """`_fail` (a runner, downloader, `run` or `popen` that must not run) was not called,
    even when `run_measure` caught its exception into the report."""
    _FAIL_CALLS.clear()
    yield
    assert _FAIL_CALLS == [], "_fail appelé (exception rattrapée par le banc)"


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


# -- story 7: pinned commit, Decision 2.0, child environment, memory watchdog --


def test_pinned_snapshot_only_counts_at_the_reviewed_commit(bench, tmp_path):
    c = bench.candidate("decision20")
    repo, files = c.repos[0]
    _fake_snapshot(bench, tmp_path, c)  # another commit, complete
    assert bench.snapshot_present(tmp_path, repo, files)  # any commit, as for `main`
    assert not bench.snapshot_present(tmp_path, repo, files, c.revision)
    assert bench.other_snapshots(tmp_path, repo, c.revision) == [_SHA]
    _fake_snapshot(bench, tmp_path, c, sha=c.revision)
    assert bench.snapshot_present(tmp_path, repo, files, c.revision)
    assert bench.other_snapshots(tmp_path, repo, c.revision) == [_SHA]
    assert bench.other_snapshots(tmp_path, repo, "") == []
    assert bench.other_snapshots(tmp_path / "vide", repo, c.revision) == []


def test_unreviewed_commit_is_never_measured(bench, tmp_path):
    c = bench.candidate("decision20")
    _fake_snapshot(bench, tmp_path, c)  # only a commit nobody reviewed
    common = dict(find_spec=lambda name: object(), packages=_no_packages, machine=_machine)
    report = bench.run_measure(c, tmp_path, tmp_path / "slm.gguf", runner=_fail, **common)
    assert report["status"] == (
        f"non mesuré : code non relu à ce commit ({_SHA}) ; relu : {c.revision}"
    )
    assert report["verdict"]["status"] == "non mesuré"
    assert "code non relu à ce commit" in report["verdict"]["reason"]

    def runner(cand, models_dir, slm_path):
        return {k: v for k, v in _measured(**_d20_measured()).items() if k != "status"}

    _fake_snapshot(bench, tmp_path, c, sha=c.revision)  # the reviewed commit: measured
    report = bench.run_measure(c, tmp_path, tmp_path / "slm.gguf", runner=runner, **common)
    assert report["status"] == "measured"
    assert report["verdict"]["status"] == "à surveiller"


def test_missing_measure_package_names_the_command(bench, tmp_path):
    c = bench.candidate("decision20")
    report = bench.run_measure(
        c,
        tmp_path,
        None,
        runner=_fail,
        downloader=_fail,
        find_spec=lambda name: None if name == "torch" else object(),
        packages=_no_packages,
        machine=_machine,
    )
    assert report["status"].startswith("non mesuré (absent : torch ; commande : uv run --with")


class _FakeDecision2:
    def __init__(self) -> None:
        self.calls = []

    def system_one(self, state, questions):
        self.calls.append((state, questions))
        ((qid, q),) = questions.items()
        if state == "trop long":
            return {"error": "max_length_exceeded"}
        return {"answers": {qid: {"choice": next(iter(q["criteria"]))}}}


def test_load_decision20_through_a_fake_transformers(bench, monkeypatch, tmp_path):
    import types

    c = bench.candidate("decision20")
    model = _FakeDecision2()
    seen = {}

    def from_pretrained(path, **kwargs):
        seen.update(path=path, **kwargs)
        return model

    fake = types.SimpleNamespace(AutoModel=types.SimpleNamespace(from_pretrained=from_pretrained))
    monkeypatch.setitem(sys.modules, "transformers", fake)
    pinned = tmp_path / "snapshots" / c.revision
    monkeypatch.setattr(bench, "_snapshot", lambda models_dir, repo, files, cand: pinned)
    decide, info = bench._load_decision20(c, tmp_path, None)
    assert seen == {"path": str(pinned), "trust_remote_code": True, "device": "cpu"}
    assert info["revisions"] == {c.repos[0][0]: c.revision}
    assert info["reviewed_revision"] == c.revision and info["trust_remote_code"] is True
    assert decide("Quelle heure est-il ?", "cost") == "simple"
    assert decide("Quelle heure est-il ?", "specialty") == "securite"
    assert model.calls[0][1] == bench.decision20_questions("cost")
    assert decide("trop long", "cost") == "erreur : max_length_exceeded"

    other = tmp_path / "snapshots" / _SHA
    monkeypatch.setattr(bench, "_snapshot", lambda models_dir, repo, files, cand: other)
    with pytest.raises(RuntimeError, match="commit relu"):
        bench._load_decision20(c, tmp_path, None)


def test_child_environment(bench, monkeypatch, tmp_path):
    base = {
        "PATH": "x",
        "HTTPS_PROXY": "http://127.0.0.1:9000",
        "DECISION2_FAST": "1",
        "DECISION2_KERNELS": "1",
        "DECISION2_GRAPHS": "1",
    }
    env = bench.child_env(base, tmp_path)
    assert env["HF_MODULES_CACHE"] == str(tmp_path / "hf_modules")
    assert env["HF_HUB_OFFLINE"] == "1" and env["PATH"] == "x"
    assert not [n for n in env if n.startswith("DECISION2_") or "PROXY" in n.upper()]
    assert "DECISION2_FAST" in base  # the parent's environment is untouched

    seen = {}
    monkeypatch.setattr(bench.s12, "_run_child", lambda cmd, env, timeout: seen.update(env=env))
    monkeypatch.setenv("DECISION2_FAST", "1")
    bench._default_runner(bench.candidate("decision20"), tmp_path, tmp_path / "slm.gguf")
    assert seen["env"]["HF_MODULES_CACHE"] == str(tmp_path / "hf_modules")
    assert "DECISION2_FAST" not in seen["env"]


def test_ram_watchdog_stops_the_child_beyond_the_budget(bench):
    lines, exits = [], []
    values = iter([1000, 3000, 5000])
    thread, stop, state = bench.start_ram_watchdog(
        [["socket.connect", "1.2.3.4"]],
        budget_mb=4096,
        period_s=0.001,
        read_rss=lambda: next(values),
        emit=lines.append,
        exit_=exits.append,
    )
    thread.join(timeout=5)
    assert not thread.is_alive() and exits == [0]
    assert state == {"status": "active", "budget_mb": 4096, "period_s": 0.001}
    report = json.loads(lines[0])
    assert report == {
        "error": "ram_ceiling",
        "rss_at_stop_mb": 5000,
        "ram_budget_mb": 4096,
        "attempts": [["socket.connect", "1.2.3.4"]],
    }


# The fake exit returns, so the write error then ends the thread (os._exit never returns).
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_ram_watchdog_stops_the_child_even_if_the_line_fails(bench):
    exits = []

    def broken_emit(line):
        raise OSError("stdout fermé")

    thread, _, _ = bench.start_ram_watchdog(
        [], budget_mb=10, period_s=0.001, read_rss=lambda: 11, emit=broken_emit, exit_=exits.append
    )
    thread.join(timeout=5)
    assert not thread.is_alive() and exits == [0]


def test_ram_watchdog_stays_quiet_within_the_budget_and_stops_on_demand(bench):
    import threading

    lines, exits, reads = [], [], []
    ready = threading.Event()
    box = {}

    def at_budget():
        ready.wait(5)  # `stop` is known once start_ram_watchdog has returned
        reads.append(1)
        if len(reads) >= 3:
            box["stop"].set()  # the measure ends after a few reads
        return 4096  # exactly the budget: not beyond it

    thread, box["stop"], state = bench.start_ram_watchdog(
        [],
        budget_mb=4096,
        period_s=0.001,
        read_rss=at_budget,
        emit=lines.append,
        exit_=exits.append,
    )
    ready.set()
    thread.join(timeout=5)
    assert not thread.is_alive() and len(reads) >= 1
    assert lines == [] and exits == [] and state["status"] == "active"

    def no_psutil():
        raise ImportError("psutil")

    thread, _, state = bench.start_ram_watchdog([], read_rss=no_psutil, exit_=exits.append)
    thread.join(timeout=5)
    assert not thread.is_alive() and exits == []
    assert state["status"] == "inactive" and "psutil" in state["reason"]
    assert state["budget_mb"] == bench.RAM_BUDGET_MB
    assert state["period_s"] == bench.RAM_WATCH_PERIOD_S


def test_ram_ceiling_line_flows_to_the_verdict(bench, tmp_path):
    c = bench.candidate("mdeberta")
    _fake_snapshot(bench, tmp_path, c)

    def runner(cand, models_dir, slm_path):  # what `_run_child` reads from the stopped child
        return json.loads(json.dumps(bench.ram_ceiling_report(4400, [])))

    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=runner,
        downloader=_fail,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
    )
    assert report["status"] == "erreur" and report["rss_at_stop_mb"] == 4400
    assert report["verdict"]["status"] == "écarté (RAM)"
    assert "4400 Mo" in report["verdict"]["reason"]


def test_measure_child_records_its_watchdog_then_stops_it(bench, monkeypatch, tmp_path):
    import threading

    state = {"status": "active", "budget_mb": 4096, "period_s": 0.5}
    started = []

    class _Stop(threading.Event):
        def set(self):  # the JSON must show the state from before the stop
            state["status"] = "arrêté"
            super().set()

    def fake_watchdog(attempts):
        stop = _Stop()
        started.append(stop)
        return None, stop, state

    monkeypatch.setattr(bench, "start_ram_watchdog", fake_watchdog)
    monkeypatch.setattr(bench.s12, "_record_and_guard", lambda **kw: ([], "garde factice"))
    monkeypatch.setattr(bench, "_measure", lambda *a: {"id": a[0]})
    out = bench._measure_child("mdeberta", tmp_path, tmp_path / "slm.gguf")
    assert out == {
        "id": "mdeberta",
        "ram_watchdog": {"status": "active", "budget_mb": 4096, "period_s": 0.5},
    }
    assert len(started) == 1 and started[0].is_set()


def test_failed_measure_keeps_the_slm_and_module_fields(bench, monkeypatch, tmp_path):
    import types

    c = bench.candidate("decision20")
    _fake_snapshot(bench, tmp_path, c, sha=c.revision)
    fake_llama = types.SimpleNamespace(Llama=_FakeLlama, __version__="0.3.35")
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama)
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace())  # loaded, then failure
    monkeypatch.setattr(bench.s12, "_record_and_guard", lambda **kw: ([], "garde factice"))
    monkeypatch.setattr(bench.s12, "_rss_mb", lambda: 1938)
    monkeypatch.setattr(bench.s12, "_blocked_host", lambda exc: None)
    monkeypatch.setattr(
        bench.s12,
        "_baseline_rss",
        lambda: {"rss_before_load_mb": 1938, "peak_before_load_mb": 1938},
    )

    def loader(cand, models_dir, slm_llm):
        raise ValueError("Model identity differs from the scored checkpoint")

    monkeypatch.setitem(bench.LOADERS, "decision20_torch", loader)
    child = bench._measure_child(c.id, tmp_path, tmp_path / "slm.gguf")
    assert "Model identity" in child["error"]
    assert child["torch_loaded"] is True and "torch" in child["heavy_modules_loaded"]
    assert child["llama_cpp_version"] == "0.3.35" and child["rss_with_slm_mb"] == 1938
    assert "slm_load_s" in child and child["ram_watchdog"]["status"] == "active"

    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=lambda cand, d, s: json.loads(json.dumps(child)),
        downloader=_fail,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
    )
    assert report["status"] == "erreur" and report["verdict"]["status"] == "non mesuré"
    for key in (
        "torch_loaded",
        "heavy_modules_loaded",
        "llama_cpp_version",
        "slm_load_s",
        "rss_with_slm_mb",
        "ram_watchdog",
    ):
        assert report[key] == child[key], key


def test_download_candidate_passes_the_pin(bench, monkeypatch, tmp_path):
    import types

    calls = []

    def snapshot_download(repo_id, cache_dir, **kwargs):
        calls.append((repo_id, kwargs))
        return str(tmp_path / "snapshots" / kwargs.get("revision", _SHA))

    fake_hub = types.SimpleNamespace(snapshot_download=snapshot_download)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    fake_truststore = types.SimpleNamespace(inject_into_ssl=lambda: None)
    monkeypatch.setitem(sys.modules, "truststore", fake_truststore)
    monkeypatch.setattr(bench.s12, "_record_and_guard", lambda **kw: ([], "garde factice"))
    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_TELEMETRY", raising=False)

    d20 = bench.download_candidate(bench.candidate("decision20"), tmp_path)
    repo, kwargs = calls[-1]
    assert repo == bench.DECISION20_REPO
    assert kwargs == {"revision": bench.DECISION20_REVISION}  # no allow_patterns: whole repo
    assert d20["revisions"] == {bench.DECISION20_REPO: bench.DECISION20_REVISION}

    bench.download_candidate(bench.candidate("mdeberta"), tmp_path)
    repo, kwargs = calls[-1]
    assert repo == "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
    assert kwargs == {
        "allow_patterns": ["config.json", "tokenizer.json", "onnx/model_quantized.onnx"]
    }


def test_shares_the_story12_helpers(bench):
    assert bench.s12.added_rss_mb(100, 120, 600) == 480
    assert re.search(r"story12_bench\.py$", bench.s12.__file__)


# -- story 8: tev1 0.8B served by Ollama on /v1/systemone --------------------------------------

_DIGEST = "8d11b3146b7f3f4f4d5e9a64665ab2bdaf8b46e4ec42a5880b60a716ae50e3fb"
_BLOB = "fa9732e3924db99f614181a7a28384a0891ae17f478db228a47c989462b2405a"
_MODELFILE = f"# generated\nFROM C:\\Users\\x\\.ollama\\models\\blobs\\sha256-{_BLOB}\nTEMPLATE x\n"
_LICENSE = (
    "\n   Apache License\n   Version 2.0, January 2004\n   Copyright 2026 Alibaba Cloud\n"
    "\n\nMIT License\n\nCopyright (c) 2026 open-jev contributors\n"
)


def test_tev1_candidate_and_command(bench):
    c = bench.candidate("tev1")
    assert c.backend == "ollama_systemone" and c.tier == "2" and c.generative
    assert c.server_url == "http://127.0.0.1:11434" and c.server_model == "tev1:0.8b"
    assert bench.license_class(c) == "unknown"  # weights licence not declared
    assert bench.command_for(c) == (
        'uv run python tools/bench/v2s6_decision_bench.py measure tev1 --slm $SLM --out "$OUT'
        '\\tev1.json"'
    )  # no `--with` (httpx, psutil are project dependencies), no implicit download
    assert c.roots == () and set(c.modules) == {"httpx", "psutil"}


def test_list_shows_the_served_model(bench, capsys):
    assert bench.main(["list"]) == 0
    block = capsys.readouterr().out.split("-- tev1", 1)[1].split("\n-- ", 1)[0]
    assert "servi par Ollama sur http://127.0.0.1:11434/v1/systemone" in block
    assert "ollama pull tev1:0.8b" in block


def _systemone_transport(seen, probs=None, status=200, body=None):
    import httpx

    def handler(request):
        payload = json.loads(request.content)
        seen.append((request.method, request.url.path, request.url.host, payload))
        if body is not None:
            return httpx.Response(status, content=body)
        ((qid, q),) = payload["questions"].items()
        p = probs or {k: 1 / len(q["criteria"]) for k in q["criteria"]}
        first = next(iter(q["criteria"]))
        answer = {"type": "choice", "choice": first, "probabilities": p, "confidence": 0.1}
        return httpx.Response(status, json={"model": payload["model"], "answers": {qid: answer}})

    return httpx.MockTransport(handler)


def test_systemone_client_request_shape_and_label(bench):
    seen = []
    # `choice` says "simple", the probabilities say "complexe": the label follows them.
    transport = _systemone_transport(seen, probs={"simple": 0.4, "complexe": 0.6})
    client = bench.SystemOneClient("http://127.0.0.1:11434", "tev1:0.8b", transport)
    assert client.decide("Quelle heure est-il ?", "cost") == "complexe"
    method, path, host, payload = seen[0]
    assert (method, path, host) == ("POST", "/v1/systemone", "127.0.0.1")
    assert payload == {
        "model": "tev1:0.8b",
        "state": "Quelle heure est-il ?",
        "questions": {
            "cost": {
                "type": "choice",
                "instructions": bench.DECISION20_INSTRUCTIONS,
                "criteria": {k: crit.text for k, crit in bench.TASKS["cost"].items()},
            }
        },
    }
    assert client.body("x", {}, keep_alive=0)["keep_alive"] == 0
    client.close()
    # Reusable for story 9: base URL and model are parameters.
    other = bench.SystemOneClient("http://localhost:8080", "decision", _systemone_transport(seen))
    assert other.decide("x", "specialty") in bench.TASKS["specialty"]
    assert seen[-1][3]["model"] == "decision" and seen[-1][2] == "localhost"


@pytest.mark.parametrize("url", ["http://10.0.0.5:11434", "http://0.0.0.0:11434", "http://ollama"])
def test_systemone_client_stays_on_the_loopback(bench, url):
    with pytest.raises(ValueError, match="boucle locale"):
        bench.SystemOneClient(url, "tev1:0.8b")


_PROBS_KO = "erreur : forme inattendue (answers.cost.probabilities)"


@pytest.mark.parametrize(
    ("response", "label"),
    [
        ({"answers": {"cost": {"probabilities": {"simple": 0.7, "complexe": 0.3}}}}, "simple"),
        ({"answers": {"cost": {"probabilities": {"simple": 0.5, "complexe": 0.5}}}}, "simple"),
        ({"answers": {"cost": {"probabilities": {"complexe": 0.9}}}}, "complexe"),
        ({"error": "HTTP 404 : model not found"}, "erreur : HTTP 404 : model not found"),
        ({"answers": {"cost": {"error": "invalid"}}}, "erreur : invalid"),
        ({"answers": {}}, "erreur : forme inattendue (answers.cost absent)"),
        ({"answers": []}, "erreur : forme inattendue (answers.cost absent)"),
        ({"result": "simple"}, "erreur : forme inattendue (answers.cost absent)"),
        ({"answers": {"cost": {"choice": "simple"}}}, _PROBS_KO),
        ({"answers": {"cost": {"probabilities": {}}}}, _PROBS_KO),
        ({"answers": {"cost": {"probabilities": {"A": 0.9, "B": 0.1}}}}, _PROBS_KO),
        ({"answers": {"cost": {"probabilities": {"simple": True}}}}, _PROBS_KO),
        ("simple", "erreur : réponse inattendue str"),
    ],
)
def test_systemone_label(bench, response, label):
    assert bench.systemone_label(response, "cost", ["simple", "complexe"]) == label


def test_systemone_unknown_answers_become_error_rows(bench):
    seen = []
    bad = bench.SystemOneClient(
        "http://127.0.0.1:11434", "tev1:0.8b", _systemone_transport(seen, body=b"<html>")
    )
    assert bad.decide("x", "cost") == "erreur : réponse non JSON ou non objet"
    err = bench.SystemOneClient(
        "http://127.0.0.1:11434",
        "tev1:0.8b",
        _systemone_transport(seen, status=400, body=b'{"error":"questions must contain 1-64"}'),
    )
    assert err.decide("x", "cost") == "erreur : HTTP 400 : questions must contain 1-64"
    rows = [
        {"task": "cost", "label": "erreur : HTTP 400 : x", "expected": "simple", "ms": 1.0},
        {"task": "cost", "label": "simple", "expected": "simple", "ms": 2.0},
    ]
    summary = bench.summarize_decisions(rows)
    assert summary["error_rows"] == 1 and summary["agreement"]["cost"] == "1/2"


_LS = "C:\\Ollama\\lib\\ollama\\llama-server.exe"


@pytest.mark.parametrize(
    ("name", "cmdline", "role"),
    [
        ("ollama.exe", ["C:\\Ollama\\ollama.exe", "serve"], "server"),
        ("llama-server.exe", [_LS, "--model", f"C:\\b\\sha256-{_BLOB}"], "runner"),
        ("llama-server.exe", [_LS, "--model", "C:\\b\\sha256-other"], "other_runner"),
        ("ollama.exe", ["ollama.exe", "runner", "--model", "x"], "other_runner"),
        ("ollama.exe", ["ollama.exe", "runner", "--model", f"C:\\b\\sha256-{_BLOB}"], "runner"),
        ("ollama app.exe", ["C:\\Ollama\\ollama app.exe"], "app"),
        ("ollama.exe", ["ollama.exe", "ps"], "other"),
        ("llama-server.exe", ["D:\\llama.cpp\\llama-server.exe", "-m", "x.gguf"], None),
        ("python.exe", ["python", "serve"], None),
        ("python.exe", ["python", "-c", f"scan('{_BLOB}')"], None),  # quotes the blob only
        (None, None, None),
    ],
)
def test_ollama_role(bench, name, cmdline, role):
    assert bench.ollama_role(name, cmdline, _BLOB) == role


def test_endpoints_keep_the_non_loopback_remotes_and_the_listening_addresses(bench):
    ns = types.SimpleNamespace
    conns = [
        ns(laddr=("127.0.0.1", 11434), raddr=(), status="LISTEN"),
        ns(laddr=("127.0.0.1", 50000), raddr=("127.0.0.1", 11434), status="ESTABLISHED"),
        ns(laddr=("10.0.0.2", 50001), raddr=("34.1.2.3", 443), status="ESTABLISHED"),
        ns(laddr=("::1", 50002), raddr=("::1", 11434), status="ESTABLISHED"),
        ns(laddr=("0.0.0.0", 11434), raddr=None, status="LISTEN"),
    ]
    assert bench.remote_endpoints(conns) == ["34.1.2.3:443"]
    assert bench.listening_endpoints(conns) == ["0.0.0.0:11434", "127.0.0.1:11434"]
    assert bench.remote_endpoints([]) == [] and bench.remote_endpoints(None) == []


def test_ollama_model_record(bench):
    assert bench.blob_sha_from_modelfile(_MODELFILE) == _BLOB
    assert bench.blob_sha_from_modelfile("FROM tev1:0.8b") == ""
    show = {"modelfile": _MODELFILE, "license": _LICENSE, "capabilities": ["decision"]}
    tags = {
        "models": [
            {"name": "qwen3.5:2b", "digest": "b" * 64},
            {"name": "tev1:0.8b", "digest": _DIGEST},
        ]
    }
    rec = bench.ollama_model_record("tev1:0.8b", show, tags)
    assert rec["digest"] == _DIGEST and rec["blob_sha256"] == _BLOB
    assert rec["capabilities"] == ["decision"]
    assert rec["license_markers"] == [
        "Apache License",
        "Version 2.0, January 2004",
        "Copyright 2026 Alibaba Cloud",
        "MIT License",
        "Copyright (c) 2026 open-jev contributors",
    ]
    assert bench.is_sha256(rec["license_sha256"])
    assert bench.ollama_model_record("absent", {}, {})["digest"] is None


def _proc(role, pid, rss, remotes=(), peak=None, listen=()):
    return {
        "pid": pid,
        "role": role,
        "rss_mb": rss,
        "peak_mb": peak,
        "remotes": list(remotes),
        "listen": list(listen),
    }


def test_ollama_watch_sums_the_server_and_the_model_process(bench):
    scans = iter(
        [
            [
                _proc("server", 1, 40, listen=["127.0.0.1:11434"]),
                _proc("app", 3, 30, ["1.1.1.1:443"]),
            ],
            [_proc("server", 1, 55), _proc("runner", 2, 900, peak=950)],
            [_proc("server", 1, 50), _proc("runner", 2, 920, peak=980)],
        ]
    )
    asked = []

    def scan(pids=None):
        asked.append(pids)
        return next(scans)

    watch = bench.OllamaWatch(_BLOB, scan=scan, period_s=60)
    watch.take("before")
    watch.take("during")
    watch.take("after")
    report = watch.report()
    assert report["ollama_rss_peak_mb"] == 55 + 980  # sum of the peaks, wset included
    parts = report["ollama_rss"]
    assert parts["server_peak_mb"] == 55 and parts["runner_peak_mb"] == 980
    assert parts["peak_of_sum_mb"] == 970 and parts["runner_peak_wset_mb"] == 980
    assert parts["runner_series_mb"] == [900, 920]  # the last point kept, never twice
    assert report["ollama_ceiling"] is None and parts["abort_threshold_mb"] == 6144
    assert report["ollama_processes"] == {"server": [1], "app": [3], "runner": [2]}
    net = report["ollama_network"]
    assert net["before"] == net["during"] == net["after"] == []
    assert net["other_processes"] == ["app : 1.1.1.1:443"]  # recorded, outside the criterion
    assert net["listen"] == ["127.0.0.1:11434"] and net["samples"] == 3
    # Full listings until the model process is known (and before, after); then its PIDs.
    assert asked == [None, None, None]
    watch.pids = {"server": {1}, "runner": {2}}
    watch._ticks = 1
    watch._scan = lambda pids=None: asked.append(pids) or []
    watch.take("during")
    assert asked[-1] == [1, 2] and watch.full_scans == 3
    # Every OLLAMA_FULL_SCAN_EVERY samples, a full listing again (a new PID would be seen).
    watch._ticks = bench.OLLAMA_FULL_SCAN_EVERY
    watch.take("during")
    assert asked[-1] is None and watch.full_scans == 4


def test_ollama_watch_thread_and_failures(bench):
    import threading

    calls = []
    third = threading.Event()

    def scan(pids=None):
        calls.append(1)
        if len(calls) >= 3:
            third.set()
        if len(calls) == 2:
            raise RuntimeError("AccessDenied")
        return [_proc("server", 1, 40, ["8.8.8.8:443"])]

    watch = bench.OllamaWatch(_BLOB, scan=scan, period_s=0.001).start()
    assert third.wait(5)
    report = watch.finish()
    assert not watch._thread.is_alive()
    assert report["ollama_rss_peak_mb"] is None  # no model process found
    net = report["ollama_network"]
    assert net["before"] == ["8.8.8.8:443"] and net["after"] == ["8.8.8.8:443"]
    assert any("AccessDenied" in e for e in net["errors"])
    assert any("processus du modèle introuvable" in e for e in net["errors"])
    # `report` is idempotent: the "introuvable" line is not added again.
    assert watch.report()["ollama_network"]["errors"] == net["errors"]


def test_ollama_watch_series_downsampled_keeps_the_last_point(bench):
    watch = bench.OllamaWatch(_BLOB, scan=lambda pids=None: [], period_s=60)
    watch.runner_series = list(range(61))  # step 2: 0, 2, …, 60 already ends on the last
    assert watch.report()["ollama_rss"]["runner_series_mb"][-2:] == [58, 60]
    watch.runner_series = list(range(62))  # 0, 2, …, 60, then 61 appended once
    assert watch.report()["ollama_rss"]["runner_series_mb"][-3:] == [58, 60, 61]


def test_ollama_watch_sets_the_ceiling_beyond_the_abort_threshold(bench):
    scans = iter([[_proc("server", 1, 50), _proc("runner", 2, 500)]] * 2)
    watch = bench.OllamaWatch(_BLOB, scan=lambda pids=None: next(scans), abort_mb=1000)
    watch.take("before")
    assert watch.ceiling is None
    watch._scan = lambda pids=None: [_proc("server", 1, 50), _proc("runner", 2, 980)]
    watch.take("during")
    assert watch.ceiling == {"threshold_mb": 1000, "rss_at_stop_mb": 1030, "phase": "during"}
    watch._scan = lambda pids=None: [_proc("server", 1, 50), _proc("runner", 2, 1200)]
    watch.take("after")  # the first crossing is kept
    assert watch.report()["ollama_ceiling"] == {
        "threshold_mb": 1000,
        "rss_at_stop_mb": 1030,
        "phase": "during",
    }


def test_ollama_ceiling_discards_for_ram(bench):
    report = {
        "status": "erreur",
        "error": "RuntimeError('ollama_ceiling : …')",
        "ollama_ceiling": {"threshold_mb": 6144, "rss_at_stop_mb": 6200, "phase": "during"},
        "target_pc": True,
    }
    v = bench.decision_verdict(bench.candidate("tev1"), report)
    assert v["status"] == "écarté (RAM)" and "6200 Mo" in v["reason"] and "6144" in v["reason"]


class _FakeProc:
    def __init__(self, pid, mem=None, conns=(), denied=False):
        self.pid, self._mem, self._conns, self._denied = pid, mem, list(conns), denied

    def memory_info(self):
        import psutil

        if self._denied:
            raise psutil.AccessDenied(self.pid)
        return self._mem

    def net_connections(self, kind):
        assert kind == "inet"
        return self._conns


def test_scan_ollama_processes_over_faked_processes(bench, monkeypatch):
    ns = types.SimpleNamespace
    runner_args = [_LS, "--model", f"C:\\b\\sha256-{_BLOB}"]
    listen = ns(laddr=("127.0.0.1", 11434), raddr=(), status="LISTEN")
    out = ns(laddr=("10.0.0.2", 5000), raddr=("34.1.2.3", 443), status="ESTABLISHED")
    procs = [
        (_FakeProc(1, ns(rss=50 << 20), [listen]), "ollama.exe", ["ollama.exe", "serve"]),
        (_FakeProc(2, ns(rss=900 << 20, peak_wset=960 << 20), [out]), "llama-server", runner_args),
        (_FakeProc(3, denied=True), "ollama app.exe", ["C:\\Ollama\\ollama app.exe"]),
        (_FakeProc(4, ns(rss=1)), "python.exe", ["python"]),
    ]
    seen = []

    def fake_processes(pids):
        seen.append(pids)
        return iter(procs)

    monkeypatch.setattr(bench, "_processes", fake_processes)
    recs = bench.scan_ollama_processes(_BLOB, [1, 2])
    assert seen == [[1, 2]]
    server, runner, app = recs  # python.exe is not an Ollama process
    assert server == {
        "pid": 1,
        "role": "server",
        "rss_mb": 50,
        "peak_mb": None,  # no `peak_wset` outside Windows
        "remotes": [],
        "listen": ["127.0.0.1:11434"],
    }
    assert runner["role"] == "runner" and runner["rss_mb"] == 900 and runner["peak_mb"] == 960
    assert runner["remotes"] == ["34.1.2.3:443"] and runner["listen"] == []
    assert app == {"pid": 3, "role": "app", "error": "AccessDenied (app 3)"}


def test_processes_over_faked_psutil(bench, monkeypatch):
    import psutil

    ns = types.SimpleNamespace
    listed = [ns(pid=1, info={"name": "ollama.exe", "cmdline": ["ollama.exe", "serve"]})]

    def process(pid):
        if pid == 9:  # the model process, gone after `ollama stop`
            raise psutil.NoSuchProcess(pid)
        return ns(pid=pid, name=lambda: "ollama.exe", cmdline=lambda: ["ollama.exe", "serve"])

    _fake_psutil(monkeypatch, procs=listed, process=process)  # its `Error` is psutil's
    full = list(bench._processes(None))
    assert [(p.pid, name, cmd) for p, name, cmd in full] == [
        (1, "ollama.exe", ["ollama.exe", "serve"])
    ]
    by_pid = list(bench._processes([9, 1]))  # a gone PID is skipped, never raised
    assert [(p.pid, name) for p, name, _cmd in by_pid] == [(1, "ollama.exe")]


def _tev1_measured(**overrides) -> dict:
    tev1 = {
        "rss_peak_mb": 1990,
        "rss_with_slm_mb": 1940,
        "rss_added_mb": 30,
        "ollama_rss_peak_mb": 1030,
        "ollama_rss": {"server_peak_mb": 50, "runner_peak_mb": 980},
        "ollama_network": {
            "before": [],
            "during": [],
            "after": [],
            "samples": 40,
            "listen": ["127.0.0.1:11434", "127.0.0.1:50276"],
            "errors": [],
        },
        "ollama_processes": {"server": [1], "runner": [2]},
        "ollama": {"version": "0.35.1", "model": {"license_markers": ["MIT License"]}},
        "revisions": {"ollama/tev1:0.8b": _DIGEST},
        "versions": {"ollama": "0.35.1"},
        "packages": [],
    }
    return dict(tev1, **overrides)


def test_tev1_is_at_best_under_watch(bench):
    v = _status(bench, "tev1", **_tev1_measured())
    assert v["status"] == "à surveiller"
    ko = [c["id"] for c in v["criteria"] if c["ok"] is False]
    assert ko == ["license", "single_generative"]
    ram = next(c for c in v["criteria"] if c["id"] == "ram")
    assert ram["ok"] is True
    assert "pic total 3020 Mo = enfant de mesure 1990 Mo" in ram["detail"]
    assert "processus Ollama 1030 Mo (serveur 50 Mo, processus du modèle 980 Mo)" in ram["detail"]
    cpu = next(c for c in v["criteria"] if c["id"] == "cpu_windows")
    assert cpu["ok"] is True and "Ollama 0.35.1 est déjà installé" in cpu["detail"]
    pinned = next(c for c in v["criteria"] if c["id"] == "pinned")
    assert pinned["ok"] is True
    offline = next(c for c in v["criteria"] if c["id"] == "offline")
    assert offline["ok"] is True and "côté Ollama" in offline["detail"]
    licence = next(c for c in v["criteria"] if c["id"] == "license")
    assert "MIT License" in licence["detail"] and not licence["forbidden"]


def test_the_single_generative_rule_alone_caps_the_verdict(bench):
    import dataclasses

    licensed = dataclasses.replace(bench.candidate("tev1"), license_class="ok")
    v = bench.decision_verdict(licensed, _measured(**_tev1_measured()))
    assert [c["id"] for c in v["criteria"] if c["ok"] is False] == ["single_generative"]
    assert v["status"] == "à surveiller" and v["reason"].startswith("Règle d'un seul modèle")


@pytest.mark.parametrize(
    ("overrides", "failed"),
    [
        ({"ollama_rss_peak_mb": 2200}, "ram"),  # 1990 + 2200 > 4096: the sum decides
        ({"ollama_network": {"before": ["34.1.2.3:443"], "samples": 3}}, "offline"),
        ({"ollama_network": {"during": ["34.1.2.3:443"], "samples": 3}}, "offline"),
        ({"ollama_network": {"after": ["34.1.2.3:443"], "samples": 3}}, "offline"),
        # An outgoing connection fails the criterion even when the reading is incomplete.
        (
            {"ollama_network": {"during": ["34.1.2.3:443"], "samples": 3, "errors": ["x"]}},
            "offline",
        ),
        ({"ollama_network": {"samples": 3, "listen": ["0.0.0.0:11434"], "errors": []}}, "offline"),
        ({"ollama_network": {"samples": 3, "listen": [":::11434"], "errors": []}}, "offline"),
        ({"latency_median_ms": 1200.0}, "latency"),
        ({"attempts": [["socket.connect", "1.2.3.4"]]}, "offline"),
    ],
)
def test_tev1_blocking_criteria_discard(bench, overrides, failed):
    v = _status(bench, "tev1", **_tev1_measured(**overrides))
    assert v["status"] == "écarté"
    assert [c["id"] for c in v["criteria"] if c["ok"] is False and c["id"] in bench.BLOCKING] == [
        failed
    ]


def test_tev1_unreadable_server_side_is_not_verifiable(bench):
    v = _status(bench, "tev1", **_tev1_measured(ollama_network={}, ollama_rss_peak_mb=None))
    offline = next(c for c in v["criteria"] if c["id"] == "offline")
    ram = next(c for c in v["criteria"] if c["id"] == "ram")
    assert offline["ok"] is None and "relevé incomplet" in offline["detail"]
    assert ram["ok"] is None and v["status"] == "à surveiller"
    unpinned = _status(bench, "tev1", **_tev1_measured(revisions={"ollama/tev1:0.8b": None}))
    assert next(c for c in unpinned["criteria"] if c["id"] == "pinned")["ok"] is False
    no_version = _status(bench, "tev1", **_tev1_measured(versions={"ollama": None}))
    assert next(c for c in no_version["criteria"] if c["id"] == "pinned")["ok"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"ollama_processes": {"server": [1]}},  # the model process was never found
        {"ollama_network": {"samples": 9, "listen": [], "errors": ["AccessDenied (runner 2)"]}},
    ],
)
def test_tev1_offline_not_verifiable_without_the_model_process_or_its_connections(bench, overrides):
    v = _status(bench, "tev1", **_tev1_measured(**overrides))
    offline = next(c for c in v["criteria"] if c["id"] == "offline")
    assert offline["ok"] is None and "relevé incomplet" in offline["detail"]


def test_error_rows_are_excluded_from_the_latency(bench):
    rows = [
        {"task": "cost", "label": "erreur : HTTP 500 : x", "expected": "simple", "ms": 9000.0},
        {"task": "cost", "label": "simple", "expected": "simple", "ms": 100.0},
    ]
    summary = bench.summarize_decisions(rows)
    assert summary["latency_median_ms"] == summary["latency_max_ms"] == 100.0
    assert summary["error_rows"] == 1
    v = _status(bench, "tev1", **_tev1_measured(**summary))
    latency = next(c for c in v["criteria"] if c["id"] == "latency")
    assert latency["ok"] is True and "1 ligne(s) en erreur exclue(s)" in latency["detail"]

    all_errors = bench.summarize_decisions(rows[:1])
    assert all_errors["latency_median_ms"] is None and all_errors["error_rows"] == 1
    v = _status(bench, "tev1", rows=rows[:1], **_tev1_measured(**all_errors))
    assert v["status"] == "non mesuré" and "toutes les décisions sont en erreur" in v["reason"]
    # No time at all (an empty run) is not verifiable, never a failure.
    no_rows = _status(bench, "deberta_xsmall", latency_median_ms=None, latency_max_ms=None)
    assert next(c for c in no_rows["criteria"] if c["id"] == "latency")["ok"] is None
    assert no_rows["status"] == "à surveiller"  # nor a pass: a blocking criterion unchecked
    assert no_rows["reason"].startswith("Latence") and "(non vérifiable)" in no_rows["reason"]


def test_rows_keep_the_probabilities_and_the_server_choice(bench):
    response = {
        "answers": {"cost": {"choice": "simple", "probabilities": {"simple": 0.4, "complexe": 0.6}}}
    }
    assert bench.systemone_row(response, "cost", ["simple", "complexe"]) == {
        "label": "complexe",
        "probabilities": {"simple": 0.4, "complexe": 0.6},
        "choice": "simple",
    }
    assert bench.systemone_row({"error": "x"}, "cost", ["simple"]) == {"label": "erreur : x"}

    def decide(text, task):
        return {"label": "simple", "probabilities": {"simple": 1.0}, "choice": "simple"}

    _, rows = bench.run_decisions(decide, clock=_Clock(0.1))
    assert rows[0]["probabilities"] == {"simple": 1.0} and rows[0]["choice"] == "simple"
    assert list(rows[0])[:5] == ["prompt", "task", "label", "expected", "ms"]


class _FakeOps:
    def __init__(self, pre):
        self.pre, self.calls = pre, []

    def preflight(self, model, download=False):
        self.calls.append(("preflight", model, download))
        return dict(self.pre)

    def unload(self, model):
        self.calls.append(("unload", model))
        return {"command": f"ollama stop {model}", "returncode": 0, "still_loaded": False}


_PRE = {
    "base_url": "http://127.0.0.1:11434",
    "version": "0.35.1",
    "model": {
        "name": "tev1:0.8b",
        "digest": _DIGEST,
        "blob_sha256": _BLOB,
        "license_markers": ["MIT License"],
    },
    "loaded_before": [],
    "other_models_loaded": [],
}


def test_run_measure_served_model(bench, tmp_path):
    c = bench.candidate("tev1")
    common = dict(find_spec=lambda name: object(), packages=_no_packages, machine=_machine)

    def runner(cand, models_dir, slm_path):  # the child's own pins: none (no roots)
        measured = _measured(**_tev1_measured())
        drop = ("status", "packages", "ollama")
        return {k: v for k, v in measured.items() if k not in drop} | {
            "revisions": {},
            "versions": {},
        }

    ops = _FakeOps(_PRE)
    report = bench.run_measure(
        c, tmp_path, tmp_path / "slm.gguf", runner=runner, server_ops=ops, **common
    )
    assert ops.calls == [("preflight", "tev1:0.8b", False), ("unload", "tev1:0.8b")]
    assert report["status"] == "measured" and report["verdict"]["status"] == "à surveiller"
    assert report["revisions"] == {"ollama/tev1:0.8b": _DIGEST}  # the parent's, never the child's
    assert report["versions"] == {"ollama": "0.35.1"}
    pinned = next(x for x in report["verdict"]["criteria"] if x["id"] == "pinned")
    assert pinned["ok"] is True
    assert report["ollama_unload"]["still_loaded"] is False
    assert report["ollama"]["model"]["license_markers"] == ["MIT License"]  # in the JSON

    def broken(cand, models_dir, slm_path):
        raise RuntimeError("enfant mort")

    ops = _FakeOps(_PRE)
    report = bench.run_measure(
        c, tmp_path, tmp_path / "slm.gguf", runner=broken, server_ops=ops, **common
    )
    assert ops.calls[-1] == ("unload", "tev1:0.8b")  # unloaded whatever happens
    assert report["status"] == "erreur" and report["verdict"]["status"] == "non mesuré"


@pytest.mark.parametrize(
    ("error", "message"),
    [
        ("unreachable", "serveur Ollama injoignable : lancez Ollama"),
        ("model_absent", "absent d'Ollama : « ollama pull tev1:0.8b »"),
    ],
)
def test_run_measure_without_server_or_model(bench, tmp_path, error, message):
    ops = _FakeOps({"error": error, "message": message})
    report = bench.run_measure(
        bench.candidate("tev1"),
        tmp_path,
        tmp_path / "slm.gguf",
        runner=_fail,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
        server_ops=ops,
    )
    assert ops.calls == [("preflight", "tev1:0.8b", False)]  # no measure, no unload
    assert report["status"] == f"non mesuré : {message}" and report["server_error"] == error
    assert report["verdict"]["status"] == "non mesuré"


def test_main_exits_non_zero_when_ollama_is_down(bench, monkeypatch, tmp_path, capsys):
    slm = tmp_path / "slm.gguf"
    slm.write_bytes(b"x")
    monkeypatch.setattr(bench, "missing_modules", lambda c, find_spec=None: [])
    down = {"error": "unreachable", "message": "serveur Ollama injoignable : lancez Ollama"}
    monkeypatch.setattr(bench, "OllamaOps", lambda url: _FakeOps(down))
    monkeypatch.setattr(bench, "_versions", lambda roots: {})
    real = bench.run_measure

    def run_measure(c, models_dir, slm_path, download=False, **kw):
        return real(
            c, models_dir, slm_path, download, packages=_no_packages, machine=_machine, **kw
        )

    monkeypatch.setattr(bench, "run_measure", run_measure)
    assert bench.main(["measure", "tev1", "--slm", str(slm)]) == 2
    assert "lancez Ollama" in capsys.readouterr().out


def _ollama_api(state, loaded=(), down=False, override=None):
    """A fake Ollama 0.35 (`/api/*`), recording the paths it is asked; `override` maps a
    path to a handler (a response, or an exception raised)."""
    import httpx

    def handler(request):
        state.setdefault("paths", []).append(request.url.path)
        if down:
            raise httpx.ConnectError("refused", request=request)
        path = request.url.path
        if override and path in override:
            return override[path](request)
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.35.1"})
        if path == "/api/show":
            model = json.loads(request.content)["model"]
            if model in state.get("pulled", set()):
                return httpx.Response(200, json={"modelfile": _MODELFILE, "license": _LICENSE})
            return httpx.Response(404, json={"error": f"model '{model}' not found"})
        if path == "/api/pull":
            state.setdefault("pulled", set()).add(json.loads(request.content)["model"])
            return httpx.Response(200, json={"status": "success"})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "tev1:0.8b", "digest": _DIGEST}]})
        if path == "/api/ps":
            names = [] if state.get("stopped") else list(loaded)
            return httpx.Response(200, json={"models": [{"name": n} for n in names]})
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def _fake_cli(state):
    def run(argv, **kwargs):
        state.setdefault("cli", []).append(argv[1:])
        state["stopped"] = True
        return types.SimpleNamespace(returncode=0)

    return run


def test_ollama_ops_preflight_and_unload(bench, monkeypatch):
    state = {}
    ops = bench.OllamaOps(transport=_ollama_api(state, down=True))
    pre = ops.preflight("tev1:0.8b")
    assert pre["error"] == "unreachable" and "lancez Ollama" in pre["message"]

    state = {}
    ops = bench.OllamaOps(transport=_ollama_api(state))
    pre = ops.preflight("tev1:0.8b")  # not pulled, no --download: nothing is downloaded
    assert pre["error"] == "model_absent" and "ollama pull tev1:0.8b" in pre["message"]
    assert "/api/pull" not in state["paths"]

    state = {}
    ops = bench.OllamaOps(
        transport=_ollama_api(state, loaded=("tev1:0.8b", "qwen3.5:2b")),
        run=_fake_cli(state),
        which=lambda name: "C:\\Ollama\\ollama.exe",
    )
    pre = ops.preflight("tev1:0.8b", download=True)
    assert "error" not in pre and pre["pull"]["http"] == 200 and pre["version"] == "0.35.1"
    assert pre["model"]["digest"] == _DIGEST and pre["model"]["blob_sha256"] == _BLOB
    assert pre["loaded_before"] == ["tev1:0.8b", "qwen3.5:2b"]
    assert pre["other_models_loaded"] == ["qwen3.5:2b"]  # noted, never unloaded by the bench
    assert state["cli"] == [["stop", "tev1:0.8b"]]  # tev1 already loaded: stopped first
    assert pre["stopped_before"]["still_loaded"] is False  # and gone before the measure

    def no_unload(argv, **kwargs):  # `ollama stop` answers, but the model stays
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    state = {"pulled": {"tev1:0.8b"}}
    ops = bench.OllamaOps(
        transport=_ollama_api(state, loaded=("tev1:0.8b",)),
        run=no_unload,
        which=lambda name: "ollama",
    )
    pre = ops.preflight("tev1:0.8b")
    assert pre["error"] == "still_loaded" and "ollama stop tev1:0.8b" in pre["message"]
    assert pre["stopped_before"]["loaded_after"] == ["tev1:0.8b"]

    state = {"pulled": {"tev1:0.8b"}}
    ops = bench.OllamaOps(
        transport=_ollama_api(state, loaded=("tev1:0.8b",)),
        run=_fake_cli(state),
        which=lambda name: "ollama",
    )
    assert ops.unload("tev1:0.8b") == {
        "command": "ollama stop tev1:0.8b",
        "returncode": 0,
        "still_loaded": False,
        "loaded_after": [],
    }
    no_cli = bench.OllamaOps(transport=_ollama_api({}), which=lambda name: None)
    assert "introuvable" in no_cli.stop("tev1:0.8b")["error"]


def _raise(exc_type):
    def handler(request):
        raise exc_type("boom", request=request)

    return handler


def _answer(status, **kw):
    import httpx

    return lambda request: httpx.Response(status, **kw)


def test_ollama_ops_pull_failures_are_named(bench):
    import httpx

    cases = [
        (_raise(httpx.ReadTimeout), "pull_timeout", "non terminé après"),
        (_raise(httpx.RemoteProtocolError), "pull_failed", "interrompu"),
        (_answer(500, json={"error": "disk full"}), "pull_failed", "disk full"),
        (_answer(200, json={"status": "pulling"}), "pull_failed", "pulling"),
        (_answer(200, json=["success"]), "pull_failed", "HTTP 200"),  # non-dict JSON
    ]
    for handler, error, words in cases:
        state = {}
        ops = bench.OllamaOps(transport=_ollama_api(state, override={"/api/pull": handler}))
        pre = ops.preflight("tev1:0.8b", download=True)
        assert pre["error"] == error and words in pre["message"], pre
        assert "lancez Ollama" not in pre["message"] and "absent d'Ollama" not in pre["message"]
        assert "ollama pull tev1:0.8b" in pre["message"]


def test_ollama_ops_show_failed_timeout_and_non_dict_json(bench):
    import httpx

    state = {}
    ops = bench.OllamaOps(
        transport=_ollama_api(state, override={"/api/show": _answer(500, text="oops")})
    )
    pre = ops.preflight("tev1:0.8b")
    assert pre["error"] == "show_failed" and "HTTP 500" in pre["message"]

    ops = bench.OllamaOps(
        transport=_ollama_api({}, override={"/api/version": _raise(httpx.ReadTimeout)})
    )
    pre = ops.preflight("tev1:0.8b")
    assert pre["error"] == "timeout" and "lancez Ollama" not in pre["message"]

    odd = {
        "/api/version": _answer(200, json=["0.35.1"]),
        "/api/tags": _answer(200, json="tags"),
    }
    state = {"pulled": {"tev1:0.8b"}}
    ops = bench.OllamaOps(transport=_ollama_api(state, override=odd), which=lambda n: None)
    pre = ops.preflight("tev1:0.8b")
    assert "error" not in pre and pre["version"] is None and pre["loaded_before"] == []
    assert pre["model"]["digest"] is None

    # An unreadable `/api/ps` (here a list that names tev1) is never "nothing loaded".
    odd_ps = {"/api/ps": _answer(200, json=[{"name": "tev1:0.8b"}])}
    ops = bench.OllamaOps(transport=_ollama_api(state, override=odd_ps), which=lambda n: None)
    pre = ops.preflight("tev1:0.8b")
    assert pre["error"] == "ps_unreadable" and "ollama ps" in pre["message"]
    assert pre["loaded_before"] is None
    unload = ops.unload("tev1:0.8b")
    assert unload["still_loaded"] is None and unload["loaded_after"] is None


def test_a_failing_unload_never_masks_the_report(bench, tmp_path):
    class _BadUnload(_FakeOps):
        def unload(self, model):
            raise ValueError("ps illisible")

    def runner(cand, models_dir, slm_path):
        measured = _measured(**_tev1_measured())
        return {k: v for k, v in measured.items() if k not in ("status", "packages", "ollama")}

    report = bench.run_measure(
        bench.candidate("tev1"),
        tmp_path,
        tmp_path / "slm.gguf",
        runner=runner,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
        server_ops=_BadUnload(_PRE),
    )
    assert report["status"] == "measured" and report["verdict"]["status"] == "à surveiller"
    assert "ps illisible" in report["ollama_unload"]["error"]
    assert report["ollama_unload"]["still_loaded"] is None


def _served_child(bench, monkeypatch, tmp_path, systemone, scan=None):
    """Runs the measurement child of `tev1` in-process: a fake Ollama API, the given
    `/v1/systemone` transport and process scan, fake llama_cpp and RSS."""
    import functools

    import httpx

    api = _ollama_api({"pulled": {"tev1:0.8b"}})

    def route(request):
        if request.url.path == "/v1/systemone":
            return systemone.handle_request(request)
        return api.handle_request(request)

    def default_scan(pids=None):
        return [_proc("server", 1, 50), _proc("runner", 2, 900, peak=960)]

    loader = functools.partial(
        bench._load_systemone, transport=httpx.MockTransport(route), scan=scan or default_scan
    )
    monkeypatch.setitem(bench.LOADERS, "ollama_systemone", loader)
    fake_llama = types.SimpleNamespace(Llama=_FakeLlama, __version__="0.3.35")
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama)
    monkeypatch.setattr(bench.s12, "_record_and_guard", lambda **kw: ([], "garde factice"))
    monkeypatch.setattr(bench.s12, "_rss_mb", lambda: 1940)
    monkeypatch.setattr(bench.s12, "_blocked_host", lambda exc: None)
    monkeypatch.setattr(
        bench.s12,
        "_baseline_rss",
        lambda: {"rss_before_load_mb": 1940, "peak_before_load_mb": 1950},
    )
    monkeypatch.setattr(
        bench.s12, "_loaded_rss", lambda: {"rss_loaded_mb": 1960, "rss_peak_mb": 1990}
    )
    return bench._measure_child("tev1", tmp_path, tmp_path / "slm.gguf")


def test_a_decision_failing_mid_run_keeps_the_ollama_fields(bench, monkeypatch, tmp_path):
    import httpx

    seen = []
    ok = _systemone_transport(seen)

    def handler(request):
        if len(seen) >= 10:  # gone after ten answers: the load, the warm-up and 7 decisions
            raise httpx.ConnectError("refused", request=request)
        return ok.handle_request(request)

    child = _served_child(bench, monkeypatch, tmp_path, httpx.MockTransport(handler))
    assert "ConnectError" in child["error"]
    assert child["ollama_rss_peak_mb"] == 1010 and child["ollama_network"]["samples"] >= 2
    report = bench.run_measure(
        bench.candidate("tev1"),
        tmp_path,
        tmp_path / "slm.gguf",
        runner=lambda cand, d, s: json.loads(json.dumps(child)),
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
        server_ops=_FakeOps(_PRE),
    )
    assert report["status"] == "erreur" and report["verdict"]["status"] == "non mesuré"
    for key in ("ollama_rss_peak_mb", "ollama_rss", "ollama_processes", "ollama_network"):
        assert report[key] == child[key], key


def test_an_unexpected_answer_mid_run_is_an_error_row(bench, monkeypatch, tmp_path):
    import httpx

    seen = []
    ok = _systemone_transport(seen)

    def handler(request):
        if len(seen) == 7:  # the 5th decision (after the load and the warm-up)
            seen.append("odd")
            return httpx.Response(200, json={"answers": {"x": {"choice": "simple"}}})
        return ok.handle_request(request)

    child = _served_child(bench, monkeypatch, tmp_path, httpx.MockTransport(handler))
    assert "error" not in child, child.get("error")
    assert child["decisions"] == 40 and child["error_rows"] == 1
    bad = [r for r in child["rows"] if r["label"].startswith("erreur")]
    assert len(bad) == 1 and "forme inattendue" in bad[0]["label"]


def test_the_client_is_built_before_the_watch_starts(bench, monkeypatch):
    started = []
    monkeypatch.setattr(bench.ServerWatch, "start", lambda self: started.append(self) or self)

    def no_client(*args, **kwargs):
        raise ValueError("client impossible")

    monkeypatch.setattr(bench, "SystemOneClient", no_client)
    api = _ollama_api({"pulled": {"tev1:0.8b"}})
    with pytest.raises(ValueError, match="client impossible"):
        bench._load_systemone(
            bench.candidate("tev1"), Path("."), None, transport=api, scan=lambda pids=None: []
        )
    assert started == []  # no watch thread left behind


def test_a_first_answer_without_probabilities_fails_the_load(bench, monkeypatch, tmp_path):
    import httpx

    no_probs = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"answers": {"cost": {"choice": "simple"}}})
    )
    child = _served_child(bench, monkeypatch, tmp_path, no_probs)
    assert "forme inattendue" in child["error"] and "decisions" not in child


def test_the_ollama_ceiling_stops_the_decisions(bench, monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "OLLAMA_ABORT_MB", 1000)

    def big(pids=None):
        return [_proc("server", 1, 50), _proc("runner", 2, 990)]

    child = _served_child(bench, monkeypatch, tmp_path, _systemone_transport([]), scan=big)
    assert "ollama_ceiling" in child["error"]
    assert child["ollama_ceiling"]["rss_at_stop_mb"] == 1040
    report = bench.run_measure(
        bench.candidate("tev1"),
        tmp_path,
        tmp_path / "slm.gguf",
        runner=lambda cand, d, s: json.loads(json.dumps(child)),
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
        server_ops=_FakeOps(_PRE),
    )
    assert report["verdict"]["status"] == "écarté (RAM)"


def test_print_measure_shows_the_ram_sum_and_the_unload(bench, tmp_path, capsys):
    def runner(cand, models_dir, slm_path):
        measured = _measured(**_tev1_measured(ram_total_peak_mb=3020))
        measured["agreement"] = {"cost": "13/20", "specialty": "15/20"}
        return {k: v for k, v in measured.items() if k not in ("status", "packages", "ollama")}

    report = bench.run_measure(
        bench.candidate("tev1"),
        tmp_path,
        tmp_path / "slm.gguf",
        runner=runner,
        find_spec=lambda name: object(),
        packages=_no_packages,
        machine=_machine,
        server_ops=_FakeOps(_PRE),
    )
    bench.print_measure(report)
    out = capsys.readouterr().out
    assert "RAM : enfant 1990 Mo + Ollama 1030 Mo (serveur 50, modèle 980) = 3020 Mo" in out
    assert "fin : ollama stop tev1:0.8b — encore chargé : False" in out


def test_measure_child_of_a_served_model(bench, monkeypatch, tmp_path):
    """The child's glue: the watch starts before the model loads and stops after the
    decisions; the RAM sum and the server-side record land in the child's JSON."""
    seen = []
    out = _served_child(bench, monkeypatch, tmp_path, _systemone_transport(seen))
    assert "error" not in out, out.get("error")
    assert out["decisions"] == 40 and len(seen) == 1 + 2 + 40  # load, warm-up, decisions
    assert out["rows"][0]["probabilities"] and out["rows"][0]["choice"]
    assert out["ollama_rss_peak_mb"] == 50 + 960 and out["ram_total_peak_mb"] == 1990 + 1010
    assert out["blob_sha256"] == _BLOB and out["systemone_api"]["doc"].endswith("/systemone")
    assert out["ollama_network"]["samples"] >= 2 and "finish" not in out
    assert out["ram_watchdog"]["status"] == "active" and out["ollama_ceiling"] is None


# -- story 9: decision encoders served by a portable llama-server ------------


_VERSION_OUT = (
    "load_backend: loaded CPU backend\nversion: 0.5.0-dev (build 11378, commit edd6e2bbd)\n"
    "built with Clang 20.1.8 for Windows x86_64\n"
)
_VERSION_LINE = "version: 0.5.0-dev (build 11378, commit edd6e2bbd)"


@pytest.mark.parametrize("cid", ["julia1", "laya"])
def test_llama_server_candidates_and_commands(bench, cid):
    c = bench.candidate(cid)
    assert c.backend == "llama_systemone" and c.server == "llama_server" and c.tier == "2"
    assert not c.generative  # encoders: the single generative model rule does not cap them
    assert bench.is_commit_sha(c.revision) and bench.is_sha256(c.gguf_sha256)
    assert c.repos[0][1][0].endswith("-Q8_0.gguf") and c.repos[0][0].startswith("ggml-org/")
    assert bench.license_class(c) == "ok" and "Apache-2.0" in c.model_license
    assert c.roots == () and set(c.modules) == {"httpx", "psutil"}
    assert bench.command_for(c) == (
        f"uv run --with huggingface-hub python tools/bench/v2s6_decision_bench.py measure {cid} "
        f'--download --slm $SLM --out "$OUT\\{cid}.json"'
    )


def test_list_shows_the_llama_server_and_the_pinned_gguf(bench, capsys):
    assert bench.main(["list"]) == 0
    block = capsys.readouterr().out.split("-- julia1", 1)[1].split("\n-- ", 1)[0]
    assert (
        f"GGUF ggml-org/Julia-1-GGUF/Julia-1-Q8_0.gguf au commit {bench.JULIA1_REVISION}" in block
    )
    assert "servi par llama-server b11378 sur 127.0.0.1" in block
    assert "jamais téléchargé par le banc" in block


def test_resolve_llama_server(bench, tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path)}
    default = tmp_path / "WaveStack" / "bench" / "llama-b11378" / "llama-server.exe"
    assert bench.resolve_llama_server(None, env) == (default, "dossier par défaut")
    env[bench.LLAMA_SERVER_ENV] = "D:\\ls\\llama-server.exe"
    assert bench.resolve_llama_server(None, env)[1] == "WAVESTACK_LLAMA_SERVER"
    assert bench.resolve_llama_server("E:\\x.exe", env) == (Path("E:\\x.exe"), "--llama-server")


def test_parse_llama_version(bench):
    assert bench.parse_llama_version(_VERSION_OUT) == {
        "version_line": _VERSION_LINE,
        "version": "0.5.0-dev",
        "build": "11378",
        "commit": "edd6e2bbd",
    }
    assert bench.parse_llama_version("garbage")["build"] is None


def test_llama_server_command_line_and_environment(bench, tmp_path):
    argv = bench.llama_server_argv(Path("C:/b/llama-server.exe"), tmp_path / "m.gguf", 5123, "J")
    assert argv[argv.index("-m") + 1] == str(tmp_path / "m.gguf")  # served by local path
    assert "-hf" not in argv and "--hf-repo" not in argv
    assert (
        argv[argv.index("--host") + 1] == "127.0.0.1" and argv[argv.index("--port") + 1] == "5123"
    )
    assert "--offline" in argv and "--no-webui" in argv
    assert argv[argv.index("-np") + 1] == "1"  # one slot: one model, one request at a time
    assert argv[argv.index("-a") + 1] == "J"  # the alias the requests send as `model`
    env = bench.llama_server_env(
        {
            "HTTPS_PROXY": "http://p:8080",
            "https_proxy": "http://p:8080",
            "LLAMA_ARG_HOST": "0.0.0.0",
            "LLAMA_ARG_HF_REPO": "ggml-org/x",
            "PATH": "x",
        }
    )
    assert env == {"PATH": "x"}


def test_log_excerpt_keeps_the_telling_lines_and_the_tail(bench):
    log = "a\nI srv init: decision model type: laya\nb\nc\nE main: failed to load model\nd\n"
    assert bench.log_excerpt(log) == [
        "I srv init: decision model type: laya",
        "E main: failed to load model",
    ]
    assert bench.log_excerpt(log, tail=2)[-1] == "d"


def _fake_exe(tmp_path, archive=True):
    folder = tmp_path / "llama-b11378"
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / "llama-server.exe"
    exe.write_bytes(b"MZ")
    (folder / "llama-server-impl.dll").write_bytes(b"impl")
    if archive:
        (tmp_path / "llama-b11378-bin-win-cpu-x64.zip").write_bytes(b"zip")
    return exe


def _fake_run(stdout="", stderr=_VERSION_OUT):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        return types.SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

    run.calls = calls
    return run


def test_llama_ops_preflight(bench, tmp_path):
    absent = bench.LlamaServerOps(tmp_path / "nope" / "llama-server.exe", run=_fail)
    pre = absent.preflight()
    assert pre["error"] == "binary_absent"
    assert "llama-b11378-bin-win-cpu-x64.zip" in pre["message"]  # where to get it
    assert "décompressez-le dans" in pre["message"] and "--llama-server" in pre["message"]
    assert "ne télécharge pas le binaire" in pre["message"]

    exe = _fake_exe(tmp_path)
    run = _fake_run()
    pre = bench.LlamaServerOps(exe, "dossier par défaut", run=run).preflight()
    assert run.calls == [[str(exe), "--version"]]
    assert "error" not in pre and pre["version_line"] == _VERSION_LINE and pre["build"] == "11378"
    assert pre["exe_sha256"] == bench.file_sha256(exe) and bench.is_sha256(pre["impl_sha256"])
    assert pre["archive"]["sha256_ok"] is False  # a fake zip: recorded, never trusted
    assert pre["archive"]["sha256"] == bench.file_sha256(tmp_path / bench.LLAMA_ZIP)
    assert "warning" not in pre
    other = bench.LlamaServerOps(exe, run=_fake_run(stderr="version: 1 (build 1, commit a)"))
    assert other.preflight()["warning"] == "build 1 au lieu de 11378"
    on_stdout = bench.LlamaServerOps(exe, run=_fake_run(stdout=_VERSION_OUT, stderr="")).preflight()
    assert on_stdout["build"] == "11378"

    # No DLL next to the launcher, no archive: recorded as absent, never a crash.
    (exe.parent / "llama-server-impl.dll").unlink()
    (tmp_path / bench.LLAMA_ZIP).unlink()
    bare = bench.LlamaServerOps(exe, run=_fake_run()).preflight()
    assert "error" not in bare and bare["impl_sha256"] is None and bare["archive"] is None
    assert bench.llama_binary_pinned(bare) is False

    def broken(argv, **kw):  # a wrong binary: present, but `--version` fails
        raise OSError("not a valid Win32 application")

    failed = bench.LlamaServerOps(exe, run=broken).preflight()
    assert failed["error"] == "binary_failed" and "Win32" in failed["message"]


class _FakeServerProc:
    def __init__(self, pid=4242, exit_code=None, log=None, text=""):
        self.pid, self.exit_code, self.terminated, self.killed = pid, exit_code, False, False
        if log is not None and text:
            log.write(text)

    def poll(self):
        return self.exit_code

    def terminate(self):
        self.terminated = True
        self.exit_code = 1

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.exit_code


def _health_transport(states):
    """`/health` answers the next status of `states` (the last one forever)."""
    import httpx

    seen = []

    def handler(request):
        seen.append((request.url.host, request.url.path))
        status = states[min(len(seen) - 1, len(states) - 1)]
        return httpx.Response(status, json={"status": "ok" if status == 200 else "loading"})

    transport = httpx.MockTransport(handler)
    transport.seen = seen
    return transport


def _llama_ops(bench, tmp_path, proc_kw=None, states=(503, 200), conns=None, left=()):
    exe = _fake_exe(tmp_path)
    procs = []

    def popen(argv, stdout=None, **kw):
        proc = _FakeServerProc(log=stdout, **(proc_kw or {}))
        proc.argv, proc.env = argv, kw["env"]
        procs.append(proc)
        return proc

    ops = bench.LlamaServerOps(
        exe,
        run=_fake_run(),
        popen=popen,
        transport=_health_transport(list(states)),
        port=lambda: 5123,
        connections=conns or (lambda pid: ([], ["127.0.0.1:5123"])),
        remaining=lambda exe: list(left),
        poll_s=0,
    )
    ops.procs = procs
    return ops


def test_llama_ops_start_waits_for_the_health_then_stop(bench, monkeypatch, tmp_path):
    monkeypatch.setenv("LLAMA_ARG_HOST", "0.0.0.0")  # would expose the server
    monkeypatch.setenv("HTTPS_PROXY", "http://p:8080")
    ops = _llama_ops(bench, tmp_path, proc_kw={"text": "I srv init: decision model type: laya\n"})
    launch = ops.start(tmp_path / "m.gguf", "Julia-1", tmp_path / "logs" / "julia1.log")
    assert "error" not in launch, launch
    env = ops.procs[0].env  # what the server really receives
    assert "LLAMA_ARG_HOST" not in env and "HTTPS_PROXY" not in env and env.get("PATH")
    assert launch["url"] == "http://127.0.0.1:5123" and launch["pid"] == 4242
    assert ops.transport.seen == [("127.0.0.1", "/health")] * 2  # 503 (loading), then 200
    assert launch["startup_remotes"] == [] and launch["startup_listen"] == ["127.0.0.1:5123"]
    assert launch["log_excerpt"] == ["I srv init: decision model type: laya"]
    assert launch["argv"][launch["argv"].index("-m") + 1] == str(tmp_path / "m.gguf")
    stop = ops.stop()
    assert ops.procs[0].terminated and stop["still_running"] is False
    assert stop == {
        "started": True,
        "pid": 4242,
        "returncode": 1,
        "killed": False,
        "remaining_pids": [],
        "still_running": False,
    }
    # A llama-server from this binary still running is reported.
    assert _llama_ops(bench, tmp_path, left=(77,)).stop()["still_running"] is True


def test_llama_ops_a_server_that_fails_to_start(bench, tmp_path):
    text = "E llama_model_load: error loading model\nE main: failed to load model\n"
    ops = _llama_ops(bench, tmp_path, proc_kw={"exit_code": 1, "text": text}, states=(503,))
    launch = ops.start(tmp_path / "m.gguf", "Laya", tmp_path / "laya.log")
    assert launch["error"] == "server_failed" and launch["returncode"] == 1
    assert "s'est arrêté au démarrage (code 1)" in launch["message"]
    assert "E main: failed to load model" in launch["log_excerpt"]  # the server's output
    stop = ops.stop()
    assert not ops.procs[0].terminated and stop["still_running"] is False  # already gone


def test_llama_ops_start_timeout_and_unlaunchable_binary(bench, tmp_path):
    ops = _llama_ops(bench, tmp_path, states=(503,))
    ops.start_timeout_s = -1
    launch = ops.start(tmp_path / "m.gguf", "Laya", tmp_path / "laya.log")
    assert launch["error"] == "server_timeout" and "/health" in launch["message"]
    assert ops.stop()["killed"] is False and ops.procs[0].terminated

    def broken(argv, **kw):
        raise OSError("not a valid Win32 application")

    ops = _llama_ops(bench, tmp_path)
    ops.popen = broken
    launch = ops.start(tmp_path / "m.gguf", "Laya", tmp_path / "laya.log")
    assert launch["error"] == "server_failed" and "Win32" in launch["message"]
    assert ops.stop() == {"started": False, "remaining_pids": [], "still_running": False}


_EXE_SHA = "6d2e001e3e366dd64f24578bad2ff461bcfdea4a0c86b134c280a952401eee20"
_IMPL_SHA = "68f82bb0491f057728f5c4b1f0036b0b4e50113a1fd2bb16eda14fd4a41bd62e"
_LLAMA_PRE = {
    "exe": "C:\\b\\llama-server.exe",
    "version_line": _VERSION_LINE,
    "exe_sha256": _EXE_SHA,
    "impl_sha256": _IMPL_SHA,
    "archive": None,
}


class _FakeLlamaOps:
    def __init__(self, pre=None, launch=None):
        self.pre = pre or _LLAMA_PRE
        self.launch = launch or {"url": "http://127.0.0.1:5123", "pid": 4242, "start_s": 0.7}
        self.calls = []

    def preflight(self):
        self.calls.append(("preflight",))
        return dict(self.pre)

    def start(self, gguf, alias, log_path):
        self.calls.append(("start", Path(gguf).name, alias))
        return dict(self.launch)

    def stop(self):
        self.calls.append(("stop",))
        return {"started": True, "pid": 4242, "returncode": 1, "still_running": False}


def _gguf_sha_only(c):
    """A `file_sha256` that gives the pinned sha256 to the candidate's GGUF only: hashing
    any other file does not match."""
    name = Path(c.repos[0][1][0]).name
    return lambda path: c.gguf_sha256 if Path(path).name == name else "0" * 64


def _julia1_measured(**overrides) -> dict:
    served = {
        "rss_peak_mb": 1990,
        "rss_with_slm_mb": 1940,
        "rss_added_mb": 30,
        "llama_server_rss_peak_mb": 310,
        "llama_server_rss": {"server_peak_mb": 310},
        "llama_server_network": {
            "before": [],
            "during": [],
            "after": [],
            "samples": 40,
            "listen": ["127.0.0.1:5123"],
            "errors": [],
        },
        "llama_server_processes": {"server": [4242]},
        "llama_server": _LLAMA_PRE,
        "llama_server_launch": {"start_s": 1.8, "startup_remotes": [], "startup_listen": []},
        "gguf": {"file": "Julia-1-Q8_0.gguf", "sha256": "x", "sha256_ok": True},
        "revisions": {"ggml-org/Julia-1-GGUF": "16fee17949206fbf58da9347daea44d792a81211"},
        "versions": {"llama-server": _VERSION_LINE},
        "packages": [],
    }
    return dict(served, **overrides)


def test_an_encoder_served_by_llama_server_can_be_retained(bench):
    v = _status(bench, "julia1", **_julia1_measured())
    assert v["status"] == "retenu", v["reason"]  # no single generative model cap
    assert "single_generative" not in [c["id"] for c in v["criteria"]]
    ram = next(c for c in v["criteria"] if c["id"] == "ram")
    assert ram["ok"] is True
    assert "pic total 2300 Mo = enfant de mesure 1990 Mo" in ram["detail"]
    assert "+ llama-server 310 Mo" in ram["detail"]
    cpu = next(c for c in v["criteria"] if c["id"] == "cpu_windows")
    assert cpu["ok"] is True and "constat pour décision d'Anaël, pas un échec" in cpu["detail"]
    offline = next(c for c in v["criteria"] if c["id"] == "offline")
    assert offline["ok"] is True and "côté llama-server" in offline["detail"]
    latency = next(c for c in v["criteria"] if c["id"] == "latency")
    assert "démarrage de llama-server 1.8 s" in latency["detail"]


@pytest.mark.parametrize(
    ("overrides", "failed"),
    [
        ({"llama_server_rss_peak_mb": 2200}, "ram"),  # 1990 + 2200 > 4096: the sum decides
        ({"llama_server_network": {"before": ["34.1.2.3:443"], "samples": 3}}, "offline"),
        ({"llama_server_network": {"during": ["34.1.2.3:443"], "samples": 3}}, "offline"),
        ({"llama_server_network": {"after": ["34.1.2.3:443"], "samples": 3}}, "offline"),
        ({"llama_server_launch": {"startup_remotes": ["34.1.2.3:443"]}}, "offline"),  # its start
        (
            {"llama_server_network": {"samples": 3, "listen": ["0.0.0.0:5123"], "errors": []}},
            "offline",
        ),
        ({"latency_median_ms": 1200.0}, "latency"),
    ],
)
def test_llama_server_blocking_criteria_discard(bench, overrides, failed):
    v = _status(bench, "laya", **_julia1_measured(**overrides))
    assert v["status"] == "écarté"
    assert [c["id"] for c in v["criteria"] if c["ok"] is False and c["id"] in bench.BLOCKING] == [
        failed
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"gguf": {"sha256": "y", "sha256_ok": False}},
        {"versions": {"llama-server": "version: 0.4 (build 9000, commit abc)"}},
        {"revisions": {"ggml-org/Julia-1-GGUF": "main"}},
        {"revisions": {"ggml-org/Julia-1-GGUF": "b" * 40}},  # a commit, not the pinned one
    ],
)
def test_llama_server_unpinned_is_under_watch(bench, overrides):
    v = _status(bench, "julia1", **_julia1_measured(**overrides))
    assert v["status"] == "à surveiller"
    assert next(c for c in v["criteria"] if c["id"] == "pinned")["ok"] is False


def test_llama_server_offline_not_verifiable_without_its_process(bench):
    v = _status(bench, "julia1", **_julia1_measured(llama_server_processes={}))
    offline = next(c for c in v["criteria"] if c["id"] == "offline")
    assert offline["ok"] is None and "relevé incomplet" in offline["detail"]
    # Not checked is no pass: an encoder is never retained on it.
    assert v["status"] == "à surveiller" and "(non vérifiable)" in v["reason"]
    v = _status(bench, "julia1", **_julia1_measured(llama_server_rss_peak_mb=None))
    assert next(c for c in v["criteria"] if c["id"] == "ram")["ok"] is None
    assert v["status"] == "à surveiller" and v["reason"].startswith("RAM")


def test_partial_error_rows_cap_an_encoder_under_watch(bench):
    v = _status(bench, "julia1", **_julia1_measured(error_rows=39, latency_median_ms=154.7))
    errors = next(c for c in v["criteria"] if c["id"] == "error_rows")
    assert errors["ok"] is False and "39 décision(s) en erreur sur 40" in errors["detail"]
    assert v["status"] == "à surveiller"
    assert v["reason"] == "Décisions sans erreur (39 sur 40 en erreur)"  # the count, in the reason
    assert "error_rows" not in [c["id"] for c in _status(bench, "julia1")["criteria"]]


def _common():
    return dict(find_spec=lambda name: object(), packages=_no_packages, machine=_machine)


def test_run_measure_without_the_llama_server_binary(bench, tmp_path):
    exe = tmp_path / "absent" / "llama-server.exe"
    report = bench.run_measure(
        bench.candidate("julia1"),
        tmp_path,
        tmp_path / "slm.gguf",
        runner=_fail,
        downloader=_fail,
        server_ops=bench.LlamaServerOps(exe, run=_fail, popen=_fail),
        **_common(),
    )
    assert report["server_error"] == "binary_absent" and report["status"].startswith("non mesuré")
    assert "llama-b11378-bin-win-cpu-x64.zip" in report["status"]
    assert report["verdict"]["status"] == "non mesuré"


def test_run_measure_gguf_absent_then_downloaded(bench, monkeypatch, tmp_path):
    c = bench.candidate("julia1")
    monkeypatch.setattr(bench, "file_sha256", _gguf_sha_only(c))
    ops = _FakeLlamaOps()
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=_fail,
        downloader=_fail,
        server_ops=ops,
        **_common(),
    )
    assert report["server_error"] == "gguf_absent" and ops.calls == [("preflight",)]
    assert "--download" in report["status"] and bench.command_for(c) in report["status"]

    def downloader(cand, models_dir):
        _fake_snapshot(bench, models_dir, cand, sha=cand.revision)
        return {"hosts": ["huggingface.co"], "errors": {}, "revisions": {}}

    seen = {}

    def runner(cand, models_dir, slm_path, server=None):
        seen["server"] = server
        measured = _measured(**_julia1_measured())
        drop = ("status", "packages", "llama_server", "llama_server_launch", "gguf", "revisions")
        return {k: v for k, v in measured.items() if k not in drop} | {"versions": {}}

    ops = _FakeLlamaOps()
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        download=True,
        runner=runner,
        downloader=downloader,
        server_ops=ops,
        **_common(),
    )
    assert ops.calls == [("preflight",), ("start", "Julia-1-Q8_0.gguf", "Julia-1"), ("stop",)]
    assert seen["server"] == {"url": "http://127.0.0.1:5123", "pid": 4242}
    assert report["download"]["hosts"] == ["huggingface.co"]
    assert report["gguf"]["sha256_ok"] is True
    assert report["revisions"] == {"ggml-org/Julia-1-GGUF": bench.JULIA1_REVISION}
    assert report["versions"] == {"llama-server": _VERSION_LINE}  # the child's never stays
    assert report["llama_server_stop"]["still_running"] is False
    assert report["verdict"]["status"] == "retenu"  # an encoder: never capped


def test_run_measure_retains_a_pinned_encoder_and_stops_the_server(bench, monkeypatch, tmp_path):
    c = bench.candidate("laya")
    _fake_snapshot(bench, tmp_path, c, sha=c.revision)
    monkeypatch.setattr(bench, "file_sha256", _gguf_sha_only(c))

    def runner(cand, models_dir, slm_path, server=None):
        measured = _measured(**_julia1_measured())
        drop = ("status", "packages", "llama_server", "llama_server_launch", "gguf", "revisions")
        return {k: v for k, v in measured.items() if k not in drop}

    ops = _FakeLlamaOps()
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=runner,
        downloader=_fail,
        server_ops=ops,
        **_common(),
    )
    assert report["status"] == "measured" and report["gguf"]["sha256_ok"] is True
    assert report["verdict"]["status"] == "retenu", report["verdict"]["reason"]

    def broken(cand, models_dir, slm_path, server=None):
        raise RuntimeError("enfant mort")

    ops = _FakeLlamaOps()
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=broken,
        downloader=_fail,
        server_ops=ops,
        **_common(),
    )
    assert ops.calls[-1] == ("stop",)  # stopped whatever happens
    assert report["status"] == "erreur" and report["verdict"]["status"] == "non mesuré"


def test_main_a_llama_server_that_does_not_start(bench, monkeypatch, tmp_path, capsys):
    c = bench.candidate("julia1")
    _fake_snapshot(bench, tmp_path, c, sha=c.revision)
    monkeypatch.setattr(bench, "file_sha256", _gguf_sha_only(c))
    slm = tmp_path / "slm.gguf"
    slm.write_bytes(b"x")
    failed = {
        "error": "server_failed",
        "message": "llama-server s'est arrêté au démarrage (code 1)",
        "log_excerpt": ["E main: failed to load model"],
    }
    ops = _FakeLlamaOps(launch=failed)
    real = bench.run_measure

    def run_measure(cand, models_dir, slm_path, download=False, llama_server=None):
        assert llama_server == "C:\\b\\llama-server.exe"
        return real(cand, models_dir, slm_path, download, runner=_fail, server_ops=ops, **_common())

    monkeypatch.setattr(bench, "run_measure", run_measure)
    argv = ["measure", "julia1", "--slm", str(slm), "--models-dir", str(tmp_path)]
    assert bench.main([*argv, "--llama-server", "C:\\b\\llama-server.exe"]) == 2
    out = capsys.readouterr().out
    assert "s'est arrêté au démarrage" in out and "| E main: failed to load model" in out
    assert "encore lancé : False" in out and "NON MESURÉ" in out
    assert ops.calls[-1] == ("stop",)  # no process left


def test_scan_llama_server_by_pid(bench, monkeypatch):
    ns = types.SimpleNamespace
    listen = ns(laddr=("127.0.0.1", 5123), raddr=(), status="LISTEN")
    procs = {
        4242: (
            _FakeProc(4242, ns(rss=300 << 20, peak_wset=310 << 20), [listen]),
            "llama-server.exe",
        ),
        7: (_FakeProc(7, ns(rss=1)), "notepad.exe"),  # a reused PID is not the server
    }
    monkeypatch.setattr(
        bench, "_processes", lambda pids: iter((procs[p][0], procs[p][1], []) for p in pids)
    )
    (rec,) = bench.scan_llama_server(4242)
    assert rec == {
        "pid": 4242,
        "role": "server",
        "rss_mb": 300,
        "peak_mb": 310,
        "remotes": [],
        "listen": ["127.0.0.1:5123"],
    }
    assert bench.scan_llama_server(7) == []


def test_llama_server_watch_reports_its_own_fields(bench):
    scans = iter([[_proc("server", 9, 280, peak=300)], [_proc("server", 9, 290, peak=320)], []])
    watch = bench.LlamaServerWatch(9, scan=lambda pids=None: next(scans), period_s=60)
    for phase in ("before", "during", "after"):
        watch.take(phase)
    report = watch.report()
    assert report["llama_server_rss_peak_mb"] == 320 and report["llama_server_ceiling"] is None
    assert report["llama_server_rss"]["server_peak_mb"] == 320
    assert report["llama_server_rss"]["server_series_mb"] == [280, 290]
    assert report["llama_server_processes"] == {"server": [9]}
    net = report["llama_server_network"]
    assert net["errors"] == [] and net["full_scans"] == 0  # one PID, never a full listing
    assert "un seul processus, relu par son PID" in net["method"]
    assert "liste complète" not in net["method"]
    gone = bench.LlamaServerWatch(9, scan=lambda pids=None: [], period_s=60)
    gone.take("before")
    assert gone.report()["llama_server_network"]["errors"] == [
        "processus llama-server introuvable (PID 9)"
    ]


def _llama_child(bench, monkeypatch, tmp_path, systemone, server, scan=None):
    """The measurement child of `julia1` in-process, against a fake llama-server."""
    import functools

    loader = functools.partial(
        bench._load_llama_server,
        transport=systemone,
        scan=scan or (lambda pids=None: [_proc("server", 4242, 300, peak=310)]),
    )
    monkeypatch.setitem(bench.LOADERS, "llama_systemone", loader)
    fake_llama = types.SimpleNamespace(Llama=_FakeLlama, __version__="0.3.35")
    monkeypatch.setitem(sys.modules, "llama_cpp", fake_llama)
    monkeypatch.setattr(bench.s12, "_record_and_guard", lambda **kw: ([], "garde factice"))
    monkeypatch.setattr(bench.s12, "_rss_mb", lambda: 1940)
    monkeypatch.setattr(bench.s12, "_blocked_host", lambda exc: None)
    monkeypatch.setattr(
        bench.s12,
        "_baseline_rss",
        lambda: {"rss_before_load_mb": 1940, "peak_before_load_mb": 1950},
    )
    monkeypatch.setattr(
        bench.s12, "_loaded_rss", lambda: {"rss_loaded_mb": 1960, "rss_peak_mb": 1990}
    )
    return bench._measure_child("julia1", tmp_path, tmp_path / "slm.gguf", server=server)


def test_measure_child_of_a_llama_server_model(bench, monkeypatch, tmp_path):
    seen = []
    server = {"url": "http://127.0.0.1:5123", "pid": 4242}
    out = _llama_child(bench, monkeypatch, tmp_path, _systemone_transport(seen), server)
    assert "error" not in out, out.get("error")
    assert out["decisions"] == 40 and len(seen) == 1 + 2 + 40
    assert {host for _m, _p, host, _b in seen} == {"127.0.0.1"} and seen[0][1] == "/v1/systemone"
    assert seen[0][3]["model"] == "Julia-1"
    assert out["llama_server_rss_peak_mb"] == 310 and out["ram_total_peak_mb"] == 1990 + 310
    assert out["server_pid"] == 4242 and "PR #29818" in out["systemone_api"]["code"]
    assert out["llama_server_network"]["samples"] >= 2 and "finish" not in out
    assert "ollama_rss_peak_mb" not in out

    asked = []
    no_server = _llama_child(bench, monkeypatch, tmp_path, _systemone_transport(asked), None)
    assert "non démarré par le parent" in no_server["error"]
    assert asked == []  # not a single request


def test_child_command_line_carries_the_llama_server(bench, monkeypatch, tmp_path, capsys):
    seen = {}
    monkeypatch.setattr(bench.s12, "_run_child", lambda cmd, env, timeout: seen.update(cmd=cmd))
    server = {"url": "http://127.0.0.1:5123", "pid": 4242}
    bench._default_runner(bench.candidate("julia1"), tmp_path, tmp_path / "s.gguf", server)
    assert seen["cmd"][-4:] == ["--server-url", "http://127.0.0.1:5123", "--server-pid", "4242"]
    got = {}

    def child(cid, d, s, server=None):
        got.update(cid=cid, server=server)
        return {"id": cid}

    monkeypatch.setattr(bench, "_measure_child", child)
    assert bench.main(seen["cmd"][2:]) == 0
    assert got == {"cid": "julia1", "server": server}
    capsys.readouterr()


# -- story 9, review fixes ----------------------------------------------------


def _llama_measured_runner(**overrides):
    def runner(cand, models_dir, slm_path, server=None):
        measured = _measured(**_julia1_measured(**overrides))
        drop = ("status", "packages", "llama_server", "llama_server_launch", "gguf", "revisions")
        return {k: v for k, v in measured.items() if k not in drop}

    return runner


def _pinned_julia1(bench, monkeypatch, tmp_path):
    c = bench.candidate("julia1")
    _fake_snapshot(bench, tmp_path, c, sha=c.revision)
    monkeypatch.setattr(bench, "file_sha256", _gguf_sha_only(c))
    return c


def test_the_abort_threshold_is_the_budget_plus_a_margin(bench):
    assert bench.OLLAMA_ABORT_MB == bench.RAM_BUDGET_MB + 2048 == 6144


def test_the_llama_server_ceiling_end_to_end(bench, monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "OLLAMA_ABORT_MB", 1000)
    server = {"url": "http://127.0.0.1:5123", "pid": 4242}

    def big(pids=None):
        return [_proc("server", 4242, 1100)]

    child = _llama_child(bench, monkeypatch, tmp_path, _systemone_transport([]), server, scan=big)
    assert "llama_server_ceiling" in child["error"] and "decisions" not in child
    assert child["llama_server_ceiling"]["rss_at_stop_mb"] == 1100
    c = _pinned_julia1(bench, monkeypatch, tmp_path)
    ops = _FakeLlamaOps()
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=lambda cand, d, s, server=None: json.loads(json.dumps(child)),
        downloader=_fail,
        server_ops=ops,
        **_common(),
    )
    assert report["llama_server_ceiling"]["threshold_mb"] == 1000
    v = report["verdict"]
    assert v["status"] == "écarté (RAM)" and "processus llama-server à 1100 Mo" in v["reason"]
    assert ops.calls[-1] == ("stop",)


def test_print_measure_of_a_measured_llama_server_model(bench, monkeypatch, tmp_path, capsys):
    c = _pinned_julia1(bench, monkeypatch, tmp_path)
    runner = _llama_measured_runner(
        ram_total_peak_mb=2300, agreement={"cost": "9/20", "specialty": "8/20"}
    )
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=runner,
        downloader=_fail,
        server_ops=_FakeLlamaOps(),
        **_common(),
    )
    bench.print_measure(report)
    out = capsys.readouterr().out
    assert "RAM : enfant 1990 Mo + llama-server 310 Mo = 2300 Mo" in out
    assert "fin : llama-server arrêté (PID 4242, code 1) — encore lancé : False" in out
    assert "== Verdict : RETENU" in out


def test_startup_connection_errors_make_offline_unverifiable(bench, tmp_path):
    launch = {"start_s": 1.0, "startup_remotes": [], "startup_errors": ["AccessDenied (4242)"]}
    v = _status(bench, "julia1", **_julia1_measured(llama_server_launch=launch))
    offline = next(c for c in v["criteria"] if c["id"] == "offline")
    assert offline["ok"] is None and "AccessDenied (4242)" in offline["detail"]

    def denied(pid):
        raise RuntimeError("AccessDenied (4242)")

    ops = _llama_ops(bench, tmp_path, conns=denied)
    launch = ops.start(tmp_path / "m.gguf", "Julia-1", tmp_path / "julia1.log")
    assert "error" not in launch and "AccessDenied" in launch["startup_errors"][0]
    ops.stop()


@pytest.mark.parametrize(
    ("server", "ok"),
    [
        ({"exe_sha256": _EXE_SHA, "impl_sha256": _IMPL_SHA, "archive": None}, True),
        # The 9 KB launcher alone is not the server's code.
        ({"exe_sha256": _EXE_SHA, "impl_sha256": None, "archive": None}, False),
        ({"exe_sha256": _EXE_SHA, "impl_sha256": "0" * 64, "archive": None}, False),
        ({"exe_sha256": "0" * 64, "impl_sha256": _IMPL_SHA, "archive": None}, False),
        # A matching archive next to the folder says nothing of the unzipped files.
        ({"exe_sha256": "0" * 64, "impl_sha256": "0" * 64, "archive": {"sha256_ok": True}}, False),
        ({}, False),
    ],
)
def test_the_binary_must_be_the_recorded_one(bench, server, ok):
    assert bench.llama_binary_pinned(server) is ok
    v = _status(bench, "julia1", **_julia1_measured(llama_server=server))
    pinned = next(c for c in v["criteria"] if c["id"] == "pinned")
    assert pinned["ok"] is ok and "autres DLL du moteur non vérifiées" in pinned["detail"]
    assert v["status"] == ("retenu" if ok else "à surveiller")


def test_a_gguf_other_than_the_pinned_one_is_never_served(bench, tmp_path):
    c = bench.candidate("laya")
    _fake_snapshot(bench, tmp_path, c, sha=c.revision)  # its sha256 is not the pinned one
    ops = _FakeLlamaOps()
    report = bench.run_measure(
        c,
        tmp_path,
        tmp_path / "slm.gguf",
        runner=_fail,
        downloader=_fail,
        server_ops=ops,
        **_common(),
    )
    assert ops.calls == [("preflight",)]  # never started
    assert report["status"].startswith("non mesuré : GGUF non conforme : Laya-Q8_0.gguf")
    assert report["server_error"] == "gguf_mismatch"
    assert report["verdict"]["status"] == "non mesuré"


def test_llama_server_env_drops_its_cache_variable(bench):
    assert bench.llama_server_env({"LLAMA_CACHE": "D:\\cache", "PATH": "x"}) == {"PATH": "x"}


def _fake_psutil(monkeypatch, procs=(), process=None):
    import psutil

    fake = types.SimpleNamespace(
        process_iter=lambda attrs: iter(procs),
        Process=process,
        AccessDenied=psutil.AccessDenied,
        Error=psutil.Error,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake)


def test_llama_processes_match_the_binary(bench, monkeypatch, tmp_path):
    exe = _fake_exe(tmp_path)
    ns = types.SimpleNamespace
    procs = [
        ns(pid=1, info={"name": "llama-server.exe", "exe": str(exe)}),
        ns(pid=2, info={"name": "llama-server.exe", "exe": str(tmp_path / "other.exe")}),
        ns(pid=3, info={"name": "llama-server.exe", "exe": None}),  # AccessDenied: no path
        ns(pid=4, info={"name": "python.exe", "exe": str(exe)}),
        ns(pid=5, info={"name": None, "exe": None}),
    ]
    _fake_psutil(monkeypatch, procs=procs)
    assert bench._llama_processes(exe) == [1]


def test_pid_connections_over_faked_psutil(bench, monkeypatch):
    import psutil

    ns = types.SimpleNamespace
    conns = [
        ns(laddr=("127.0.0.1", 5123), raddr=(), status="LISTEN"),
        ns(laddr=("10.0.0.2", 5000), raddr=("34.1.2.3", 443), status="ESTABLISHED"),
    ]

    def process(pid):
        if pid == 9:
            raise psutil.AccessDenied(pid)
        return ns(net_connections=lambda kind: conns)

    _fake_psutil(monkeypatch, process=process)
    assert bench._pid_connections(4242) == (["34.1.2.3:443"], ["127.0.0.1:5123"])
    with pytest.raises(psutil.AccessDenied):
        bench._pid_connections(9)  # recorded by `start` as a start-up error


def test_stop_survives_a_server_that_does_not_die(bench, tmp_path):
    import subprocess

    class _Stuck(_FakeServerProc):
        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("llama-server", timeout)

        def terminate(self):
            self.terminated = True  # ignored: still running

    ops = _llama_ops(bench, tmp_path, left=(4242,))
    ops.proc = _Stuck()
    stop = ops.stop()
    assert stop["killed"] is True and "TimeoutExpired" in stop["kill_error"]
    assert stop["still_running"] is True and stop["remaining_pids"] == [4242]


@pytest.mark.parametrize(("still_running", "code"), [(True, 2), (None, 2), (False, 0)])
def test_main_exits_non_zero_when_llama_server_is_left_running(
    bench, monkeypatch, tmp_path, capsys, still_running, code
):
    class _Left(_FakeLlamaOps):
        def stop(self):
            self.calls.append(("stop",))
            return {"started": True, "pid": 4242, "returncode": 1, "still_running": still_running}

    _pinned_julia1(bench, monkeypatch, tmp_path)
    slm = tmp_path / "slm.gguf"
    slm.write_bytes(b"x")
    real = bench.run_measure

    def run_measure(cand, models_dir, slm_path, download=False, llama_server=None):
        return real(
            cand,
            models_dir,
            slm_path,
            download,
            runner=_llama_measured_runner(agreement={"cost": "9/20", "specialty": "8/20"}),
            server_ops=_Left(),
            **_common(),
        )

    monkeypatch.setattr(bench, "run_measure", run_measure)
    argv = ["measure", "julia1", "--slm", str(slm), "--models-dir", str(tmp_path)]
    assert bench.main(argv) == code  # not verified: 2
    assert f"encore lancé : {still_running}" in capsys.readouterr().out


@pytest.mark.parametrize(("still_loaded", "code"), [(True, 2), (None, 2), (False, 0)])
def test_main_exits_non_zero_when_ollama_keeps_the_model(
    bench, monkeypatch, tmp_path, capsys, still_loaded, code
):
    class _Kept(_FakeOps):
        def unload(self, model):
            self.calls.append(("unload", model))
            return {
                "command": f"ollama stop {model}",
                "returncode": 0,
                "still_loaded": still_loaded,
            }

    slm = tmp_path / "slm.gguf"
    slm.write_bytes(b"x")
    monkeypatch.setattr(bench, "missing_modules", lambda c, find_spec=None: [])
    real = bench.run_measure

    def runner(cand, models_dir, slm_path):
        measured = _measured(**_tev1_measured(), agreement={"cost": "13/20", "specialty": "15/20"})
        return {k: v for k, v in measured.items() if k not in ("status", "packages", "ollama")}

    def run_measure(c, models_dir, slm_path, download=False, **kw):
        return real(
            c, models_dir, slm_path, download, runner=runner, server_ops=_Kept(_PRE), **_common()
        )

    monkeypatch.setattr(bench, "run_measure", run_measure)
    assert bench.main(["measure", "tev1", "--slm", str(slm)]) == code  # not verified: 2
    assert f"encore chargé : {still_loaded}" in capsys.readouterr().out


def test_run_measure_takes_the_llama_server_from_the_flag_or_the_variable(
    bench, monkeypatch, tmp_path
):
    real, seen = bench.LlamaServerOps, []

    def ops(exe, source):
        seen.append((exe, source))
        return real(exe, source, run=_fail, popen=_fail)  # absent: no measure

    monkeypatch.setattr(bench, "LlamaServerOps", ops)
    monkeypatch.delenv(bench.LLAMA_SERVER_ENV, raising=False)
    flag, env = tmp_path / "flag" / "llama-server.exe", tmp_path / "env" / "llama-server.exe"

    def measure(llama_server):
        return bench.run_measure(
            bench.candidate("julia1"),
            tmp_path,
            tmp_path / "slm.gguf",
            runner=_fail,
            downloader=_fail,
            llama_server=llama_server,
            **_common(),
        )

    report = measure(str(flag))
    assert seen == [(flag, "--llama-server")]
    assert report["server_error"] == "binary_absent" and str(flag) in report["status"]
    monkeypatch.setenv(bench.LLAMA_SERVER_ENV, str(env))
    report = measure(None)
    assert seen[-1] == (env, bench.LLAMA_SERVER_ENV) and str(env) in report["status"]


def test_an_unknown_server_label_never_raises(bench):
    import dataclasses

    c = dataclasses.replace(bench.candidate("julia1"), server="autre_serveur")
    v = bench.decision_verdict(c, _measured(**_julia1_measured()))
    offline = next(x for x in v["criteria"] if x["id"] == "offline")
    assert "processus autre_serveur" in offline["label"]
    ceiling = {"status": "erreur", "llama_server_ceiling": {"rss_at_stop_mb": 7000}}
    assert "processus autre_serveur" in bench.decision_verdict(c, ceiling)["reason"]
