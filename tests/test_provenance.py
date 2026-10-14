"""Recognition provenance: which engine produced a stored result."""

from __future__ import annotations

import sqlite3

from duosave import db, patchfmt, sync

from helpers import png_bytes

PNG = png_bytes()
SHA = patchfmt.sha256_bytes(PNG)
REL = "screens/shot.png"


def _usable_data() -> dict:
    """Cache dict of a successful recognition (the shape `Recognition.to_cache` emits)."""
    return {
        "version": 1,
        "usable": True,
        "app": "duolingo_card",
        "screen_type": "card",
        "language": "pl",
        "language_source": "ocr",
        "pairs": [{"original": "kot", "translation": "cat", "kind": "word"}],
        "agreement": True,
        "status": "auto",
        "reason": "",
    }


def _file_recognizer(conn: sqlite3.Connection, path: str = REL) -> str:
    row = conn.execute("SELECT recognizer FROM files WHERE path = ?", (path,)).fetchone()
    return str(row["recognizer"])


def _source_recognizer(conn: sqlite3.Connection, path: str = REL) -> str:
    row = conn.execute("SELECT recognizer FROM sources WHERE path = ?", (path,)).fetchone()
    return str(row["recognizer"])


def test_store_recognition_writes_vision_to_files_and_sources(tmp_repo) -> None:
    path = tmp_repo.screens / "shot.png"
    path.write_bytes(PNG)

    status = sync.store_recognition(tmp_repo.conn, REL, path, SHA, _usable_data(),
                                    recognizer="vision")

    assert status == "auto"
    assert _file_recognizer(tmp_repo.conn) == "vision"
    assert _source_recognizer(tmp_repo.conn) == "vision"


def test_store_recognition_defaults_to_ocr(tmp_repo) -> None:
    path = tmp_repo.screens / "shot.png"
    path.write_bytes(PNG)

    status = sync.store_recognition(tmp_repo.conn, REL, path, SHA, _usable_data())

    assert status == "auto"
    assert _file_recognizer(tmp_repo.conn) == "ocr"
    assert _source_recognizer(tmp_repo.conn) == "ocr"


def test_set_file_without_recognizer_keeps_the_existing_value(tmp_db) -> None:
    db.set_file(tmp_db, path=REL, sha256=SHA, size=len(PNG), mtime=1.0, status="review",
                recognizer="vision")

    db.set_file(tmp_db, path=REL, sha256=SHA, size=len(PNG), mtime=1.0, status="review")

    assert _file_recognizer(tmp_db) == "vision"


def test_set_file_new_row_gets_ocr(tmp_db) -> None:
    db.set_file(tmp_db, path=REL, sha256=SHA, size=len(PNG), mtime=1.0, status="review")

    assert _file_recognizer(tmp_db) == "ocr"


def test_set_file_with_recognizer_updates_the_column(tmp_db) -> None:
    db.set_file(tmp_db, path=REL, sha256=SHA, size=len(PNG), mtime=1.0, status="review",
                recognizer="ocr")
    db.set_file(tmp_db, path=REL, sha256=SHA, size=len(PNG), mtime=1.0, status="review",
                recognizer="vision")

    assert _file_recognizer(tmp_db) == "vision"

    db.set_file(tmp_db, path=REL, sha256=SHA, size=len(PNG), mtime=1.0, status="review",
                recognizer="ocr")

    assert _file_recognizer(tmp_db) == "ocr"
