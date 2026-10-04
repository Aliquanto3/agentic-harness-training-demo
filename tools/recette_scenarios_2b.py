"""The scenarios with Qwen3.5-2B, without a browser (finition V1, entries #4 to #6).

Launches WaveStack in its own console (port 8420, the user's data dir: save `settings.json`
and `memory.json` first, the session saves the language, the model and the demo memory there),
selects Qwen3.5-2B and French, then plays each scenario's prompts by the API, as the trainer
would; every event read from `/api/stream`, any H5 validation allowed. Writes
`recette-scenarios-2b.json` in the current folder. `--attach`: use a WaveStack already
running. First argument, optional: the scenarios, comma-separated. Needs about 4 GB of free
RAM (the 2B loaded): close Edge, Teams and Outlook first.

    uv run python tools/recette_scenarios_2b.py
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import yaml

REPO = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8420"
MODEL = str(Path(os.environ["LOCALAPPDATA"]) / "WaveStack" / "models" / "Qwen3.5-2B-Q4_K_M.gguf")
SCENARIOS = (
    sys.argv[1].split(",")
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-")
    else ["mcp_lazy", "iam", "sovereignty", "soc", "subagent", "compression", "skills"]
)
CLEARED = {"iam", "sovereignty"}  # « Vider la conversation » between their prompts
TURN_TIMEOUT = 420

client = httpx.Client(base_url=BASE, timeout=30, trust_env=False, headers={"Origin": BASE})
events: list[dict] = []
lock = threading.Lock()


def listen() -> None:
    while True:
        try:
            with httpx.stream("GET", BASE + "/api/stream", timeout=None, trust_env=False) as r:
                for line in r.iter_lines():
                    if line.startswith("data:"):
                        with lock:
                            events.append(json.loads(line[5:]))
        except Exception:  # noqa: BLE001 - reconnect
            time.sleep(1)


def mark() -> int:
    with lock:
        return len(events)


def since(n: int, kind: str | None = None) -> list[dict]:
    with lock:
        return [e for e in events[n:] if kind is None or e["kind"] == kind]


def wait(n: int, kind: str, pred=lambda p: True, timeout: float = TURN_TIMEOUT) -> dict | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for e in since(n, kind):
            if pred(e["payload"]):
                return e
        # H5: answer « Autoriser » to any validation asked meanwhile.
        for e in since(n, "approval_requested"):
            aid = e["payload"]["approval_id"]
            if not any(x["payload"]["approval_id"] == aid for x in since(n, "approval_resolved")):
                client.post("/api/intentions/approval", json={"approval_id": aid, "approved": True})
        time.sleep(0.5)
    return None


def state() -> dict:
    return client.get("/api/state").json()


def wait_idle(timeout: float = 600) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        s = (state().get("session_state") or {}).get("state")
        if s == "idle":
            return
        time.sleep(1)
    raise TimeoutError("jamais idle")


def launch() -> subprocess.Popen:
    env = dict(os.environ)
    env["BROWSER"] = "C:/Windows/System32/where.exe /Q %s"  # no browser opened
    env.pop("WAVESTACK_DATA_DIR", None)
    proc = subprocess.Popen(
        ["uv", "run", "--no-sync", "wavestack"],
        cwd=REPO,
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        try:
            if client.get("/api/health").status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise TimeoutError("WaveStack ne répond pas")


def play(scenario_id: str, prompts: list[str]) -> dict:
    r = client.post("/api/intentions/scenario", json={"scenario_id": scenario_id})
    out = {"scenario": scenario_id, "start_status": r.status_code, "prompts": []}
    time.sleep(2)
    wait_idle()
    for i, prompt in enumerate(prompts):
        if i and scenario_id in CLEARED:
            client.post("/api/intentions/clear_conversation", json={})
            wait_idle()
        m = mark()
        started = time.monotonic()
        r = client.post("/api/intentions/send", json={"message": prompt})
        if r.status_code != 200:
            out["prompts"].append(
                {"prompt": prompt[:80], "refused": r.status_code, "body": r.text[:300]}
            )
            continue
        ended = wait(m, "turn_ended")
        took = time.monotonic() - started
        calls = [e for e in since(m, "model_call_ended")]
        main_calls = [e["payload"] for e in calls if e.get("context_id") == "main"]
        tools = [(e.get("context_id"), e["payload"].get("tool")) for e in since(m, "tool_started")]
        hooks = [
            (e["payload"].get("hook"), e["payload"].get("decision"))
            for e in since(m, "hook_decided")
        ]
        text = "".join(
            e["payload"].get("text", "")
            for e in since(m, "model_delta")
            if e.get("context_id") == "main"
        )
        out["prompts"].append(
            {
                "prompt": prompt[:90],
                "status": (ended or {}).get("payload", {}).get("status", "timeout"),
                "seconds": round(took, 1),
                "tools": tools,
                "hooks": hooks,
                "approvals": len(since(m, "approval_requested")),
                "first_prompt_ms": main_calls[0]["prompt_ms"] if main_calls else None,
                "first_prompt_tokens": main_calls[0]["prompt_tokens"] if main_calls else None,
                "main_calls": [
                    (c["prompt_tokens"], c["prompt_ms"], c["output_tokens"], c["stop_reason"])
                    for c in main_calls
                ],
                "prefix_not_reused": [e["payload"]["cause"] for e in since(m, "prefix_not_reused")],
                "errors": [
                    e["payload"].get("message_text", "")[:200] for e in since(m, "harness_error")
                ],
                "answer_tail": text[-400:],
            }
        )
        print(json.dumps(out["prompts"][-1], ensure_ascii=False)[:700], flush=True)
        wait_idle()
    return out


def main() -> int:
    threading.Thread(target=listen, daemon=True).start()
    proc = None if "--attach" in sys.argv else launch()
    time.sleep(2)
    wait_idle(900)
    if (state().get("language") or "fr") != "fr":
        print(
            "langue :", client.post("/api/intentions/language", json={"language": "fr"}).status_code
        )
        time.sleep(3)
    active = (state().get("active_model") or {}).get("ref") or ""
    if not active.endswith("Qwen3.5-2B-Q4_K_M.gguf"):
        n = mark()
        r = client.post("/api/intentions/select_model", json={"kind": "file", "ref": MODEL})
        print("select_model :", r.status_code, r.text[:200])
        ended = wait(n, "model_load_ended", timeout=600)
        print("chargement :", (ended or {}).get("payload", {}).get("status"))
    wait_idle()
    content = yaml.safe_load((REPO / "content" / "scenarios.yaml").read_text(encoding="utf-8"))
    results = []
    for sid in SCENARIOS:
        prompts = content["scenarios"][sid]["prompts"]
        print(f"=== {sid} ({len(prompts)} prompts)", flush=True)
        results.append(play(sid, prompts))
        (Path.cwd() / "recette-scenarios-2b.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=1), "utf-8"
        )
    print("pid du serveur :", proc.pid if proc else "attaché")
    return 0


if __name__ == "__main__":
    sys.exit(main())
