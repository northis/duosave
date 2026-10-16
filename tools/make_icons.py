"""Regenerate the app icons from the header owl emoji (🦉) — run by hand, commit the PNGs.

    python tools/make_icons.py

The site itself needs no build step: `duosave/server/static/icons/*.png` are the artifacts
(and `duosave/server/static/manifest.webmanifest` points at them). This script exists so the
owl can be re-rendered — a new font, another size, a different background — without hunting
for the original file.

Layout follows the maskable icon rules (https://web.dev/articles/maskable-icon): the
`purpose: any` icons are transparent and tight, like the favicon; the maskable one is opaque
and keeps the owl inside the safe zone (a centred circle of radius 40% of the width), which is
what removes the white circle Android draws around a transparent PWA icon. The owl is scaled
so that its *silhouette* — not its bounding box — touches that circle: the glyph is a roundish
body with ear tufts and feet, so the corners of the box are empty and fitting the box would
make the owl needlessly small.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "duosave" / "server" / "static" / "icons"

OWL = "🦉"
BACKGROUND = "#f6f1e8"  # style.css --bg (light theme): the canvas of the opaque icons only —
# the manifest's splash colour is the dark --bg, see duosave/server/static/manifest.webmanifest
RENDER_SIZE = 1024  # the glyph is rasterised once, large, then scaled down (LANCZOS)
ALPHA_CUTOFF = 8  # pixels fainter than this are antialiasing, not the silhouette
FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\seguiemj.ttf"),  # Segoe UI Emoji (scalable COLR glyphs)
    Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
    Path("/System/Library/Fonts/Apple Color Emoji.ttc"),
)


@dataclass(frozen=True)
class Icon:
    """One output file: how much of the canvas the owl takes, and whether it is opaque."""

    name: str
    size: int
    height: float | None = None  # owl height / canvas (for transparent, box-fitted icons)
    safe_zone: float | None = None  # owl silhouette radius / canvas (maskable, mask-proof)
    opaque: bool = False


ICONS = (
    Icon("icon-192.png", 192, height=0.88),
    Icon("icon-512.png", 512, height=0.88),
    Icon("maskable-512.png", 512, safe_zone=0.38, opaque=True),  # the spec guarantees 0.40
    Icon("apple-touch-icon-180.png", 180, height=0.82, opaque=True),
)


def find_font(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    for candidate in FONT_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit(f"no colour emoji font found, pass --font (looked at {', '.join(map(str, FONT_CANDIDATES))})")


def render_owl(font_path: Path) -> Image.Image:
    """The emoji as a tight RGBA image: the glyph, cropped to its alpha."""
    font = ImageFont.truetype(str(font_path), RENDER_SIZE)
    canvas = Image.new("RGBA", (RENDER_SIZE * 2, RENDER_SIZE * 2), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text(
        (canvas.width / 2, canvas.height / 2), OWL, font=font, embedded_color=True, anchor="mm"
    )
    box = canvas.getbbox()
    if box is None:
        raise SystemExit(f"{font_path} drew nothing for {OWL} (bitmap-only emoji font?)")
    return canvas.crop(box)


def silhouette_radius_ratio(glyph: Image.Image) -> float:
    """Max distance from the glyph's centre to an opaque pixel, in units of its height."""
    alpha = glyph.getchannel("A").load()
    cx, cy = glyph.width / 2, glyph.height / 2
    farthest = 0.0
    for y in range(glyph.height):
        for x in range(glyph.width):
            if alpha[x, y] > ALPHA_CUTOFF:
                distance = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
                farthest = max(farthest, distance)
    return farthest / glyph.height


def build_icon(glyph: Image.Image, radius_ratio: float, spec: Icon) -> Image.Image:
    if spec.height is not None:
        height = spec.height * spec.size
    else:
        height = spec.safe_zone * spec.size / radius_ratio
    width = round(glyph.width * height / glyph.height)
    owl = glyph.resize((width, round(height)), Image.LANCZOS)
    icon = Image.new("RGBA", (spec.size, spec.size), BACKGROUND if spec.opaque else (0, 0, 0, 0))
    icon.alpha_composite(owl, ((spec.size - width) // 2, (spec.size - owl.height) // 2))
    return icon.convert("RGB") if spec.opaque else icon


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, help="colour emoji font to draw the owl with")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help=f"where to write the icons (default: {OUT_DIR})")
    args = parser.parse_args()

    font_path = find_font(args.font)
    glyph = render_owl(font_path)
    radius_ratio = silhouette_radius_ratio(glyph)
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"font: {font_path} · owl {glyph.width}x{glyph.height} · silhouette radius {radius_ratio:.3f} of height")
    for spec in ICONS:
        icon = build_icon(glyph, radius_ratio, spec)
        icon.save(args.out / spec.name)
        print(f"  {spec.name}: {icon.width}x{icon.height} {icon.mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
