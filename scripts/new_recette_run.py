"""Creates a blank copy of the Claude in Chrome test book for a new campaign, under
`docs/recette/runs/`, and prints the address it is served at.

    uv run python scripts/new_recette_run.py [--stamp YYYY-MM-DD-HHMM] [--seed results.json]

The copy shows the current branch and commit, and keeps its statuses and notes in the
browser under its own path, so a new campaign never inherits an earlier one. `--seed`
embeds results ({"CT-01": {"status": "ok", "note": "…"}, …}) to archive a campaign: the
page shows them until the viewer changes something. The book is served by
`uv run python -m http.server 8430 --bind 127.0.0.1 -d docs/recette`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BOOK = REPO / "docs" / "recette"
TEMPLATE = BOOK / "cahier-tests-chrome.html"
RUNS = BOOK / "runs"
PORT = 8430
SEED_TAG = r'(<script id="seed" type="application/json">).*?(</script>)'


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()


def replace_once(html: str, pattern: str, value: str) -> str:
    result, count = re.subn(pattern, lambda m: m.group(1) + value + m.group(2), html, count=1)
    if count != 1:
        sys.exit(f"Marker not found in {TEMPLATE.name}: {pattern}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stamp", default=datetime.now().strftime("%Y-%m-%d-%H%M"))
    parser.add_argument("--seed", type=Path, help="results to embed (JSON)")
    args = parser.parse_args()

    html = TEMPLATE.read_text(encoding="utf-8")
    version = f"{git('branch', '--show-current')} @ {git('rev-parse', '--short', 'HEAD')}"
    html = replace_once(html, r'(<span id="meta-version">).*?(</span>)', version)
    html = replace_once(html, r'(<span id="meta-run">).*?(</span>)', args.stamp)
    if args.seed:
        seed = json.dumps(json.loads(args.seed.read_text(encoding="utf-8")), ensure_ascii=False)
        # A note holding "</script>" would close the seed's tag.
        seed = seed.replace("</", "<\\/")
        html = replace_once(html, SEED_TAG, seed)

    RUNS.mkdir(exist_ok=True)
    out = RUNS / f"cahier-{args.stamp}.html"
    if out.exists():
        sys.exit(f"{out.relative_to(REPO)} already exists: pick another --stamp.")
    out.write_text(html, encoding="utf-8")
    print(out.relative_to(REPO).as_posix())
    print(f"http://127.0.0.1:{PORT}/runs/{out.name}")


if __name__ == "__main__":
    main()
