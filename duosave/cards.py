"""Card maintenance that spans the database and the files on disk.

The only operation here is deleting a card: the admin page removes a wrong card together
with the frames it was recognized from, so a fresh share of the same image is processed
again instead of answering "duplicate". `sources` and `card_embeddings` cascade from the
card row; the `files` rows go in the same transaction, then the images, Drops crops and
recognition caches are removed — and only when no other card still references the frame.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config


class CardNotFound(Exception):
    """No card with that id."""


def delete_card(conn: sqlite3.Connection, card_id: int) -> dict:
    """Delete one card with its sources, embeddings and source frames.

    The database changes are committed before any file disappears: a crash in the middle
    leaves frames without rows (the next sync or share re-recognizes them) rather than a
    card pointing at an image that is already gone.
    """
    card = conn.execute(
        "SELECT language, original, translation FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if card is None:
        raise CardNotFound(card_id)
    sources = conn.execute(
        "SELECT path, sha256, crop_path FROM sources WHERE card_id = ? ORDER BY id", (card_id,)
    ).fetchall()
    conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    report = {"removed": [], "missing": [], "kept": []}
    doomed = []
    for source in sources:
        if _still_referenced(conn, source["path"]):
            report["kept"].append(source["path"])
            continue
        conn.execute("DELETE FROM files WHERE path = ?", (source["path"],))
        doomed.append(source)
    conn.commit()

    for source in doomed:
        report[_remove_files(source)].append(source["path"])
    return {
        "card_id": card_id,
        "language": card["language"],
        "original": card["original"],
        "translation": card["translation"],
        "removed": report["removed"],
        "missing": report["missing"],
        "kept": report["kept"],
    }


def _remove_files(source: sqlite3.Row) -> str:
    """Drop one source's frame, crop and cache; returns removed/missing/kept."""
    _unlink(_inside_repo(source["crop_path"]))
    _unlink(config.CACHE_DIR / f"{source['sha256']}.json")
    image = _source_file(source["path"])
    if image is None:
        return "kept"
    if not image.exists():
        return "missing"
    try:
        image.unlink()
    except OSError:
        return "kept"
    return "removed"


def _still_referenced(conn: sqlite3.Connection, path: str) -> bool:
    """True when some other card also has a source row for this path.

    Called after the card row is gone, so only the rows of other cards remain.
    """
    row = conn.execute("SELECT COUNT(*) AS n FROM sources WHERE path = ?", (path,)).fetchone()
    return bool(row["n"])


def _source_file(rel: str) -> Path | None:
    """The frame on disk, or None when the path is not a known source folder."""
    if not rel:
        return None
    folder = rel.replace("\\", "/").split("/", 1)[0]
    if folder not in config.SOURCE_FOLDERS:
        return None
    return _inside_repo(rel)


def _inside_repo(rel: str | None) -> Path | None:
    """Resolve a stored relative path, refusing anything outside the repository."""
    if not rel:
        return None
    repo = config.REPO.resolve()
    candidate = (repo / rel).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError:
        return None
    return candidate


def _unlink(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
