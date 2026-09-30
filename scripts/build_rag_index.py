"""Builds the RAG index (story 15, AD-22): the corpus of `content/`, chunked and embedded
offline with the model `[rag.embedding]` names, written into `[rag] index_path`. The RAG
card of WaveStack does the same (« Construire l'index »). Languages (4/5): `--lang` (`fr` by
default, never read from `settings.json`) picks the corpus and its titles
(`content/i18n/{lang}/`) and the index (`rag_index.{lang}.sqlite` outside French).
Languages (5/5): what it prints is always English (`content/messages.yaml`, section
`build_rag_index`, read in `en`), whatever `--lang` and `settings.json` say.

    uv run python scripts/build_rag_index.py [--lang fr|en|de] [--download] [--model CHEMIN]

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
from wavestack.messages import msg, render  # noqa: E402
from wavestack.models import download  # noqa: E402
from wavestack.models.embedding import LlamaCppEmbedder, model_path  # noqa: E402
from wavestack.models.engine import CancelToken  # noqa: E402
from wavestack.rag.corpus import load_rag_content  # noqa: E402
from wavestack.rag.index import (  # noqa: E402
    IndexInUse,
    VecUnavailable,
    build_index,
    exception_text,
    file_sha256,
)

TERMINAL = "en"  # the terminal's language (languages 5/5), never `settings.json`'s


def _en(key: str, **kw: object) -> str:
    """`build_rag_index.{key}`, in English."""
    return msg(f"build_rag_index.{key}", TERMINAL, **kw)


BUILD_FROM_THE_CARD_FR = _en("from_the_card")  # the name kept; English since languages 5/5


def _fail(message: str, code: int = 2) -> int:
    print(message, file=sys.stderr)
    return code


def _mo(n: int) -> str:
    return f"{round(n / 1_000_000)}"


def main(argv: list[str] | None = None, embedder_factory=LlamaCppEmbedder) -> int:  # noqa: ANN001
    parser = argparse.ArgumentParser(description=_en("description"))
    parser.add_argument("--model", type=Path, help=_en("help_model"))
    parser.add_argument("--download", action="store_true", help=_en("help_download"))
    parser.add_argument(
        "--lang",
        choices=config.LANGUAGES,
        default=config.DEFAULT_LANGUAGE,
        help=_en("help_lang"),
    )
    args = parser.parse_args(argv)
    cfg = config.load_config()
    model, error_text = cfg.rag_embedding
    if model is None:
        return _fail(render(error_text, TERMINAL) if error_text else _en("embedding_invalid"))
    try:
        content = load_rag_content(args.lang)
    except (OSError, ValueError, ValidationError) as exc:
        rel = config.content_file("rag.yaml", args.lang).relative_to(config.repo_root())
        return _fail(_en("content_invalid", path=rel.as_posix(), cause=exc))
    if args.download:
        missing = download.missing_files(model.files, config.models_dir())
        if missing:
            print(_en("downloading", count=len(missing), folder=config.models_dir()))
            try:
                download.download_files(missing, config.models_dir(), CancelToken(), _dots)
            except download.DownloadError as exc:
                reason = render(exc.reason_text, TERMINAL)
                return _fail("\n" + _en("download_failed", reason=reason))
            print()
    path = args.model or model_path(model)
    if not path.is_file():
        return _fail(_en("model_missing", path=path, url=model.load_file.url))
    declared = model.load_file
    size = path.stat().st_size
    if size != declared.size:
        return _fail(
            _en("wrong_size", path=path, size=size, expected=declared.size, model=model.id)
        )
    if declared.sha256 and file_sha256(path) != declared.sha256.lower():
        return _fail(_en("wrong_sha256", path=path))
    started = time.monotonic()
    print(_en("loading", model=model.label_text, path=path))
    try:
        embedder = embedder_factory(model, path)
    except (ValueError, OSError) as exc:
        return _fail(_en("model_unusable", cause=exception_text(exc, TERMINAL)))
    target = cfg.rag_index_path(args.lang)
    try:
        meta = build_index(
            content,
            embedder,
            target,
            cfg.rag_chunk_max_chars,
            on_progress=lambda i, n: print(
                "\r" + _en("progress", done=i, total=n), end="", flush=True
            ),
            model_file=path,
            lang=args.lang,
        )
    except IndexInUse as exc:  # held open (Windows): its message, then what to do
        return _fail(f"\n{exc.render(TERMINAL)} {BUILD_FROM_THE_CARD_FR}", 1)
    except (ValueError, OSError, sqlite3.Error, VecUnavailable) as exc:
        return _fail("\n" + _en("not_built", cause=exception_text(exc, TERMINAL)), 1)
    finally:
        embedder.close()
    lines = [
        _en("written", path=target),
        _en("documents", count=len(content.documents)),
        _en("extracts", count=meta.chunks, max=meta.chunk_max_chars),
        _en(
            "model",
            model=meta.embedding_model_id,
            dims=meta.dims,
            size=_mo(meta.model_size),
            sha256=meta.model_sha256,
        ),
        _en("duration", seconds=f"{time.monotonic() - started:.1f}"),
    ]
    print("\n" + "\n".join(lines))
    return 0


def _dots(done: int, total: int) -> None:
    print("\r" + _en("download_progress", done=_mo(done), total=_mo(total)), end="", flush=True)


if __name__ == "__main__":
    sys.exit(main())
