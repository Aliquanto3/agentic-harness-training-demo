"""Compose the README demo from drive.py's screenshots: captions, highlights, title and end cards.

Writes `docs/assets/wavestack-demo.gif` and `.mp4` with ffmpeg, and the guide's
`docs/assets/atelier.jpg`. Fonts: Segoe UI and Segoe UI Emoji (Windows). A highlight is either
named (measured by drive.py on each screenshot) or a box in the 1600 × 900 pixels of the
screenshots: check those against the new screenshots whenever the layout changes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "docs" / "assets"
W, SCREEN_H, BAR = 1280, 720, 72
H = SCREEN_H + BAR
SCALE = W / 1600
PRIMARY, DEEP, ACCENT, ORANGE, LAVENDER = "#451DC7", "#250F6B", "#04F06A", "#E0762B", "#D9D0F6"
FONTS = Path("C:/Windows/Fonts")
EMOJI = ImageFont.truetype(str(FONTS / "seguiemj.ttf"), 109)  # bitmap strike, scaled after


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def emoji(char: str, size: int) -> Image.Image:
    im = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((60, 60), char, font=EMOJI, embedded_color=True)
    im = im.crop(im.getbbox())
    return im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)


def screen(path: Path) -> Image.Image:
    shot = Image.open(path).convert("RGB").resize((W, SCREEN_H), Image.LANCZOS)
    img = Image.new("RGB", (W, H), DEEP)
    img.paste(shot, (0, BAR))
    return img


def caption(img: Image.Image, step: str, text: str, icon: str) -> None:
    d = ImageDraw.Draw(img)
    d.ellipse([20, 16, 60, 56], fill=ACCENT)
    d.text((40, 36), step, font=font("segoeuib.ttf", 24), fill=DEEP, anchor="mm")
    e = emoji(icon, 34)
    img.paste(e, (76, 36 - e.height // 2), e)
    d.text((122, 36), text, font=font("seguisb.ttf", 26), fill="white", anchor="lm")


def highlight(img: Image.Image, box, label: str, color: str = ORANGE, side: str = "above") -> None:
    x0, y0, x1, y1 = [round(v * SCALE) for v in box]
    y0, y1 = y0 + BAR, y1 + BAR
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], radius=12, outline=color, width=5)
    f = font("segoeuib.ttf", 20)
    width = d.textlength(label, font=f)
    lx = min(max(x0, 8), W - width - 28)
    ly = y0 - 38 if side == "above" else y1 + 10
    d.rounded_rectangle([lx, ly, lx + width + 20, ly + 32], radius=8, fill=color)
    d.text((lx + 10, ly + 16), label, font=f, fill="white", anchor="lm")


def card(lines, icons) -> Image.Image:
    img = Image.new("RGB", (W, H), DEEP)
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 10, W, H], fill=ACCENT)
    y = 210
    for text, name, size, color in lines:
        d.text((W // 2, y), text, font=font(name, size), fill=color, anchor="mm")
        y += size + 34
    gap = 300
    x = W // 2 - gap * (len(icons) - 1) // 2
    for char, label in icons:
        e = emoji(char, 64)
        img.paste(e, (x - e.width // 2, 520), e)
        d.text((x, 620), label, font=font("seguisb.ttf", 24), fill="white", anchor="mm")
        x += gap
    return img


class Film:
    def __init__(self, frames: Path) -> None:
        self.frames, self.shots = frames, []  # (image, seconds)
        self.entries: dict[Path, dict] = {}  # screenshot -> its manifest entry

    def phase(self, sequence: str, name: str) -> list[Path]:
        manifest_path = self.frames / sequence / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        paths = []
        for entry in manifest:
            if entry["phase"] == name:
                path = self.frames / sequence / entry["file"]
                self.entries[path] = entry
                paths.append(path)
        if not paths:
            sys.exit(f"Aucune capture pour {sequence}/{name} : relancez drive.py.")
        return paths

    def add(self, img: Image.Image, seconds: float) -> None:
        self.shots.append((img, seconds))

    def run(self, paths, step, text, total, icon, highlights=()) -> None:
        for path in paths:
            img = screen(path)
            caption(img, step, text, icon)
            for box, *rest in highlights:
                if isinstance(box, str):  # measured by drive.py on this very screenshot
                    box = self.entries[path].get("boxes", {}).get(box)
                    if box is None:  # not (whole) in view
                        continue
                highlight(img, box, *rest)
            self.add(img, total / len(paths))


def build(frames: Path) -> Film:
    film = Film(frames)
    title = [
        ("WaveStack", "segoeuib.ttf", 96, "white"),
        ("Ce qu'un harnais agentique ajoute à un LLM nu,", "seguisb.ttf", 38, "white"),
        ("brique par brique", "seguisb.ttf", 38, ACCENT),
    ]
    badges = [
        ("💻", "SLM local, sur CPU"),
        ("🧩", "Briques activables"),
        ("🔍", "Tout est visible"),
    ]
    film.add(card(title, badges), 2.8)

    def main(name: str) -> list[Path]:
        return film.phase("main", name)

    bare = "Le LLM nu reçoit votre message, et rien d'autre"
    film.run(
        main("bare_scenario")[-2:],
        "1",
        "Le LLM nu : toutes les briques éteintes",
        1.4,
        "🤖",
        [("picker", "Scénario « LLM nu »")],
    )
    film.run(main("bare_type"), "1", bare, 1.3, "🤖")
    film.run(main("bare_turn"), "1", bare, 3.0, "🤖")
    film.run(
        main("bare_turn_done")[-1:],
        "1",
        "Sans outil, il ne peut pas connaître l'heure",
        3.2,
        "🤷",
        [
            ("answer", "Réponse sans outil"),
            ((740, 160, 1150, 566), "Contexte : 17 tokens", PRIMARY),
        ],
    )

    film.run(
        main("tools_scenario")[-3:],
        "2",
        "On branche des briques : prompt système, mémoire, outils",
        1.8,
        "🧩",
        [("picker", "Scénario « Outils natifs »")],
    )
    film.run(main("tools_type"), "2", "Même question, avec le harnais", 1.2, "🧩")
    film.run(
        main("tools_turn"),
        "2",
        "Le modèle demande un outil, le harnais l'exécute et réinjecte le résultat",
        4.6,
        "🔧",
    )
    final = main("tools_final")[-1:]
    answer = ("answer", "Réponse avec l'outil")
    done = "La bonne réponse, et chaque étape est visible"
    film.run(final, "2", done, 1.6, "✅", [answer])
    film.run(
        final,
        "2",
        done,
        4.0,
        "✅",
        [
            answer,
            ((1186, 200, 1580, 362), "Cycle d'appel de get_datetime", ORANGE, "below"),
            ((748, 290, 1145, 330), "Descriptions d'outils : 271 tokens", PRIMARY),
            ((476, 655, 626, 776), "Schéma : outils sur le poste", PRIMARY),
        ],
    )

    def lab(name: str) -> list[Path]:
        return film.phase("llm", name)

    inside = "L'Atelier LLM : ce qui se passe dans le modèle"
    film.run(lab("llm_intro")[-2:] + lab("llm_type"), "3", inside, 2.0, "🔬")
    numbers = "Le texte devient des tokens, puis des nombres"
    film.run(
        lab("input_text") + lab("input_tokens") + lab("input_ids")[:-1], "3", numbers, 2.0, "🔢"
    )
    film.run(
        lab("input_ids")[-1:],
        "3",
        numbers,
        2.2,
        "🔢",
        [("chips", "Le modèle ne lit que ces nombres", ORANGE, "below")],
    )
    layers = "Chaque nombre devient un vecteur, que les couches transforment"
    film.run(lab("transfo_scroll") + lab("transfo_embedding"), "3", layers, 2.0, "🧠")
    film.run(
        lab("transfo_attention")[-1:],
        "3",
        layers,
        2.6,
        "🧠",
        [("facts", "Vraies dimensions du modèle chargé", PRIMARY)],
    )
    film.run(
        lab("output_scroll") + lab("output_logits")[:-1],
        "3",
        "Une probabilité pour chaque token suivant",
        1.4,
        "📊",
    )
    film.run(
        lab("output_logits")[-1:],
        "3",
        "Une probabilité pour chaque token suivant",
        2.2,
        "📊",
        [("logits", "Les 6 plus probables, en direct", PRIMARY, "below")],
    )
    film.run(
        lab("output_draw")[-1:],
        "3",
        "Puis un token est tiré au sort : c'est toute la génération",
        3.0,
        "🎲",
        [("token", "Token tiré selon ces chances")],
    )

    def rag(name: str) -> list[Path]:
        return film.phase("rag", name)

    chain = "L'Atelier RAG : la chaîne RAG, étape par étape"
    film.run(rag("rag_intro") + rag("rag_steps"), "4", chain, 3.0, "📚")
    film.run(
        rag("rag_done")[-1:],
        "4",
        chain,
        1.8,
        "📚",
        [("focus", "Ce que fait chaque étape", PRIMARY, "below")],
    )

    def mcp(name: str) -> list[Path]:
        return film.phase("mcp", name)

    protocol = "L'Atelier MCP : le protocole, message par message"
    film.run(mcp("mcp_intro") + mcp("mcp_handshake"), "5", protocol, 3.0, "🔌")
    film.run(
        mcp("mcp_done")[-1:],
        "5",
        protocol,
        2.2,
        "🔌",
        [
            ("seq", "Les messages JSON-RPC, capturés", ORANGE, "below"),
            ("model", "Le poids des outils en tokens", PRIMARY, "below"),
        ],
    )

    end = [
        ("uv run wavestack", "consolab.ttf", 64, ACCENT),
        ("6 modules de formation · 5 h 15 · 3 ateliers", "seguisb.ttf", 36, "white"),
        (
            "Raisonnement · mémoire · outils · RAG · MCP · skills · hooks · sous-agent",
            "segoeui.ttf",
            26,
            LAVENDER,
        ),
    ]
    systems = [("🪟", "Windows"), ("🐧", "Linux"), ("🍎", "macOS (puce Apple)")]
    film.add(card(end, systems), 3.5)
    return film


def render(film: Film, work: Path) -> None:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    lines = []
    for i, (img, seconds) in enumerate(film.shots):
        path = work / f"{i:04d}.png"
        img.save(path)
        lines += [f"file '{path.as_posix()}'", f"duration {seconds:.3f}"]
    lines.append(f"file '{path.as_posix()}'")  # the concat demuxer ignores the last duration
    concat = work / "concat.txt"
    concat.write_text("\n".join(lines), encoding="utf-8")
    source = ["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat)]
    palette = (
        "fps=10,split[a][b];[a]palettegen=max_colors=256:stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
    )
    gif = ASSETS / "wavestack-demo.gif"
    mp4 = ASSETS / "wavestack-demo.mp4"
    subprocess.run([*source, "-vf", palette, "-loop", "0", str(gif)], check=True)
    video = ["-vf", "fps=25,format=yuv420p", "-c:v", "libx264", "-crf", "23", "-preset", "slow"]
    subprocess.run([*source, *video, "-movflags", "+faststart", str(mp4)], check=True)


def still(film: Film) -> None:
    """The guide's picture of the atelier: the last screenshot after the tools turn, bare."""
    shot = Image.open(film.phase("main", "tools_final")[-1]).convert("RGB")
    shot = shot.resize((W, SCREEN_H), Image.LANCZOS)
    shot.save(ASSETS / "atelier.jpg", quality=88, optimize=True, progressive=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage : compose.py <dossier des captures>")
    frames = Path(sys.argv[1])
    film = build(frames)
    render(film, frames / "composed")
    still(film)
    print(f"{len(film.shots)} images, {sum(s for _, s in film.shots):.1f} s -> {ASSETS}")
