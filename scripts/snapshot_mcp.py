"""Captures the tool definitions of the public MCP servers (AD-9, story 21).

    uv run python scripts/snapshot_mcp.py [--server datagouv] [--out content/mcp_snapshots]

Connects to each public server of the `mcp` brick (data.gouv.fr, Microsoft Learn) as
WaveStack does, lists its tools, and writes them to `{out}/{server_id}.json`. To run on the
target workstation, network open: the scenario window test (`tests/test_program.py`) counts
these snapshots instead of the plausible fixtures of `tests/fixtures/mcp_tools/`.
The network guard is installed first, with the hosts of `[net] allowed_hosts`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from wavestack import config as _config
from wavestack.net.guard import install as _install_guard

# AD-15: before any third-party import.
_install_guard(_config.load_config().allowed_hosts)

from wavestack import config  # noqa: E402
from wavestack.mcp.connection import McpConnection, describe_error  # noqa: E402
from wavestack.mcp.servers import mcp_servers  # noqa: E402


async def _tools(server, timeout: float) -> list[dict]:  # noqa: ANN001
    connection = McpConnection(
        server, asyncio.get_running_loop(), connect_timeout=timeout, call_timeout=timeout
    )
    tools = await connection.start()
    await connection.aclose()
    return [t.model_dump(by_alias=True, exclude_none=True) for t in tools]


def main(argv: list[str] | None = None) -> int:
    cfg = config.load_config()
    public = {i: s for i, s in mcp_servers(cfg).items() if s.network}
    parser = argparse.ArgumentParser(
        description="Enregistre les définitions d'outils des serveurs MCP publics (AD-9)."
    )
    parser.add_argument("--server", choices=sorted(public), action="append")
    parser.add_argument("--out", type=Path, default=config.content_dir() / "mcp_snapshots")
    args = parser.parse_args(argv)
    timeout = cfg.mcp_connect_timeout_s
    failed = 0
    for server_id in args.server or sorted(public):
        server = public[server_id]
        try:
            tools = asyncio.run(_tools(server, timeout))
        except Exception as exc:  # noqa: BLE001 - reported, then the next server
            print(f"{server_id} : {describe_error(exc, timeout)}", file=sys.stderr)
            failed += 1
            continue
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{server_id}.json"
        snapshot = {
            "server": server_id,
            "url": server.url,
            "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "tools": tools,
        }
        text = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8")
        print(f"{server_id} : {len(tools)} outils enregistrés dans {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
