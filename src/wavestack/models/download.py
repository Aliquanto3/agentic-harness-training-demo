"""Model file download (story 15, AD-15, AD-21): the traced client of `net`, no hub library.

Each file is streamed into `*.part`, its size (and its sha256 when declared) checked, then
renamed. Redirects are followed hop by hop, each hop checked again by the factory (allowed
host, traced as `origin = download`) and here (https, http on the loopback only), as the
network tools do. Any failure removes the `.part` and raises `DownloadError` in French.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx

from wavestack.config import EmbeddingFile
from wavestack.models.engine import CancelToken
from wavestack.net.factory import create_client
from wavestack.net.guard import NetworkBlocked, find_blocked, is_loopback
from wavestack.trace.scope import scoped

CHUNK_BYTES = 1024 * 1024
TIMEOUT = httpx.Timeout(30.0, read=60.0)


class DownloadError(Exception):
    """A download that did not complete: `reason_fr` says why, in French."""

    def __init__(self, reason_fr: str, *, cancelled: bool = False) -> None:
        super().__init__(reason_fr)
        self.reason_fr = reason_fr
        self.cancelled = cancelled


def missing_files(files: Sequence[EmbeddingFile], dest: Path) -> list[EmbeddingFile]:
    """The declared files not yet in `dest`."""
    return [f for f in files if not (dest / f.path).is_file()]


def _check_hop(request: httpx.Request) -> None:
    url = request.url
    if url.scheme != "https" and not (url.scheme == "http" and is_loopback(url.host)):
        raise NetworkBlocked(f"adresse non https refusée : {url}")


def download_files(
    files: Sequence[EmbeddingFile],
    dest: Path,
    cancel: CancelToken,
    on_progress: Callable[[int, int], None],
    *,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Download `files` into `dest` (their `path` under it). `on_progress(done, total)` in
    bytes, for all the files. Raises `DownloadError` (`cancelled` when `cancel` fired)."""
    total = sum(f.size for f in files)
    done = 0
    for file in files:
        target = dest / file.path
        part = target.with_name(target.name + ".part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            done = _download_one(file, part, cancel, on_progress, done, total, transport)
            os.replace(part, target)
        except DownloadError:
            part.unlink(missing_ok=True)
            raise
        except OSError as exc:
            part.unlink(missing_ok=True)
            raise DownloadError(f"écriture impossible de {part} ({exc})") from None
        except BaseException:
            part.unlink(missing_ok=True)
            raise


def _download_one(
    file: EmbeddingFile,
    part: Path,
    cancel: CancelToken,
    on_progress: Callable[[int, int], None],
    done: int,
    total: int,
    transport: httpx.BaseTransport | None,
) -> int:
    digest = hashlib.sha256()
    written = 0
    try:
        with scoped(origin="download"), create_client(timeout=TIMEOUT, transport=transport) as c:
            c.event_hooks["request"].insert(0, _check_hop)
            with c.stream("GET", file.url, follow_redirects=True) as response:
                if response.status_code >= 400:
                    raise DownloadError(
                        f"le serveur a répondu {response.status_code} "
                        f"({response.reason_phrase}) pour {response.url}"
                    )
                with part.open("wb") as out:
                    for chunk in response.iter_bytes(CHUNK_BYTES):
                        if cancel.cancelled:
                            raise DownloadError("téléchargement arrêté", cancelled=True)
                        out.write(chunk)
                        digest.update(chunk)
                        written += len(chunk)
                        if written > file.size:
                            raise DownloadError(
                                f"le fichier reçu dépasse la taille déclarée ({file.size} octets)"
                            )
                        on_progress(done + written, total)
    except DownloadError:
        raise
    except httpx.TooManyRedirects:
        raise DownloadError("trop de redirections") from None
    except (NetworkBlocked, httpx.HTTPError) as exc:
        blocked = find_blocked(exc)
        if blocked is not None:
            raise DownloadError(f"connexion refusée par le harnais ({blocked})") from None
        raise DownloadError(
            f"serveur injoignable ({type(exc).__name__}) : le poste n'a pas accès à "
            f"{httpx.URL(file.url).host}"
        ) from None
    if written != file.size:
        raise DownloadError(f"taille reçue incorrecte : {written} octets au lieu de {file.size}")
    if file.sha256 and digest.hexdigest() != file.sha256.lower():
        raise DownloadError("empreinte sha256 différente de celle déclarée")
    return done + written
