"""Backups: consistent snapshots, streamed zip contents, retention, estimates."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

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


def _set_mtime(path, moment: datetime) -> None:
    os.utime(path, (moment.timestamp(), moment.timestamp()))


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


def test_parse_moment_accepts_a_date_and_iso() -> None:
    aware = backup.parse_moment("2026-01-15T10:00:00+03:00")

    assert aware == datetime(2026, 1, 15, 7, tzinfo=timezone.utc)
    assert backup.parse_moment("2026-01-15T07:00:00Z") == aware
    assert backup.parse_moment("2026-01-15") == datetime(2026, 1, 15).astimezone(timezone.utc)
    with pytest.raises(ValueError):
        backup.parse_moment("15.01.2026")


def test_incremental_first_run_needs_since(tmp_repo) -> None:
    with pytest.raises(ValueError):
        backup.run_incremental()


def test_incremental_archive_has_new_files_and_the_db(tmp_repo) -> None:
    old = tmp_repo.root / "pictures" / "old.png"
    new = tmp_repo.root / "screens" / "new.png"
    _write(old, png_bytes())
    _write(new, png_bytes(color=(1, 2, 3)))
    _set_mtime(old, datetime(2025, 12, 31, tzinfo=timezone.utc))
    _set_mtime(new, datetime(2026, 2, 1, tzinfo=timezone.utc))

    result = backup.run_incremental("2026-01-15T00:00:00+00:00")

    assert result["files"] == 1
    assert result["since"] == "2026-01-15T00:00:00+00:00"
    with zipfile.ZipFile(result["archive"]) as zf:
        assert set(zf.namelist()) == {"data/duosave.db", "screens/new.png",
                                      "backup-manifest.json"}
        assert zf.testzip() is None
        assert zf.getinfo("screens/new.png").compress_type == zipfile.ZIP_STORED
        assert zf.getinfo("data/duosave.db").compress_type == zipfile.ZIP_DEFLATED
        assert json.loads(zf.read("backup-manifest.json"))["kind"] == "incremental"
    state = tmp_repo.data / "backups" / "incremental" / backup.STATE_NAME
    assert json.loads(state.read_text(encoding="utf-8"))["last_backup"]


def test_incremental_second_run_continues_from_the_previous_one(tmp_repo) -> None:
    now = datetime.now(timezone.utc)
    first = tmp_repo.root / "pictures" / "a.png"
    _write(first, png_bytes())
    _set_mtime(first, now - timedelta(days=1))
    backup.run_incremental((now - timedelta(days=2)).isoformat())

    second = tmp_repo.root / "pictures" / "b.png"
    _write(second, png_bytes(color=(9, 9, 9)))
    _set_mtime(second, now + timedelta(minutes=1))

    result = backup.run_incremental()

    with zipfile.ZipFile(result["archive"]) as zf:
        names = zf.namelist()
    assert "pictures/b.png" in names
    assert "pictures/a.png" not in names
    with pytest.raises(ValueError):
        backup.run_incremental((now - timedelta(days=2)).isoformat())


def test_incremental_skips_and_keeps_the_cutoff_when_nothing_changed(tmp_repo) -> None:
    folder = tmp_repo.data / "backups" / "incremental"
    state = folder / backup.STATE_NAME
    # Everything in the repository is older than the run, as it is after a quiet day:
    # the state time has a second of slack, so fresh timestamps would count as changes.
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    for path in (tmp_repo.data / "duosave.db", tmp_repo.data / "duosave.db-wal"):
        if path.exists():
            _set_mtime(path, old)

    result = backup.run_incremental((old - timedelta(hours=1)).isoformat())

    assert result["skipped"] is False  # the DB alone was written after the cutoff
    assert result["files"] == 0
    cutoff = state.read_text(encoding="utf-8")
    archives = sorted(folder.glob("*.zip"))
    assert len(archives) == 1

    skipped = backup.run_incremental()

    assert skipped["skipped"] is True
    assert skipped["archive"] is None
    assert state.read_text(encoding="utf-8") == cutoff
    assert sorted(folder.glob("*.zip")) == archives
