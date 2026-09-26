"""Scripted OpenAI-compatible server for WaveStack's end-to-end tests (no real model).

`POST /v1/chat/completions` (SSE stream, `usage` at the end when asked) and
`GET /v1/models`, on the loopback only. Every answer is deterministic: it depends on the
last user message of the turn, on the tools offered and on the tool results already
received. `plan_reply` holds the whole script; `README.md` lists the triggers.

Debug routes: `GET /_e2e/requests` (the bodies received, newest last) and
`POST /_e2e/reset` (forget them). Story 15: `GET /_e2e/model.gguf` is the fake embedding
model's file, a 503 until `POST /_e2e/model_ready` (a failed, then a successful download);
story 16: `GET /_e2e/reranker.gguf` is the fake reranker's, always served.

Run: `uv run python tools/e2e/fake_openai.py --port 8765`.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import json
import re
from dataclasses import dataclass, field
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

MODEL_ID = "wavestack-fake"
EXPECTED_KEY = "e2e-fake-key"  # any other key gets a 401, like a real provider
CHUNK_DELAY_S = 0.02  # between two SSE chunks: the UI sees a real stream
SLOW_DELAY_S = 0.4  # with the « [lent] » trigger: time to click « Arrêter » or test a 409

# What a harness error reinjected as a user message starts with (tools/executor.py, AD-10).
_HARNESS_ERROR = re.compile(r"^\s*Erreur\s*:")
# What hook H3 adds before the user's message (content/hooks.yaml, `injection`): never read
# as the user's words, or « heure » and « confidentiel » would trigger tools.
_H3_INJECTION = re.compile(r"Date et heure du poste.*?données confidentielles\.\s*", re.S)
# Story 15: the RAG's intro (content/rag.yaml, `intro_fr`); its excerpts follow it, and the
# user's words are the last part of the message.
_RAG_INTRO = "Extraits de la documentation interne d'Exemplia"
_RAG_EXCERPT = re.compile(r"Extrait (\d+) — ([^:\n]+) :")
MODEL_FILE_SIZE = 4096  # the fake embedding model's file (tools/e2e/stack.py declares it)
RERANKER_FILE_SIZE = 2048  # story 16: the fake reranker's, always served


@dataclass
class Reply:
    """One scripted completion. `status` other than 200 answers `error` as JSON."""

    text: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, str]] = field(default_factory=list)  # {name, arguments}
    finish: str = "stop"
    status: int = 200
    error: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    delay_s: float = CHUNK_DELAY_S
    stream_error: dict[str, Any] | None = None  # an `error` chunk in the middle of the stream
    usage: bool = True  # `usage` at the end when asked; False: as a provider that omits it


# ---------- reading the request ----------


def text_of(content: Any) -> str:
    """A message's `content`: a string, or a list of parts (`{type: text, text}`)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in content)
    return ""


def tool_names(body: dict[str, Any]) -> list[str]:
    names = []
    for tool in body.get("tools") or []:
        function = tool.get("function") if isinstance(tool, dict) else None
        if isinstance(function, dict) and function.get("name"):
            names.append(str(function["name"]))
    return names


def turn_slice(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """The turn's user message (the last one that is not a reinjected harness error) and
    the messages after it."""
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if m.get("role") == "user" and not _HARNESS_ERROR.match(text_of(m.get("content"))):
            text = _H3_INJECTION.sub("", text_of(m.get("content")))
            return strip_rag(text), messages[i + 1 :]
    return "", []


@functools.cache
def _chunk_texts() -> tuple[str, ...]:
    """The corpus's chunks, as the harness cuts them (the longest first)."""
    from wavestack import config
    from wavestack.rag.corpus import chunk_corpus, load_rag_content

    chunks = chunk_corpus(load_rag_content(), config.load_config().rag_chunk_max_chars)
    return tuple(sorted((c.text for c in chunks), key=len, reverse=True))


def strip_rag(text: str) -> str:
    """The user's words without the RAG's intro and excerpts: everything up to the end of
    the last excerpt, whose text is a chunk of the corpus (it may hold blank lines)."""
    at = text.find(_RAG_INTRO)
    if at < 0:
        return text
    headers = list(_RAG_EXCERPT.finditer(text, at))
    if not headers:
        return text[:at]
    body = text[headers[-1].end() :].lstrip("\n")
    chunk = next((c for c in _chunk_texts() if body.startswith(c)), None)
    rest = body[len(chunk) :] if chunk is not None else body.rsplit("\n\n", 1)[-1]
    return text[:at] + rest.lstrip("\n")


def called_in_turn(after: list[dict[str, Any]]) -> list[str]:
    names = []
    for m in after:
        for call in m.get("tool_calls") or []:
            names.append(str((call.get("function") or {}).get("name", "")))
    return names


def tool_results(after: list[dict[str, Any]]) -> list[str]:
    return [text_of(m.get("content")) for m in after if m.get("role") == "tool"]


def harness_errors(after: list[dict[str, Any]]) -> int:
    return sum(
        1
        for m in after
        if m.get("role") == "user" and _HARNESS_ERROR.match(text_of(m.get("content")))
    )


def all_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(text_of(m.get("content")) for m in messages)


def system_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(text_of(m.get("content")) for m in messages if m.get("role") == "system")


# ---------- the script ----------

_LONG_HARNESS = (
    "Un harnais d'agent est tout le code qui entoure le modèle de langage. Il prépare le "
    "contexte à chaque appel : prompt système, historique de la conversation, description "
    "des outils, documents retrouvés. Il lit ensuite la réponse du modèle, repère les "
    "demandes d'outil, les exécute lui-même et réinjecte leurs résultats. Il applique enfin "
    "des règles, les hooks, que le modèle ne peut pas contourner. Le modèle, lui, ne fait "
    "que prédire du texte : c'est le harnais qui en fait un agent."
)
_SHORT_HARNESS = (
    "Harnais = code autour du modèle. Prépare contexte, exécute outils, applique règles."
)


def _plan(user: str, offered: list[str]) -> list[tuple[str, dict[str, Any]]]:
    """The tool calls a prompt leads to, in order; unavailable tools are skipped later."""
    low = user.lower()
    if "test de connexion wavestack" in low:
        return [("get_datetime", {})]
    if "sous-agent" in low and "délègue" in low:  # story 19: the main agent delegates
        task = "Lis le fichier guide_harnais.md et résume-le en cinq points courts."
        if "page web" in low:  # the sub-agent fetches a page (H5 asks inside it)
            task = "Lis la page web https://fr.wikipedia.org/wiki/Paris et résume-la."
        return [("delegate", {"task": task + (" [lent]" if "[lent]" in low else "")})]
    if "journal_serveur" in low:  # story 20: a big log, for the compression
        return [("read_file", {"path": "journal_serveur.log"})]
    if "guide_harnais" in low:  # the sub-agent's task (or a main agent reading it itself)
        return [("read_file", {"path": "guide_harnais.md"})]
    if "alertes_siem" in low:  # story 21: the SOC scenario's alerts
        return [("read_file", {"path": "alertes_siem.log"})]
    if "confidentiel" in low:  # the file named in the message, else the hooks scenario's
        named = re.search(r"confidentiel/[\w.-]+\.\w+", user)
        return [
            ("read_file", {"path": named.group(0) if named else "confidentiel/budget_projet.txt"})
        ]
    if "entra id" in low:  # story 21, IAM: Microsoft Learn's search, when connected
        mslearn = [n for n in offered if n.startswith("mslearn__") and "search" in n]
        return [(mslearn[0], {"query": "Entra ID"})] if mslearn else []
    if "data.gouv.fr" in low:  # story 21, sovereignty: data.gouv.fr's search, when connected
        datagouv = [n for n in offered if n.startswith("datagouv__") and "search" in n]
        return [(datagouv[0], {"query": "cybersécurité"})] if datagouv else []
    if "recette_crepes" in low or "crêpes" in low:
        return [("read_file", {"path": "recette_crepes.txt"})]
    if "notes_reunion" in low:
        return [("read_file", {"path": "notes_reunion.txt"})]
    if "combien font" in low or "calcule" in low:
        numbers = re.findall(r"\d+", user)
        expression = "*".join(numbers[:2]) if len(numbers) >= 2 else "12*37"
        return [("calculator", {"expression": expression})]
    if "férié" in low:
        return [("public_holidays", {"year": 2026})]
    # Before « wikipédia »: a page web task names a fr.wikipedia.org address.
    if "page web" in low or "fetch_page" in low:
        return [("fetch_page", {"url": "https://fr.wikipedia.org/wiki/Paris"})]
    if "wikipédia" in low or "wikipedia" in low:
        return [("wikipedia_summary", {"title": "Mont-Saint-Michel"})]
    if "mcp" in low and "veut dire" in low:
        return [
            ("load_tool_doc", {"tool": "local__define_term"}),
            ("local__define_term", {"term": "MCP"}),
        ]
    if "qualité de l'air" in low:
        datagouv = [n for n in offered if n.startswith("datagouv__") and "search" in n]
        return [(datagouv[0], {"query": "qualité de l'air"})] if datagouv else []
    if "compte rendu" in low:
        return [("load_skill", {"skill": "meeting_minutes"})]
    remember = re.search(r"retiens que (.+)", user, re.IGNORECASE)
    if remember:  # story 14: the global memory's meta-tool
        wish = remember.group(1).strip().rstrip(".")
        return [("remember", {"text": f"L'utilisateur a demandé : {wish}."})]
    if "heure" in low:
        return [("get_datetime", {})]
    return []


def _final_text(user: str, messages: list[dict[str, Any]], results: list[str]) -> str:
    low = user.lower()
    everything = all_text(messages)
    if "homme des cavernes" in everything and "harnais" in low:
        return _SHORT_HARNESS  # the Caveman skill's instructions are in the context
    asked = re.search(r"\blot (\d+)\b", user)
    if asked and results:  # story 20: a line of the log, there or cut by the compression
        wanted = f"lot {asked.group(1)} "
        hit = next((line for line in results[-1].splitlines() if wanted in line + " "), None)
        if hit:
            return f"D'après le journal : {hit.strip()}"
        return f"Le résultat de l'outil ne mentionne pas le lot {asked.group(1)}."
    errors = [line for line in (results[-1] if results else "").splitlines() if " ERROR " in line]
    if errors:  # story 20: the log's error, kept by the compression
        return f"D'après le journal : {errors[0].strip()}"
    if results:
        last = " ".join(results[-1].split())
        excerpt = last if len(last) <= 240 else last[:240] + "…"
        return f"D'après le résultat de l'outil : {excerpt}"
    if "toujours en une phrase, comme un pirate" in system_text(messages).lower():
        return "Arrr ! Je suis le faux modèle de WaveStack, moussaillon."
    if "rappelle-moi mon prénom" in low:  # story 14: read from the global memory
        known = re.search(r"s'appelle (\w+)", system_text(messages))
        if known:
            return f"Vous vous appelez {known.group(1)}, d'après la mémoire globale."
        return "Je ne connais pas votre prénom : la mémoire globale est vide."
    if "comment je m'appelle" in low:
        earlier = re.search(r"Je m'appelle (\w+)(?: et je suis ([^.]+))?", everything)
        if earlier:
            job = f", et vous êtes {earlier.group(2)}" if earlier.group(2) else ""
            return f"Vous vous appelez {earlier.group(1)}{job}."
        return "Je ne sais pas comment vous vous appelez : je ne vois aucun message précédent."
    if "je m'appelle" in low:
        name = re.search(r"je m'appelle (\w+)", low)
        return f"Enchanté, {name.group(1).capitalize() if name else 'inconnu'} !"
    if "heure" in low:
        return "Je n'ai pas accès à une horloge : je ne peux pas connaître l'heure."
    if "harnais" in low:
        return _LONG_HARNESS
    if "mot de passe" in low and "exemplia" in low:  # story 15: with or without the RAG
        last_user = next((m for m in reversed(messages) if m.get("role") == "user"), {})
        found = _RAG_EXCERPT.findall(text_of(last_user.get("content")))
        source = next((f"extrait {n} ({title})" for n, title in found if "passe" in title), None)
        if source:
            return f"D'après l'{source} : au minimum 14 caractères chez Exemplia."
        return "Je ne connais pas les règles d'Exemplia ; en général, on conseille 8 caractères."
    if "entra id" in low:  # story 21: Microsoft Learn unreachable (no network in the run)
        return "Sans la documentation Microsoft Learn, je ne peux pas détailler Entra ID."
    if "data.gouv.fr" in low:
        return "Sans accès à data.gouv.fr, je ne peux pas chercher dans les données publiques."
    if "présente-toi" in low:
        return "Je suis le faux modèle de WaveStack : mes réponses sont écrites d'avance."
    if "mcp" in low:
        return "MCP signifie Model Context Protocol (réponse sans outil)."
    return f"Réponse scriptée du faux modèle au message : « {user.strip()[:120]} »."


def plan_reply(body: dict[str, Any]) -> Reply:
    """The whole script: what to answer to `body`, a chat completions request."""
    messages = [m for m in body.get("messages") or [] if isinstance(m, dict)]
    offered = tool_names(body)
    user, after = turn_slice(messages)
    low = user.lower()
    called = called_in_turn(after)
    results = tool_results(after)

    # Provider refusals (AD-16), shown by the harness in French.
    if "[erreur429]" in low:
        return Reply(
            status=429,
            error={"message": "Rate limit reached: tokens per minute (TPM) exceeded."},
            headers={"retry-after": "7"},
        )
    if "[erreur500]" in low:
        return Reply(status=500, error={"message": "internal fake error"})
    if "[erreur401]" in low:
        return Reply(status=401, error={"message": "Invalid API key"})
    if "[flux-erreur]" in low:
        return Reply(text="Début de réponse…", stream_error={"message": "stream broken"})

    delay = SLOW_DELAY_S if "[lent]" in low else CHUNK_DELAY_S
    reasoning = (
        "Je réfléchis : la question demande une réponse scriptée." if "[raisonne]" in low else ""
    )

    # A malformed call (AD-10): bad JSON first; once, or every time.
    if "[mal-formé-toujours]" in low and "get_datetime" in offered:
        return Reply(tool_calls=[{"name": "get_datetime", "arguments": '{"oops": '}], delay_s=delay)
    if "[mal-formé]" in low and "get_datetime" in offered:
        if harness_errors(after) == 0:
            return Reply(
                text="J'appelle l'outil.",
                tool_calls=[{"name": "get_datetime", "arguments": '{"oops": '}],
                delay_s=delay,
            )
        if "get_datetime" not in called:
            return Reply(tool_calls=[{"name": "get_datetime", "arguments": "{}"}], delay_s=delay)
    if "[outil-inconnu]" in low and not results:
        return Reply(tool_calls=[{"name": "outil_imaginaire", "arguments": "{}"}], delay_s=delay)
    if "[tool_use_failed]" in low and not results:
        return Reply(
            status=400,
            error={
                "message": "Failed to call a function. Please adjust your prompt.",
                "code": "tool_use_failed",
                "failed_generation": '<function=get_datetime{"x":}>',
            },
        )
    if "[coupé]" in low:
        return Reply(text=_LONG_HARNESS, finish="length", delay_s=delay)

    for name, arguments in _plan(user, offered):
        if name in offered and name not in called:
            return Reply(
                reasoning=reasoning,
                tool_calls=[{"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}],
                delay_s=delay,
            )
    text = _final_text(user, messages, results)
    if "[long]" in low:
        text = " ".join([_LONG_HARNESS] * 6)
    return Reply(text=text, reasoning=reasoning, delay_s=delay, usage="[sans-usage]" not in low)


# ---------- the stream ----------


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def _pieces(text: str, size: int = 12) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def sse_chunks(reply: Reply, body: dict[str, Any], completion_id: str) -> list[dict[str, Any]]:
    """The chunks of a 200 answer, in order, without the final `[DONE]`."""
    base = {"id": completion_id, "object": "chat.completion.chunk", "model": MODEL_ID}

    def chunk(delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
        return base | {"choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}

    out = [chunk({"role": "assistant", "content": ""})]
    out += [chunk({"reasoning": p}) for p in _pieces(reply.reasoning)]
    out += [chunk({"content": p}) for p in _pieces(reply.text)]
    if reply.stream_error:
        return out + [{"error": reply.stream_error}]
    for index, call in enumerate(reply.tool_calls):
        first = {
            "index": index,
            "id": f"call_{completion_id[-6:]}_{index}",
            "type": "function",
            "function": {"name": call["name"], "arguments": ""},
        }
        out.append(chunk({"tool_calls": [first]}))
        for piece in _pieces(call["arguments"], 8):
            out.append(chunk({"tool_calls": [{"index": index, "function": {"arguments": piece}}]}))
    finish = "tool_calls" if reply.tool_calls and reply.finish == "stop" else reply.finish
    out.append(chunk({}, finish))
    if reply.usage and (body.get("stream_options") or {}).get("include_usage"):
        prompt = estimate_tokens(json.dumps(body.get("messages"), ensure_ascii=False))
        prompt += estimate_tokens(json.dumps(body.get("tools") or [], ensure_ascii=False))
        completion = estimate_tokens(reply.reasoning + reply.text) + sum(
            estimate_tokens(c["name"] + c["arguments"]) for c in reply.tool_calls
        )
        usage = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }
        out.append(base | {"choices": [], "usage": usage})
    return out


# ---------- the app ----------


def create_app() -> Starlette:
    received: list[dict[str, Any]] = []
    counter = {"n": 0}

    async def models(_: Request) -> JSONResponse:
        return JSONResponse(
            {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "e2e"}]}
        )

    async def completions(request: Request) -> Response:
        if request.headers.get("authorization") != f"Bearer {EXPECTED_KEY}":
            return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)
        try:
            body = json.loads(await request.body())
        except ValueError:
            return JSONResponse({"error": {"message": "invalid JSON"}}, status_code=400)
        received.append(body)
        counter["n"] += 1
        reply = plan_reply(body)
        if reply.status != 200:
            return JSONResponse(
                {"error": reply.error}, status_code=reply.status, headers=reply.headers
            )
        if not body.get("stream"):
            message: dict[str, Any] = {"role": "assistant", "content": reply.text}
            return JSONResponse(
                {"choices": [{"index": 0, "message": message, "finish_reason": reply.finish}]}
            )
        chunks = sse_chunks(reply, body, f"chatcmpl-e2e{counter['n']:06d}")

        async def stream():
            for c in chunks:
                yield f"data: {json.dumps(c, ensure_ascii=False)}\n\n"
                await asyncio.sleep(reply.delay_s)
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    async def requests_log(_: Request) -> JSONResponse:
        return JSONResponse(received)

    async def reset(_: Request) -> JSONResponse:
        received.clear()
        return JSONResponse({"ok": True})

    model = {"ready": False}

    async def model_file(_: Request) -> Response:
        if not model["ready"]:
            return JSONResponse({"error": "fichier indisponible (e2e)"}, status_code=503)
        return Response(b"\0" * MODEL_FILE_SIZE, media_type="application/octet-stream")

    async def reranker_file(_: Request) -> Response:
        return Response(b"\1" * RERANKER_FILE_SIZE, media_type="application/octet-stream")

    async def model_ready(_: Request) -> JSONResponse:
        model["ready"] = True
        return JSONResponse({"ok": True})

    return Starlette(
        routes=[
            Route("/v1/models", models),
            Route("/v1/chat/completions", completions, methods=["POST"]),
            Route("/_e2e/requests", requests_log),
            Route("/_e2e/reset", reset, methods=["POST"]),
            Route("/_e2e/model.gguf", model_file),
            Route("/_e2e/model_ready", model_ready, methods=["POST"]),
            Route("/_e2e/reranker.gguf", reranker_file),
        ]
    )


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Faux serveur compatible OpenAI (tests e2e).")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
