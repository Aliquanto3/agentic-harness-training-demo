"""Builds the RAG index (story 15, AD-22): the corpus of `content/`, chunked and embedded
offline with the model `[rag.embedding]` names, written into `[rag] index_path`.

    uv run python scripts/build_rag_index.py [--model CHEMIN_DU_GGUF]

The network guard is installed first, loopback only: nothing leaves the workstation.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from wavestack.net.guard import install as _install_guard

_install_guard(allowed_hosts=[])  # AD-15: before any third-party import

from wavestack import config  # noqa: E402
from wavestack.models.embedding import LlamaCppEmbedder, model_path  # noqa: E402
from wavestack.rag.corpus import load_rag_content  # noqa: E402
from wavestack.rag.index import build_index  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Construit l'index RAG (sqlite-vec) du corpus de démonstration."
    )
    parser.add_argument(
        "--model",
        type=Path,
        help="Chemin du GGUF d'embedding (par défaut : load_path de [rag.embedding], "
        "dans le dossier des modèles).",
    )
    args = parser.parse_args(argv)
    cfg = config.load_config()
    model, error_fr = cfg.rag_embedding
    if model is None:
        print(error_fr, file=sys.stderr)
        return 2
    path = args.model or model_path(model)
    if not path.is_file():
        print(
            f"Modèle d'embedding introuvable : {path}. Téléchargez-le ({model.files[0].url}) "
            "et copiez-le à cet endroit, ou passez --model CHEMIN.",
            file=sys.stderr,
        )
        return 2
    content = load_rag_content()
    started = time.monotonic()
    print(f"Chargement du modèle d'embedding {model.label_fr} ({path})…")
    try:
        embedder = LlamaCppEmbedder(model, path)
    except ValueError as exc:
        print(f"Modèle d'embedding inutilisable : {exc}.", file=sys.stderr)
        return 2
    target = cfg.rag_index_path()
    try:
        meta = build_index(
            content,
            embedder,
            target,
            cfg.rag_chunk_max_chars,
            on_progress=lambda i, n: print(f"\r  extrait {i} / {n}", end="", flush=True),
        )
    except ValueError as exc:
        print(f"\nIndex non construit : {exc}.", file=sys.stderr)
        return 1
    finally:
        embedder.close()
    print(
        f"\nIndex écrit : {target}\n"
        f"  documents : {len(content.documents)}\n"
        f"  extraits : {meta.chunks} (au plus {meta.chunk_max_chars} caractères)\n"
        f"  modèle : {meta.embedding_model_id}, {meta.dims} dimensions\n"
        f"  durée : {time.monotonic() - started:.1f} s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
