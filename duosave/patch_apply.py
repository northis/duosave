"""Server-side patch handling: staging, preview, atomic apply, history, reindex."""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path
from uuid import uuid4

from PIL import Image

from . import backup, cards, config, crops, patchfmt, store
from .perf import timed
from .db import (
    add_source,
    all_file_hashes,
    card_by_key,
    connect,
    file_by_sha,
    get_patch,
    insert_patch,
    list_patches,
    set_file,
    upsert_card,
)
from .filenames import created_ts as file_created_ts
from .text import fold_text


class PatchTooLarge(Exception):
    """Uploaded body exceeded DUOSAVE_PATCH_MAX_MB."""

    def __init__(self, limit_mb: int) -> None:
        self.limit_mb = limit_mb
        super().__init__(f"patch is larger than {limit_mb} MB")


class PatchNotFound(Exception):
    pass


class AlreadyApplied(Exception):
    pass


class PatchApplyError(Exception):
    pass


def staged_dir() -> Path:
    return config.PATCHES_DIR / "staged"


def applied_dir() -> Path:
    return config.PATCHES_DIR / "applied"


def max_upload_bytes() -> int:
    return config.PATCH_MAX_MB * 1024 * 1024


# --------------------------------------------------------------------- staging


def stage(chunks: Iterable[bytes], *, actor: str | None = None) -> dict:
    """Stream the upload to a temp file, validate it and store it as a staged patch."""
    incoming = config.PATCHES_DIR / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    limit = max_upload_bytes()
    tmp = incoming / f"{uuid4().hex}.zip"
    size = 0
    try:
        with tmp.open("wb") as target:
            for chunk in chunks:
                size += len(chunk)
                if size > limit:
                    raise PatchTooLarge(config.PATCH_MAX_MB)
                target.write(chunk)
        return stage_file(tmp, actor=actor)
    finally:
        tmp.unlink(missing_ok=True)


def stage_file(path: Path, *, actor: str | None = None) -> dict:
    """Validate an already-written upload, move it into staged/ and store the preview."""
    with timed("stage.validate", size=path.stat().st_size):
        validated = patchfmt.validate_archive(path, max_bytes=max_upload_bytes())
    patch_id = validated.manifest.patch_id
    staged = staged_dir()
    staged.mkdir(parents=True, exist_ok=True)
    os.replace(path, staged / f"{patch_id}.zip")
    conn = connect()
    try:
        with timed("stage.preview", patch=patch_id, records=len(validated.records)):
            payload = preview(conn, validated, uploaded_by=actor)
    finally:
        conn.close()
    (staged / f"{validated.manifest.patch_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def _target_for(conn, record: patchfmt.Record) -> tuple[str, bool]:
    folder, _, name = record.file.partition("/")
    return store.target_path(conn, folder, name, record.sha256)


def _classify(conn, records: list[patchfmt.Record]) -> tuple[list[dict], dict]:
    """Read-only plan: outcomes, targets and card statuses for every record."""
    items: list[dict] = []
    summary = {"records": len(records), "new_files": 0, "duplicates": 0, "renamed": 0,
               "set": 0, "review": 0, "new_cards": 0, "existing_cards": 0}
    for record in records:
        existing = file_by_sha(conn, record.sha256)
        if existing is not None:
            summary["duplicates"] += 1
            items.append({"file": record.file, "outcome": "duplicate",
                          "existing_path": existing["path"]})
            continue
        target, renamed = _target_for(conn, record)
        summary["new_files"] += 1
        summary["renamed"] += int(renamed)
        summary[record.action] += 1
        pairs = []
        for pair in record.pairs:
            card = card_by_key(conn, record.language, pair.original, pair.translation)
            outcome = "existing" if card is not None else "new"
            summary["existing_cards" if card is not None else "new_cards"] += 1
            pairs.append({"original": pair.original, "translation": pair.translation,
                          "kind": pair.kind, "card": outcome})
        items.append({
            "file": record.file, "target": target,
            "outcome": "renamed" if renamed else "new", "action": record.action,
            "app": record.app, "screen_type": record.screen_type, "language": record.language,
            "pairs": pairs, "note": record.note,
        })
    return items, summary


def preview(conn, validated: patchfmt.ValidatedPatch,
            *, uploaded_by: str | None = None) -> dict:
    """Preview payload of a staged patch (contracts/admin-api.md)."""
    items, summary = _classify(conn, validated.records)
    return {
        "patch_id": validated.manifest.patch_id,
        "state": "staged",
        "already_applied": get_patch(conn, validated.manifest.patch_id) is not None,
        "uploaded_at": patchfmt.utc_now_iso(),
        "uploaded_by": uploaded_by,
        "archive_sha256": validated.archive_sha256,
        "generator": validated.manifest.generator.model_dump(),
        "part": validated.manifest.part.model_dump(),
        "summary": summary,
        "items": items,
    }


# ------------------------------------------------------------------- applying


def _write_image(archive: Path, record: patchfmt.Record, target: Path) -> None:
    """Write one image through a `.partial` file so readers never see half a file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    with zipfile.ZipFile(archive) as zf, zf.open(patchfmt.FILE_PREFIX + record.file) as source, \
            partial.open("wb") as destination:
        shutil.copyfileobj(source, destination)
    os.replace(partial, target)


def _created_ts(record: patchfmt.Record) -> int:
    return int(record.created_ts or file_created_ts(Path(record.file), fallback=time.time()))


def _apply_record(conn, record: patchfmt.Record, item: dict, patch_id: str,
                  report: dict, doomed: list) -> None:
    target_path = item["target"]
    target = config.REPO / target_path
    stat = target.stat()
    created_ts = _created_ts(record)
    crop_path = None
    if record.app == "drops":
        with Image.open(target) as image:
            crop_path = crops.save_crop(image, record.sha256)
    if record.action == "set":
        reason = f"patch {patch_id}"
    elif record.pairs:
        reason = record.note or f"patch {patch_id}: agent unsure"
    else:
        reason = f"no_pair: {record.note}"
    for pair in record.pairs:
        existing = None
        if record.action == "review":
            existing = card_by_key(conn, record.language, pair.original, pair.translation)
        if existing is not None:
            card_id = int(existing["id"])
            report["cards_existing"] += 1
        else:
            card_id = upsert_card(
                conn,
                language=record.language,
                original=pair.original,
                translation=pair.translation,
                kind=pair.kind,
                app=record.app,
                screen_type=record.screen_type,
                status="manual" if record.action == "set" else "review",
                notes=record.note or f"patch {patch_id}",
                original_folded=fold_text(pair.original),
                translation_folded=fold_text(pair.translation),
            )
            report["cards_new"] += 1
        add_source(conn, card_id=card_id, path=target_path, sha256=record.sha256,
                      app=record.app, screen_type=record.screen_type, crop_path=crop_path,
                      agreement=None, recognizer="agent")
        # the same phrase imported again: this frame replaces the card's older ones
        doomed.extend(cards.supersede_sources(conn, card_id, target_path))
    set_file(conn, path=target_path, sha256=record.sha256, size=stat.st_size,
                mtime=stat.st_mtime_ns, status="reviewed" if record.action == "set" else "review",
                reason=reason, created_ts=created_ts)


def apply(patch_id: str, *, actor: str | None = None) -> dict:
    """Apply a staged patch: recompute the plan, snapshot the DB, one transaction."""
    conn = connect()
    written: list[Path] = []
    doomed: list = []
    try:
        if get_patch(conn, patch_id) is not None:
            raise AlreadyApplied(patch_id)
        staged_zip = staged_dir() / f"{patch_id}.zip"
        if not staged_zip.exists():
            raise PatchNotFound(patch_id)
        with timed("apply.validate", patch=patch_id):
            validated = patchfmt.validate_archive(staged_zip)
        with timed("apply.classify", patch=patch_id, records=len(validated.records)):
            items, summary = _classify(conn, validated.records)
        with timed("apply.snapshot", patch=patch_id):
            snapshot = backup.snapshot(f"pre-patch-{patch_id}", prefix="pre-patch-")
        records = {record.file: record for record in validated.records}
        report = {"files_written": summary["new_files"], "duplicates": summary["duplicates"],
                  "renamed": [], "cards_new": 0, "cards_existing": 0,
                  "set": summary["set"], "review": summary["review"],
                  "touched": 0, "superseded": []}
        try:
            with timed("apply.write_images", patch=patch_id, files=summary["new_files"]):
                for item in items:
                    if item["outcome"] == "duplicate":
                        continue
                    record = records[item["file"]]
                    _write_image(staged_zip, record, config.REPO / item["target"])
                    written.append(config.REPO / item["target"])
                    if item["outcome"] == "renamed":
                        report["renamed"].append({"from": record.file, "to": item["target"]})
            with timed("apply.db_lock", patch=patch_id):
                conn.execute("BEGIN IMMEDIATE")
            try:
                with timed("apply.db_write", patch=patch_id):
                    for item in items:
                        record = records[item["file"]]
                        if item["outcome"] == "duplicate":
                            # the same image again: only its date moves forward
                            cards.touch_file(conn, item["existing_path"], _created_ts(record))
                            report["touched"] += 1
                            continue
                        _apply_record(conn, record, item, patch_id, report, doomed)
                    report["superseded"] = [source["path"] for source in doomed]
                    insert_patch(conn, patch_id=patch_id,
                                    archive_sha256=validated.archive_sha256,
                                    format_version=validated.manifest.format_version,
                                    generator=validated.manifest.generator.model_dump(),
                                    report=report, applied_by=actor)
                    conn.commit()
            except BaseException:
                conn.rollback()
                raise
        except Exception as exc:
            for path in written:
                path.unlink(missing_ok=True)
            if isinstance(exc, (AlreadyApplied, PatchNotFound)):
                raise
            raise PatchApplyError(str(exc)) from exc
        cards.remove_superseded(doomed)
        applied = applied_dir()
        applied.mkdir(parents=True, exist_ok=True)
        os.replace(staged_zip, applied / staged_zip.name)
        (staged_dir() / f"{patch_id}.json").unlink(missing_ok=True)
    finally:
        conn.close()
    start_reindex()
    return {
        "patch_id": patch_id,
        "state": "applied",
        "applied_at": patchfmt.utc_now_iso(),
        "applied_by": actor,
        "snapshot": snapshot.relative_to(config.REPO).as_posix(),
        "report": report,
        "reindex": {"state": "running"},
    }


def discard(patch_id: str) -> None:
    """Drop a staged patch; applied patches are kept forever."""
    conn = connect()
    try:
        if get_patch(conn, patch_id) is not None:
            raise AlreadyApplied(patch_id)
    finally:
        conn.close()
    staged_zip = staged_dir() / f"{patch_id}.zip"
    if not staged_zip.exists():
        raise PatchNotFound(patch_id)
    staged_zip.unlink()
    (staged_dir() / f"{patch_id}.json").unlink(missing_ok=True)


# ------------------------------------------------------------------- listing


def _expire_staged(now: float | None = None) -> None:
    """Staged patches older than STAGED_TTL_DAYS disappear when the list is requested."""
    staged = staged_dir()
    if not staged.is_dir():
        return
    cutoff = (now if now is not None else time.time()) - config.STAGED_TTL_DAYS * 86400
    for path in staged.glob("*.json"):
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink(missing_ok=True)
            (staged / f"{path.stem}.zip").unlink(missing_ok=True)
        except OSError:
            continue


def listing(conn) -> dict:
    _expire_staged()
    staged = []
    for path in sorted(staged_dir().glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        staged.append({"patch_id": payload.get("patch_id", path.stem),
                       "uploaded_at": payload.get("uploaded_at"),
                       "summary": payload.get("summary", {})})
    applied = [{"patch_id": row["patch_id"], "applied_at": row["applied_at"],
                "applied_by": row["applied_by"], "report": row["report"]}
               for row in list_patches(conn, limit=50)]
    return {"staged": staged, "applied": applied, "reindex": reindex_state()}


def get(conn, patch_id: str) -> dict:
    staged_json = staged_dir() / f"{patch_id}.json"
    if staged_json.exists():
        payload = json.loads(staged_json.read_text(encoding="utf-8"))
        payload["already_applied"] = get_patch(conn, patch_id) is not None
        return payload
    row = get_patch(conn, patch_id)
    if row is not None:
        return {"patch_id": row["patch_id"], "state": "applied", "applied_at": row["applied_at"],
                "applied_by": row["applied_by"], "report": row["report"]}
    raise PatchNotFound(patch_id)


def image(patch_id: str, folder: str, name: str) -> bytes:
    """Image bytes from a staged archive (preview thumbnails)."""
    if folder not in patchfmt.FOLDERS or not patchfmt.NAME_RE.match(name):
        raise PatchNotFound(patch_id)
    staged_zip = staged_dir() / f"{patch_id}.zip"
    if not staged_zip.exists():
        raise PatchNotFound(patch_id)
    try:
        with zipfile.ZipFile(staged_zip) as zf:
            return zf.read(f"{patchfmt.FILE_PREFIX}{folder}/{name}")
    except (KeyError, zipfile.BadZipFile, OSError):
        raise PatchNotFound(patch_id) from None


def known_hashes(conn) -> list[str]:
    return all_file_hashes(conn)


# ------------------------------------------------------------------- reindex


_reindex_lock = threading.Lock()
_reindex_state: dict = {"state": "idle", "detail": None, "finished_at": None, "result": None}


def reindex_state() -> dict:
    with _reindex_lock:
        return dict(_reindex_state)


def _set_reindex(state: str, *, detail: str | None = None, result: dict | None = None) -> None:
    with _reindex_lock:
        _reindex_state.update({"state": state, "detail": detail,
                               "finished_at": None if state == "running" else patchfmt.utc_now_iso(),
                               "result": result})


def start_reindex() -> None:
    """Single-flight background reindex with its own connection."""
    with _reindex_lock:
        if _reindex_state["state"] == "running":
            return
        _reindex_state.update({"state": "running", "detail": None, "finished_at": None,
                               "result": None})
    threading.Thread(target=_run_reindex, name="duosave-reindex", daemon=True).start()


def _run_reindex() -> None:
    from .semantic import SemanticUnavailable, reindex

    conn = connect()
    try:
        with timed("reindex"):
            result = reindex(conn)
            conn.commit()
    except SemanticUnavailable as exc:
        _set_reindex("unavailable", detail=exc.reason)
    except Exception as exc:  # noqa: BLE001 - background job must not kill the server
        _set_reindex("failed", detail=str(exc))
    else:
        _set_reindex("done", result=result)
    finally:
        conn.close()


def wait_reindex(timeout: float = 10.0) -> dict:
    """Test helper: block until the background reindex leaves the running state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = reindex_state()
        if state["state"] != "running":
            return state
        time.sleep(0.05)
    return reindex_state()
