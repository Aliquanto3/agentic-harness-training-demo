"""Story 30, increment 3: FAISS and LanceDB, the RAG workshop's vector stores of the optional
`rag-alt` extra (AD-8, AD-15, AD-20).

Without the extra (or with `find_spec` answering `None`), both options are unavailable with
the command that installs them. With it (`uv run --extra compression --extra rag-alt pytest
tests/test_rag_lab_alt.py`), they rank as the exhaustive search in memory, under the
network guard of `conftest.py`.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import json
import sys
import types
from pathlib import Path

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


# ---------- fake `faiss` and `lancedb` modules: the import and the stores, without the extra


class FakeFaissIndex:
    def __init__(self, d: int, vectors: list | None = None) -> None:
        self.d = d
        self.vectors = vectors or []

    @property
    def ntotal(self) -> int:
        return len(self.vectors)

    def add(self, matrix) -> None:  # noqa: ANN001
        self.vectors += [[float(x) for x in row] for row in matrix]

    def search(self, queries, k: int):  # noqa: ANN001, ANN201
        import numpy

        query = [float(x) for x in queries[0]]
        scores = [sum(a * b for a, b in zip(query, v, strict=True)) for v in self.vectors]
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        return numpy.array([[scores[i] for i in order]]), numpy.array([order])


def fake_faiss() -> types.ModuleType:
    module = types.ModuleType("faiss")
    module.__spec__ = importlib.machinery.ModuleSpec("faiss", None)
    module.IndexFlatIP = FakeFaissIndex

    def write_index(built, path: str) -> None:  # noqa: ANN001
        Path(path).write_text(json.dumps({"d": built.d, "v": built.vectors}))

    def read_index(path: str) -> FakeFaissIndex:
        data = json.loads(Path(path).read_text())
        return FakeFaissIndex(data["d"], data["v"])

    module.write_index, module.read_index = write_index, read_index
    return module


class FakeLanceTable:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def count_rows(self) -> int:
        return len(self.rows)

    def head(self, n: int) -> types.SimpleNamespace:
        return types.SimpleNamespace(to_pylist=lambda: self.rows[:n])

    def search(self, vector, vector_column_name: str):  # noqa: ANN001, ANN201
        assert vector_column_name == "vector"
        table = self

        class Query:
            def distance_type(self, kind: str):  # noqa: ANN202
                assert kind == "cosine"
                return self

            def limit(self, k: int):  # noqa: ANN202
                self.k = k
                return self

            def to_list(self) -> list[dict]:
                found = []
                for row in table.rows:
                    dot = sum(a * b for a, b in zip(vector, row["vector"], strict=True))
                    distance = float("nan") if row["id"] == 99 else 1.0 - dot
                    found.append(row | {"_distance": distance})
                return sorted(found, key=lambda r: r["_distance"])[: self.k]

        return Query()


def fake_lancedb() -> types.ModuleType:
    module = types.ModuleType("lancedb")
    module.__spec__ = importlib.machinery.ModuleSpec("lancedb", None)

    class Db:
        def __init__(self, path: str) -> None:
            self.path = Path(path)

        def create_table(self, name: str, data: list, mode: str) -> FakeLanceTable:
            self.path.mkdir(parents=True, exist_ok=True)
            (self.path / f"{name}.json").write_text(json.dumps(data))
            return FakeLanceTable(data)

        def open_table(self, name: str) -> FakeLanceTable:
            return FakeLanceTable(json.loads((self.path / f"{name}.json").read_text()))

    module.connect = Db
    return module


def test_the_stores_convert_ids_and_scores(tmp_path):
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]]
    store = rag_lab.FaissStore(fake_faiss(), tmp_path, vectors)
    assert store.built and store.search([1.0, 0.0], 2) == [(1, 1.0), (3, 0.6)]  # ids from 0
    assert not rag_lab.FaissStore(fake_faiss(), tmp_path, vectors).built  # read again
    lance = rag_lab.LanceStore(fake_lancedb(), tmp_path, vectors)
    assert lance.built and lance.search([1.0, 0.0], 2) == [(1, 1.0), (3, 0.6)]  # 1 − distance
    assert not rag_lab.LanceStore(fake_lancedb(), tmp_path, vectors).built
    wider = [v + [0.0] for v in vectors]  # another dimension: rebuilt, never read
    assert rag_lab.LanceStore(fake_lancedb(), tmp_path, wider).built
    assert not (tmp_path / "lancedb.tmp").exists()
    nan = rag_lab.LanceStore(fake_lancedb(), tmp_path / "nan", [[1.0, 0.0]])
    nan._table.rows[0]["id"] = 99  # its distance is NaN: a score of 0, never a crash
    assert nan.search([1.0, 0.0], 1) == [(99, 0.0)]


@pytest.mark.parametrize(
    ("option", "label", "make"),
    [("faiss", "FAISS", fake_faiss), ("lancedb", "LanceDB", fake_lancedb)],
)
def test_the_first_import_is_counted_for_life_with_fake_modules(
    index,  # noqa: F811
    monkeypatch,
    option,
    label,
    make,
):
    monkeypatch.setitem(sys.modules, option, make())
    monkeypatch.setattr(rag_lab, "_find_spec", lambda name: object())
    session, _ = ready(index)
    catalog, a, b = chains(session)
    for chain in (a, b):
        stage(chain, "chunking").params["chunk_max_chars"] = 300
    stage(a, "vector_store").option = "memory"
    stage(b, "vector_store").option = option
    first = run(session, QUESTION, [a, b])
    store = ended(first, "vector_store", "b")
    facts = {f["label_fr"]: f["value_fr"] for f in store["facts"]}
    assert (
        store["status"] == "ok" and f"Index {label} construit (77 vecteurs)" in store["output_fr"]
    )
    assert facts["Import"].startswith("premier import") and "réservés à vie" in facts["Budget"]
    assert session._load_registry.holder(f"rag_lab.{option}") == label
    searched = [ended(first, "vector_search", lane)["items"] for lane in "ab"]
    assert [i["chunk_id"] for i in searched[0]] == [i["chunk_id"] for i in searched[1]]
    second = run(session, QUESTION, [a, b])
    store = ended(second, "vector_store", "b")
    facts = {f["label_fr"]: f["value_fr"] for f in store["facts"]}
    assert f"Index {label} relu (77 vecteurs)" in store["output_fr"]
    assert facts["Import"].startswith("déjà fait")
    assert session._load_registry.holder(f"rag_lab.{option}") == label  # never released


def test_a_broken_install_is_recorded_then_unavailable(index, monkeypatch):  # noqa: F811
    monkeypatch.setattr(rag_lab, "_find_spec", lambda name: object())
    real = importlib.import_module

    def broken(name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if name == "faiss":
            raise RuntimeError("module compiled against ABI version 0x1000009")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", broken)
    session, _ = ready(index)
    a, b = _faiss_chain(session)
    events = run(session, QUESTION, [a, b])
    store = ended(events, "vector_store", "b")
    assert store["status"] == "error" and store["error_fr"].startswith("Import en échec : FAISS")
    state = options(session)[("vector_store", "faiss")]
    assert not state["available"] and "Import en échec" in state["reason_fr"]
