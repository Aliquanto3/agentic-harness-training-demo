"""Lot 5c-1: the RAG workshop's own embedding models (`[[rag_lab.embeddings]]`), each an
option of its Embedding stage with its slot and its vector cache; the truncation warning; the
embedding and reranking GGUF never offered as chat models.

The models are `FakeEmbedder`s (no file is read, no network); the GGUF headers are written by
`gguf_writer`.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
from fake_embedder import DIMS, MODEL_ID, FakeEmbedder
from gguf_writer import write_gguf
from test_rag import build, place_model
from test_rag_lab import QUESTION, ended, run, run_status, stage
from test_rag_rerank import place_reranker, rerank_config, session_for

from wavestack import config
from wavestack.messages import Message, render
from wavestack.models import catalog as model_catalog
from wavestack.models import discovery, gguf_meta
from wavestack.models.capabilities import capabilities_for
from wavestack.models.embedding import LlamaCppEmbedder
from wavestack.models.load_registry import EMBEDDING
from wavestack.rag import index as rag_index
from wavestack.rag import lab as rag_lab
from wavestack.rag.corpus import chunk_corpus, load_rag_content
from wavestack.session import diagnostic as diagnostic_module
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.trace.journal import get_journal

URL = "https://huggingface.co/demo/resolve/main/lab.gguf"
E5 = "multilingual-e5-small"
QWEN = "qwen3-embedding-0.6b"


@pytest.fixture
def index(tmp_path) -> Path:
    path = tmp_path / "rag_index.sqlite"
    build(path)
    return path


def lab_entry(model_id: str = E5, **changes: object) -> dict:
    """A `[[rag_lab.embeddings]]` entry for the tests: the fake model's 64 dimensions."""
    path = f"embedding/{model_id}.gguf"
    return {
        "id": model_id,
        "backend": "llama_cpp",
        "label_text": f"Faux {model_id}",
        "license": "MIT",
        "dims": DIMS,
        "max_tokens": 512,
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "load_path": path,
        "files": [{"url": URL, "path": path, "size": 1000}],
    } | changes


def lab_values(index: Path, *entries: dict, **kwargs: object) -> dict:
    values = rerank_config(index, **kwargs)
    values["rag_lab"] = {"embeddings": list(entries)}
    return values


def place_lab(model_id: str = E5) -> Path:
    path = config.models_dir() / f"embedding/{model_id}.gguf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * 1000)
    return path


def lab_session(values: dict, **kwargs) -> AppSession:  # noqa: ANN003
    """A booted session, the RAG brick off unless asked: the workshop loads its own models."""
    kwargs.setdefault("rerank", False)
    kwargs.setdefault("bricks", ())
    session, _ = session_for(values, **kwargs)
    return session


def options(session: AppSession, kind: str = "embedding") -> dict:
    stages = session.rag_lab_state()["catalog"]["stages"]
    return {o["id"]: o for o in next(s for s in stages if s["kind"] == kind)["options"]}


def chain_with(session: AppSession, option: str, *, size: int = 300) -> rag_lab.Pipeline:
    """The shipped chain, its embedding model `option`, another chunk size (the brick's index
    never serves) and the memory store."""
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    chain = catalog.default.model_copy(deep=True)
    stage(chain, "embedding").option = option
    stage(chain, "chunking").params["chunk_max_chars"] = size
    stage(chain, "vector_store").option = "memory"
    return chain


# ---------- the declaration ----------


def test_the_shipped_configuration_declares_e5_and_qwen3():
    models, errors = config.load_config().rag_lab_embeddings
    assert errors == []
    e5, qwen = models
    assert (e5.id, e5.dims, e5.max_tokens, e5.license) == (E5, 384, 512, "MIT")
    assert (e5.query_prefix, e5.passage_prefix) == ("query: ", "passage: ")
    assert e5.load_file.size == 132439008
    assert e5.load_file.sha256.startswith("e011debc")
    assert (qwen.id, qwen.dims, qwen.max_tokens, qwen.license) == (QWEN, 1024, 2048, "Apache-2.0")
    assert qwen.query_prefix.startswith("Instruct: ") and qwen.query_prefix.endswith("\nQuery:")
    assert qwen.passage_prefix == "" and qwen.load_file.sha256.startswith("06507c7b")
    assert (e5.measured_rss_mb, qwen.measured_rss_mb) == (440, 1055)
    for model in models:
        url = model.load_file.url
        commit = url.split("/resolve/")[1].split("/")[0]
        assert len(commit) == 40, url  # a full commit, never a branch
        assert model.load_path.startswith("embedding/")
    brick, _ = config.load_config().rag_embedding
    assert brick is not None and brick.id not in {m.id for m in models}


@pytest.mark.parametrize(
    ("entry", "said"),
    [
        (lab_entry("sans-dims", dims=None), "déclaration invalide (dims)"),
        (lab_entry("x" * 33), "dépasse 32 caractères"),
        (lab_entry("declared"), "déjà celui d'une option"),
        (lab_entry("fastembed"), "déjà celui d'une option"),
        (lab_entry(MODEL_ID), "déjà celui d'une option"),  # the brick's id
        (lab_entry(E5, label_text="Autre"), "porte déjà cet id"),
        (
            lab_entry(
                "ailleurs",
                load_path="autre/a.gguf",
                files=[{"url": URL, "path": "autre/a.gguf", "size": 1}],
            ),
            "sous embedding/",
        ),
    ],
)
def test_an_invalid_entry_is_left_out_with_its_reason_the_others_kept(index, entry, said):
    cfg = config.Config(values=lab_values(index, lab_entry(E5), entry, lab_entry(QWEN)))
    models, errors = cfg.rag_lab_embeddings
    assert [m.id for m in models] == [E5, QWEN]
    assert len(errors) == 1 and said in errors[0], errors
    assert "wavestack.toml" in render(errors[0], "en")
    assert "wavestack.toml" in render(errors[0], "de")


def test_a_path_without_parts_is_outside_embedding(index):
    """« . » passes the models folder's rule; it is no file under `embedding/`: left out,
    never an IndexError."""
    entry = lab_entry(E5, load_path=".", files=[{"url": URL, "path": ".", "size": 1}])
    models, errors = config.Config(values=lab_values(index, entry)).rag_lab_embeddings
    assert models == [] and len(errors) == 1 and "sous embedding/" in errors[0]


def test_the_reserved_ids_are_the_workshops_own_embedding_options():
    assert set(config.RAG_LAB_RESERVED_IDS) == set(rag_lab.OPTIONS["embedding"])


def test_an_id_of_32_characters_is_accepted(index):
    models, errors = config.Config(values=lab_values(index, lab_entry("x" * 32))).rag_lab_embeddings
    assert [m.id for m in models] == ["x" * 32] and errors == []


def test_settings_json_never_declares_a_workshop_model():
    shipped = config.load_config().get("rag_lab", "embeddings")
    config.save_setting(
        "rag_lab",
        {"embeddings": [lab_entry("pirate")], "fastembed": {"model_name": "a/b", "dims": 8}},
    )
    cfg = config.load_config()
    assert cfg.get("rag_lab", "embeddings") == shipped
    assert "pirate" not in {m.id for m in cfg.rag_lab_embeddings[0]}
    assert cfg.get("rag_lab", "fastembed", "model_name") == "a/b"  # settings.json still merges
    assert cfg.get("rag_lab", "faiss_cost_mb") == 60


def test_an_invalid_entry_is_traced_once(index):
    values = lab_values(index, lab_entry("declared"), lab_entry(E5))
    session = lab_session(values)
    mark = get_journal().last_seq()
    session.rag_lab_state()
    session.rag_lab_state()
    errors = [e for e in get_journal().events_since(mark) if e.kind == "harness_error"]
    assert len(errors) == 1 and "« declared » écarté" in errors[0].payload["message_text"]
    assert E5 in options(session)


# ---------- the options of the Embedding stage ----------


def test_each_declared_model_is_an_option_available_only_with_its_file(index):
    place_model()
    session = lab_session(lab_values(index, lab_entry(E5), lab_entry(QWEN)))
    found = options(session)
    assert list(found) == ["declared", "fastembed", E5, QWEN]
    assert found[E5]["label_text"] == f"Faux {E5}" and found[E5]["params"] == []
    for model_id in (E5, QWEN):
        assert not found[model_id]["available"]
        reason = found[model_id]["reason_text"]
        assert f"embedding/{model_id}.gguf" in reason and str(config.models_dir()) in reason
    place_lab(E5)
    found = options(session)
    assert found[E5]["available"] and found[E5]["reason_text"] is None
    assert not found[QWEN]["available"]
    # The presets and the shipped chain stay on the brick's model.
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    assert stage(catalog.default, "embedding").option == "declared"
    for key in rag_lab.PRESETS:
        assert stage(catalog.preset_pipeline(key), "embedding").option == "declared"


def test_a_model_whose_file_is_absent_is_refused_on_its_line(index):
    session = lab_session(lab_values(index, lab_entry(QWEN)))
    chain = chain_with(session, QWEN)
    catalog = session._rag_lab_catalog(rag_lab.load_lab_content())
    reason, stage_id = rag_lab.check_pipeline(chain, catalog)
    assert stage_id == stage(chain, "embedding").id
    assert "« Embedding »" in reason and f"embedding/{QWEN}.gguf" in reason
    mark = get_journal().last_seq()
    with pytest.raises(SendRefused) as refused:
        session.run_rag_lab(QUESTION, chain)
    assert f"embedding/{QWEN}.gguf" in refused.value.reason_text
    assert not [e for e in get_journal().events_since(mark) if e.kind.startswith("rag_lab")]


@pytest.mark.parametrize("lang", ["en", "de"])
def test_the_reason_of_a_missing_file_is_translated(index, lang):
    session = lab_session(lab_values(index, lab_entry(QWEN)))
    session.set_language(lang)
    reason = options(session)[QWEN]["reason_text"]
    assert f"embedding/{QWEN}.gguf" in reason and "Indisponible" not in reason
    assert reason == render(session._rag_lab_absent(session.cfg.rag_lab_embedding(QWEN)), lang)


# ---------- a run with a declared model ----------


def test_a_run_with_e5_loads_it_in_its_own_slot_and_frees_it(index):
    place_model()
    place_reranker()
    place_lab(E5)
    session = lab_session(lab_values(index, lab_entry(E5)), bricks=("rag",))  # brick: Granite
    embedders = session._embedder_factory
    brick_embedder = session._embedder
    registry = session._load_registry
    assert registry.holder(EMBEDDING) and brick_embedder is embedders.made[0]
    grants = []
    original = registry.grant
    registry.grant = lambda *a, **k: (grants.append(a[2]), original(*a, **k))  # type: ignore[method-assign]
    events = run(session, QUESTION, chain_with(session, E5))
    assert run_status(events) == "ok"
    embedding = ended(events, "embedding")
    assert embedding["status"] == "ok" and not embedding["borrowed"]
    facts = {f["label_text"]: f["value_text"] for f in embedding["facts"]}
    assert facts["Modèle"] == f"Faux {E5}"
    slot = f"rag_lab.embedding.{E5}"
    assert slot in grants and EMBEDDING not in grants  # never the brick's slot
    assert registry.holder(slot) is None  # freed at the run's end
    assert registry.holder(EMBEDDING) and session._embedder is brick_embedder  # brick intact
    assert not brick_embedder.closed
    lab = embedders.made[1]
    assert lab.model_id == E5 and lab.closed


def test_each_model_has_its_own_vector_cache(index):
    place_model()
    place_lab(E5)
    session = lab_session(lab_values(index, lab_entry(E5)))
    e5, granite = chain_with(session, E5), chain_with(session, "declared")
    assert "calculés" in ended(run(session, QUESTION, e5), "embedding")["output_text"]
    assert "calculés" in ended(run(session, QUESTION, granite), "embedding")["output_text"]
    assert "relus du cache" in ended(run(session, QUESTION, granite), "embedding")["output_text"]
    assert "relus du cache" in ended(run(session, QUESTION, e5), "embedding")["output_text"]
    folders = list(config.rag_lab_dir().iterdir())
    assert len(folders) == 2
    identities = sorted(
        json.loads((f / "chunks.json").read_text(encoding="utf-8"))["embedder"]["id"]
        for f in folders
    )
    assert identities == sorted([E5, MODEL_ID])


def test_the_cache_identity_names_the_prefixes_and_max_tokens(index):
    place_lab(E5)
    session = lab_session(lab_values(index, lab_entry(E5)))
    identity = session._rag_lab_identity(E5)
    assert identity == {
        "id": E5,
        "dims": DIMS,
        "size": 1000,
        "sha256": rag_lab.file_digest(config.models_dir() / f"embedding/{E5}.gguf"),
        "query_prefix": "query: ",
        "passage_prefix": "passage: ",
        "max_tokens": 512,
    }
    other = lab_session(lab_values(index, lab_entry(E5, passage_prefix="")))
    assert rag_lab.cache_key(identity, 300, "x") != rag_lab.cache_key(
        other._rag_lab_identity(E5), 300, "x"
    )


def test_the_budget_refuses_a_model_too_heavy_and_names_it(index):
    place_model()
    place_lab(QWEN)
    values = lab_values(index, lab_entry(QWEN, measured_rss_mb=5000), budget_mb=4096)
    session = lab_session(values, rss=200 * 1024**2)
    embedders = session._embedder_factory
    events = run(session, QUESTION, chain_with(session, QWEN))
    embedding = ended(events, "embedding")
    assert embedding["status"] == "error" and "Mémoire insuffisante" in embedding["error_text"]
    assert f"le modèle d'embedding Faux {QWEN}" in embedding["error_text"]
    assert (
        embedders.made == [] and session._load_registry.holder(f"rag_lab.embedding.{QWEN}") is None
    )


def test_a_file_of_another_sha256_is_refused_and_nothing_granted(index):
    place_lab(E5)
    files = [{"url": URL, "path": f"embedding/{E5}.gguf", "size": 1000, "sha256": "0" * 64}]
    session = lab_session(lab_values(index, lab_entry(E5, files=files)))
    events = run(session, QUESTION, chain_with(session, E5))
    embedding = ended(events, "embedding")
    assert embedding["status"] == "error" and "sha256" in embedding["error_text"]
    assert "rag_lab.embeddings" in embedding["error_text"]
    assert session._load_registry.holder(f"rag_lab.embedding.{E5}") is None


# ---------- the truncation warning ----------


class Truncating(FakeEmbedder):
    """A fake model of 512 tokens that says which passages it cut: those over 1 000
    characters."""

    max_tokens = 512

    def embed_passages(self, texts):  # noqa: ANN001, ANN201
        self.last_truncated = sum(len(t) > 1000 for t in texts)
        return super().embed_passages(texts)


def _truncating(session: AppSession) -> None:
    session._embedder_factory = lambda model: Truncating(model_id=model.id)


def test_chunks_longer_than_the_model_are_said_truncated(index):
    place_model()
    session = lab_session(lab_values(index))
    _truncating(session)
    chain = chain_with(session, "declared", size=1500)
    events = run(session, QUESTION, chain)
    embedding = ended(events, "embedding")
    assert embedding["status"] == "ok" and run_status(events) == "ok"  # a warning, no error
    chunks = chunk_corpus(load_rag_content(), 1500)
    long = sum(len(rag_index.passage_text(c)) > 1000 for c in chunks)
    assert long > 1
    expected = f"{long} chunks sur {len(chunks)} dépassent 512 tokens, tronqués"
    assert embedding["warning_text"].replace(" ", " ").startswith(expected)
    again = ended(run(session, QUESTION, chain), "embedding")  # read from the cache
    assert "relus du cache" in again["output_text"]
    assert again["warning_text"] == embedding["warning_text"]
    for other in ("vector_store", "context"):
        assert ended(events, other)["warning_text"] is None


class TruncatingOne(FakeEmbedder):
    """A fake model of 512 tokens that cut one passage only: the first it reads."""

    max_tokens = 512

    def embed_passages(self, texts):  # noqa: ANN001, ANN201
        self.last_truncated = 0 if getattr(self, "seen", False) else 1
        self.seen = True
        return super().embed_passages(texts)


@pytest.mark.parametrize(
    ("lang", "said"),
    [
        ("fr", "1 chunk sur {n} dépasse 512 tokens, tronqué : la fin de ce chunk"),
        ("en", "1 chunk out of {n} exceeds 512 tokens, truncated: the end of this chunk"),
        ("de", "1 Chunk von {n} überschreitet 512 Tokens, gekürzt: Das Ende dieses Chunks"),
    ],
)
def test_one_chunk_truncated_is_said_in_the_singular(index, lang, said):
    place_model()
    session = lab_session(lab_values(index))
    session.set_language(lang)
    session._embedder_factory = lambda model: TruncatingOne(model_id=model.id)
    events = run(session, QUESTION, chain_with(session, "declared", size=1500))
    n = len(chunk_corpus(load_rag_content(lang), 1500, lang))
    warning = ended(events, "embedding")["warning_text"].replace("\u202f", " ")
    assert warning.startswith(said.format(n=n)), warning


@pytest.mark.parametrize(
    ("lang", "said"),
    [("en", "exceed 512 tokens, truncated"), ("de", "überschreiten 512 Tokens, gekürzt")],
)
def test_the_truncation_warning_is_translated(index, lang, said):
    place_model()
    session = lab_session(lab_values(index))
    session.set_language(lang)
    _truncating(session)
    events = run(session, QUESTION, chain_with(session, "declared", size=1500))
    assert said in ended(events, "embedding")["warning_text"]


def test_no_warning_when_nothing_is_cut_or_the_model_does_not_say(index):
    place_model()
    session = lab_session(lab_values(index))
    _truncating(session)
    events = run(session, QUESTION, chain_with(session, "declared", size=300))
    assert ended(events, "embedding")["warning_text"] is None  # every chunk under 1 000
    session._embedder_factory = lambda model: FakeEmbedder(model_id=model.id)
    events = run(session, QUESTION, chain_with(session, "declared", size=1400))
    assert ended(events, "embedding")["warning_text"] is None  # no `max_tokens`: not said


def _fake_llama(monkeypatch, seen: list) -> None:  # noqa: ANN001
    class Llama:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.n_batch = kwargs["n_batch"]

        def n_embd(self) -> int:
            return DIMS

        def tokenize(self, data: bytes) -> list[int]:
            return list(range(len(data.decode("utf-8").split())))  # a token per word

        def embed(self, text, **kwargs):  # noqa: ANN001, ANN003
            seen.append(text)
            return [0.5] * DIMS

        def close(self) -> None:
            pass

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=Llama))


def test_the_llama_cpp_adapter_prefixes_and_counts_the_texts_it_cuts(monkeypatch, tmp_path):
    seen: list[str] = []
    _fake_llama(monkeypatch, seen)
    model = config.EmbeddingModel.model_validate(lab_entry(E5, max_tokens=4))
    embedder = LlamaCppEmbedder(model, tmp_path / "x.gguf")
    assert embedder.max_tokens == 4 and embedder.last_truncated is None
    seen.clear()
    embedder.embed_passages(["un deux", "un deux trois quatre", "court"])
    assert seen == ["passage: un deux", "passage: un deux trois quatre", "passage: court"]
    assert embedder.last_truncated == 1  # « passage: » counts: 5 words over 4
    embedder.embed_queries(["Quelle capitale ?"])
    assert seen[-1] == "query: Quelle capitale ?" and embedder.last_truncated == 0


# ---------- an embedding or reranking GGUF is never a chat model ----------


QWEN3_TEMPLATE = "<|im_start|>{{ messages }}<|im_end|>"


def _embedding_gguf(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_gguf(
        path,
        {
            "general.architecture": "qwen3",
            "general.name": "Qwen3-Embedding-0.6B",
            "qwen3.context_length": 32768,
            "qwen3.pooling_type": 3,
            "tokenizer.chat_template": QWEN3_TEMPLATE,
        },
    )


def test_capabilities_refuse_a_gguf_with_a_pooling_type(tmp_path):
    header = model_catalog.header_metadata(str(_embedding_gguf(tmp_path / "e.gguf")))
    assert header is not None and header[0].pooling_type == 3
    caps = capabilities_for(header[0])
    assert caps.incompatible_reason == Message("models.capabilities.pooling")
    assert caps.chat_template is None
    chat = write_gguf(
        tmp_path / "chat.gguf",
        {"general.architecture": "qwen3", "tokenizer.chat_template": QWEN3_TEMPLATE},
    )
    meta = model_catalog.header_metadata(str(chat))[0]
    assert meta.pooling_type is None and capabilities_for(meta).incompatible_reason is None


def test_a_pooling_type_of_0_is_a_generative_model(tmp_path):
    """llama.cpp's « none » (0) is a generative model's: neither refused nor marked."""
    path = write_gguf(
        tmp_path / "gen.gguf",
        {
            "general.architecture": "qwen3",
            "qwen3.pooling_type": 0,
            "tokenizer.chat_template": QWEN3_TEMPLATE,
        },
    )
    meta = model_catalog.header_metadata(str(path))[0]
    assert meta.pooling_type == 0 and capabilities_for(meta).incompatible_reason is None
    assert not diagnostic_module._embedding_or_reranking(str(path))
    assert diagnostic_module._embedding_or_reranking(str(_embedding_gguf(tmp_path / "e.gguf")))


def test_the_header_reader_can_stop_at_the_tokenizer(tmp_path):
    """Lot 5c-1: the header's head only (the diagnostic's pooling check); default unchanged."""
    path = write_gguf(
        tmp_path / "h.gguf",
        {
            "general.architecture": "qwen3",
            "qwen3.pooling_type": 3,
            "tokenizer.ggml.model": "gpt2",
            "tokenizer.chat_template": QWEN3_TEMPLATE,
            "zz.after": 1,
        },
    )
    whole = gguf_meta.read_metadata(path)
    assert list(whole) == [
        "general.architecture",
        "qwen3.pooling_type",
        "tokenizer.ggml.model",
        "tokenizer.chat_template",
        "zz.after",
    ]
    head = gguf_meta.try_read_metadata(path, stop_at="tokenizer.")
    assert head == {"general.architecture": "qwen3", "qwen3.pooling_type": 3}
    assert gguf_meta.try_read_metadata(path) == whole


def test_the_workshops_files_are_never_offered_as_chat_models(index, monkeypatch):
    cfg = config.Config(
        values=lab_values(
            index,
            lab_entry(
                E5,
                load_path="embedding/sub/e5.gguf",
                files=[{"url": URL, "path": "embedding/sub/e5.gguf", "size": 1}],
            ),
        )
    )
    files = discovery._rag_model_files(cfg)
    assert discovery._key(config.models_dir() / "embedding/sub/e5.gguf") in files


def test_an_embedding_gguf_in_the_hf_cache_is_incompatible_never_chosen(monkeypatch, tmp_path):
    from test_cli_diagnostic import _build

    session, _ = _build(monkeypatch, tmp_path, models=("chat.gguf",))
    hf = tmp_path / "no-hf-cache"
    embedding = _embedding_gguf(hf / "models--Qwen--Qwen3-Embedding-0.6B-GGUF" / "q.gguf")
    result = session.check_model()
    assert result.ready and result.model_path == str(config.models_dir() / "chat.gguf")
    candidate = next(c for c in result.candidates if c.path == str(embedding))
    assert candidate.status == "incompatible" and candidate.source == "hf_cache"
    assert discovery.reason_message(candidate.reason) == Message("models.capabilities.pooling")
    [entry] = [
        e
        for e in model_catalog.local_entries([candidate], session.cfg)
        if e.gguf_path == str(embedding)
    ]
    assert not entry.usable and "modèle d'embedding ou de reranking" in entry.disabled_text
    english = model_catalog.local_entries([candidate], session.cfg, lang="en")[0]
    assert "embedding or reranking model" in english.disabled_text
