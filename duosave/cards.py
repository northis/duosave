"""Card maintenance that spans the database and the files on disk.

Deleting a card removes it together with the frames it was recognized from, so a fresh
share of the same image is processed again instead of answering "duplicate": `sources`
and `card_embeddings` cascade from the card row; the `files` rows go in the same
transaction, then the images, Drops crops and recognition caches are removed — and only
when no other card still references the frame. Changing a card's language re-keys it,
merging into the card that already owns the pair when there is one.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config
from .db import card_by_key, now


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


def set_language(conn: sqlite3.Connection, card_id: int, language: str) -> dict:
    """Change one card's language, merging into the card that already owns the pair.

    The pair key is (language, original, translation): when another card already has the
    pair under the target language, this card's frames move there and the emptied row is
    dropped, so a change never leaves a duplicate behind. The card keeps its status and
    notes — fixing a language is metadata maintenance, not a review decision.
    """
    card = conn.execute(
        "SELECT language, original, translation FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if card is None:
        raise CardNotFound(card_id)
    report = {
        "card_id": card_id,
        "language": language,
        "original": card["original"],
        "translation": card["translation"],
        "merged_into": None,
        "changed": False,
    }
    if card["language"] == language:
        return report
    report["changed"] = True
    target = card_by_key(conn, language, card["original"], card["translation"])
    if target is not None and int(target["id"]) != card_id:
        report["merged_into"] = int(target["id"])
        conn.execute("UPDATE OR IGNORE sources SET card_id = ? WHERE card_id = ?",
                     (report["merged_into"], card_id))
        conn.execute("DELETE FROM sources WHERE card_id = ?", (card_id,))
        conn.execute(
            "DELETE FROM cards WHERE id = ? AND NOT EXISTS"
            " (SELECT 1 FROM sources WHERE card_id = ?)",
            (card_id, card_id),
        )
        return report
    conn.execute("UPDATE cards SET language = ?, updated_at = ? WHERE id = ?",
                 (language, now(), card_id))
    return report


def supersede_sources(conn: sqlite3.Connection, card_id: int, keep_path: str) -> list[sqlite3.Row]:
    """Make `keep_path` the only frame of the card: a re-import of the same phrase wins.

    Older source rows of the card go away; their `files` rows go too unless another card
    still uses the frame. Returns the rows whose files must be removed with
    `remove_superseded` after the caller commits.
    """
    old = conn.execute(
        "SELECT path, sha256, crop_path FROM sources WHERE card_id = ? AND path != ?",
        (card_id, keep_path),
    ).fetchall()
    doomed = []
    for source in old:
        conn.execute("DELETE FROM sources WHERE card_id = ? AND path = ?", (card_id, source["path"]))
        if _still_referenced(conn, source["path"]):
            continue
        conn.execute("DELETE FROM files WHERE path = ?", (source["path"],))
        doomed.append(source)
    return doomed


def remove_superseded(doomed: list[sqlite3.Row]) -> list[str]:
    """Remove the frames returned by `supersede_sources` (after commit); returns their paths."""
    return [source["path"] for source in doomed if _remove_files(source) == "removed"]


def touch_file(conn: sqlite3.Connection, path: str, created_ts: int) -> None:
    """A known frame was imported again: move its date (and so its card's) forward."""
    conn.execute("UPDATE files SET created_ts = ?, last_seen = datetime('now') WHERE path = ?",
                 (int(created_ts), path))


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
