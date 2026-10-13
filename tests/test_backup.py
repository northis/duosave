"""Backups: consistent snapshots, streamed zip contents, retention, estimates."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from datetime import datetime

from duosave import backup, db

from helpers import png_bytes, sha256_hex

INSERT_CARD = (
    "INSERT INTO cards (language, original, translation, kind, app, original_folded,"
    " translation_folded, status, created_at, updated_at) VALUES (?, ?, ?, 'word', 'drops',"
    " ?, ?, 'auto', 't', 't')"
)


def _write(path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _archive(kind: str) -> zipfile.ZipFile:
    buffer = io.BytesIO(b"".join(backup.iter_backup_zip(kind)))
    return zipfile.ZipFile(buffer)


def test_snapshot_is_consistent_during_open_write(tmp_repo) -> None:
    assert tmp_repo.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    tmp_repo.conn.execute(INSERT_CARD, ("pl", "jeden", "one", "jeden", "one"))
    tmp_repo.conn.commit()
    writer = db.connect()
    try:
        writer.execute("BEGIN")
        writer.execute(INSERT_CARD, ("pl", "dwa", "two", "dwa", "two"))

        dest = backup.snapshot_db(tmp_repo.data / "backups" / "check.db")
        snapshot = sqlite3.connect(dest)
        try:
            assert snapshot.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            originals = [row[0] for row in snapshot.execute("SELECT original FROM cards")]
        finally:
            snapshot.close()
    finally:
        writer.rollback()
        writer.close()

    assert originals == ["jeden"]


def test_snapshot_label_and_retention(tmp_repo) -> None:
    other = backup.snapshot("pre-update")

    for _ in range(12):
        backup.snapshot("manual", keep=10)

    manual = list((tmp_repo.data / "backups").glob("manual-*.db"))
    assert len(manual) == 10
    assert other.exists()
    assert not list((tmp_repo.data / "backups").glob("pre-update-*.db"))[1:]


def test_db_backup_zip_contents(tmp_repo) -> None:
    tmp_repo.conn.execute(INSERT_CARD, ("pl", "jeden", "one", "jeden", "one"))
    tmp_repo.conn.commit()

    with _archive("db") as zf:
        assert zf.namelist() == ["data/duosave.db", "backup-manifest.json"]
        manifest = json.loads(zf.read("backup-manifest.json"))
        db_bytes = zf.read("data/duosave.db")

    assert manifest["format"] == "duosave-backup"
    assert manifest["format_version"] == 1
    assert manifest["kind"] == "db"
    assert manifest["db"]["sha256"] == hashlib.sha256(db_bytes).hexdigest()
    assert manifest["db"]["size"] == len(db_bytes)
    assert manifest["db"]["counts"] == {"cards": 1, "sources": 0, "files": 0, "patches": 0}
    assert manifest["entries"] == []
    assert manifest["totals"]["files"] == 1


def test_full_backup_zip_contents(tmp_repo) -> None:
    included = {
        "pictures/card.png": png_bytes(),
        "screens/screen.png": png_bytes(color=(1, 2, 3)),
        "data/media/drops/crop.jpg": png_bytes(fmt="JPEG"),
        "data/wordlists/pl.txt": b"slowo\n",
    }
    excluded = [
        "data/models/model.bin",
        "data/thumbs/x.png",
        "data/cache/x.json",
        "data/backups/old.db",
        "data/other/x",
        "data/patches/applied/x.zip",
        "screens_raw/raw.png",
    ]
    for name, data in included.items():
        _write(tmp_repo.root / name, data)
    for name in excluded:
        _write(tmp_repo.root / name, b"junk")

    with _archive("full") as zf:
        names = zf.namelist()
        manifest = json.loads(zf.read("backup-manifest.json"))
        contents = {name: zf.read(name) for name in names if name != "backup-manifest.json"}

    assert set(names) == set(included) | {"data/duosave.db", "backup-manifest.json"}
    assert names[-1] == "backup-manifest.json"
    for name, data in included.items():
        assert contents[name] == data
        entry = next(item for item in manifest["entries"] if item["path"] == name)
        assert entry["sha256"] == sha256_hex(data)
        assert entry["size"] == len(data)
    assert manifest["totals"]["bytes"] == sum(len(data) for data in contents.values())


def test_zip_is_readable_and_images_stored(tmp_repo) -> None:
    _write(tmp_repo.root / "screens/a.png", png_bytes())

    with _archive("full") as zf:
        assert zf.testzip() is None
        assert zf.getinfo("screens/a.png").compress_type == zipfile.ZIP_STORED
        assert zf.getinfo("data/duosave.db").compress_type == zipfile.ZIP_DEFLATED
        assert zf.getinfo("backup-manifest.json").compress_type == zipfile.ZIP_DEFLATED


def test_closing_generator_removes_temp_snapshot(tmp_repo) -> None:
    gen = backup.iter_backup_zip("db")
    next(gen)
    tmp_dir = tmp_repo.data / "backups" / "tmp"
    assert list(tmp_dir.glob("*.db"))

    gen.close()

    assert list(tmp_dir.glob("*.db")) == []


def test_backup_filename() -> None:
    assert backup.backup_filename("full", datetime(2026, 10, 12, 10, 50, 0), "9c96590") == \
        "duosave-backup-full-20261012-105000-9c96590.zip"
    assert backup.backup_filename("db", datetime(2026, 10, 12, 10, 50, 0), None) == \
        "duosave-backup-db-20261012-105000-nocommit.zip"


def test_estimate(tmp_repo) -> None:
    _write(tmp_repo.root / "pictures/a.png", b"x" * 100)
    backup._estimate_cache.clear()
    db_size = db.DB_PATH.stat().st_size

    assert backup.estimate("db") == db_size
    assert backup.estimate("full") == db_size + 100
