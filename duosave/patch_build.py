"""Agent-side patch building: scan an inbox, check drafts, pack archives.

Runs on any machine with a repository clone — no database, no FastAPI, no ML stack
(FR-063). The inbox folder is only ever read; everything else lives in `outbox/`.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from . import __version__, config, patchfmt
from .buildinfo import build_info
from .filenames import created_ts as file_created_ts

LEDGER_NAME = "ledger.jsonl"
KNOWN_NAME = "known-hashes.txt"
WORK_DIR = ".work"
DONE_DIR = "done"
SLICE_RE = re.compile(r"^slice-(\d{3,})\.jsonl$")
COPY_CHUNK = 1024 * 1024


@dataclass
class ScanResult:
    new: int = 0          # new unique images (drafts without duplicate_of)
    known: int = 0        # skipped: already in the database (known-hashes)
    processed: int = 0    # skipped: already handled on this machine (ledger or drafts)
    duplicates: int = 0   # copies of an image already seen in this inbox
    total: int = 0        # images found in the inbox


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    pending: int = 0
    done: int = 0

    @property
    def exit_code(self) -> int:
        if self.errors:
            return 1
        if self.pending:
            return 2
        return 0


def resolve_inbox(arg: str | None) -> Path:
    """--inbox > DUOSAVE_INBOX > <repo>/inbox."""
    if arg:
        return Path(arg)
    env = os.environ.get("DUOSAVE_INBOX")
    return Path(env) if env else config.INBOX_DIR


def load_known(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    return patchfmt.parse_known_hashes(path.read_text(encoding="utf-8"))


def load_ledger(outbox: Path) -> set[str]:
    path = outbox / LEDGER_NAME
    if not path.exists():
        return set()
    hashes: set[str] = set()
    errors: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            hashes.add(patchfmt.LedgerEntry.model_validate_json(line).sha256)
        except ValidationError as exc:
            errors.append(f"{LEDGER_NAME}:{number}: {exc.errors()[0]['msg']}")
    if errors:
        raise patchfmt.PatchError(errors)
    return hashes


def slice_files(outbox: Path) -> list[Path]:
    work = outbox / WORK_DIR
    if not work.is_dir():
        return []
    return sorted(path for path in work.iterdir() if SLICE_RE.match(path.name))


def _read_slice(path: Path) -> list[patchfmt.WorkRecord]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(patchfmt.WorkRecord.model_validate_json(line))
    return records


def draft_hashes(outbox: Path) -> set[str]:
    hashes: set[str] = set()
    for path in slice_files(outbox):
        for record in _read_slice(path):
            hashes.add(record.sha256)
    return hashes


def _next_slice_number(work: Path) -> int:
    numbers = [int(SLICE_RE.match(path.name).group(1)) for path in work.iterdir()
               if SLICE_RE.match(path.name)]
    return max(numbers, default=0) + 1


def scan(inbox: Path, outbox: Path, known: Path | None = None,
         slice_size: int = 20) -> ScanResult:
    """Create draft records for new inbox images; the inbox itself is never modified."""
    inbox, outbox = Path(inbox), Path(outbox)
    known_hashes = load_known(known if known is not None else outbox / KNOWN_NAME)
    ledger_hashes = load_ledger(outbox)
    existing = draft_hashes(outbox)
    result = ScanResult()
    fresh: list[dict] = []
    seen: set[str] = set()
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.suffix.lower() not in patchfmt.IMAGE_SUFFIXES:
            continue
        result.total += 1
        stat = path.stat()
        sha256 = patchfmt.sha256_file(path)
        if sha256 in known_hashes:
            result.known += 1
            continue
        if sha256 in ledger_hashes or sha256 in existing:
            result.processed += 1
            continue
        duplicate = sha256 in seen
        seen.add(sha256)
        if duplicate:
            result.duplicates += 1
        else:
            result.new += 1
        fresh.append({
            "source": path.resolve().as_posix(),
            "sha256": sha256,
            "size": stat.st_size,
            "created_ts": file_created_ts(path, fallback=stat.st_mtime),
            "safe_name": patchfmt.safe_name(path.name),
            "duplicate_of": sha256 if duplicate else None,
            "action": None,
            "folder": None,
            "app": None,
            "screen_type": None,
            "language": None,
            "pairs": [],
            "note": "",
        })
    if fresh:
        work = outbox / WORK_DIR
        work.mkdir(parents=True, exist_ok=True)
        start = _next_slice_number(work)
        for offset in range(0, len(fresh), slice_size):
            chunk = fresh[offset:offset + slice_size]
            path = work / f"slice-{start + offset // slice_size:03d}.jsonl"
            body = "\n".join(json.dumps(item, ensure_ascii=False) for item in chunk) + "\n"
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(body, encoding="utf-8")
            os.replace(tmp, path)
    return result


def check(outbox: Path) -> CheckResult:
    """Validate every draft: schema, action filled in, sources unchanged."""
    outbox = Path(outbox)
    result = CheckResult()
    for slice_path in slice_files(outbox):
        for number, line in enumerate(slice_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = patchfmt.WorkRecord.model_validate_json(line)
            except ValidationError as exc:
                result.errors.extend(
                    f"{slice_path.name}:{number}: {item['msg']}" for item in exc.errors()
                )
                continue
            if record.duplicate_of is not None:
                result.done += 1  # a copy of an image already in the set: nothing to fill in
                continue
            if record.action is None:
                result.pending += 1
                continue
            result.done += 1
            source = Path(record.source)
            if not source.exists():
                result.errors.append(f"{slice_path.name}:{number}: {record.source}: source missing")
            elif patchfmt.sha256_file(source) != record.sha256:
                result.errors.append(
                    f"{slice_path.name}:{number}: {record.source}: source changed (sha256 differs)"
                )
    return result


def _split_parts(records: list[patchfmt.WorkRecord], limit: int) -> list[list[patchfmt.WorkRecord]]:
    """Greedy split by the sum of image sizes, keeping the record order."""
    parts: list[list[patchfmt.WorkRecord]] = []
    current: list[patchfmt.WorkRecord] = []
    size = 0
    for record in records:
        record_size = Path(record.source).stat().st_size
        if current and size + record_size > limit:
            parts.append(current)
            current, size = [], 0
        current.append(record)
        size += record_size
    if current:
        parts.append(current)
    return parts


def _write_archive(path: Path, manifest: dict, records_body: bytes,
                   images: list[tuple[str, Path]]) -> None:
    with zipfile.ZipFile(path, "w", allowZip64=True) as zf:
        zf.writestr(patchfmt.MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
                    compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr(patchfmt.RECORDS_NAME, records_body, compress_type=zipfile.ZIP_DEFLATED)
        for arcname, source in images:
            info = zipfile.ZipInfo(arcname, date_time=time.localtime()[:6])
            info.compress_type = zipfile.ZIP_STORED
            with zf.open(info, "w", force_zip64=True) as target, source.open("rb") as image:
                while chunk := image.read(COPY_CHUNK):
                    target.write(chunk)


def _write_part(path: Path, patch_id: str, records: list[patchfmt.WorkRecord], *,
                group: str, index: int, count: int, agent: str | None) -> None:
    converted = [record.to_record() for record in records]
    files = {
        patchfmt.FILE_PREFIX + record.file: {
            "sha256": record.sha256,
            "size": Path(draft.source).stat().st_size,
        }
        for record, draft in zip(converted, records)
    }
    manifest = patchfmt.build_manifest(
        patch_id=patch_id,
        records=converted,
        files=files,
        generator={"tool": "duosave", "version": __version__, "commit": build_info()["commit"],
                   "agent": agent},
        part={"group": group, "index": index, "count": count},
    )
    _write_archive(path, manifest, patchfmt.records_to_jsonl(converted),
                   [(patchfmt.FILE_PREFIX + record.file, Path(draft.source))
                    for record, draft in zip(converted, records)])


def _append_ledger(outbox: Path, entries: list[patchfmt.LedgerEntry]) -> None:
    if not entries:
        return
    body = "".join(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n" for entry in entries)
    with (outbox / LEDGER_NAME).open("a", encoding="utf-8") as ledger:
        ledger.write(body)


def _archive_drafts(outbox: Path, slices: list[Path], group: str) -> None:
    done = outbox / WORK_DIR / DONE_DIR / group
    done.mkdir(parents=True, exist_ok=True)
    for path in slices:
        os.replace(path, done / path.name)


def pack(outbox: Path, max_mb: int = config.PATCH_PART_MB, agent: str | None = None,
         *, max_bytes: int | None = None) -> list[Path]:
    """Pack every filled draft into one or more validated archives; drafts move to done/."""
    outbox = Path(outbox)
    result = check(outbox)
    if result.exit_code != 0:
        if result.errors:
            raise patchfmt.PatchError(result.errors)
        raise patchfmt.PatchError([f"{result.pending} draft(s) are not filled in (action: null)"])
    slices = slice_files(outbox)
    drafts = [record for path in slices for record in _read_slice(path)]
    filled = [record for record in drafts
              if record.action in ("set", "review") and record.duplicate_of is None]
    rejects = [record for record in drafts if record.action == "reject"]
    duplicates = [record for record in drafts if record.duplicate_of is not None]
    if not filled:
        raise patchfmt.PatchError(["nothing to pack: no set/review records"])

    server_limit = config.PATCH_MAX_MB * 1024 * 1024
    for record in filled:
        if Path(record.source).stat().st_size > server_limit:
            raise patchfmt.PatchError([
                f"{record.source}: larger than the server limit ({config.PATCH_MAX_MB} MB)"
            ])

    limit = max_bytes if max_bytes is not None else max_mb * 1024 * 1024
    parts = _split_parts(filled, limit)
    group = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
    written: list[Path] = []
    temporary: list[Path] = []
    try:
        for index, part in enumerate(parts, 1):
            patch_id = f"{group}-p{index}"
            path = outbox / f"duosave-patch-{patch_id}.zip"
            tmp = outbox / f".{patch_id}.zip.tmp"
            temporary.append(tmp)
            _write_part(tmp, patch_id, part, group=group, index=index, count=len(parts),
                        agent=agent)
            patchfmt.validate_archive(tmp)
            os.replace(tmp, path)
            written.append(path)
    except BaseException:
        for path in written + temporary:
            path.unlink(missing_ok=True)
        raise

    at = patchfmt.utc_now_iso()
    entries = [
        patchfmt.LedgerEntry(sha256=record.sha256, source=record.source, outcome="packed",
                             patch_id=f"{group}-p{index}", note="", at=at)
        for index, part in enumerate(parts, 1)
        for record in part
    ]
    entries += [
        patchfmt.LedgerEntry(sha256=record.sha256, source=record.source, outcome="rejected",
                             patch_id=None, note=record.note, at=at)
        for record in rejects
    ]
    entries += [
        patchfmt.LedgerEntry(sha256=record.sha256, source=record.source, outcome="duplicate",
                             patch_id=None, note=f"duplicate of {record.duplicate_of}", at=at)
        for record in duplicates
    ]
    _append_ledger(outbox, entries)
    _archive_drafts(outbox, slices, group)
    return written
