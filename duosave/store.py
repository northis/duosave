"""Common invariants for placing an image into a source folder.

Shared by the patch pipeline (`duosave.patch_apply`) and direct uploads: a safe
name, a collision suffix when the path already holds different content, and an
atomic write so readers never see half a file.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import config, patchfmt
from .db import file_by_path


def target_path(conn: sqlite3.Connection, folder: str, name: str,
                sha256: str) -> tuple[str, bool]:
    """Return `("<folder>/<safe-name>", renamed)` for an image about to be stored.

    A name that is already valid per `patchfmt.NAME_RE` and has an image suffix is
    kept as is; anything else goes through `patchfmt.safe_name`. When the target
    path holds different content (a `files` row or a file on disk), the stem gets
    a `-<sha[:8]>` suffix and `renamed` is True.
    """
    if patchfmt.NAME_RE.match(name) and name.lower().endswith(patchfmt.IMAGE_SUFFIXES):
        safe = name
    else:
        safe = patchfmt.safe_name(name)
    rel = f"{folder}/{safe}"
    if not _name_taken(conn, rel, sha256):
        return rel, False
    stem, _, suffix = safe.rpartition(".")
    return f"{folder}/{stem}-{sha256[:8]}.{suffix}", True


def write_atomic(path: Path, data: bytes) -> None:
    """Write bytes through a `.partial` file so readers never see half a file.

    `OSError` propagates: callers write the file before opening a DB transaction,
    so a failure leaves neither rows nor a target file behind.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(data)
    os.replace(partial, path)


def place_image(conn: sqlite3.Connection, folder: str, name: str, data: bytes,
                sha256: str) -> tuple[str, bool]:
    """Write the image into its source folder; returns `(rel_path, renamed)`."""
    rel, renamed = target_path(conn, folder, name, sha256)
    write_atomic(config.REPO / rel, data)
    return rel, renamed


def _name_taken(conn: sqlite3.Connection, path: str, sha256: str) -> bool:
    """True when the target name holds different content (in `files` or on disk)."""
    row = file_by_path(conn, path)
    if row is not None:
        return row["sha256"] != sha256
    file_path = config.REPO / path
    if file_path.exists():
        return patchfmt.sha256_file(file_path) != sha256
    return False
