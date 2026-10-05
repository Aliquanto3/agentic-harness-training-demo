"""FastAPI app: health, `/diagnostic`, `/`, `/api/*`, SSE, intentions.

Protected per AD-18's subset: `TrustedHostMiddleware` on
`127.0.0.1`/`localhost`, POST restricted to same-origin JSON, no CORS.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import subprocess
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from wavestack import config
from wavestack.messages import in_language, msg, render
from wavestack.models import catalog
from wavestack.models.cloud_base import session_spend
from wavestack.models.engine import SAMPLING_BOUNDS, Sampling
from wavestack.rag.lab import LANES_MAX, QUESTION_MAX, Pipeline
from wavestack.session.app_session import (
    AppSession,
    ArmRefused,
    DistributionMissing,
    SendRefused,
)
from wavestack.session.diagnostic import DiagnosticSession, Refused
from wavestack.trace.envelope import Envelope
from wavestack.trace.journal import get_journal

STATIC_DIR = Path(__file__).parent / "static"
log = logging.getLogger(__name__)

# Recette du 02/10 (R1): from this total, `/api/diagnostic`'s timing line is a warning,
# visible in the console of `uv run wavestack`; below, a debug line.
SLOW_DIAGNOSTIC_S = 1.0


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


class LanguageIntention(BaseModel):
    """Languages (1/5): one of `config.LANGUAGES`; any other value is refused (422)."""

    language: Literal["fr", "en", "de"]


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


class RagRerankIntention(BaseModel):
    """Story 16: the RAG brick's reranking sub-option."""

    enabled: bool


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
    story 14: a memory write (`target = remember`, `args = {text}`); story 19: the
    delegation to the sub-agent (`target = delegate`, `args = {task}`)."""

    kind: Literal["tool", "skill", "tool_doc", "memory", "delegate"]
    target: str
    args: dict[str, Any] = {}


class DownloadModelIntention(BaseModel):
    """Stories 15 and 16: the model to download, `rag_embedding` or `rag_reranker`."""

    target: str


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


class ContextWindowIntention(BaseModel):
    """Story 26 (AD-9): one of the windows the interface offers (`config.WINDOW_CHOICES`)."""

    window: Literal[config.WINDOW_CHOICES]  # type: ignore[valid-type]


class LlmTokenizeIntention(BaseModel):
    """Story 29: the text the « LLM nu » screen cuts into tokens (2 000 characters at most)."""

    text: str = Field(min_length=1, max_length=2000)


def _bounded(name: str) -> Any:
    low, high = SAMPLING_BOUNDS[name]
    return Field(ge=low, le=high)


class SamplingIntention(BaseModel):
    """Story 29: the screen's four sampling settings, within `engine.SAMPLING_BOUNDS` (the
    single source of the bounds)."""

    temperature: float = _bounded("temperature")
    top_k: int = _bounded("top_k")
    top_p: float = _bounded("top_p")
    min_p: float = _bounded("min_p")


class LlmGenerateIntention(BaseModel):
    """Story 29: the screen's prompt (2 000 characters at most) and its sampling."""

    prompt: str = Field(min_length=1, max_length=2000)
    sampling: SamplingIntention
    reasoning: bool = False  # refused (409) by a model that cannot reason
    candidates: bool = False  # the in-process engine only, else 409


class LlmCompareIntention(BaseModel):
    """Story 5 of 2026-09-30: the screen's prompt generated with two samplings, A then B."""

    prompt: str = Field(min_length=1, max_length=2000)
    sampling_a: SamplingIntention
    sampling_b: SamplingIntention
    reasoning: bool = False
    candidates: bool = False  # A's live distribution; the in-process engine only, else 409


class LlmDistributionRequest(BaseModel):
    """Story 5 of 2026-09-30, read only: a token of the last generation (its `llm_token`
    index) and the sampling to draw its candidates again with."""

    index: int = Field(default=0, ge=0)
    sampling: SamplingIntention


class RagLabRunIntention(BaseModel):
    """Story 30: the question the RAG workshop's chains run on (500 characters at most), and
    the chain (the shipped one when absent)."""

    question: str = Field(min_length=1, max_length=QUESTION_MAX)
    pipelines: list[Pipeline] | None = Field(default=None, min_length=1, max_length=LANES_MAX)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question vide")
        return value


class RagLabValidateRequest(BaseModel):
    """Story 30, increment 4: the chains the page is editing, checked without running them."""

    pipelines: list[Pipeline] = Field(min_length=1, max_length=LANES_MAX)


class McpLabConnectIntention(BaseModel):
    """Story 6 (2026-09-30): the server the MCP workshop connects to, with its own connection."""

    server: str


class McpLabCallIntention(BaseModel):
    """Story 6 (2026-09-30): a tool of the server the workshop is connected to, as the server
    names it, and its arguments (the page builds them from the tool's schema). Lot 4 of
    2026-10-04 (AD-27): `arguments`, one name everywhere; `args` still accepted."""

    server: str
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(
        default={}, validation_alias=AliasChoices("arguments", "args")
    )


class McpLabReadIntention(BaseModel):
    """Lot 4 of 2026-10-04 (AD-27): a resource the server listed, by its URI."""

    server: str
    uri: str = Field(min_length=1)


class McpLabPromptIntention(BaseModel):
    """Lot 4 of 2026-10-04 (AD-27): a prompt the server listed, its arguments as strings."""

    server: str
    prompt: str = Field(min_length=1)
    arguments: dict[str, str] = {}


class McpLabAskIntention(BaseModel):
    """Lot 4 of 2026-10-04 (AD-27): « Par le modèle » (a question) or « Envoyer au modèle »
    (`of`: the step of a read or a prompt of the current connection, whose content the
    session kept; never a content from the page)."""

    server: str
    question: str | None = Field(default=None, max_length=4000)
    of: str | None = None
    doc_mode: Literal["full", "lazy"] = "full"


class SystemPromptIntention(BaseModel):
    text: str | None  # null: restore the default


def _latest(events: list[Envelope], kind: str) -> Envelope | None:
    return next((e for e in reversed(events) if e.kind == kind), None)


def _git_commit(root: Path) -> str | None:
    """Story R0 (CAP-1): the short commit of `root`, read once when the app is built; `None`
    without git, without `.git` (a zip archive), past 2 s or on an empty answer, never an
    error."""
    try:
        if not (root / ".git").exists():
            return None  # never the commit of a repository above an unzipped archive
        done = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    commit = (done.stdout or "").strip()
    return commit if done.returncode == 0 and commit else None


def create_app(
    session: DiagnosticSession,
    *,
    port: int,
    version: str,
    app_session: AppSession | None = None,
) -> FastAPI:
    """`app_session` is the single application session; built here only when a test omits it."""
    app_session = app_session or AppSession(session.cfg)
    # Languages (3/5): the diagnostic's cloud texts follow the session's language.
    session.language = lambda: app_session.language

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        app_session.attach_loop(asyncio.get_running_loop())  # AD-24: MCP clients live here
        yield
        await app_session.aclose_mcp()  # AD-21: no local MCP server outlives WaveStack
        app_session.close()  # AD-21: engines are closed on shutdown

    app = FastAPI(title="WaveStack", version=version, lifespan=lifespan)
    app.state.app_session = app_session
    created = time.perf_counter()  # R1: each diagnostic call says how long after this
    diagnostic_calls = itertools.count(1)

    def t(key: str, **kw: Any) -> str:
        """Languages (5/5): an HTTP `detail` in the session's language."""
        return msg(key, app_session.language, **kw)

    def shown(value: Any) -> Any:
        """Languages (5/5): an answer with every text of the session (a `Message`, at any
        depth) in its language; anything else as it is."""
        return in_language(value, app_session.language)

    @app.exception_handler(RequestValidationError)
    async def _invalid_intention(_: Request, exc: RequestValidationError) -> JSONResponse:
        """AD-18: a message with `loc` and `type`, never `input` nor `ctx` (a key)."""
        errors = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        body = t("web.body")
        fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) or body for e in errors)
        return JSONResponse(
            {"detail": t("web.invalid_intention", fields=fields), "errors": errors},
            status_code=422,
        )

    def _diagnostic_class_b() -> None:
        """AD-3: the diagnostic's intentions are refused outside `diagnostic` and `idle`."""
        if app_session.state not in ("idle", "diagnostic"):
            reason = app_session.reason_text or t("web.busy")
            raise HTTPException(status_code=409, detail=t("web.refused_now", reason=reason))

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
                return JSONResponse({"detail": t("web.origin_refused")}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": t("web.json_expected")}, status_code=415)
        return await call_next(request)

    @app.middleware("http")
    async def _revalidate_pages(request: Request, call_next):  # noqa: ANN001, ANN202
        """Pages and static files are revalidated, never served stale from the browser cache."""
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.middleware("http")
    async def _diagnostic_arrival(request: Request, call_next):  # noqa: ANN001, ANN202
        """R1: when `/api/diagnostic` reached the application (the outermost middleware), so
        its handler can tell the wait before it ran (a sync handler waits for a thread)."""
        if request.url.path == "/api/diagnostic":
            request.state.diagnostic_arrived = time.perf_counter()
        return await call_next(request)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    root = config.repo_root()
    commit = _git_commit(root)  # once, never at each request

    @app.get("/api/health")
    def health() -> dict[str, str | None]:
        """Story R0 (CAP-1): which folder and which commit serve the page."""
        return {"status": "ok", "version": version, "root": str(root), "commit": commit}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        """Lot K, suite (K7): a browser asks for `/favicon.ico` when a page declares no icon
        (the cause of the 404 seen in Edge) or on a direct request; the same SVG icon as each
        page's `<link rel="icon">`."""
        return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")

    @app.get("/")
    def index_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/diagnostic")
    def diagnostic_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "diagnostic.html")

    @app.get("/models")
    def models_page() -> FileResponse:
        """Story 25: the table of the available models and their capabilities."""
        return FileResponse(STATIC_DIR / "models.html")

    @app.get("/llm")
    def llm_page() -> FileResponse:
        """Story 29: the « LLM nu » screen, the inside of the active model."""
        return FileResponse(STATIC_DIR / "llm.html")

    @app.get("/api/ui_texts")
    def api_ui_texts() -> dict[str, object]:
        """Languages (2/5): the interface's texts (`content/ui.yaml`) in the session's
        language, `{language, texts}`, read by `i18n.js` before the page's first render."""
        return app_session.ui_texts()

    @app.get("/api/llm_lab")
    def api_llm_lab() -> dict[str, object]:
        """Story 29 (AD-1): the screen's texts, the active model, the session's state and the
        journal's tip; the page then streams from `seq`."""
        return shown(app_session.lab_state())

    @app.post("/api/intentions/llm_tokenize")
    def llm_tokenize(intention: LlmTokenizeIntention) -> dict[str, str]:
        """Story 29, class (b): accepted in `idle` only (AD-3); `llm_tokenized` answers."""
        try:
            return {"request_id": app_session.llm_tokenize(intention.text)}
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=t("web.refused_now", reason=refused.reason_text)
            ) from None

    @app.post("/api/intentions/llm_generate")
    def llm_generate(intention: LlmGenerateIntention) -> dict[str, str]:
        """Story 29, class (b): accepted in `idle` only, the session in `llm_lab` until the
        generation ends; « Arrêter » (`stop`) stops it."""
        sampling = Sampling(**intention.sampling.model_dump())
        try:
            request_id = app_session.llm_generate(
                intention.prompt,
                sampling,
                reasoning=intention.reasoning,
                candidates=intention.candidates,
            )
            return {"request_id": request_id}
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=t("web.refused_now", reason=refused.reason_text)
            ) from None

    @app.post("/api/intentions/llm_compare")
    def llm_compare(intention: LlmCompareIntention) -> dict[str, object]:
        """Story 5 of 2026-09-30, class (b): accepted in `idle` only; `llm{n}.a` then
        `llm{n}.b`, the session in `llm_lab` until B ends; « Arrêter » stops both."""
        try:
            request_id = app_session.llm_compare(
                intention.prompt,
                Sampling(**intention.sampling_a.model_dump()),
                Sampling(**intention.sampling_b.model_dump()),
                reasoning=intention.reasoning,
                candidates=intention.candidates,
            )
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=t("web.refused_now", reason=refused.reason_text)
            ) from None
        return {"request_id": request_id, "request_ids": [f"{request_id}.a", f"{request_id}.b"]}

    @app.post("/api/llm_lab/distribution")
    def llm_lab_distribution(request: LlmDistributionRequest) -> dict[str, object]:
        """Story 5 of 2026-09-30, read only, in any state (AD-1: computed by the session):
        the candidates of a token of the last local generation for a sampling; 404 when
        none are kept."""
        sampling = Sampling(**request.sampling.model_dump())
        try:
            return shown(app_session.llm_distribution(request.index, sampling))
        except DistributionMissing as missing:
            raise HTTPException(
                status_code=404, detail=render(missing.reason_text, app_session.language)
            ) from None

    @app.get("/rag")
    def rag_page() -> FileResponse:
        """Story 30: the RAG workshop, a RAG chain drawn and run apart from the brick."""
        return FileResponse(STATIC_DIR / "rag.html")

    @app.get("/api/rag_lab")
    def api_rag_lab() -> dict[str, object]:
        """Story 30 (AD-1): the catalog, the shipped chain, the texts, the last run read in the
        journal, the session's state and the journal's tip; the page then streams from `seq`."""
        return shown(app_session.rag_lab_state())

    @app.post("/api/rag_lab/validate")
    def rag_lab_validate(request: RagLabValidateRequest) -> dict[str, object]:
        """Story 30, increment 4, read only: why each chain would be refused, and the stage at
        fault; nothing runs, nothing is emitted."""
        return shown(app_session.validate_rag_lab(request.pipelines))

    @app.post("/api/intentions/rag_lab_run")
    def rag_lab_run(intention: RagLabRunIntention) -> dict[str, str]:
        """Story 30, class (b): accepted in `idle` only, the session in `rag_lab` until the run
        ends; « Arrêter » (`stop`) stops it. A chain refused: 409 with the reason."""
        try:
            return {"run_id": app_session.run_rag_lab(intention.question, intention.pipelines)}
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None

    @app.get("/mcp")
    def mcp_page() -> FileResponse:
        """Story 6 (2026-09-30): the MCP workshop, the protocol between the harness and a
        server, with connections of its own (never the brick's)."""
        return FileResponse(STATIC_DIR / "mcp.html")

    @app.get("/api/mcp_lab")
    def api_mcp_lab() -> dict[str, object]:
        """Story 6 (AD-1): the servers, the texts, the presets, the open connection, the last
        connection's envelopes, the session's state and the journal's tip; the page then
        streams from `seq`."""
        return shown(app_session.mcp_lab_state())

    @app.post("/api/intentions/mcp_lab_connect")
    def mcp_lab_connect(intention: McpLabConnectIntention) -> dict[str, str]:
        """Story 6, class (b): accepted in `idle` only, the session in `mcp_lab` until the
        handshake ends; « Arrêter » (`stop`) closes the connection. Busy: 409 with the
        reason."""
        try:
            return {"step_id": app_session.mcp_lab_connect(intention.server)}
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.mcp_server")) from None
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None

    @app.post("/api/intentions/mcp_lab_call")
    def mcp_lab_call(intention: McpLabCallIntention) -> dict[str, str]:
        """Story 6, class (b): a call through the workshop's connection, accepted in `idle`
        only; without a connection to the server, or for a tool it did not list: 409."""
        return _mcp_lab_intention(
            lambda: app_session.mcp_lab_call(intention.server, intention.tool, intention.arguments)
        )

    def _mcp_lab_intention(start: Callable[[], str]) -> dict[str, str]:
        """Lot 4 of 2026-10-04 (AD-27): class (b), the session in `mcp_lab` until the end;
        an unknown server: 404; busy, not connected or a precondition missing: 409 with the
        reason, nothing emitted."""
        try:
            return {"step_id": start()}
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.mcp_server")) from None
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None

    @app.post("/api/intentions/mcp_lab_read")
    def mcp_lab_read(intention: McpLabReadIntention) -> dict[str, str]:
        """A resource read through the workshop's connection (`resources/read`)."""
        return _mcp_lab_intention(lambda: app_session.mcp_lab_read(intention.server, intention.uri))

    @app.post("/api/intentions/mcp_lab_prompt")
    def mcp_lab_prompt(intention: McpLabPromptIntention) -> dict[str, str]:
        """A prompt got through the workshop's connection (`prompts/get`)."""
        return _mcp_lab_intention(
            lambda: app_session.mcp_lab_prompt(
                intention.server, intention.prompt, intention.arguments
            )
        )

    @app.post("/api/intentions/mcp_lab_ask")
    def mcp_lab_ask(intention: McpLabAskIntention) -> dict[str, str]:
        """An exchange with the model (« Par le modèle », « Envoyer au modèle »); « Arrêter »
        during a generation keeps the connection open."""
        return _mcp_lab_intention(
            lambda: app_session.mcp_lab_ask(
                intention.server, intention.question, intention.of, intention.doc_mode
            )
        )

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
        # The gauge stays on the main context: a sub-agent's is never its source (story 19),
        # nor the « LLM nu » screen's (story 29, which emits no context event anyway), nor the
        # MCP workshop's (lot 4 of 2026-10-04, AD-27).
        main = [
            e
            for e in events
            if not (e.context_id or "").startswith("sub") and e.context_id not in ("llm", "mcp_lab")
        ]
        rendered = _latest(main, "context_rendered")
        reconciled = _latest(main, "context_reconciled")  # chat mode (AD-4)
        bricks = _latest(events, "bricks_changed")
        # H5: the last validation asked, while no resolution follows it (one at a time).
        asked = _latest(events, "approval_requested")
        resolved = _latest(events, "approval_resolved")
        pending = asked.payload if asked and (not resolved or resolved.seq < asked.seq) else None
        armed = _latest(events, "armed_actions_changed")  # story 9: the chips after a reload
        scenario = _latest(events, "scenario_changed")  # story 10: programme and active one
        memory = _latest(events, "memory_changed")  # story 14: the drawer and the card
        window = _latest(events, "context_window_state")  # story 26: the window panel
        return shown(
            {
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
                "context_window_state": window.payload if window else None,
                # FinOps: the session's API spend, from the session (never reset by a reset).
                "consumption_updated": app_session.consumption(),
                # Finition V1 (#27): the session's cap, said in the spend's tooltip.
                "max_session_usd": app_session.cfg.max_session_usd,
                # Languages (1/5): `language`, `languages` and `language_locked`.
                **app_session.language_state(),
                "seq": seq,
            }
        )

    @app.get("/api/diagnostic")
    def diagnostic_state(request: Request) -> dict[str, object]:
        # R1 (recette du 02/10): each step timed, then one log line (never a journal event).
        started = time.perf_counter()
        steps: dict[str, float] = {}

        def lap(name: str) -> None:
            steps[name] = time.perf_counter() - started - sum(steps.values())

        # The journal's last `seq` before anything is read: the page's stream replays the
        # events up to it as history, without their side effects; a later one is live.
        tip = get_journal().last_seq()
        result = session.last_result
        # Story 17: the application session alone says which model is loaded (AD-12).
        active = app_session.active_choice()
        lap("active_choice")
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
        cloud = session.cloud_rows(active.ref if active and active.kind == "cloud" else None)
        lap("cloud_rows")
        candidates = result.candidates if result else []
        timings = catalog.PayloadTimings()
        models = _models(candidates, cloud, timings)
        lap("_models")
        answer = shown(
            {
                "version": version,
                "ready": result.ready if result else False,
                "blocking_checks": result.blocking_checks if result else [],
                "candidates": [c.model_dump() for c in candidates],
                "selected_model": session.selected_model_path,
                "loaded_model": active.ref if active and active.kind == "file" else None,
                # Story 18: the saved choice and the loaded model, whatever their kind.
                "selected": selected,
                "loaded": (
                    {"kind": active.kind, "ref": active.ref, "label": active.label}
                    if active
                    else None
                ),
                # Story 11: each declared cloud model, `key_set` only, never the key (AD-20).
                "cloud": cloud,
                # Story 25: the picker's groups and the `/models` table, built in Python (AD-1).
                **models,
                # Story 24: the budget the session refuses with (the diagnostic's memory line).
                "memory_budget_bytes": app_session.memory_budget_bytes,
                # Finition V1 (#27): the session's cap and its spend so far (CAP-4), said
                # before the cap bites.
                "spend_cap": {
                    "total_usd": (spend := session_spend(1.0) or {}).get("total_usd", 0),
                    "approx": spend.get("approx", False),
                    "cap_usd": app_session.cfg.max_session_usd,
                },
                # Story 3 (corrections): the model search runs until the `model` check's
                # first result; meanwhile, its last progress (probes done on probes needed).
                "searching": result is None,
                "progress": _search_progress() if result is None else None,
                "seq": tip,
            }
        )
        lap("shown")
        arrived = getattr(request.state, "diagnostic_arrived", started)
        total = time.perf_counter() - arrived
        _log_diagnostic_timing(
            next(diagnostic_calls), total, started - arrived, steps, timings.summary()
        )
        return answer

    def _log_diagnostic_timing(
        call: int, total: float, wait: float, steps: dict[str, float], models: str
    ) -> None:
        """R1: the call's total (from its arrival), the wait before the handler and each
        step, in ms, `_models` detailed (`catalog.PayloadTimings.summary`); a warning from
        `SLOW_DIAGNOSTIC_S`, so a slow first call is seen."""
        level = logging.WARNING if total >= SLOW_DIAGNOSTIC_S else logging.DEBUG
        log.log(
            level,
            "/api/diagnostic n° %d : %.0f ms au total (attente avant le gestionnaire %.0f ms ; "
            "%s), %.1f s après la création de l'application",
            call,
            total * 1000,
            wait * 1000,
            ", ".join(
                f"{name} {seconds * 1000:.0f} ms"
                + (f" [{models}]" if name == "_models" and models else "")
                for name, seconds in steps.items()
            ),
            time.perf_counter() - created,
        )

    def _search_progress() -> dict[str, int] | None:
        """The last `diagnostic_progress` of the journal, or None before the first one."""
        for event in reversed(get_journal().all_events()):
            if event.kind == "diagnostic_progress":
                return {"done": event.payload["done"], "total": event.payload["total"]}
        return None

    def _models(
        candidates: list, cloud: dict[str, Any], timings: catalog.PayloadTimings
    ) -> dict[str, object]:
        """`models`, or nothing when it could not be built: the picker then lists the
        candidates as before (AD-16: a failure is contained)."""
        try:
            return {
                "models": catalog.models_payload(
                    candidates,
                    session.cfg,
                    cloud["models"],
                    app_session.configured_window,
                    app_session.language,
                    timings,
                )
            }
        except Exception:  # noqa: BLE001 - the diagnostic's answer never fails for the table
            log.exception("Tableau des modèles impossible à construire")
            return {}

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
                detail=t("web.model_ref_missing"),
            )
        hot = session.handed_out or app_session.state != "diagnostic"
        if intention.kind == "cloud":
            try:
                result = session.select_cloud(ref, intention.acknowledged, hot=hot)
            except Refused as refused:
                raise HTTPException(
                    status_code=409, detail=render(refused.reason_text, app_session.language)
                ) from None
        elif intention.kind == "server":
            result = session.select_server(ref, hot=hot)
        else:
            result = session.select_model(ref, hot=hot)
        switching = bool(result.model_path or result.cloud_model or result.server)
        message_text = result.message_text
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
                message_text, switching = session.switch(app_session, result)
            except SendRefused as refused:
                raise HTTPException(
                    status_code=409, detail=render(refused.reason_text, app_session.language)
                ) from None
        else:
            session.hand_to(app_session, result)
        return {
            "ready": result.ready,
            "blocking_checks": result.blocking_checks,
            # A hot switch is saved once it succeeded: `model_load_ended` says so.
            "saved": result.saved,
            "switching": switching,
            "ref": ref_loading if switching else None,
            "message_text": shown(message_text),
        }

    @app.post("/api/intentions/context_window")
    def context_window(intention: ContextWindowIntention) -> dict[str, object]:
        """Story 26, class (b): the window, applied in `idle` only (AD-3). A local or served
        model reloads with it (after the budget's check, AD-8), a cloud model takes it at the
        next turn; without a model, it is saved for the next load (AD-9)."""
        _diagnostic_class_b()
        try:
            message_text, future = app_session.set_context_window(intention.window)
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        return {"switching": future is not None, "message_text": shown(message_text)}

    @app.post("/api/intentions/set_api_key")
    def set_api_key(intention: SetApiKeyIntention) -> dict[str, object]:
        """Class (b): the key is saved with its host; the answer never repeats it (AD-15)."""
        _diagnostic_class_b()
        try:
            return shown(session.set_api_key(intention.id, intention.key))
        except Refused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None

    @app.post("/api/intentions/test_cloud_model")
    def test_cloud_model(intention: CloudTestIntention) -> dict[str, object]:
        """Class (b): holds `model_load` (« Test de {modèle} ») for its duration (AD-3)."""
        _diagnostic_class_b()
        entry = session.cfg.cloud_model(intention.id)
        label = (
            t("web.cloud_test.label", model=entry.model, provider=entry.provider)
            if entry
            else intention.id
        )
        try:
            return shown(
                app_session.hold(
                    "model_load",
                    t("web.cloud_test.reason", label=label),
                    lambda: session.test_cloud_model(intention.id),
                )
            )
        except Refused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None

    @app.post("/api/intentions/send")
    def send(intention: SendIntention) -> dict[str, str]:
        """Class (b): refused outside `idle`, with the French reason (AD-3)."""
        try:
            return {"turn_id": app_session.send(intention.message)}
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None

    @app.post("/api/intentions/replay")
    def replay() -> dict[str, str]:
        """Class (b): the last prompt again, from the state before its turn (AD-17)."""
        try:
            return {"turn_id": app_session.replay()}
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None

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
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        return {"accepted": True}

    @app.post("/api/intentions/brick")
    def brick(intention: BrickIntention) -> dict[str, bool]:
        """Class (a): accepted even during a turn, effective from the next one (AD-3)."""
        try:
            app_session.set_brick(intention.brick, intention.wanted)
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.brick")) from None
        return {"accepted": True}

    @app.post("/api/intentions/tool")
    def tool(intention: ToolIntention) -> dict[str, bool]:
        """Class (a): a tool sub-option, effective from the next turn (AD-3)."""
        try:
            app_session.set_tool(intention.tool, intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.tool")) from None
        return {"accepted": True}

    @app.post("/api/intentions/mcp_server")
    def mcp_server(intention: McpServerIntention) -> dict[str, bool]:
        """Class (a): an MCP server sub-option; contacted now if the brick is wanted (AD-15)."""
        try:
            app_session.set_mcp_server(intention.server, intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.mcp_server")) from None
        return {"accepted": True}

    @app.post("/api/intentions/mcp_mode")
    def mcp_mode(intention: McpModeIntention) -> dict[str, bool]:
        """Class (a): documentation complète or lazy loading, from the next turn (AD-25)."""
        app_session.set_mcp_mode(intention.lazy)
        return {"accepted": True}

    @app.post("/api/intentions/rag_rerank")
    def rag_rerank(intention: RagRerankIntention) -> dict[str, bool]:
        """Class (a), story 16: reranking of the RAG's excerpts, from the next turn; its model
        loads or leaves on the worker (AD-8)."""
        try:
            app_session.set_rag_rerank(intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.rag")) from None
        return {"accepted": True}

    @app.post("/api/intentions/skill")
    def skill(intention: SkillIntention) -> dict[str, bool]:
        """Class (a): a skill sub-option, effective from the next turn (AD-3)."""
        try:
            app_session.set_skill(intention.skill, intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.skill")) from None
        return {"accepted": True}

    @app.post("/api/intentions/hook")
    def hook(intention: HookIntention) -> dict[str, bool]:
        """Class (a): a hook sub-option, effective from the next turn (AD-3)."""
        try:
            app_session.set_hook(intention.hook, intention.enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.hook")) from None
        return {"accepted": True}

    @app.post("/api/intentions/arm")
    def arm(intention: ArmIntention) -> dict[str, str]:
        """Class (a): arms an action for the next turn (AD-3); unknown target: 404."""
        try:
            armed_id = app_session.arm(intention.kind, intention.target, intention.args)
        except ArmRefused as refused:
            status = 404 if refused.not_found else 422
            raise HTTPException(
                status_code=status, detail=render(refused.reason_text, app_session.language)
            ) from None
        return {"armed_id": armed_id}

    @app.post("/api/intentions/disarm")
    def disarm(intention: DisarmIntention) -> dict[str, bool]:
        """Class (a): removes an armed action; one no longer armed: 404."""
        try:
            app_session.disarm(intention.armed_id)
        except ArmRefused as refused:
            raise HTTPException(
                status_code=404, detail=render(refused.reason_text, app_session.language)
            ) from None
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
                detail=t("web.audit_unreadable", path=path, cause=exc.strerror or exc),
            ) from None
        return {"path": str(path), "text": text}

    @app.post("/api/intentions/system_prompt")
    def system_prompt(intention: SystemPromptIntention) -> dict[str, object]:
        """Class (a): the saved prompt applies from the next turn (AD-3)."""
        return shown(app_session.save_system_prompt(intention.text))

    @app.post("/api/intentions/clear_conversation")
    def clear_conversation() -> dict[str, bool]:
        """Class (b): refused outside `idle`, with the French reason (AD-3)."""
        try:
            app_session.clear_conversation()
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        return {"cleared": True}

    @app.post("/api/intentions/language")
    def language(intention: LanguageIntention) -> dict[str, str]:
        """Class (b), languages (1/5): refused outside `idle` or on a conversation that is
        not empty, with the reason (409); the front then reloads the page."""
        try:
            app_session.set_language(intention.language)
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        return {"language": intention.language}

    @app.post("/api/intentions/memory")
    def memory(intention: MemoryIntention) -> dict[str, bool]:
        """Class (b), the edit drawer (AD-23): outside `idle` or unreadable memory: 409,
        unknown entry: 404, invalid text: 422, file not written: 500."""
        try:
            app_session.edit_memory(intention.op, intention.entry_id, intention.text)
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.memory_entry")) from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=render(exc, app_session.language)) from None
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from None
        return {"accepted": True}

    @app.post("/api/intentions/scenario")
    def scenario(intention: ScenarioIntention) -> dict[str, bool]:
        """Class (b): launches a scenario (FR-38); unknown: 404, outside `idle`: 409."""
        try:
            app_session.launch_scenario(intention.scenario_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.scenario")) from None
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        return {"launched": True}

    @app.post("/api/intentions/download_model")
    def download_model(intention: DownloadModelIntention) -> dict[str, object]:
        """Class (b), story 15 (AD-21): unknown target: 404; outside `idle`, or nothing to
        download: 409, with the reason. « Arrêter » (`stop`) cancels it."""
        try:
            reason_text = app_session.download_model(intention.target)
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.download_target")) from None
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        return {
            "started": True,
            "reason_text": shown(reason_text),
        }

    @app.post("/api/intentions/build_rag_index")
    def build_rag_index() -> dict[str, object]:
        """Class (b), story 15: outside `idle`, or nothing to build: 409, with the reason.
        « Arrêter » (`stop`) cancels it."""
        try:
            reason_text = app_session.build_rag_index()
        except KeyError:
            raise HTTPException(status_code=404, detail=t("web.unknown.rag")) from None
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
        return {
            "started": True,
            "reason_text": shown(reason_text),
        }

    @app.post("/api/intentions/reset")
    def reset() -> dict[str, bool]:
        """Class (b): back to the launch state, the bare LLM (FR-39)."""
        try:
            app_session.reset()
        except SendRefused as refused:
            raise HTTPException(
                status_code=409, detail=render(refused.reason_text, app_session.language)
            ) from None
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
        # Subscribed before the snapshot is taken: an event emitted while the replay is
        # being sent (each `yield` may wait on the socket) is queued, never lost. The
        # overlap this creates (an event both in the snapshot and in the queue) is dropped
        # by `seq`, which `emit` assigns under its lock and notifies in order.
        journal.subscribe(_on_event)
        try:
            # First, which journal this stream reads: a tab left open across a relaunch sees
            # a new instance and resyncs (its `Last-Event-ID` belongs to the old journal).
            yield _format_instance(journal.instance_id)
            # The last replayed `seq`, not `since_seq`: a `Last-Event-ID` of another instance
            # (relaunch, tab left open) may exceed this journal's, whose live events still go.
            last_sent = 0
            for envelope in journal.events_since(since_seq):
                last_sent = envelope.seq
                yield _format_sse(envelope)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    envelope = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if envelope.seq <= last_sent:
                    continue  # already replayed from the snapshot
                last_sent = envelope.seq
                yield _format_sse(envelope)
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
