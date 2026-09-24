"""FastAPI app: health, `/diagnostic`, `/`, `/api/*`, SSE, intentions.

Protected per AD-18's subset: `TrustedHostMiddleware` on
`127.0.0.1`/`localhost`, POST restricted to same-origin JSON, no CORS.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from wavestack import config
from wavestack.session.app_session import AppSession, SendRefused
from wavestack.session.diagnostic import DiagnosticSession
from wavestack.trace.envelope import Envelope
from wavestack.trace.journal import get_journal

STATIC_DIR = Path(__file__).parent / "static"


class SelectModelIntention(BaseModel):
    path: str


class SendIntention(BaseModel):
    message: str = Field(min_length=1)


class BrickIntention(BaseModel):
    brick: str
    wanted: bool


class ToolIntention(BaseModel):
    tool: str
    enabled: bool


class McpServerIntention(BaseModel):
    server: str
    enabled: bool


class McpModeIntention(BaseModel):
    lazy: bool


class SkillIntention(BaseModel):
    skill: str
    enabled: bool


class HookIntention(BaseModel):
    hook: str
    enabled: bool


class ApprovalIntention(BaseModel):
    approval_id: str
    approved: bool
    disable_hook: bool = False  # « Autoriser et ne plus demander »: only with `approved`


class SystemPromptIntention(BaseModel):
    text: str | None  # null: restore the default


def _latest(events: list[Envelope], kind: str) -> Envelope | None:
    return next((e for e in reversed(events) if e.kind == kind), None)


def create_app(
    session: DiagnosticSession,
    *,
    port: int,
    version: str,
    app_session: AppSession | None = None,
) -> FastAPI:
    """`app_session` is the single application session; built here only when a test omits it."""
    app_session = app_session or AppSession(session.cfg)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        app_session.attach_loop(asyncio.get_running_loop())  # AD-24: MCP clients live here
        yield
        await app_session.aclose_mcp()  # AD-21: no local MCP server outlives WaveStack
        app_session.close()  # AD-21: engines are closed on shutdown

    app = FastAPI(title="WaveStack", version=version, lifespan=lifespan)
    app.state.app_session = app_session
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

    @app.middleware("http")
    async def _revalidate_pages(request: Request, call_next):  # noqa: ANN001, ANN202
        """Pages and static files are revalidated, never served stale from the browser cache."""
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": version}

    @app.get("/")
    def index_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/diagnostic")
    def diagnostic_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "diagnostic.html")

    @app.get("/api/state")
    def api_state() -> dict[str, object]:
        """AD-1: what the front's store needs to boot without waiting on SSE.

        `seq` is the journal's current tip: the front resumes `/api/stream`
        from there (`Last-Event-ID`), so it never replays what this snapshot
        already gave it.
        """
        journal = get_journal()
        events = journal.all_events()
        seq = events[-1].seq if events else 0  # the snapshot's own tip, no gap nor overlap
        session_state = _latest(events, "session_state")
        architecture = _latest(events, "architecture_changed")
        # Whole envelopes: the front shows whichever of the two is the most recent (`seq`).
        preview = _latest(events, "context_preview")
        rendered = _latest(events, "context_rendered")
        bricks = _latest(events, "bricks_changed")
        # H5: the last validation asked, while no resolution follows it (one at a time).
        asked = _latest(events, "approval_requested")
        resolved = _latest(events, "approval_resolved")
        pending = asked.payload if asked and (not resolved or resolved.seq < asked.seq) else None
        return {
            "session_state": session_state.payload if session_state else None,
            "architecture_changed": architecture.payload if architecture else None,
            "context_preview": preview.model_dump(mode="json") if preview else None,
            "context_rendered": rendered.model_dump(mode="json") if rendered else None,
            "bricks_changed": bricks.payload if bricks else None,
            "pending_approval": pending,
            "seq": seq,
        }

    @app.get("/api/diagnostic")
    def diagnostic_state() -> dict[str, object]:
        result = session.last_result
        return {
            "version": version,
            "ready": result.ready if result else False,
            "blocking_checks": result.blocking_checks if result else [],
            "candidates": [c.model_dump() for c in result.candidates] if result else [],
            "selected_model": session.selected_model_path,
            "loaded_model": session.booted_path,
        }

    @app.post("/api/intentions/select_model")
    def select_model(intention: SelectModelIntention) -> dict[str, object]:
        """Loads the chosen file only if none was loaded yet; else saved for next launch."""
        result = session.select_model(intention.path)
        if result.model_path:
            app_session.boot(result.model_path).add_done_callback(
                lambda _: session.boot_finished(app_session.model_loaded)
            )
        return {
            "ready": result.ready,
            "blocking_checks": result.blocking_checks,
            "saved": result.saved,
            "next_launch": result.saved and not result.model_path,
            "message_fr": result.message_fr,
        }

    @app.post("/api/intentions/send")
    def send(intention: SendIntention) -> dict[str, str]:
        """Class (b): refused outside `idle`, with the French reason (AD-3)."""
        try:
            return {"turn_id": app_session.send(intention.message)}
        except SendRefused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None

    @app.post("/api/intentions/stop")
    def stop() -> dict[str, bool]:
        """Class (c): preemptive, arms the turn's CancelToken; no effect outside a turn."""
        return {"stopping": app_session.stop()}

    @app.post("/api/intentions/approval")
    def approval(intention: ApprovalIntention) -> dict[str, bool]:
        """Class (c): answers the pending human validation (H5); the first answer wins."""
        try:
            app_session.answer_approval(
                intention.approval_id, intention.approved, intention.disable_hook
            )
        except SendRefused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None
        return {"accepted": True}

    @app.post("/api/intentions/brick")
    def brick(intention: BrickIntention) -> dict[str, bool]:
        """Class (a): accepted even during a turn, effective from the next one (AD-3)."""
        try:
            app_session.set_brick(intention.brick, intention.wanted)
        except KeyError:
            raise HTTPException(status_code=404, detail="Brique inconnue.") from None
        return {"accepted": True}

    @app.post("/api/intentions/tool")
    def tool(intention: ToolIntention) -> dict[str, bool]:
        """Class (a): a tool sub-option, effective from the next turn (AD-3)."""
        try:
            app_session.set_tool(intention.tool, intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail="Outil inconnu.") from None
        return {"accepted": True}

    @app.post("/api/intentions/mcp_server")
    def mcp_server(intention: McpServerIntention) -> dict[str, bool]:
        """Class (a): an MCP server sub-option; contacted now if the brick is wanted (AD-15)."""
        try:
            app_session.set_mcp_server(intention.server, intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail="Serveur MCP inconnu.") from None
        return {"accepted": True}

    @app.post("/api/intentions/mcp_mode")
    def mcp_mode(intention: McpModeIntention) -> dict[str, bool]:
        """Class (a): documentation complète or lazy loading, from the next turn (AD-25)."""
        app_session.set_mcp_mode(intention.lazy)
        return {"accepted": True}

    @app.post("/api/intentions/skill")
    def skill(intention: SkillIntention) -> dict[str, bool]:
        """Class (a): a skill sub-option, effective from the next turn (AD-3)."""
        try:
            app_session.set_skill(intention.skill, intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail="Skill inconnu.") from None
        return {"accepted": True}

    @app.post("/api/intentions/hook")
    def hook(intention: HookIntention) -> dict[str, bool]:
        """Class (a): a hook sub-option, effective from the next turn (AD-3)."""
        try:
            app_session.set_hook(intention.hook, intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail="Hook inconnu.") from None
        return {"accepted": True}

    @app.get("/api/audit")
    def audit() -> dict[str, str]:
        """The whole audit log H2 feeds, read only; empty text while it does not exist."""
        path = config.audit_path()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            text = ""
        except OSError as exc:  # a folder in its place, a locked file
            raise HTTPException(
                status_code=500,
                detail=f"Le journal d'audit ({path}) est illisible : {exc.strerror or exc}",
            ) from None
        return {"path": str(path), "text": text}

    @app.post("/api/intentions/system_prompt")
    def system_prompt(intention: SystemPromptIntention) -> dict[str, object]:
        """Class (a): the saved prompt applies from the next turn (AD-3)."""
        return app_session.save_system_prompt(intention.text)

    @app.post("/api/intentions/clear_conversation")
    def clear_conversation() -> dict[str, bool]:
        """Class (b): refused outside `idle`, with the French reason (AD-3)."""
        try:
            app_session.clear_conversation()
        except SendRefused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None
        return {"cleared": True}

    @app.get("/api/diagnostic/stream")
    async def diagnostic_stream(request: Request) -> StreamingResponse:
        return _sse_stream(request)

    @app.get("/api/stream")
    async def stream(request: Request) -> StreamingResponse:
        """AD-1: same generic replay/subscribe logic, every event kind."""
        return _sse_stream(request)

    return app


def _sse_stream(request: Request) -> StreamingResponse:
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


def _format_sse(envelope: Envelope) -> str:
    data = envelope.model_dump_json()
    return f"id: {envelope.seq}\nevent: {envelope.kind}\ndata: {data}\n\n"
