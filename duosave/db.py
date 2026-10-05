"""SQLite storage: cards (unique pairs), sources (image references), files (sync state)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH, DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    language TEXT NOT NULL DEFAULT 'unk',
    original TEXT NOT NULL,
    translation TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'sentence',
    app TEXT,
    screen_type TEXT,
    original_folded TEXT NOT NULL,
    translation_folded TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'auto',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_cards_pair ON cards(language, original, translation);
CREATE INDEX IF NOT EXISTS ix_cards_lang ON cards(language);
CREATE INDEX IF NOT EXISTS ix_cards_app ON cards(app);
CREATE INDEX IF NOT EXISTS ix_cards_status ON cards(status);
CREATE INDEX IF NOT EXISTS ix_cards_orig_folded ON cards(original_folded);
CREATE INDEX IF NOT EXISTS ix_cards_trans_folded ON cards(translation_folded);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    app TEXT,
    screen_type TEXT,
    crop_path TEXT,
    pass_agreement INTEGER,
    recognizer TEXT NOT NULL DEFAULT 'ocr',
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sources_card_path ON sources(card_id, path);
CREATE INDEX IF NOT EXISTS ix_sources_sha ON sources(sha256);
CREATE INDEX IF NOT EXISTS ix_sources_card ON sources(card_id);

CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    mtime REAL NOT NULL DEFAULT 0,
    created_ts INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    reason TEXT,
    recognizer TEXT NOT NULL DEFAULT 'ocr',
    elapsed REAL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_files_status ON files(status);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # migration for databases created before created_ts existed
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(files)")}
    if "created_ts" not in columns:
        conn.execute("ALTER TABLE files ADD COLUMN created_ts INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_files_created ON files(created_ts)")
    conn.commit()


def upsert_card(
    conn: sqlite3.Connection,
    *,
    language: str,
    original: str,
    translation: str,
    kind: str,
    app: str,
    screen_type: str | None,
    status: str,
    notes: str = "",
    original_folded: str,
    translation_folded: str,
) -> int:
    timestamp = now()
    conn.execute(
        """
        INSERT INTO cards (language, original, translation, kind, app, screen_type,
                           original_folded, translation_folded, status, notes,
                           created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(language, original, translation) DO UPDATE SET
            updated_at = excluded.updated_at,
            status = CASE WHEN cards.status = 'manual' THEN cards.status ELSE excluded.status END,
            notes = CASE WHEN cards.status = 'manual' THEN cards.notes ELSE excluded.notes END
        """,
        (language, original, translation, kind, app, screen_type,
         original_folded, translation_folded, status, notes, timestamp, timestamp),
    )
    row = conn.execute(
        "SELECT id FROM cards WHERE language = ? AND original = ? AND translation = ?",
        (language, original, translation),
    ).fetchone()
    return int(row["id"])


def add_source(
    conn: sqlite3.Connection,
    *,
    card_id: int,
    path: str,
    sha256: str,
    app: str,
    screen_type: str | None,
    crop_path: str | None,
    agreement: bool | None,
    recognizer: str = "ocr",
) -> None:
    conn.execute(
        """
        INSERT INTO sources (card_id, path, sha256, app, screen_type, crop_path,
                             pass_agreement, recognizer, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(card_id, path) DO UPDATE SET
            crop_path = COALESCE(excluded.crop_path, sources.crop_path),
            pass_agreement = excluded.pass_agreement,
            recognizer = excluded.recognizer
        """,
        (card_id, path, sha256, app, screen_type, crop_path,
         (1 if agreement else 0) if agreement is not None else None, recognizer, now()),
    )


def set_file(
    conn: sqlite3.Connection,
    *,
    path: str,
    sha256: str,
    size: int,
    mtime: float,
    status: str,
    reason: str | None = None,
    elapsed: float | None = None,
    created_ts: int | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO files (path, sha256, size, mtime, created_ts, status, reason, elapsed, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            sha256 = CASE WHEN excluded.sha256 != '' THEN excluded.sha256 ELSE files.sha256 END,
            size = CASE WHEN excluded.size > 0 THEN excluded.size ELSE files.size END,
            mtime = CASE WHEN excluded.mtime > 0 THEN excluded.mtime ELSE files.mtime END,
            created_ts = COALESCE(excluded.created_ts, files.created_ts),
            status = CASE WHEN files.status IN ('reviewed', 'rejected') THEN files.status
                          ELSE excluded.status END,
            reason = excluded.reason, elapsed = excluded.elapsed, last_seen = excluded.last_seen
        """,
        (path, sha256, size, mtime, created_ts, status, reason, elapsed, now(), now()),
    )


def search_cards(conn: sqlite3.Connection, query: str = "", lang: str = "", app: str = "",
                 limit: int = 60, offset: int = 0, sort: str = "new") -> tuple[list[dict], int]:
    clauses, params = [], []
    clauses.append("c.status != 'rejected'")
    if lang:
        clauses.append("c.language = ?")
        params.append(lang)
    if app == "duolingo":
        clauses.append("c.app IN ('duolingo_card', 'duolingo_app')")
    elif app:
        clauses.append("c.app = ?")
        params.append(app)
    from .text import fold_text

    folded = [fold_text(token) for token in query.split() if token]
    for token in folded:
        clauses.append("(c.original_folded LIKE ? OR c.translation_folded LIKE ?)")
        params.extend([f"%{token}%", f"%{token}%"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    time_expr = (
        "(SELECT MAX(f.created_ts) FROM sources s JOIN files f ON f.path = s.path "
        "WHERE s.card_id = c.id)"
    )
    direction = "ASC" if sort == "old" else "DESC"
    order_by = f"COALESCE(card_time, 0) {direction}, c.id DESC"
    rank_params: list[str] = []
    if folded:
        first = folded[0]
        rank = (
            "(CASE WHEN c.original_folded = ? OR c.translation_folded = ? THEN 0 "
            "WHEN c.original_folded LIKE ? OR c.translation_folded LIKE ? THEN 1 ELSE 2 END)"
        )
        rank_params = [first, first, f"{first}%", f"{first}%"]
        order_by = f"{rank}, {order_by}"

    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM cards c {where}", params
    ).fetchone()["n"]
    rows = conn.execute(
        f"""
        SELECT c.*, {time_expr} AS card_time,
               (SELECT COUNT(*) FROM sources s WHERE s.card_id = c.id) AS source_count
        FROM cards c {where}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
        """,
        [*params, *rank_params, limit, offset],
    ).fetchall()
    return [dict(row) for row in rows], int(total)


def get_card(conn: sqlite3.Connection, card_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT c.*,
               (SELECT MAX(f.created_ts) FROM sources s JOIN files f ON f.path = s.path
                WHERE s.card_id = c.id) AS card_time,
               (SELECT COUNT(*) FROM sources s WHERE s.card_id = c.id) AS source_count
        FROM cards c WHERE c.id = ?
        """,
        (card_id,),
    ).fetchone()
    if row is None:
        return None
    card = dict(row)
    sources = conn.execute(
        """SELECT s.path, s.app, s.screen_type, s.crop_path, s.pass_agreement, s.recognizer,
                  f.created_ts AS file_time
           FROM sources s LEFT JOIN files f ON f.path = s.path
           WHERE s.card_id = ? ORDER BY s.id""",
        (card_id,),
    ).fetchall()
    card["sources"] = [dict(s) for s in sources]
    return card


def update_card(conn: sqlite3.Connection, card_id: int, *, original: str | None = None,
                translation: str | None = None, language: str | None = None,
                status: str = "manual", notes: str | None = None) -> None:
    from .text import fold_text

    sets, params = [], []
    if original is not None:
        sets.append("original = ?")
        params.append(original)
        sets.append("original_folded = ?")
        params.append(fold_text(original))
    if translation is not None:
        sets.append("translation = ?")
        params.append(translation)
        sets.append("translation_folded = ?")
        params.append(fold_text(translation))
    if language is not None:
        sets.append("language = ?")
        params.append(language)
    sets.append("status = ?")
    params.append(status)
    if notes is not None:
        sets.append("notes = ?")
        params.append(notes)
    sets.append("updated_at = ?")
    params.append(now())
    params.append(card_id)
    conn.execute(f"UPDATE cards SET {', '.join(sets)} WHERE id = ?", params)


def review_files(conn: sqlite3.Connection, limit: int = 40, offset: int = 0) -> tuple[list[dict], int]:
    total = conn.execute("SELECT COUNT(*) AS n FROM files WHERE status = 'review'").fetchone()["n"]
    rows = conn.execute(
        """
        SELECT f.path, f.sha256, f.status, f.reason, f.elapsed,
               c.id AS card_id, c.language, c.original, c.translation, c.kind, c.app, c.screen_type,
               s.crop_path
        FROM files f
        LEFT JOIN sources s ON s.path = f.path
        LEFT JOIN cards c ON c.id = s.card_id
        WHERE f.status = 'review'
        ORDER BY f.last_seen DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [dict(row) for row in rows], int(total)


def stats(conn: sqlite3.Connection) -> dict:
    cards = conn.execute(
        "SELECT language, app, status, COUNT(*) AS n FROM cards GROUP BY language, app, status"
    ).fetchall()
    files = conn.execute("SELECT status, COUNT(*) AS n FROM files GROUP BY status").fetchall()
    return {
        "cards": [dict(row) for row in cards],
        "files": [dict(row) for row in files],
    }


def card_rows_for_export(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.language, c.app, c.original, c.translation, c.kind, c.screen_type, c.status,
               (SELECT COUNT(*) FROM sources s WHERE s.card_id = c.id) AS source_count
        FROM cards c
        WHERE c.status != 'rejected'
        ORDER BY c.language, c.original
        """
    ).fetchall()
    return [dict(row) for row in rows]
