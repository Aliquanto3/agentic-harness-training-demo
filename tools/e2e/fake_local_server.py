"""Scripted local servers for WaveStack's end-to-end tests (story 18, no real model).

`--flavor llama_server` imitates llama-server: `/health`, `/props` (Qwen3.5's template),
`/v1/models`, `/tokenize` (with pieces), `/detokenize` and `/completion` (SSE), with a
byte-level tokenizer whose template markers are single tokens. `--flavor ollama` imitates
an Ollama that serves one model whose GGUF is not on this disk (`/api/tags`, `/api/ps`,
`/api/generate` for `keep_alive: 0`): WaveStack lists it « incompatible ».

The answer of `/completion` depends on the prompt the harness rendered: the result of a
tool if the turn has one, a call to `get_datetime` for « heure » when the tool is offered,
else « Réponse du faux llama-server au message : « … » ». With the reasoning on, « [réfléchis
longtemps] » gives a reasoning longer than the budget (story 32: the harness cuts it).

Debug routes: `GET /_e2e/requests` (the POST bodies received, newest last).

Run: `uv run python tools/e2e/fake_local_server.py --flavor llama_server --port 8081`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = (REPO / "tests" / "fixtures" / "qwen3_5_chat_template.jinja").read_text("utf-8")
MODEL_FILE = "faux-llama-server.gguf"
OLLAMA_MODEL = "faux-ollama:latest"
SPECIAL = {"<|im_start|>": 1001, "<|im_end|>": 1002, "<|endoftext|>": 1003}
PIECES = {v: k.encode() for k, v in SPECIAL.items()}
CHUNK_DELAY_S = 0.02
N_CTX = 8192
# Story 32: streamed one character per chunk (the adapter counts a token per chunk), without
# delay, so that it passes the reasoning budget (768 by default) quickly.
LONG_REASONING = "Je réfléchis longuement à la question. " * 25


def tokenize(text: str) -> list[int]:
    """One token per UTF-8 byte, a template marker as one token."""
    ids: list[int] = []
    i = 0
    while i < len(text):
        special = next((s for s in SPECIAL if text.startswith(s, i)), None)
        if special:
            ids.append(SPECIAL[special])
            i += len(special)
        else:
            ids += list(text[i].encode("utf-8"))
            i += 1
    return ids


def piece(token: int) -> bytes:
    return PIECES.get(token, bytes([token]) if 0 <= token < 256 else b"")


def detokenize(ids: list[int]) -> str:
    return b"".join(piece(t) for t in ids).decode("utf-8", "replace")


def plan(prompt: str) -> str:
    """The scripted answer to the rendered `prompt`."""
    user_at = prompt.rfind("<|im_start|>user\n")
    turn = prompt[user_at:] if user_at >= 0 else prompt
    message = turn.removeprefix("<|im_start|>user\n").split("<|im_end|>")[0].strip()
    if "[réfléchis longtemps]" in message and prompt.endswith("<think>\n"):
        # Story 32: a reasoning never closed, longer than the budget (one token per byte):
        # the harness cuts it and relaunches on this prompt and the reasoning kept, which ends
        # with the closure, so the relaunch gets the answer below.
        return LONG_REASONING
    thinking = "Je réfléchis.\n</think>\n\n" if prompt.endswith("<think>\n") else ""
    if "<tool_response>" in turn:
        result = turn.rsplit("<tool_response>", 1)[1].split("</tool_response>")[0].strip()
        return f"{thinking}D'après le résultat de l'outil : {result}"
    if "heure" in message.lower() and "get_datetime" in prompt:
        return f"{thinking}<tool_call>\n<function=get_datetime>\n</function>\n</tool_call>"
    return f"{thinking}Réponse du faux llama-server au message : « {message} »"


def create_app(flavor: str) -> Starlette:
    received: list[dict[str, Any]] = []

    async def body_of(request: Request) -> dict[str, Any]:
        body = json.loads(await request.body() or b"{}")
        received.append({"path": request.url.path, "body": body})
        return body

    async def health(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    async def props(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "model_path": f"/modeles/{MODEL_FILE}",
                "chat_template": TEMPLATE,
                "bos_token": "",
                "eos_token": "<|im_end|>",
                "default_generation_settings": {"n_ctx": N_CTX},
            }
        )

    async def models(_: Request) -> JSONResponse:
        meta = {"n_ctx_train": 32768, "size": 1_500_000_000}
        return JSONResponse({"data": [{"id": MODEL_FILE, "meta": meta}]})

    async def tokenize_route(request: Request) -> JSONResponse:
        body = json.loads(await request.body())
        tokens = []
        for token in tokenize(body.get("content", "")):
            raw = piece(token)
            tokens.append({"id": token, "piece": raw.decode() if raw.isascii() else list(raw)})
        return JSONResponse({"tokens": tokens})

    async def detokenize_route(request: Request) -> JSONResponse:
        body = json.loads(await request.body())
        return JSONResponse({"content": detokenize(body.get("tokens", []))})

    async def completion(request: Request) -> Response:
        body = await body_of(request)
        output = plan(detokenize(body.get("prompt", [])))
        size, delay = (1, 0) if output == LONG_REASONING else (4, CHUNK_DELAY_S)
        chunks = [output[i : i + size] for i in range(0, len(output), size)]

        async def stream():
            for text in chunks:
                yield f"data: {json.dumps({'content': text, 'stop': False})}\n\n"
                await asyncio.sleep(delay)
            end = {"content": "", "stop": True, "stop_type": "eos"}
            yield f"data: {json.dumps(end | {'tokens_predicted': len(tokenize(output))})}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    async def tags(_: Request) -> JSONResponse:
        # Story 25: `details`, as a real Ollama, for the model table's publisher and size.
        details = {"family": "qwen3", "parameter_size": "0.6B"}
        model = {"name": OLLAMA_MODEL, "size": 1_000_000_000, "details": details}
        return JSONResponse({"models": [model]})

    async def ps(_: Request) -> JSONResponse:
        return JSONResponse({"models": []})

    async def generate(request: Request) -> JSONResponse:
        await body_of(request)
        return JSONResponse({"done": True, "done_reason": "unload"})

    async def requests_log(_: Request) -> JSONResponse:
        return JSONResponse(received)

    if flavor == "ollama":
        routes = [
            Route("/api/tags", tags),
            Route("/api/ps", ps),
            Route("/api/generate", generate, methods=["POST"]),
        ]
    else:
        routes = [
            Route("/health", health),
            Route("/props", props),
            Route("/v1/models", models),
            Route("/tokenize", tokenize_route, methods=["POST"]),
            Route("/detokenize", detokenize_route, methods=["POST"]),
            Route("/completion", completion, methods=["POST"]),
        ]
    return Starlette(routes=[*routes, Route("/_e2e/requests", requests_log)])


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Faux serveur local (tests e2e, story 18).")
    parser.add_argument("--flavor", choices=["llama_server", "ollama"], required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(create_app(args.flavor), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
