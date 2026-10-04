"""Copies the publishers' logos from the banque-visuels into `web/static/logos/` (lot 3 of
2026-10-04), the wide wordmarks cropped on their symbol, and writes `SOURCES.md`.

    uv run --with pillow python scripts/crop_logos.py [--bank PATH]

`--bank`: the banque-visuels folder (its `logos/` and `manifeste.json`); by default the one
synced under `~/.claude/skills/synced/*/banque-visuels`. Pillow is a tool of this script
only, never a dependency of WaveStack: the page serves the PNG files written here, and
loads nothing from the network.

A symbol is the first block of opaque columns of the logo, up to the first transparent gap
(Qwen, DeepSeek, Hugging Face, OpenAI, and the ∞ of Meta for Llama); every logo is trimmed
to its opaque pixels and fits 128 px on its longer side.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "src" / "wavestack" / "web" / "static" / "logos"
SIDE = 128  # px, the longer side
ALPHA = 32  # a pixel more opaque than this is part of the logo
GAP = 0.02  # a gap of transparent columns this wide (share of the width) ends the symbol


@dataclass(frozen=True)
class Logo:
    file: str  # in the bank's `logos/`, and the name written under `static/logos/`
    publishers: str  # the publishers of `content/models/publishers.yaml` it stands for
    symbol: bool = False  # crop on the symbol (a wordmark in the bank)
    note: str = ""


LOGOS = (
    Logo("qwen.png", "Qwen (Alibaba)", symbol=True),
    Logo(
        "meta.png",
        "Llama (Meta)",
        symbol=True,
        note="symbole ∞ de Meta : le logotype « LLaMA by Meta » de la banque n'a pas de "
        "symbole séparé (décision d'Anaël du 2026-10-04)",
    ),
    Logo("gemma.png", "Gemma (Google)"),
    Logo("gemini.png", "Gemini (Google)"),
    Logo(
        "ibm.png",
        "Granite (IBM)",
        note="logo IBM entier : watsonx n'a pas de symbole (décision d'Anaël du 2026-10-04)",
    ),
    Logo("microsoft.png", "Phi (Microsoft)"),
    Logo("mistral.png", "Mistral (Mistral AI)"),
    Logo("nvidia.png", "Nemotron (NVIDIA)"),
    Logo("openai.png", "gpt-oss (OpenAI), GPT (OpenAI)", symbol=True),
    Logo("claude.png", "Claude (Anthropic)"),
    Logo("deepseek.png", "DeepSeek (DeepSeek AI)", symbol=True),
    Logo("huggingface.png", "SmolLM (Hugging Face)", symbol=True),
)


def default_bank() -> Path | None:
    found = sorted((Path.home() / ".claude" / "skills" / "synced").glob("*/banque-visuels"))
    return found[0] if found else None


def _opaque_columns(image: Image.Image) -> list[bool]:
    alpha = image.getchannel("A").point(lambda a: 255 if a > ALPHA else 0)
    width, height = alpha.size
    data = alpha.load()
    return [any(data[x, y] for y in range(height)) for x in range(width)]


def symbol_box(image: Image.Image) -> tuple[int, int, int, int]:
    """The columns of the logo's first block, up to the first transparent gap."""
    columns = _opaque_columns(image)
    start = columns.index(True)
    gap = max(4, round(image.width * GAP))
    end, empty = start, 0
    for x in range(start, len(columns)):
        if columns[x]:
            end, empty = x + 1, 0
        else:
            empty += 1
            if empty >= gap:
                break
    return start, 0, end, image.height


def prepared(source: Path, symbol: bool) -> Image.Image:
    image = Image.open(source).convert("RGBA")
    if symbol:
        image = image.crop(symbol_box(image))
    mask = image.getchannel("A").point(lambda a: 255 if a > ALPHA else 0)
    box = mask.getbbox()
    if box:
        image = image.crop(box)
    image.thumbnail((SIDE, SIDE), Image.Resampling.LANCZOS)
    return image


def sources_md(manifest: dict[str, dict]) -> str:
    lines = [
        "# Logos des éditeurs (lot 3 du 2026-10-04)",
        "",
        "Copiés de la banque-visuels (skill `banque-visuels`, `logos/` et `manifeste.json`) par",
        "`scripts/crop_logos.py`, qui réécrit aussi ce fichier : relancer le script plutôt que",
        "modifier un logo à la main. Chaque logo est détouré sur ses pixels opaques et tient",
        f"dans {SIDE} px de plus grand côté ; un logotype large est recadré sur son symbole.",
        "",
        "**Diffusion : formation interne, à vérifier avant usage client.** Les marques restent",
        "à leurs propriétaires ; un logo désigne le modèle d'un éditeur, il ne suggère aucun",
        "partenariat. Aucun logo n'est chargé depuis le réseau.",
        "",
        "| Fichier | Éditeurs (`publishers.yaml`) | Recadrage | Provenance (banque) "
        "| Licence (banque) | Diffusion (banque) |",
        "|---|---|---|---|---|---|",
    ]
    for logo in LOGOS:
        entry = manifest.get(logo.file, {})
        crop = "symbole" if logo.symbol else "entier"
        if logo.note:
            crop += f" ({logo.note})"
        source = entry.get("source") or "non renseignée"
        licence = entry.get("licence") or "non renseignée"
        lines.append(
            f"| `{logo.file}` | {logo.publishers} | {crop} | {source} | {licence} "
            f"| {entry.get('diffusion') or '?'} |"
        )
    lines += [
        "",
        "Sans logo (LFM, MiniCPM, « Autres éditeurs ») : la page montre l'initiale de l'éditeur.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bank", type=Path, default=default_bank())
    args = parser.parse_args()
    if args.bank is None or not (args.bank / "logos").is_dir():
        print("banque-visuels introuvable : passez --bank <dossier>", file=sys.stderr)
        return 1
    manifest_path = args.bank / "manifeste.json"
    manifest = {e["fichier"]: e for e in json.loads(manifest_path.read_text(encoding="utf-8"))}
    OUT.mkdir(parents=True, exist_ok=True)
    for logo in LOGOS:
        image = prepared(args.bank / "logos" / logo.file, logo.symbol)
        image.save(OUT / logo.file, optimize=True)
        print(f"{logo.file}: {image.width} × {image.height}")
    (OUT / "SOURCES.md").write_text(sources_md(manifest), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
