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
from wavestack.messages import KeyedError, Message
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


class DownloadError(KeyedError):
    """A download that did not complete: `reason_text` says why, a `Message` (languages
    5/5: French as a text, `render(lang)` in the session's language; a plain text is kept
    verbatim)."""

    def __init__(self, reason_text: str | Message, *, cancelled: bool = False) -> None:
        if not isinstance(reason_text, Message):
            reason_text = Message("common.verbatim", text=reason_text)
        super().__init__(reason_text)
        self.reason_text = reason_text
        self.cancelled = cancelled


def _stopped() -> DownloadError:
    return DownloadError(Message("models.download.stopped"), cancelled=True)


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
        raise NetworkBlocked(Message("models.download.not_https", url=str(url)))


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
            raise _stopped()
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
            raise DownloadError(
                Message("models.download.write_failed", path=str(part), cause=exc)
            ) from None
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
                        Message(
                            "models.download.http_error",
                            status=response.status_code,
                            reason=response.reason_phrase,
                            url=str(response.url),
                        )
                    )
                with part.open("wb") as out:
                    for chunk in response.iter_bytes(CHUNK_BYTES):
                        if cancel.cancelled:
                            raise _stopped()
                        out.write(chunk)
                        digest.update(chunk)
                        written += len(chunk)
                        if written > file.size:
                            raise DownloadError(
                                Message("models.download.too_large", size=file.size)
                            )
                        on_progress(done + written, total)
    except DownloadError:
        raise
    except Exception as exc:
        if cancel.cancelled:  # the response closed by « Arrêter »
            raise _stopped() from None
        raise _network_error(exc, file) from None
    finally:
        if isinstance(cancel, StopToken):
            cancel.watch(None)
    if cancel.cancelled:
        raise _stopped()
    if written != file.size:
        raise DownloadError(Message("models.download.wrong_size", written=written, size=file.size))
    if file.sha256 and digest.hexdigest() != file.sha256.lower():
        raise DownloadError(Message("models.download.wrong_sha256"))
    return done + written, digest.hexdigest()


def _network_error(exc: Exception, file: ModelFile) -> Exception:
    """A network failure as a keyed `DownloadError`; anything else unchanged."""
    if isinstance(exc, httpx.TooManyRedirects):
        return DownloadError(Message("models.download.too_many_redirects"))
    if isinstance(exc, NetworkBlocked | httpx.HTTPError):
        blocked = find_blocked(exc)
        if blocked is not None:
            return DownloadError(Message("models.download.blocked", cause=blocked))
        return DownloadError(
            Message(
                "models.download.unreachable",
                kind=type(exc).__name__,
                host=httpx.URL(file.url).host,
            )
        )
    return exc
