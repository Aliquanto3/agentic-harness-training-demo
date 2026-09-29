"""Model file download (story 15, AD-15, AD-21): the traced client of `net`, no hub library.

Each file is streamed into `*.part`, its size (and its sha256 when declared) checked, then
renamed. Redirects are followed hop by hop, each hop checked again by the factory (allowed
host, traced as `origin = download`) and here (https, http on the loopback only), as the
network tools do. Any failure removes the `.part` and raises `DownloadError` in French.
« Arrêter » (`StopToken.cancel`) also closes the response being read, so it acts at once
while waiting for data; during the connection, within `TIMEOUT.connect` at most.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx

from wavestack.config import ModelFile
from wavestack.models.engine import CancelToken
from wavestack.net.factory import create_client
from wavestack.net.guard import NetworkBlocked, find_blocked, is_loopback
from wavestack.trace.scope import scoped

CHUNK_BYTES = 1024 * 1024
TIMEOUT = httpx.Timeout(10.0, read=60.0)


class StopToken(CancelToken):
    """A download's cancel token: `cancel()` also closes the response being read."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._response: httpx.Response | None = None

    def watch(self, response: httpx.Response | None) -> None:
        with self._lock:
            self._response = response
        if response is not None and self.cancelled:
            response.close()

    def cancel(self) -> None:
        super().cancel()
        with self._lock:
            response = self._response
        if response is not None:
            response.close()


class DownloadError(Exception):
    """A download that did not complete: `reason_fr` says why, in French."""

    def __init__(self, reason_fr: str, *, cancelled: bool = False) -> None:
        super().__init__(reason_fr)
        self.reason_fr = reason_fr
        self.cancelled = cancelled


def missing_files(files: Sequence[ModelFile], dest: Path) -> list[ModelFile]:
    """The declared files not yet in `dest`, or there with another size (another model's
    file: « Télécharger » replaces it)."""
    return [f for f in files if not _same_size(dest / f.path, f.size)]


def _same_size(path: Path, size: int) -> bool:
    try:
        return path.is_file() and path.stat().st_size == size
    except OSError:
        return False


def _check_hop(request: httpx.Request) -> None:
    url = request.url
    if url.scheme != "https" and not (url.scheme == "http" and is_loopback(url.host)):
        raise NetworkBlocked(f"adresse non https refusée : {url}")


def download_files(
    files: Sequence[ModelFile],
    dest: Path,
    cancel: CancelToken,
    on_progress: Callable[[int, int], None],
    *,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Download `files` into `dest` (their `path` under it). `on_progress(done, total)` in
    bytes, for all the files. Returns each file's sha256, by `path`. Raises `DownloadError`
    (`cancelled` when `cancel` fired)."""
    total = sum(f.size for f in files)
    done = 0
    digests: dict[str, str] = {}
    for file in files:
        if cancel.cancelled:
            raise DownloadError("téléchargement arrêté", cancelled=True)
        target = dest / file.path
        part = target.with_name(target.name + ".part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            done, digests[file.path] = _download_one(
                file, part, cancel, on_progress, done, total, transport
            )
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
    return digests


def _download_one(
    file: ModelFile,
    part: Path,
    cancel: CancelToken,
    on_progress: Callable[[int, int], None],
    done: int,
    total: int,
    transport: httpx.BaseTransport | None,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    written = 0
    try:
        with scoped(origin="download"), create_client(timeout=TIMEOUT, transport=transport) as c:
            c.event_hooks["request"].insert(0, _check_hop)
            with c.stream("GET", file.url, follow_redirects=True) as response:
                if isinstance(cancel, StopToken):
                    cancel.watch(response)
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
    except Exception as exc:
        if cancel.cancelled:  # the response closed by « Arrêter »
            raise DownloadError("téléchargement arrêté", cancelled=True) from None
        raise _network_error(exc, file) from None
    finally:
        if isinstance(cancel, StopToken):
            cancel.watch(None)
    if cancel.cancelled:
        raise DownloadError("téléchargement arrêté", cancelled=True)
    if written != file.size:
        raise DownloadError(f"taille reçue incorrecte : {written} octets au lieu de {file.size}")
    if file.sha256 and digest.hexdigest() != file.sha256.lower():
        raise DownloadError("empreinte sha256 différente de celle déclarée")
    return done + written, digest.hexdigest()


def _network_error(exc: Exception, file: ModelFile) -> Exception:
    """A network failure as a `DownloadError` in French; anything else unchanged."""
    if isinstance(exc, httpx.TooManyRedirects):
        return DownloadError("trop de redirections")
    if isinstance(exc, NetworkBlocked | httpx.HTTPError):
        blocked = find_blocked(exc)
        if blocked is not None:
            return DownloadError(f"connexion refusée par le harnais ({blocked})")
        return DownloadError(
            f"serveur injoignable ({type(exc).__name__}) : le poste n'a pas accès à "
            f"{httpx.URL(file.url).host}"
        )
    return exc
