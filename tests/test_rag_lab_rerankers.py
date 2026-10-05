"""Lot 5c-2: the RAG workshop's own reranking models (`[[rag_lab.rerankers]]`), each an option
of its Reranking stage with its slot; the pair's format read in the GGUF header (a template
and a probability for an LLM reranker, the pair and a sigmoid for a cross-encoder), the
cross-encoders that need segment ids and the LLMs without a rerank template refused; the pairs
cut said as a warning.

The session's models are `FakeReranker`s; the adapter is tested on the synthetic fixtures and
on a fake `llama_cpp`; the GGUF headers are written by `gguf_writer`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from fake_reranker import MODEL_ID, FakeReranker
from gguf_writer import write_gguf
from test_rag import build, place_model
from test_rag_lab import QUESTION, ended, run, run_status, stage
from test_rag_rerank import Rerankers, place_reranker, rerank_config, session_for

from wavestack import config
from wavestack.config import RerankerModel
from wavestack.messages import render
from wavestack.models import discovery
from wavestack.models import reranker as reranker_module
from wavestack.models.load_registry import RERANKER
from wavestack.models.reranker import (
    PAIR,
    LlamaCppReranker,
    RerankerRefused,
    RerankFormat,
    rerank_format,
)
from wavestack.rag import lab as rag_lab
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.trace.journal import get_journal

URL = "https://huggingface.co/demo/resolve/main/lab-reranker.gguf"
QWEN = "qwen3-reranker-0.6b"
FIXTURES = Path(__file__).parent / "fixtures"
# Qwen3-Reranker-0.6B's own template (its GGUF, 2026-10-05), shortened.
TEMPLATE = (
    "<|im_start|>system\nJudge whether the Document meets the requirements.<|im_end|>\n"
    "<|im_start|>user\n<Query>: {query}\n<Document>: {document}<|im_end|>\n"
    "<|im_start|>assistant\n"
)
BGE_HEADER = {  # bge-reranker-v2-m3 (gpustack), its keys that count
    "general.architecture": "bert",
    "bert.attention.causal": False,
    "tokenizer.ggml.token_type_count": 1,
}
MINILM_HEADER = BGE_HEADER | {"tokenizer.ggml.token_type_count": 2}
QWEN_HEADER = {
    "general.architecture": "qwen3",
    "qwen3.pooling_type": 4,
    "tokenizer.chat_template.rerank": TEMPLATE,
}


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def lab_entry(model_id: str = QWEN, **changes: object) -> dict:
    """A `[[rag_lab.rerankers]]` entry for the tests."""
    path = f"reranker/{model_id}.gguf"
    return {
        "id": model_id,
        "backend": "llama_cpp",
        "label_text": f"Faux {model_id}",
        "license": "Apache-2.0",
        "max_tokens": 1024,
        "load_path": path,
        "files": [{"url": URL, "path": path, "size": 1000}],
    } | changes


def lab_values(index: Path, *entries: dict, **kwargs: object) -> dict:
    values = rerank_config(index, **kwargs)
    values["rag_lab"] = {"rerankers": list(entries)}
    return values


def place_lab(model_id: str = QWEN, header: dict | None = None) -> Path:
    """The model's file, of its declared 1 000 bytes: null bytes (no GGUF header: the load
    judges), or a header padded with them."""
    path = config.models_dir() / f"reranker/{model_id}.gguf"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = b"" if header is None else write_gguf(path, header).read_bytes()
    path.write_bytes(data.ljust(1000, b"\0"))
    return path


class LabRerankers(Rerankers):
    """The session's factory: a declared model's fake says it reads a probability and cuts
    pairs past 400 characters at its `max_tokens`; the brick's says nothing (as before)."""

    def __call__(self, model) -> FakeReranker:  # noqa: ANN001
        reranker = super().__call__(model)
        if model.id != MODEL_ID:
            reranker.score_reading = "probability"  # type: ignore[attr-defined]
            reranker.max_tokens = model.max_tokens  # type: ignore[attr-defined]
            reranker.truncate_over = 400
        return reranker


def lab_session(values: dict, **kwargs) -> tuple[AppSession, Rerankers]:  # noqa: ANN003
    """A booted session, the RAG brick off unless asked: the workshop loads its own models."""
    kwargs.setdefault("rerank", False)
    kwargs.setdefault("bricks", ())
    kwargs.setdefault("rerankers", LabRerankers())
    return session_for(values, **kwargs)


def options(session: AppSession, kind: str = "rerank") -> dict:
    stages = session.rag_lab_state()["catalog"]["stages"]
    return {o["id"]: o for o in next(s for s in stages if s["kind"] == kind)["options"]}


def chain_with(session: AppSession, option: str) -> rag_lab.Pipeline:
    """The shipped chain, its reranking model `option`."""
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    chain = catalog.default.model_copy(deep=True)
    stage(chain, "rerank").option = option
    return chain


# ---------- the declaration ----------


def test_the_shipped_configuration_declares_qwen3_reranker():
    models, errors = config.load_config().rag_lab_rerankers
    assert errors == []
    [qwen] = models
    assert (qwen.id, qwen.max_tokens, qwen.license, qwen.measured_rss_mb) == (
        QWEN,
        1024,
        "Apache-2.0",
        937,
    )
    assert qwen.load_path == "reranker/qwen3-reranker-0.6b-q8_0.gguf"
    assert qwen.load_file.size == 639153184
    assert qwen.load_file.sha256 == (
        "22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48"
    )
    url = qwen.load_file.url
    assert url.startswith("https://huggingface.co/ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF/")
    assert url.split("/resolve/")[1].split("/")[0] == "a02f48bb4f057028298c21fa033da2b30d7742d5"
    brick, _ = config.load_config().rag_reranker
    assert brick is not None and brick.id != QWEN


@pytest.mark.parametrize(
    ("entry", "said"),
    [
        (lab_entry("sans-taille", max_tokens=4), "déclaration invalide (max_tokens)"),
        (lab_entry("x" * 33), "dépasse 32 caractères"),
        (lab_entry("declared"), "déjà celui d'une option"),
        (lab_entry(MODEL_ID), "déjà celui d'une option"),  # the brick's id
        (lab_entry(QWEN, label_text="Autre"), "porte déjà cet id"),
        (
            lab_entry(
                "ailleurs",
                load_path="embedding/a.gguf",
                files=[{"url": URL, "path": "embedding/a.gguf", "size": 1}],
            ),
            "sous reranker/",
        ),
    ],
)
def test_an_invalid_entry_is_left_out_with_its_reason_the_others_kept(index, entry, said):
    cfg = config.Config(values=lab_values(index, lab_entry(QWEN), entry, lab_entry("autre")))
    models, errors = cfg.rag_lab_rerankers
    assert [m.id for m in models] == [QWEN, "autre"]
    assert len(errors) == 1 and said in errors[0], errors
    assert "Modèle de reranking de l'atelier" in errors[0]
    assert "Workshop reranking model" in render(errors[0], "en")
    assert "Reranking-Modell der Werkstatt" in render(errors[0], "de")


def test_the_reserved_ids_are_the_workshops_own_reranking_options():
    assert set(config.RAG_LAB_RERANKER_RESERVED_IDS) == set(rag_lab.OPTIONS["rerank"])
    assert rag_lab.OPTIONS["rerank"] == ("declared",)


def test_settings_json_never_declares_a_workshop_reranker():
    shipped = config.load_config().get("rag_lab", "rerankers")
    config.save_setting("rag_lab", {"rerankers": [lab_entry("pirate")], "faiss_cost_mb": 61})
    cfg = config.load_config()
    assert cfg.get("rag_lab", "rerankers") == shipped
    assert "pirate" not in {m.id for m in cfg.rag_lab_rerankers[0]}
    assert cfg.get("rag_lab", "faiss_cost_mb") == 61  # settings.json still merges
    assert [m.id for m in cfg.rag_lab_embeddings[0]] == [
        "multilingual-e5-small",
        "qwen3-embedding-0.6b",
    ]


def test_an_invalid_entry_is_traced_once(index):
    session, _ = lab_session(lab_values(index, lab_entry("declared"), lab_entry(QWEN)))
    mark = get_journal().last_seq()
    session.rag_lab_state()
    session.rag_lab_state()
    errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert len(errors) == 1 and "« declared » écarté" in errors[0].payload["message_text"]
    assert "[[rag_lab.rerankers]]" in errors[0].payload["cause"]
    assert errors[0].payload["effect_text"] == (
        "Les autres modèles de reranking de l'atelier restent proposés."
    )
    assert QWEN in options(session)


def test_the_workshops_reranker_files_are_never_offered_as_chat_models(index):
    entry = lab_entry(
        QWEN,
        load_path="reranker/sub/q.gguf",
        files=[{"url": URL, "path": "reranker/sub/q.gguf", "size": 1}],
    )
    files = discovery._rag_model_files(config.Config(values=lab_values(index, entry)))
    assert discovery._key(config.models_dir() / "reranker/sub/q.gguf") in files


# ---------- the options of the Reranking stage ----------


def test_each_declared_reranker_is_an_option_available_only_with_its_file(index):
    place_model()
    session, _ = lab_session(lab_values(index, lab_entry(QWEN)))
    found = options(session)
    assert list(found) == ["declared", QWEN]
    assert found[QWEN]["label_text"] == f"Faux {QWEN}" and found[QWEN]["params"] == []
    reason = found[QWEN]["reason_text"]
    assert not found[QWEN]["available"]
    assert f"reranker/{QWEN}.gguf" in reason and str(config.models_dir()) in reason
    assert "[[rag_lab.rerankers]]" in reason
    place_lab()
    found = options(session)
    assert found[QWEN]["available"] and found[QWEN]["reason_text"] is None
    # The presets and the shipped chain stay on the brick's model.
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    assert stage(catalog.default, "rerank").option == "declared"
    for key in rag_lab.PRESETS:
        rerank = [s for s in catalog.preset_pipeline(key).stages if s.kind == "rerank"]
        assert all(s.option == "declared" for s in rerank)


def test_a_reranker_whose_file_is_absent_is_refused_on_its_line(index):
    place_model()
    session, _ = lab_session(lab_values(index, lab_entry(QWEN)))
    chain = chain_with(session, QWEN)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    reason, stage_id = rag_lab.check_pipeline(chain, catalog)
    assert stage_id == stage(chain, "rerank").id
    assert "« Reranking »" in reason and f"reranker/{QWEN}.gguf" in reason
    mark = get_journal().last_seq()
    with pytest.raises(SendRefused) as refused:
        session.run_rag_lab(QUESTION, chain)
    assert f"reranker/{QWEN}.gguf" in refused.value.reason_text
    assert not [e for e in get_journal().events_since(mark) if e.kind.startswith("rag_lab")]


@pytest.mark.parametrize(
    ("header", "key", "said"),
    [
        (MINILM_HEADER, "models.reranker.segments", "identifiants de segment"),
        (
            {k: v for k, v in QWEN_HEADER.items() if k != "tokenizer.chat_template.rerank"},
            "models.reranker.no_rerank_template",
            "architecture LLM (qwen3)",
        ),
        (
            BGE_HEADER | {"general.architecture": "bert", "bert.pooling_type": 2},
            "models.reranker.embedding_pooling",
            "modèle d'embedding",
        ),
    ],
)
def test_a_file_the_adapter_would_refuse_makes_its_option_unavailable(index, header, key, said):
    place_model()
    session, rerankers = lab_session(lab_values(index, lab_entry(QWEN)))
    place_lab(header=header)
    found = options(session)[QWEN]
    assert not found["available"] and said in found["reason_text"]
    assert found["reason_text"].startswith("Indisponible : ")
    model = session.cfg.rag_lab_reranker(QWEN)
    assert session._rag_lab_refused(model).kw["reason"].key == key
    with pytest.raises(SendRefused) as refused:
        session.run_rag_lab(QUESTION, chain_with(session, QWEN))
    assert said in refused.value.reason_text
    assert rerankers.made == []


@pytest.mark.parametrize("header", [BGE_HEADER, QWEN_HEADER])
def test_a_file_the_adapter_scores_is_available(index, header):
    session, _ = lab_session(lab_values(index, lab_entry(QWEN)))
    place_lab(header=header)
    assert options(session)[QWEN]["available"]


@pytest.mark.parametrize("lang", ["en", "de"])
def test_the_reasons_are_translated(index, lang):
    session, _ = lab_session(lab_values(index, lab_entry(QWEN)))
    session.set_language(lang)
    absent = options(session)[QWEN]["reason_text"]
    assert f"reranker/{QWEN}.gguf" in absent and "Indisponible" not in absent
    place_lab(header=MINILM_HEADER)
    refused = options(session)[QWEN]["reason_text"]
    assert "token_type_count" in refused and "Indisponible" not in refused
    assert {"en": "segment ids", "de": "Segment-IDs"}[lang] in refused
    place_lab(header={"general.architecture": "qwen3", "qwen3.pooling_type": 4})
    llm = options(session)[QWEN]["reason_text"]
    assert {"en": "LLM architecture (qwen3)", "de": "LLM-Architektur (qwen3)"}[lang] in llm


# ---------- a run with a declared reranker ----------


def test_a_run_with_qwen3_loads_it_in_its_own_slot_and_frees_it(index):
    place_model()
    place_reranker()
    place_lab()
    session, rerankers = lab_session(
        lab_values(index, lab_entry(QWEN)), bricks=("rag",), rerank=True
    )  # the brick holds its reranker (BGE in the shipped configuration)
    registry = session._load_registry
    brick_reranker = rerankers.made[0]
    assert registry.holder(RERANKER) and session._reranker is brick_reranker
    grants = []
    original = registry.grant
    registry.grant = lambda *a, **k: (grants.append(a[2]), original(*a, **k))  # type: ignore[method-assign]
    events = run(session, QUESTION, chain_with(session, QWEN))
    assert run_status(events) == "ok"
    rerank = ended(events, "rerank")
    assert rerank["status"] == "ok" and not rerank["borrowed"]
    facts = {f["label_text"]: f["value_text"] for f in rerank["facts"]}
    assert facts["Modèle"] == f"Faux {QWEN}"
    assert facts["Lecture du score"] == "probabilité rendue par le modèle, lue telle quelle"
    slot = f"rag_lab.reranker.{QWEN}"
    assert slot in grants and RERANKER not in grants  # never the brick's slot
    assert registry.holder(slot) is None  # freed at the run's end
    assert registry.holder(RERANKER) and session._reranker is brick_reranker  # brick intact
    assert not brick_reranker.closed
    lab = rerankers.made[1]
    assert lab.model_id == QWEN and lab.closed and lab.calls[0][0] == QUESTION
    # The scores are the model's, as it gives them (the stage only rounds them).
    assert [i["score"] for i in rerank["items"]] == sorted(
        (i["score"] for i in rerank["items"]), reverse=True
    )


def test_the_brick_reranker_says_the_sigmoid_when_its_adapter_says_so(index):
    place_model()
    place_reranker()
    session, rerankers = lab_session(rerank_config(index))
    events = run(session, QUESTION, chain_with(session, "declared"))
    facts = {f["label_text"] for f in ended(events, "rerank")["facts"]}
    assert "Lecture du score" not in facts  # the fake says nothing: no fact
    rerankers.made[0].score_reading = "sigmoid"  # type: ignore[attr-defined]
    rerankers.made[0].closed = False
    session._rag_lab_reranker = lambda option, loans: rag_lab.Lent(  # type: ignore[method-assign]
        rerankers.made[0], True, "Faux reranker"
    )
    events = run(session, QUESTION, chain_with(session, "declared"))
    facts = {f["label_text"]: f["value_text"] for f in ended(events, "rerank")["facts"]}
    assert facts["Lecture du score"] == "sigmoïde du logit du modèle, ramené entre 0 et 1"


@pytest.mark.parametrize(
    ("lang", "question", "reading", "label", "value"),
    [
        (
            "en",
            "How many days of remote work per week?",
            "probability",
            "Score reading",
            "probability returned by the model, read as it is",
        ),
        (
            "en",
            "How many days of remote work per week?",
            "sigmoid",
            "Score reading",
            "sigmoid of the model's logit, brought between 0 and 1",
        ),
        (
            "de",
            "Wie viele Tage Telearbeit pro Woche?",
            "probability",
            "Lesart des Scores",
            "vom Modell gelieferte Wahrscheinlichkeit, unverändert gelesen",
        ),
        (
            "de",
            "Wie viele Tage Telearbeit pro Woche?",
            "sigmoid",
            "Lesart des Scores",
            "Sigmoid des Logits des Modells, auf 0 bis 1 gebracht",
        ),
    ],
)
def test_the_score_reading_is_translated(index, lang, question, reading, label, value):
    place_model()
    place_lab()

    class Reading(LabRerankers):
        def __call__(self, model) -> FakeReranker:  # noqa: ANN001
            reranker = super().__call__(model)
            reranker.score_reading = reading  # type: ignore[attr-defined]
            return reranker

    session, _ = lab_session(lab_values(index, lab_entry(QWEN)), rerankers=Reading())
    session.set_language(lang)
    chain = chain_with(session, QWEN)  # the brick's index is French: the workshop's own
    stage(chain, "chunking").params["chunk_max_chars"] = 300
    stage(chain, "vector_store").option = "memory"
    facts = ended(run(session, question, chain), "rerank")["facts"]
    assert {f["label_text"]: f["value_text"] for f in facts}[label] == value


def test_a_file_of_another_sha256_is_refused_and_the_chain_goes_on(index):
    place_model()
    place_lab()
    files = [{"url": URL, "path": f"reranker/{QWEN}.gguf", "size": 1000, "sha256": "0" * 64}]
    session, rerankers = lab_session(lab_values(index, lab_entry(QWEN, files=files)))
    events = run(session, QUESTION, chain_with(session, QWEN))
    rerank = ended(events, "rerank")
    assert rerank["status"] == "error" and "sha256" in rerank["error_text"]
    assert "[[rag_lab.rerankers]]" in rerank["error_text"]
    assert run_status(events) == "ok"  # the context keeps the search's order
    assert rerankers.made == []
    assert session._load_registry.holder(f"rag_lab.reranker.{QWEN}") is None


def test_the_budget_refuses_a_reranker_too_heavy_and_names_it(index):
    place_model()
    place_lab()
    values = lab_values(index, lab_entry(QWEN, measured_rss_mb=5000), budget_mb=4096)
    session, rerankers = lab_session(values, rss=200 * 1024**2)
    rerank = ended(run(session, QUESTION, chain_with(session, QWEN)), "rerank")
    assert rerank["status"] == "error" and "Mémoire insuffisante" in rerank["error_text"]
    assert f"Faux {QWEN}" in rerank["error_text"]
    assert rerankers.made == []


# ---------- the pairs cut ----------


def test_the_pairs_cut_are_said_as_a_warning(index):
    place_model()
    place_lab()
    session, rerankers = lab_session(lab_values(index, lab_entry(QWEN)))
    events = run(session, QUESTION, chain_with(session, QWEN))
    rerank = ended(events, "rerank")
    assert rerank["status"] == "ok" and run_status(events) == "ok"  # a warning, no error
    lab = rerankers.made[0]
    passages = lab.calls[0][1]
    cut = sum(len(p) > 400 for p in passages)
    assert 1 < cut < len(passages), (cut, len(passages))
    warning = rerank["warning_text"].replace(" ", " ").replace("\xa0", " ")
    expected = (
        f"{cut} candidats sur {len(passages)} dépassent la longueur d'une paire : coupés à "
        "1 024 tokens"
    )
    assert warning.startswith(expected), warning
    for other in ("embedding", "vector_search", "context"):
        assert ended(events, other)["warning_text"] is None


@pytest.mark.parametrize(
    ("lang", "question", "said"),
    [
        (
            "fr",
            QUESTION,
            "1 candidat sur {n} dépasse la longueur d'une paire : coupé à 1 024 tokens",
        ),
        (
            "en",
            "How many days of remote work per week?",
            "1 candidate out of {n} exceeds the length of a pair: cut to 1,024 tokens",
        ),
        (
            "de",
            "Wie viele Tage Telearbeit pro Woche?",
            "1 Kandidat von {n} überschreitet die Länge eines Paares: auf 1.024 Tokens gekürzt",
        ),
    ],
)
def test_one_pair_cut_is_said_in_the_singular_and_translated(index, lang, question, said):
    place_model()
    place_lab()
    session, rerankers = lab_session(lab_values(index, lab_entry(QWEN)))
    session.set_language(lang)

    class CutsOne(LabRerankers):
        def __call__(self, model) -> FakeReranker:  # noqa: ANN001
            reranker = super().__call__(model)
            reranker.truncate_over = 10**6
            original = reranker.score

            def score(query, passages, cancelled=None, progress=None):  # noqa: ANN001, ANN202
                scores = original(query, passages, cancelled, progress)
                return [scores[0]._replace(truncated=True), *scores[1:]]

            reranker.score = score  # type: ignore[method-assign]
            return reranker

    session._reranker_factory = CutsOne()
    chain = chain_with(session, QWEN)  # the brick's index is French: the workshop's own
    stage(chain, "chunking").params["chunk_max_chars"] = 300
    stage(chain, "vector_store").option = "memory"
    events = run(session, question, chain)
    n = len(ended(events, "rerank")["items"])
    warning = ended(events, "rerank")["warning_text"]
    warning = warning.replace(" ", " ").replace("\xa0", " ")
    assert warning.startswith(said.format(n=n)), warning


class Cutting(LabRerankers):
    """`LabRerankers`, each fake made cutting the passages past `cut_over` characters."""

    def __init__(self, cut_over: int) -> None:
        super().__init__()
        self.cut_over = cut_over

    def __call__(self, model) -> FakeReranker:  # noqa: ANN001
        reranker = super().__call__(model)
        reranker.truncate_over = self.cut_over
        return reranker


def test_no_warning_when_pairs_are_cut_but_the_reranker_does_not_say_its_length(index):
    place_model()
    place_reranker()
    rerankers = Cutting(10)  # every pair cut
    session, _ = lab_session(rerank_config(index), rerankers=rerankers)
    events = run(session, QUESTION, chain_with(session, "declared"))  # the brick's: no max
    rerank = ended(events, "rerank")
    assert rerank["status"] == "ok" and rerank["error_text"] is None
    assert rerank["warning_text"] is None
    assert not hasattr(rerankers.made[0], "max_tokens") and rerankers.made[0].truncate_over == 10


def test_no_warning_when_the_reranker_says_its_length_and_nothing_is_cut(index):
    place_model()
    place_lab()
    rerankers = Cutting(10**6)  # no pair cut
    session, _ = lab_session(lab_values(index, lab_entry(QWEN)), rerankers=rerankers)
    events = run(session, QUESTION, chain_with(session, QWEN))
    rerank = ended(events, "rerank")
    assert rerank["status"] == "ok" and rerank["warning_text"] is None
    assert rerankers.made[0].max_tokens == 1024


def test_the_order_is_the_models_even_where_the_rounded_scores_tie(index):
    """Qwen3's probabilities saturate: 0.99995 ranks above 0.99991, though both show 1.0."""
    place_model()
    place_lab()

    class Saturated(LabRerankers):
        def __call__(self, model) -> FakeReranker:  # noqa: ANN001
            reranker = super().__call__(model)

            def score(query, passages, cancelled=None, progress=None):  # noqa: ANN001, ANN202
                figures = [0.99991, 0.99995] + [0.1] * (len(passages) - 2)
                return [reranker_module.RerankScore(f) for f in figures]

            reranker.score = score  # type: ignore[method-assign]
            return reranker

    session, _ = lab_session(lab_values(index, lab_entry(QWEN)), rerankers=Saturated())
    items = ended(run(session, QUESTION, chain_with(session, QWEN)), "rerank")["items"]
    assert [(i["before"], i["score"]) for i in items[:2]] == [(2, 1.0), (1, 1.0)]


# ---------- the pair's format, read in the GGUF header ----------


def test_the_format_of_each_header():
    assert rerank_format(BGE_HEADER) == PAIR and PAIR.score_reading == "sigmoid"
    qwen = rerank_format(QWEN_HEADER)
    assert qwen == RerankFormat("template", TEMPLATE) and qwen.score_reading == "probability"
    assert rerank_format(None) == PAIR and rerank_format({}) == PAIR  # unread: the load judges
    # llama.cpp's metadata gives texts: the same verdicts.
    assert rerank_format({k: str(v).lower() for k, v in BGE_HEADER.items()}) == PAIR
    with pytest.raises(RerankerRefused) as refused:
        rerank_format({k: str(v) for k, v in MINILM_HEADER.items()})
    assert refused.value.message.key == "models.reranker.segments"


@pytest.mark.parametrize("arch", sorted(reranker_module.ENCODERS))
def test_an_encoder_converted_without_its_causal_key_takes_the_pair(arch):
    """BGE converted without `bert.attention.causal`: still a cross-encoder, never an LLM."""
    assert rerank_format({"general.architecture": arch}) == PAIR
    assert rerank_format({"general.architecture": arch, f"{arch}.pooling_type": 4}) == PAIR


@pytest.mark.parametrize(
    ("header", "key"),
    [
        (MINILM_HEADER, "models.reranker.segments"),
        # Causal (`{arch}.attention.causal` absent or true), no rerank template: an LLM.
        ({"general.architecture": "qwen3", "qwen3.pooling_type": 4}, "no_rerank_template"),
        (BGE_HEADER | {"bert.attention.causal": True}, "no_rerank_template"),
        ({"general.architecture": "qwen3"}, "no_rerank_template"),
        # A template without both fields is not one llama-server fills.
        (QWEN_HEADER | {"tokenizer.chat_template.rerank": "<Q>: {query}"}, "no_rerank_template"),
        (
            QWEN_HEADER | {"tokenizer.chat_template.rerank": "{query} {query} {document}"},
            "no_rerank_template",
        ),
        (QWEN_HEADER | {"qwen3.pooling_type": 3}, "embedding_pooling"),
    ],
)
def test_the_headers_refused(header, key):
    with pytest.raises(RerankerRefused) as refused:
        rerank_format(header)
    assert refused.value.message.key.endswith(key)


def test_the_synthetic_cross_encoder_of_one_token_type_scores_pairs_with_the_sigmoid():
    """`tiny-bert-rank.gguf` declares one token type, as BGE's GGUF: the pair, the sigmoid."""
    reranker = LlamaCppReranker(TINY, FIXTURES / "tiny-bert-rank.gguf")
    try:
        assert reranker.format == PAIR and reranker.score_reading == "sigmoid"
        assert reranker.max_tokens == 64
        logit = reranker._figure("mot de passe", "le mot de passe")[0]
        [score] = reranker.score("mot de passe", ["le mot de passe"])
    finally:
        reranker.close()
    assert score.score == pytest.approx(reranker_module.sigmoid(logit))


def test_the_synthetic_cross_encoder_with_segment_ids_is_refused_before_any_load(monkeypatch):
    import llama_cpp

    def never(**kwargs) -> None:  # noqa: ANN003
        raise AssertionError("llama.cpp must not load a refused file")

    monkeypatch.setattr(llama_cpp, "Llama", never)
    with pytest.raises(RerankerRefused) as refused:
        LlamaCppReranker(TINY, FIXTURES / "tiny-bert-rank-segments.gguf")
    assert refused.value.message.key == "models.reranker.segments"
    assert "llama.cpp ne transmet pas" in str(refused.value)
    assert "llama.cpp does not pass" in refused.value.render("en")


TINY = RerankerModel(
    id="tiny",
    backend="llama_cpp",
    label_text="Petit reranker synthétique",
    license="MIT",
    max_tokens=64,
    load_path="reranker/tiny.gguf",
    files=[{"url": "https://huggingface.co/d/t.gguf", "path": "reranker/tiny.gguf", "size": 1}],
)


def _fake_llama(monkeypatch, decoded: list, figure: float = 0.8) -> list:  # noqa: ANN001
    """A `llama_cpp` whose model tokenizes a word per token (the token is the word) and gives
    `figure` for each pair decoded, recorded in `decoded`; `tokenized` records each call."""
    tokenized: list[tuple[str, bool, bool]] = []

    class Batch:
        def reset(self) -> None:
            pass

        def add_sequence(self, tokens, seq, logits) -> None:  # noqa: ANN001
            decoded.append(list(tokens))

    class Ctx:
        ctx = object()

        def kv_cache_clear(self) -> None:
            pass

        def decode(self, batch) -> None:  # noqa: ANN001
            pass

    class Llama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.metadata: dict = {}
            self._model = types.SimpleNamespace(model=object())
            self._ctx, self._batch = Ctx(), Batch()

        def tokenize(self, data: bytes, add_bos: bool = True, special: bool = False) -> list:
            text = data.decode("utf-8")
            tokenized.append((text, add_bos, special))
            return text.split()

        def close(self) -> None:
            pass

    fake = types.SimpleNamespace(
        Llama=Llama,
        LLAMA_POOLING_TYPE_RANK=4,
        llama_model_get_vocab=lambda model: object(),
        llama_get_embeddings_seq=lambda ctx, seq: [figure],
    )
    monkeypatch.setitem(sys.modules, "llama_cpp", fake)
    return tokenized


def _template_model(tmp_path: Path, template: str, max_tokens: int = 64) -> LlamaCppReranker:
    path = write_gguf(
        tmp_path / "q.gguf", QWEN_HEADER | {"tokenizer.chat_template.rerank": template}
    )
    model = RerankerModel.model_validate(lab_entry(QWEN, max_tokens=max_tokens))
    return LlamaCppReranker(model, path)


def test_the_template_pair_is_one_sequence_its_special_tokens_parsed(monkeypatch, tmp_path):
    decoded: list = []
    tokenized = _fake_llama(monkeypatch, decoded)
    reranker = _template_model(tmp_path, "A {query} B {document} C")
    assert reranker.format.kind == "template" and reranker.score_reading == "probability"
    decoded.clear()
    tokenized.clear()
    [score] = reranker.score("deux mots", "trois mots ici".split("|"))
    assert decoded == [["A", "deux", "mots", "B", "trois", "mots", "ici", "C"]]
    assert tokenized == [("A deux mots B trois mots ici C", False, True)]  # one sequence
    assert score.score == pytest.approx(0.8) and not score.truncated  # no sigmoid (0.69)


def test_the_template_fills_its_fields_wherever_they_are(monkeypatch, tmp_path):
    decoded: list = []
    _fake_llama(monkeypatch, decoded)
    reranker = _template_model(tmp_path, "{document} puis {query}")
    decoded.clear()
    reranker.score("{document}", ["texte"])  # a field's name in the question stays text
    assert decoded == [["texte", "puis", "{document}"]]


def test_a_template_pair_too_long_cuts_the_document_only(monkeypatch, tmp_path):
    decoded: list = []
    _fake_llama(monkeypatch, decoded)
    reranker = _template_model(tmp_path, "A {query} B {document} C", max_tokens=9)
    decoded.clear()
    passage = " ".join(f"d{i}" for i in range(10))
    [score] = reranker.score("q1 q2", [passage])
    assert decoded == [["A", "q1", "q2", "B", "d0", "d1", "d2", "d3", "C"]]  # 9 tokens
    assert score.truncated


@pytest.mark.parametrize(("figure", "score"), [(1.7, 1.0), (-0.2, 0.0), (float("nan"), 0.0)])
def test_a_template_score_is_only_bounded(monkeypatch, tmp_path, figure, score):
    decoded: list = []
    _fake_llama(monkeypatch, decoded, figure=0.5)
    reranker = _template_model(tmp_path, "{query} {document}")
    assert reranker._score(figure) == score


def test_an_unread_header_is_judged_by_llama_cpp_s_metadata(monkeypatch, tmp_path):
    """A file the Python reader cannot read: llama.cpp's metadata (texts) says the format."""
    decoded: list = []
    _fake_llama(monkeypatch, decoded)
    import llama_cpp

    class Minilm(llama_cpp.Llama):  # type: ignore[misc, name-defined]
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            super().__init__(**kwargs)
            self.metadata = {k: str(v).lower() for k, v in MINILM_HEADER.items()}

    monkeypatch.setattr(llama_cpp, "Llama", Minilm)
    path = tmp_path / "not-a-header.gguf"
    path.write_bytes(b"\0" * 10)
    with pytest.raises(RerankerRefused) as refused:
        LlamaCppReranker(TINY, path)
    assert refused.value.message.key == "models.reranker.segments"


@pytest.mark.model
def test_real_qwen3_reranker_reads_its_template_and_a_probability(real_models_dir):
    model = config.load_config().rag_lab_reranker(QWEN)
    assert model is not None
    path = real_models_dir / model.load_path
    if not path.is_file():
        pytest.skip(f"modèle de reranking absent : {path}")
    reranker = LlamaCppReranker(model, path)
    try:
        assert reranker.score_reading == "probability"
        scores = reranker.score(
            "Quelle est la capitale de la France ?",
            [
                "Paris est la capitale et la plus grande ville de France.",
                "Le Rhin traverse Strasbourg et marque la frontière avec l'Allemagne.",
                "Berlin ist die Hauptstadt Deutschlands.",
            ],
        )
    finally:
        reranker.close()
    assert scores[0].score > 0.9 and max(s.score for s in scores[1:]) < 0.2  # essai : 1,0 / 0,0
