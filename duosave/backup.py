"""Consistent SQLite snapshots and streamed zip backups."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import time
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from . import config, db
from .buildinfo import build_info

Kind = Literal["db", "full"]

# Archive paths (relative to the repository) included in each backup kind.
INCLUDE: dict[str, list[str]] = {
    "db": [],
    "full": ["pictures", "screens", "data/media", "data/wordlists"],
}

DB_ARCHIVE_PATH = "data/duosave.db"
MANIFEST_NAME = "backup-manifest.json"
COPY_CHUNK = 1024 * 1024
ESTIMATE_TTL = 60
_counts_tables = ("cards", "sources", "files", "patches")

_estimate_cache: dict[str, tuple[float, int]] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot_db(dest: Path, src: Path | None = None) -> Path:
    """Consistent copy of the live database via the SQLite online backup API."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(src or db.DB_PATH))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return dest


def _unique(path: Path) -> Path:
    """Same-second snapshots must not overwrite each other: add -2, -3, ... if taken."""
    if not path.exists():
        return path
    for index in range(2, 1000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError(f"cannot find a free snapshot name next to {path}")


def snapshot(label: str, keep: int | None = None, prefix: str | None = None) -> Path:
    """Snapshot the DB to `data/backups/<label>-<UTC>.db` and prune the same label.

    `prefix` overrides the retention group (patches keep `pre-patch-` as one group).
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = _unique(config.BACKUPS_DIR / f"{label}-{stamp}.db")
    snapshot_db(dest)
    prune(prefix or label, config.SNAPSHOT_KEEP if keep is None else keep)
    return dest


def prune(prefix: str, keep: int) -> list[Path]:
    """Delete the oldest `<prefix>-*.db` beyond `keep`; return the removed paths."""
    files = sorted(
        config.BACKUPS_DIR.glob(f"{prefix}-*.db"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    )
    removed: list[Path] = []
    for path in files[:-keep] if keep > 0 else files:
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            pass
    return removed


def iter_files(kind: Kind) -> Iterator[tuple[str, Path]]:
    """(archive path, disk path) pairs: recursive, sorted, regular files, no symlinks."""
    for folder in INCLUDE[kind]:
        base = config.REPO / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            yield path.relative_to(config.REPO).as_posix(), path


class _Sink(io.RawIOBase):
    """Non-seekable write-only buffer that hands bytes to the stream generator."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:  # type: ignore[override]
        self._buffer.extend(data)
        return len(data)

    def pop(self) -> bytes:
        data = bytes(self._buffer)
        self._buffer.clear()
        return data


def _stream_file(zf: zipfile.ZipFile, sink: _Sink, arcname: str, path: Path,
                 compress_type: int) -> Iterator[bytes]:
    """Copy one file into the archive in 1 MiB chunks, yielding bytes as they appear."""
    info = zipfile.ZipInfo(arcname, date_time=time.localtime()[:6])
    info.compress_type = compress_type
    digest = hashlib.sha256()
    size = 0
    with zf.open(info, "w", force_zip64=True) as target, path.open("rb") as source:
        while chunk := source.read(COPY_CHUNK):
            target.write(chunk)
            digest.update(chunk)
            size += len(chunk)
            data = sink.pop()
            if data:
                yield data
    return digest.hexdigest(), size


def _counts(snapshot_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(str(snapshot_path))
    try:
        counts: dict[str, int] = {}
        for table in _counts_tables:
            try:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.OperationalError:
                counts[table] = 0
        return counts
    finally:
        conn.close()


def manifest(kind: Kind, entries: list[dict], db_info: dict) -> dict:
    """backup-manifest.json body (contracts/admin-api.md)."""
    info = build_info()
    return {
        "format": "duosave-backup",
        "format_version": 1,
        "kind": kind,
        "created_at": now_iso(),
        "version": info["version"],
        "commit": info["commit"],
        "db": db_info,
        "totals": {
            "files": len(entries) + 1,
            "bytes": int(db_info.get("size", 0)) + sum(int(entry["size"]) for entry in entries),
        },
        "entries": entries,
    }


def iter_backup_zip(kind: Kind) -> Iterator[bytes]:
    """Stream the archive: DB snapshot first, manifest last, temp snapshot always removed."""
    config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = config.BACKUPS_DIR / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = tmp_dir / f"{uuid4().hex}.db"
    snapshot_db(snapshot_path)
    sink = _Sink()
    entries: list[dict] = []
    try:
        with zipfile.ZipFile(sink, "w", allowZip64=True) as zf:
            db_sha, db_size = yield from _stream_file(
                zf, sink, DB_ARCHIVE_PATH, snapshot_path, zipfile.ZIP_DEFLATED
            )
            data = sink.pop()
            if data:
                yield data
            db_info = {
                "path": DB_ARCHIVE_PATH,
                "size": db_size,
                "sha256": db_sha,
                "counts": _counts(snapshot_path),
            }
            for arcname, path in iter_files(kind):
                sha256, size = yield from _stream_file(
                    zf, sink, arcname, path, zipfile.ZIP_STORED
                )
                data = sink.pop()
                if data:
                    yield data
                entries.append({"path": arcname, "size": size, "sha256": sha256})
            body = json.dumps(manifest(kind, entries, db_info), ensure_ascii=False).encode("utf-8")
            zf.writestr(MANIFEST_NAME, body, compress_type=zipfile.ZIP_DEFLATED)
            data = sink.pop()
            if data:
                yield data
        # The central directory is written on close: flush it to the client too.
        data = sink.pop()
        if data:
            yield data
    finally:
        snapshot_path.unlink(missing_ok=True)


def estimate(kind: Kind) -> int:
    """Approximate download size in bytes (DB snapshot + included files), cached 60 s."""
    cached = _estimate_cache.get(kind)
    now = time.time()
    if cached is not None and now - cached[0] < ESTIMATE_TTL:
        return cached[1]
    size = db.DB_PATH.stat().st_size if db.DB_PATH.exists() else 0
    if kind == "full":
        size += sum(path.stat().st_size for _, path in iter_files(kind))
    _estimate_cache[kind] = (now, size)
    return size


def backup_filename(kind: Kind, now: datetime | None = None, short: str | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"duosave-backup-{kind}-{stamp}-{short or 'nocommit'}.zip"
