"""Story 30, increment 3: FAISS and LanceDB, the RAG workshop's vector stores of the optional
`rag-alt` extra (AD-8, AD-15, AD-20).

Without the extra (or with `find_spec` answering `None`), both options are unavailable with
the command that installs them. With it (`uv run --extra compression --extra rag-alt pytest
tests/test_rag_lab_alt.py`), they rank as the exhaustive search in memory, under the
network guard of `conftest.py`.
"""

from __future__ import annotations

import importlib

import pytest
from test_rag import place_model
from test_rag_lab import (
    QUESTION,
    chains,
    ended,
    index,  # noqa: F401 - the fixture
    lab_session,
    ready,
    run,
    run_status,
    stage,
)
from test_rag_rerank import place_reranker, rerank_config

from wavestack import config
from wavestack.rag import lab as rag_lab
from wavestack.session.app_session import SendRefused

INSTALL = "uv sync --extra compression --extra rag-alt"


def options(session) -> dict:  # noqa: ANN001
    return {
        (s["kind"], o["id"]): o
        for s in session.rag_lab_state()["catalog"]["stages"]
        for o in s["options"]
    }


@pytest.fixture
def without_extra(monkeypatch):
    real = rag_lab._find_spec
    monkeypatch.setattr(
        rag_lab, "_find_spec", lambda name: None if name in ("faiss", "lancedb") else real(name)
    )


@pytest.mark.parametrize(("option", "label"), [("faiss", "FAISS"), ("lancedb", "LanceDB")])
def test_unavailable_without_the_extra_with_the_command(index, without_extra, option, label):  # noqa: F811
    session, _ = ready(index)
    state = options(session)[("vector_store", option)]
    assert not state["available"] and state["label_fr"] == label
    assert INSTALL in state["reason_fr"] and f"{label} n'est pas installé" in state["reason_fr"]
    assert "Headroom serait retiré" in state["reason_fr"]
    catalog, a, b = chains(session)
    stage(b, "chunking").params["chunk_max_chars"] = 300
    stage(b, "vector_store").option = option
    with pytest.raises(SendRefused) as refused:
        session.run_rag_lab(QUESTION, [a, b])
    assert INSTALL in refused.value.reason_fr and "« Base vectorielle »" in refused.value.reason_fr


def _faiss_chain(session):  # noqa: ANN001, ANN202
    catalog, a, b = chains(session)
    stage(b, "chunking").params["chunk_max_chars"] = 300
    stage(b, "vector_store").option = "faiss"
    return a, b


def test_the_budget_refuses_the_import(index, monkeypatch):  # noqa: F811
    monkeypatch.setattr(rag_lab, "_find_spec", lambda name: object())  # said installed
    place_model()
    place_reranker()
    values = rerank_config(index, budget_mb=100)
    session, _ = lab_session(values, rss=50 * 1024**2)
    a, b = _faiss_chain(session)
    events = run(session, QUESTION, [a, b])
    store = ended(events, "vector_store", "b")
    assert (
        store["status"] == "error"
        and "Mémoire insuffisante pour charger FAISS" in store["error_fr"]
    )
    assert ended(events, "vector_store", "a")["status"] == "ok"  # lane A untouched
    assert session._load_registry.holder("rag_lab.faiss") is None
    assert "faiss" not in session._rag_lab_imported


def test_an_import_refused_is_said_in_french_then_unavailable(index, monkeypatch):  # noqa: F811
    monkeypatch.setattr(rag_lab, "_find_spec", lambda name: object())
    real = importlib.import_module

    def refuse(name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if name == "faiss":
            raise ImportError("DLL load failed while importing _swigfaiss: accès refusé")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", refuse)
    session, _ = ready(index)
    a, b = _faiss_chain(session)
    events = run(session, QUESTION, [a, b])
    store = ended(events, "vector_store", "b")
    assert store["status"] == "error"
    assert store["error_fr"].startswith("Import refusé : FAISS n'a pas pu être chargé (ImportError")
    assert "AppLocker" in store["error_fr"]
    assert run_status(events) == "error" and session.state == "idle"
    state = options(session)[("vector_store", "faiss")]
    assert not state["available"] and "Import refusé" in state["reason_fr"]
    with pytest.raises(SendRefused):
        session.run_rag_lab(QUESTION, [a, b])


@pytest.mark.parametrize("option", ["faiss", "lancedb"])
def test_ranks_as_the_memory_search(index, option):  # noqa: F811
    pytest.importorskip(option)
    session, _ = ready(index)
    catalog, a, b = chains(session)
    for chain in (a, b):
        stage(chain, "chunking").params["chunk_max_chars"] = 300
    stage(a, "vector_store").option = "memory"
    stage(b, "vector_store").option = option
    label = rag_lab.LIBRARIES[option][1]
    for i, question in enumerate(
        (QUESTION, "Quel plafond pour une nuit d'hôtel à Paris ?", QUESTION)
    ):
        events = run(session, question, [a, b])
        store = ended(events, "vector_store", "b")
        assert store["status"] == "ok", store["error_fr"]
        facts = {f["label_fr"]: f["value_fr"] for f in store["facts"]}
        if i == 0:
            assert f"Index {label} construit (77 vecteurs)" in store["output_fr"]
            assert facts["Import"].startswith("premier import : +")
        else:
            assert f"Index {label} relu (77 vecteurs)" in store["output_fr"]
            assert facts["Import"].startswith("déjà fait")
        searched = [ended(events, "vector_search", lane)["items"] for lane in "ab"]
        assert [(x["chunk_id"], x["score"]) for x in searched[0]] == [
            (x["chunk_id"], x["score"]) for x in searched[1]
        ]
        contexts = [ended(events, "context", lane)["items"] for lane in "ab"]
        assert [x["chunk_id"] for x in contexts[0]] == [x["chunk_id"] for x in contexts[1]]
    slot = f"rag_lab.{option}"
    assert session._load_registry.holder(slot) == label  # counted for life, never released
    folder = next(config.rag_lab_dir().iterdir())
    assert (folder / ("faiss" if option == "faiss" else "lancedb")).exists()
    assert not list(config.rag_lab_dir().rglob("*.tmp"))
