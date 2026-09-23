"""FastAPI app for this story: health, `/diagnostic`, `/api/diagnostic`, SSE, `select_model`.

No 5-volet interface, no full `tokens.css` (story 2). Protected per AD-18's
subset: `TrustedHostMiddleware` on `127.0.0.1`/`localhost`, POST restricted
to same-origin JSON, no CORS.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.envelope import Envelope
from wavestack.trace.journal import get_journal

STATIC_DIR = Path(__file__).parent / "static"


class SelectModelIntention(BaseModel):
    path: str


def create_app(session: DiagnosticSession, *, port: int, version: str) -> FastAPI:
    app = FastAPI(title="WaveStack", version=version)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost"],
    )

    @app.middleware("http")
    async def _same_origin_post(request: Request, call_next):  # noqa: ANN001, ANN202
        if request.method == "POST":
            origin = request.headers.get("origin")
            expected = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
            if origin not in expected:
                return JSONResponse({"detail": "Origine refusée."}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "JSON attendu."}, status_code=415)
        return await call_next(request)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": version}

    @app.get("/diagnostic")
    def diagnostic_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "diagnostic.html")

    @app.get("/api/diagnostic")
    def diagnostic_state() -> dict[str, object]:
        result = session.last_result
        return {
            "version": version,
            "ready": result.ready if result else False,
            "blocking_checks": result.blocking_checks if result else [],
            "candidates": [c.model_dump() for c in result.candidates] if result else [],
        }

    @app.post("/api/intentions/select_model")
    def select_model(intention: SelectModelIntention) -> dict[str, object]:
        result = session.select_model(intention.path)
        return {"ready": result.ready, "blocking_checks": result.blocking_checks}

    @app.get("/api/diagnostic/stream")
    async def diagnostic_stream(request: Request) -> StreamingResponse:
        journal = get_journal()
        last_event_id = request.headers.get("last-event-id")
        try:
            since_seq = int(last_event_id) if last_event_id else 0
        except ValueError:
            since_seq = 0
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Envelope] = asyncio.Queue()

        def _on_event(envelope: Envelope) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, envelope)

        async def _generate():  # noqa: ANN202
            for envelope in journal.events_since(since_seq):
                yield _format_sse(envelope)
            journal.subscribe(_on_event)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        envelope = await asyncio.wait_for(queue.get(), timeout=15)
                        yield _format_sse(envelope)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                journal.unsubscribe(_on_event)

        return StreamingResponse(_generate(), media_type="text/event-stream")

    return app


def _format_sse(envelope: Envelope) -> str:
    data = envelope.model_dump_json()
    return f"id: {envelope.seq}\nevent: {envelope.kind}\ndata: {data}\n\n"
