"""Builds the RAG index (story 15, AD-22): the corpus of `content/`, chunked and embedded
offline with the model `[rag.embedding]` names, written into `[rag] index_path`. The RAG
card of WaveStack does the same (« Construire l'index »).

    uv run python scripts/build_rag_index.py [--download] [--model CHEMIN_DU_GGUF]

The network guard is installed first: loopback only, or, with `--download`, the hosts of
`[net] allowed_hosts` (huggingface.co, *.hf.co) to fetch the model's files beforehand.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from wavestack import config as _config
from wavestack.net.guard import install as _install_guard

# AD-15: before any third-party import; the network only for `--download`.
_install_guard(_config.load_config().allowed_hosts if "--download" in sys.argv[1:] else [])

from pydantic import ValidationError  # noqa: E402

from wavestack import config  # noqa: E402
from wavestack.models import download  # noqa: E402
from wavestack.models.embedding import LlamaCppEmbedder, model_path  # noqa: E402
from wavestack.models.engine import CancelToken  # noqa: E402
from wavestack.rag.corpus import load_rag_content  # noqa: E402
from wavestack.rag.index import (  # noqa: E402
    IndexInUse,
    VecUnavailable,
    build_index,
    file_sha256,
)

BUILD_FROM_THE_CARD_FR = (
    "Construisez-le depuis la carte RAG, ou arrêtez WaveStack, puis relancez ce script."
)


def _fail(message: str, code: int = 2) -> int:
    print(message, file=sys.stderr)
    return code


def _mo(n: int) -> str:
    return f"{round(n / 1_000_000)}"


def main(argv: list[str] | None = None, embedder_factory=LlamaCppEmbedder) -> int:  # noqa: ANN001
    parser = argparse.ArgumentParser(
        description="Construit l'index RAG (sqlite-vec) du corpus de démonstration."
    )
    parser.add_argument(
        "--model",
        type=Path,
        help="Chemin du GGUF d'embedding (par défaut : load_path de [rag.embedding], "
        "dans le dossier des modèles). Il doit être le fichier déclaré (même taille, même "
        "sha256 s'il est renseigné).",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Télécharge d'abord les fichiers manquants de [rag.embedding].",
    )
    args = parser.parse_args(argv)
    cfg = config.load_config()
    model, error_fr = cfg.rag_embedding
    if model is None:
        return _fail(error_fr or "La section [rag.embedding] est invalide.")
    try:
        content = load_rag_content()
    except (OSError, ValueError, ValidationError) as exc:
        return _fail(f"Le fichier content/rag.yaml est absent ou invalide : {exc}")
    if args.download:
        missing = download.missing_files(model.files, config.models_dir())
        if missing:
            print(f"Téléchargement de {len(missing)} fichier(s) dans {config.models_dir()}…")
            try:
                download.download_files(missing, config.models_dir(), CancelToken(), _dots)
            except download.DownloadError as exc:
                return _fail(f"\nTéléchargement impossible : {exc.reason_fr}.")
            print()
    path = args.model or model_path(model)
    if not path.is_file():
        return _fail(
            f"Modèle d'embedding introuvable : {path}. Relancez avec --download, ou copiez-le "
            f"à cet endroit ({model.load_file.url}), ou passez --model CHEMIN."
        )
    declared = model.load_file
    size = path.stat().st_size
    if size != declared.size:
        return _fail(
            f"{path} n'est pas le modèle déclaré dans [rag.embedding] : {size} octets au lieu "
            f"de {declared.size}. L'index porterait l'identifiant « {model.id} » à tort."
        )
    if declared.sha256 and file_sha256(path) != declared.sha256.lower():
        return _fail(f"{path} n'est pas le modèle déclaré : sha256 différent de [rag.embedding].")
    started = time.monotonic()
    print(f"Chargement du modèle d'embedding {model.label_fr} ({path})…")
    try:
        embedder = embedder_factory(model, path)
    except (ValueError, OSError) as exc:
        return _fail(f"Modèle d'embedding inutilisable : {exc}.")
    target = cfg.rag_index_path()
    try:
        meta = build_index(
            content,
            embedder,
            target,
            cfg.rag_chunk_max_chars,
            on_progress=lambda i, n: print(f"\r  extrait {i} / {n}", end="", flush=True),
            model_file=path,
        )
    except IndexInUse as exc:  # held open (Windows): its message, then what to do
        return _fail(f"\n{exc} {BUILD_FROM_THE_CARD_FR}", 1)
    except (ValueError, OSError, sqlite3.Error, VecUnavailable) as exc:
        return _fail(f"\nIndex non construit : {exc}.", 1)
    finally:
        embedder.close()
    print(
        f"\nIndex écrit : {target}\n"
        f"  documents : {len(content.documents)}\n"
        f"  extraits : {meta.chunks} (au plus {meta.chunk_max_chars} caractères)\n"
        f"  modèle : {meta.embedding_model_id}, {meta.dims} dimensions, "
        f"{_mo(meta.model_size)} Mo, sha256 {meta.model_sha256}\n"
        f"  durée : {time.monotonic() - started:.1f} s"
    )
    return 0


def _dots(done: int, total: int) -> None:
    print(f"\r  {_mo(done)} / {_mo(total)} Mo", end="", flush=True)


if __name__ == "__main__":
    sys.exit(main())
