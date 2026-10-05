"""Small JPEG previews so vision review batches stay under request size limits."""

from __future__ import annotations

from PIL import Image

from .config import DATA_DIR, REPO

THUMB_DIR = DATA_DIR / "thumbs"


def ensure_thumb(rel_path: str, sha256: str, max_side: int = 900) -> str:
    """Create (once) a downscaled JPEG of a source image; return repo-relative path."""
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{sha256[:16]}.jpg"
    out = THUMB_DIR / name
    if not out.exists():
        with Image.open(REPO / rel_path) as raw:
            img = raw.convert("RGB")
            img.thumbnail((max_side, max_side), Image.LANCZOS)
            img.save(out, quality=85)
    return f"data/thumbs/{name}"
