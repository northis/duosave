"""Incremental sync: scan image folders, recognize new/changed files, store in DB."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from PIL import Image

from .config import CACHE_DIR, IMAGE_SUFFIXES, RECOGNIZER_VERSION, REPO, SOURCE_FOLDERS
from .crops import save_crop
from .db import add_source, connect, init_db, set_file, upsert_card
from .filenames import created_ts as file_created_ts
from .recognize import Recognition, recognize_image
from .text import fold_text


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cache(sha256: str) -> dict | None:
    path = CACHE_DIR / f"{sha256}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("version") != RECOGNIZER_VERSION:
        return None
    return data


def save_cache(sha256: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{sha256}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def store_recognition(conn, rel_path: str, path: Path, sha256: str, data: dict) -> str:
    """Store one recognition result; returns the file status."""
    recognition = Recognition.from_cache(data)
    stat = path.stat()
    taken_ts = file_created_ts(path, fallback=stat.st_ctime)
    if not recognition.usable:
        set_file(conn, path=rel_path, sha256=sha256, size=stat.st_size,
                 mtime=stat.st_mtime_ns, status=recognition.status,
                 reason=recognition.reason, elapsed=recognition.elapsed,
                 created_ts=taken_ts)
        return recognition.status

    crop_path = None
    if recognition.app == "drops":
        with Image.open(path) as raw:
            crop_path = save_crop(raw.convert("RGB"), sha256)

    first = recognition.pairs[0]
    card_id = upsert_card(
        conn,
        language=recognition.language or "unk",
        original=first.original,
        translation=first.translation,
        kind=first.kind,
        app=recognition.app,
        screen_type=recognition.screen_type,
        status=recognition.status,
        original_folded=fold_text(first.original),
        translation_folded=fold_text(first.translation),
    )
    add_source(
        conn,
        card_id=card_id,
        path=rel_path,
        sha256=sha256,
        app=recognition.app,
        screen_type=recognition.screen_type,
        crop_path=crop_path,
        agreement=recognition.agreement,
    )
    set_file(conn, path=rel_path, sha256=sha256, size=stat.st_size,
             mtime=stat.st_mtime_ns, status=recognition.status,
             reason=recognition.reason, elapsed=recognition.elapsed,
             created_ts=taken_ts)
    return recognition.status


def sync(folders: list[str] | None = None, limit: int | None = None, passes: int = 2,
         retry: bool = False, quiet: bool = False) -> dict:
    folders = folders or list(SOURCE_FOLDERS)
    conn = connect()
    init_db(conn)

    tasks: list[tuple[str, Path]] = []
    for folder in folders:
        base = REPO / folder
        if not base.exists():
            continue
        for path in sorted(base.iterdir()):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                tasks.append((folder, path))

    stats = Counter()
    started = time.perf_counter()
    processed = 0
    for folder, path in tasks:
        rel_path = f"{folder}/{path.name}"
        stat = path.stat()
        existing = conn.execute(
            "SELECT sha256, mtime, size, status FROM files WHERE path = ?", (rel_path,)
        ).fetchone()
        if existing is not None and not retry:
            if existing["mtime"] == stat.st_mtime_ns and existing["size"] == stat.st_size:
                stats["skipped_unchanged"] += 1
                continue
            if existing["status"] == "reviewed" and existing["mtime"] == stat.st_mtime_ns:
                stats["skipped_reviewed"] += 1
                continue
        if limit is not None and processed >= limit:
            break

        sha256 = file_sha(path)
        data = load_cache(sha256)
        if data is None:
            recognition, data = recognize_image(path, kind_hint=SOURCE_FOLDERS.get(folder, "auto"),
                                                passes=passes)
            save_cache(sha256, data)
        else:
            recognition = Recognition.from_cache(data)
        status = store_recognition(conn, rel_path, path, sha256, data)
        stats[status] += 1
        stats["processed"] += 1
        processed += 1
        if not quiet and processed % 25 == 0:
            elapsed = time.perf_counter() - started
            rate = processed / elapsed
            remaining = (len(tasks) - processed) / rate if rate else 0
            print(f"  ... {processed}/{len(tasks)}  {rate:.1f} img/s  ETA {remaining / 60:.0f} min")
        conn.commit()

    conn.commit()
    elapsed = time.perf_counter() - started
    result = dict(stats)
    result["elapsed"] = round(elapsed, 1)
    result["total_found"] = len(tasks)
    if not quiet:
        print(f"sync done: {dict(stats)} in {elapsed:.0f}s")
    conn.close()
    return result
