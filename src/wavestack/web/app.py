"""FastAPI app: health, `/diagnostic`, `/`, `/api/*`, SSE, intentions.

Protected per AD-18's subset: `TrustedHostMiddleware` on
`127.0.0.1`/`localhost`, POST restricted to same-origin JSON, no CORS.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr, model_validator

from wavestack import config
from wavestack.session.app_session import AppSession, ArmRefused, SendRefused
from wavestack.session.diagnostic import DiagnosticSession, Refused
from wavestack.trace.envelope import Envelope
from wavestack.trace.journal import get_journal

STATIC_DIR = Path(__file__).parent / "static"


class SelectModelIntention(BaseModel):
    """AD-21: `{kind, ref, acknowledged}`; `path` (story 1b) still names a file. Story 18:
    `kind = server`, `ref` = `ollama/{name}` or `llama_server/{file}`."""

    kind: Literal["file", "server", "cloud"] = "file"
    ref: str | None = None
    path: str | None = None
    acknowledged: bool = False  # a cloud model: the `cloud-warning` was confirmed


class SetApiKeyIntention(BaseModel):
    id: str
    key: SecretStr  # AD-15: a secret from the intention to the adapter


class CloudTestIntention(BaseModel):
    id: str


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


class ScenarioIntention(BaseModel):
    scenario_id: str


class ApprovalIntention(BaseModel):
    approval_id: str
    approved: bool
    disable_hook: bool = False  # « Autoriser et ne plus demander »: only with `approved`


class ArmIntention(BaseModel):
    """Story 9: a native tool call with its arguments, a skill, or an MCP documentation;
    story 14: a memory write (`target = remember`, `args = {text}`)."""

    kind: Literal["tool", "skill", "tool_doc", "memory"]
    target: str
    args: dict[str, Any] = {}


class DisarmIntention(BaseModel):
    armed_id: str


class MemoryIntention(BaseModel):
    """Story 14, the edit drawer: `replace` or `delete` one entry, or `clear` them all."""

    op: Literal["replace", "delete", "clear"]
    entry_id: str | None = None
    text: str | None = None

    @model_validator(mode="after")
    def _fields_of_the_op(self) -> MemoryIntention:
        """AD-18: `replace` and `delete` name their entry, `replace` carries its text (422)."""
        if self.op != "clear" and not self.entry_id:
            raise ValueError("entry_id est requis pour replace et delete")
        if self.op == "replace" and self.text is None:
            raise ValueError("text est requis pour replace")
        return self


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

    @app.exception_handler(RequestValidationError)
    async def _invalid_intention(_: Request, exc: RequestValidationError) -> JSONResponse:
        """AD-18: a French message with `loc` and `type`, never `input` nor `ctx` (a key)."""
        errors = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "corps" for e in errors)
        return JSONResponse(
            {"detail": f"Intention invalide : vérifiez {fields}.", "errors": errors},
            status_code=422,
        )

    def _diagnostic_class_b() -> None:
        """AD-3: the diagnostic's intentions are refused outside `diagnostic` and `idle`."""
        if app_session.state not in ("idle", "diagnostic"):
            reason = app_session.reason_fr or "WaveStack est occupé."
            raise HTTPException(status_code=409, detail=f"Refusé pour l'instant : {reason}")

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
        reconciled = _latest(events, "context_reconciled")  # chat mode (AD-4)
        bricks = _latest(events, "bricks_changed")
        # H5: the last validation asked, while no resolution follows it (one at a time).
        asked = _latest(events, "approval_requested")
        resolved = _latest(events, "approval_resolved")
        pending = asked.payload if asked and (not resolved or resolved.seq < asked.seq) else None
        armed = _latest(events, "armed_actions_changed")  # story 9: the chips after a reload
        scenario = _latest(events, "scenario_changed")  # story 10: programme and active one
        memory = _latest(events, "memory_changed")  # story 14: the drawer and the card
        return {
            # A1: the front compares it with the stream's `server_instance` event.
            "instance_id": journal.instance_id,
            "session_state": session_state.payload if session_state else None,
            # AD-12: the model indicator, rebuilt from the session on every reload.
            "active_model": app_session.active_model(),
            "architecture_changed": architecture.payload if architecture else None,
            "context_preview": preview.model_dump(mode="json") if preview else None,
            "context_rendered": rendered.model_dump(mode="json") if rendered else None,
            "context_reconciled": reconciled.model_dump(mode="json") if reconciled else None,
            "bricks_changed": bricks.payload if bricks else None,
            "pending_approval": pending,
            "armed_actions_changed": armed.payload if armed else None,
            "scenario_changed": scenario.payload if scenario else None,
            "memory_changed": memory.payload if memory else None,
            "seq": seq,
        }

    @app.get("/api/diagnostic")
    def diagnostic_state() -> dict[str, object]:
        result = session.last_result
        # Story 17: the application session alone says which model is loaded (AD-12).
        active = app_session.active_choice()
        selected = next(
            (
                {"kind": kind, "ref": ref}
                for kind, ref in (
                    ("file", session.selected_model_path),
                    ("server", session.selected_server),
                    ("cloud", session.selected_cloud),
                )
                if ref
            ),
            None,
        )
        return {
            "version": version,
            "ready": result.ready if result else False,
            "blocking_checks": result.blocking_checks if result else [],
            "candidates": [c.model_dump() for c in result.candidates] if result else [],
            "selected_model": session.selected_model_path,
            "loaded_model": active.ref if active and active.kind == "file" else None,
            # Story 18: the saved choice and the loaded model, whatever their kind.
            "selected": selected,
            "loaded": (
                {"kind": active.kind, "ref": active.ref, "label": active.label} if active else None
            ),
            # Story 11: each declared cloud model, `key_set` only, never the key (AD-20).
            "cloud": session.cloud_rows(active.ref if active and active.kind == "cloud" else None),
        }

    @app.post("/api/intentions/select_model")
    def select_model(intention: SelectModelIntention) -> dict[str, object]:
        """Before any model is handed out: saves and loads the chosen one (class a). After:
        a hot switch (class b, story 17), refused outside `idle` or over the memory budget,
        saved once it succeeded. A cloud model needs the warning's confirmation and a key
        (AD-21)."""
        _diagnostic_class_b()
        ref = intention.ref or intention.path or ""
        if not ref.strip():
            raise HTTPException(
                status_code=422,
                detail="Intention invalide : indiquez le modèle choisi (ref) ou le chemin (path).",
            )
        hot = session.handed_out or app_session.state != "diagnostic"
        if intention.kind == "cloud":
            try:
                result = session.select_cloud(ref, intention.acknowledged, hot=hot)
            except Refused as refused:
                raise HTTPException(status_code=409, detail=refused.reason_fr) from None
        elif intention.kind == "server":
            result = session.select_server(ref, hot=hot)
        else:
            result = session.select_model(ref, hot=hot)
        switching = bool(result.model_path or result.cloud_model or result.server)
        message_fr = result.message_fr
        # The model this answer loads: the page matches it with `model_load_ended.model.ref`.
        ref_loading = (
            result.cloud_model.id
            if result.cloud_model
            else result.server.ref
            if result.server
            else result.model_path
        )
        if result.hot:
            try:
                message_fr, switching = session.switch(app_session, result)
            except SendRefused as refused:
                raise HTTPException(status_code=409, detail=refused.reason_fr) from None
        else:
            session.hand_to(app_session, result)
        return {
            "ready": result.ready,
            "blocking_checks": result.blocking_checks,
            # A hot switch is saved once it succeeded: `model_load_ended` says so.
            "saved": result.saved,
            "switching": switching,
            "ref": ref_loading if switching else None,
            "message_fr": message_fr,
        }

    @app.post("/api/intentions/set_api_key")
    def set_api_key(intention: SetApiKeyIntention) -> dict[str, object]:
        """Class (b): the key is saved with its host; the answer never repeats it (AD-15)."""
        _diagnostic_class_b()
        try:
            return session.set_api_key(intention.id, intention.key)
        except Refused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None

    @app.post("/api/intentions/test_cloud_model")
    def test_cloud_model(intention: CloudTestIntention) -> dict[str, object]:
        """Class (b): holds `model_load` (« Test de {modèle} ») for its duration (AD-3)."""
        _diagnostic_class_b()
        entry = session.cfg.cloud_model(intention.id)
        label = f"{entry.model} chez {entry.provider}" if entry else intention.id
        try:
            return app_session.hold(
                "model_load", f"Test de {label}", lambda: session.test_cloud_model(intention.id)
            )
        except Refused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None
        except SendRefused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None

    @app.post("/api/intentions/send")
    def send(intention: SendIntention) -> dict[str, str]:
        """Class (b): refused outside `idle`, with the French reason (AD-3)."""
        try:
            return {"turn_id": app_session.send(intention.message)}
        except SendRefused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None

    @app.post("/api/intentions/replay")
    def replay() -> dict[str, str]:
        """Class (b): the last prompt again, from the state before its turn (AD-17)."""
        try:
            return {"turn_id": app_session.replay()}
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

    @app.post("/api/intentions/arm")
    def arm(intention: ArmIntention) -> dict[str, str]:
        """Class (a): arms an action for the next turn (AD-3); unknown target: 404."""
        try:
            armed_id = app_session.arm(intention.kind, intention.target, intention.args)
        except ArmRefused as refused:
            status = 404 if refused.not_found else 422
            raise HTTPException(status_code=status, detail=refused.reason_fr) from None
        return {"armed_id": armed_id}

    @app.post("/api/intentions/disarm")
    def disarm(intention: DisarmIntention) -> dict[str, bool]:
        """Class (a): removes an armed action; one no longer armed: 404."""
        try:
            app_session.disarm(intention.armed_id)
        except ArmRefused as refused:
            raise HTTPException(status_code=404, detail=refused.reason_fr) from None
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

    @app.post("/api/intentions/memory")
    def memory(intention: MemoryIntention) -> dict[str, bool]:
        """Class (b), the edit drawer (AD-23): outside `idle` or unreadable memory: 409,
        unknown entry: 404, invalid text: 422, file not written: 500."""
        try:
            app_session.edit_memory(intention.op, intention.entry_id, intention.text)
        except SendRefused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None
        except KeyError:
            raise HTTPException(status_code=404, detail="Entrée de mémoire inconnue.") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from None
        return {"accepted": True}

    @app.post("/api/intentions/scenario")
    def scenario(intention: ScenarioIntention) -> dict[str, bool]:
        """Class (b): launches a scenario (FR-38); unknown: 404, outside `idle`: 409."""
        try:
            app_session.launch_scenario(intention.scenario_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Scénario inconnu.") from None
        except SendRefused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None
        return {"launched": True}

    @app.post("/api/intentions/reset")
    def reset() -> dict[str, bool]:
        """Class (b): back to the launch state, the bare LLM (FR-39)."""
        try:
            app_session.reset()
        except SendRefused as refused:
            raise HTTPException(status_code=409, detail=refused.reason_fr) from None
        return {"reset": True}

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
        # First, which journal this stream reads: a tab left open across a relaunch sees
        # a new instance and resyncs (its `Last-Event-ID` belongs to the old journal).
        yield _format_instance(journal.instance_id)
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


def _format_instance(instance_id: str) -> str:
    """Outside the AD-2 envelope and without `id:`: it never moves `Last-Event-ID`."""
    data = json.dumps({"instance_id": instance_id})
    return f"event: server_instance\ndata: {data}\n\n"
