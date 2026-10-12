"""Shared helpers for tests: in-memory images and hashes."""

from __future__ import annotations

import hashlib
import io

from PIL import Image


def png_bytes(color: tuple[int, int, int] = (10, 20, 30), size: tuple[int, int] = (40, 30),
              fmt: str = "PNG") -> bytes:
    """A tiny in-memory image, no files touched."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
