"""Review queue for agent/human batches: export pending files, import results."""

from __future__ import annotations

import json
from pathlib import Path

from .db import add_source, connect, set_file, update_card, upsert_card
from .text import fold_text


def cut_slices(count: int, size: int, start_index: int) -> list[str]:
    """Cut the next review items into slice files (with thumbnail previews)."""
    from .thumbs import ensure_thumb

    conn = connect()
    rows = conn.execute(
        """SELECT f.path, f.sha256, c.language, c.original, c.translation, c.app, c.screen_type
           FROM files f LEFT JOIN sources s ON s.path=f.path LEFT JOIN cards c ON c.id=s.card_id
           WHERE f.status='review' ORDER BY f.path LIMIT ?""",
        (count * size,),
    ).fetchall()
    conn.close()
    base = Path(__file__).resolve().parents[1] / "data" / "agent_results"
    base.mkdir(parents=True, exist_ok=True)
    names = []
    for i in range(count):
        chunk = rows[i * size : (i + 1) * size]
        if not chunk:
            break
        name = f"slice_{start_index + i:03d}.jsonl"
        with (base / name).open("w", encoding="utf-8") as fh:
            for row in chunk:
                item = dict(row)
                item["thumb"] = ensure_thumb(item["path"], item["sha256"])
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        names.append(name)
    return names


def write_queue(out_path: Path, limit: int | None = None, offset: int = 0) -> int:
    conn = connect()
    rows, _ = review_rows(conn, limit=limit, offset=offset)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    conn.close()
    return len(rows)


def review_rows(conn, limit: int | None = None, offset: int = 0):
    query = """
        SELECT f.path, f.sha256, f.status, f.reason,
               c.id AS card_id, c.language, c.original, c.translation,
               c.app, c.screen_type, s.crop_path
        FROM files f
        LEFT JOIN sources s ON s.path = f.path
        LEFT JOIN cards c ON c.id = s.card_id
        WHERE f.status = 'review'
        ORDER BY f.last_seen DESC
    """
    params: list = []
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params = [limit, offset]
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows], None


def import_results(results_path: Path) -> dict:
    """Apply agent results: one JSONL object per file path.

    Accepted fields: path, sha256, action ("set"|"reject"|"accept"), usable,
    language, pairs [{original, translation, kind}], note.
    """
    conn = connect()
    applied = {"set": 0, "accept": 0, "reject": 0, "skipped": 0}
    for line in results_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        path = item.get("path")
        if not path:
            applied["skipped"] += 1
            continue
        row = conn.execute("SELECT path, sha256 FROM files WHERE path = ?", (path,)).fetchone()
        if row is None:
            applied["skipped"] += 1
            continue
        action = item.get("action", "set")
        if action == "reject":
            set_file(conn, path=path, sha256=item.get("sha256", ""), size=0, mtime=0,
                     status="rejected", reason=item.get("note", "rejected by agent"))
            applied["reject"] += 1
            conn.commit()
            continue
        if action == "accept":
            card_row = conn.execute(
                "SELECT card_id FROM sources WHERE path = ?", (path,)
            ).fetchone()
            if card_row is not None and card_row["card_id"] is not None:
                update_card(conn, card_row["card_id"], status="manual",
                            notes="accepted by agent")
                set_file(conn, path=path, sha256=item.get("sha256", ""), size=0, mtime=0,
                         status="reviewed", reason="agent accepted")
                applied["accept"] += 1
            else:
                applied["skipped"] += 1
            conn.commit()
            continue
        usable = item.get("usable", True)
        if not usable or not item.get("pairs"):
            set_file(conn, path=path, sha256=item.get("sha256", ""), size=0, mtime=0,
                     status="skipped", reason=item.get("note", "no pair"))
            applied["skipped"] += 1
            conn.commit()
            continue
        pairs = item["pairs"]
        language = item.get("language") or "unk"
        old_ids = [
            r["card_id"]
            for r in conn.execute("SELECT card_id FROM sources WHERE path = ?", (path,))
            if r["card_id"] is not None
        ]
        crop_path = None
        if item.get("app") == "drops":
            from PIL import Image

            from .config import REPO
            from .crops import save_crop

            full = REPO / path
            if full.exists():
                with Image.open(full) as raw:
                    crop_path = save_crop(raw.convert("RGB"), row["sha256"])
        new_ids: list[int] = []
        for pair in pairs:
            card_id = upsert_card(
                conn,
                language=language,
                original=pair["original"],
                translation=pair["translation"],
                kind=pair.get("kind", "sentence"),
                app=item.get("app"),
                screen_type=item.get("screen_type"),
                status="manual",
                notes=item.get("note", ""),
                original_folded=fold_text(pair["original"]),
                translation_folded=fold_text(pair["translation"]),
            )
            add_source(conn, card_id=card_id, path=path, sha256=item.get("sha256", ""),
                       app=item.get("app"), screen_type=item.get("screen_type"),
                       crop_path=crop_path, agreement=None, recognizer="agent")
            new_ids.append(card_id)
        for old_id in old_ids:
            if old_id in new_ids:
                continue
            conn.execute("DELETE FROM sources WHERE path = ? AND card_id = ?", (path, old_id))
            leftover = conn.execute(
                "SELECT COUNT(*) AS n FROM sources WHERE card_id = ?", (old_id,)
            ).fetchone()["n"]
            if leftover == 0:
                conn.execute("DELETE FROM cards WHERE id = ? AND status != 'manual'", (old_id,))
        set_file(conn, path=path, sha256=item.get("sha256", ""), size=0, mtime=0,
                 status="reviewed", reason=item.get("note"))
        applied["set"] += 1
        conn.commit()
    conn.close()
    return applied
