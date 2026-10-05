"""Drops card image crops: keep the solid-colour card, strip phone UI."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .config import DROPS_MEDIA_DIR


def crop_drops(image: Image.Image, margin: float = 0.02) -> Image.Image:
    """Crop to the dominant solid-colour region (removes status bar, nav bars)."""
    rgb = image.convert("RGB")
    small = rgb.resize((64, 64))
    pixels = np.asarray(small).reshape(-1, 3)
    quantized = (pixels // 24) * 24
    values, counts = np.unique(quantized, axis=0, return_counts=True)
    background = tuple(int(v) for v in values[int(counts.argmax())])

    arr = np.asarray(rgb).astype(np.int16)
    distance = np.abs(arr - np.asarray(background, dtype=np.int16)).sum(axis=2)
    mask = distance < 90

    row_share = mask.mean(axis=1)
    col_share = mask.mean(axis=0)
    rows = np.where(row_share > 0.45)[0]
    cols = np.where(col_share > 0.45)[0]
    if len(rows) == 0 or len(cols) == 0:
        return rgb

    top, bottom = int(rows.min()), int(rows.max())
    left, right = int(cols.min()), int(cols.max())
    pad_x = int((right - left) * margin)
    pad_y = int((bottom - top) * margin)
    box = (
        max(left - pad_x, 0),
        max(top - pad_y, 0),
        min(right + pad_x + 1, rgb.width),
        min(bottom + pad_y + 1, rgb.height),
    )
    return rgb.crop(box)


def save_crop(image: Image.Image, sha256: str) -> str | None:
    """Save the Drops crop and return its path relative to the repo (or None)."""
    DROPS_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{sha256[:16]}.jpg"
    path = DROPS_MEDIA_DIR / name
    if not path.exists():
        crop = crop_drops(image)
        crop.thumbnail((720, 720), Image.LANCZOS)
        crop.convert("RGB").save(path, quality=88)
    return str(path.relative_to(Path(__file__).resolve().parents[1])).replace("\\", "/")
