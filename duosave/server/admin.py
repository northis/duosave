"""Maintenance page and /api/admin/* router (reachable only via the admin listener)."""

from __future__ import annotations

import mimetypes
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .. import backup, cards, config, patch_apply, patchfmt
from ..buildinfo import build_info
from ..db import connect, search_cards
from .security import AdminError, actor, audit, forbid_cross_site, require_csrf, require_local

STATIC = Path(__file__).resolve().parent / "static"

# Single uvicorn process (design): process-wide locks are enough for mutual exclusion.
APPLY_LOCK = threading.Lock()
FULL_BACKUP_LOCK = threading.Lock()

router = APIRouter(dependencies=[Depends(require_local)])


def busy_reason() -> str | None:
    """Why a new update request must be refused right now, if any."""
    if APPLY_LOCK.locked():
        return "patch apply in progress"
    if FULL_BACKUP_LOCK.locked():
        return "full backup in progress"
    return None


@router.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(STATIC / "admin.html")


@router.get("/api/admin/backup/estimate")
def api_backup_estimate() -> dict:
    return {
        "db": backup.estimate("db"),
        "full": backup.estimate("full"),
        "computed_at": backup.now_iso(),
    }


@router.get("/api/admin/backup")
def api_backup(request: Request, kind: Literal["db", "full"] = "db",
               _: None = Depends(forbid_cross_site)) -> StreamingResponse:
    """Stream a consistent archive; only one full backup may run at a time."""
    if kind == "full" and not FULL_BACKUP_LOCK.acquire(blocking=False):
        raise AdminError(409, "busy", "full backup in progress")
    who = actor(request)
    filename = backup.backup_filename(kind, short=build_info().get("short"))

    def stream() -> Iterator[bytes]:
        try:
            yield from backup.iter_backup_zip(kind)
        finally:
            if kind == "full":
                FULL_BACKUP_LOCK.release()
            audit("backup", who, kind=kind)

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    return StreamingResponse(stream(), media_type="application/zip", headers=headers)


# ----------------------------------------------------------------------- patches


@router.post("/api/admin/patches")
async def api_patch_upload(request: Request, _: None = Depends(require_csrf)) -> dict:
    """Stream the upload to disk (bounded memory), validate and stage it."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("application/zip"):
        raise AdminError(415, "unsupported_media_type", "Content-Type must be application/zip")
    limit = patch_apply.max_upload_bytes()
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise AdminError(413, "too_large", f"patch is larger than {config.PATCH_MAX_MB} MB",
                         limit_mb=config.PATCH_MAX_MB)
    incoming = config.PATCHES_DIR / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    tmp = incoming / f"{uuid4().hex}.zip"
    size = 0
    who = actor(request)
    try:
        with tmp.open("wb") as target:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise AdminError(413, "too_large",
                                     f"patch is larger than {config.PATCH_MAX_MB} MB",
                                     limit_mb=config.PATCH_MAX_MB)
                target.write(chunk)
        payload = await run_in_threadpool(patch_apply.stage_file, tmp, actor=who)
    except patchfmt.PatchError as exc:
        raise AdminError(422, "invalid_patch", "patch does not match the format",
                         errors=exc.errors[:patchfmt.MAX_ERRORS]) from exc
    finally:
        tmp.unlink(missing_ok=True)
    audit("patch_upload", who, patch_id=payload["patch_id"])
    return payload


@router.get("/api/admin/patches")
def api_patches() -> dict:
    conn = connect()
    try:
        return patch_apply.listing(conn)
    finally:
        conn.close()


@router.get("/api/admin/patches/{patch_id}")
def api_patch(patch_id: str) -> dict:
    conn = connect()
    try:
        return patch_apply.get(conn, patch_id)
    except patch_apply.PatchNotFound:
        raise AdminError(404, "not_found", "no such patch") from None
    finally:
        conn.close()


@router.get("/api/admin/patches/{patch_id}/files/{folder}/{name}")
def api_patch_image(patch_id: str, folder: str, name: str) -> Response:
    try:
        data = patch_apply.image(patch_id, folder, name)
    except patch_apply.PatchNotFound:
        raise AdminError(404, "not_found", "no such image") from None
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return Response(data, media_type=media_type,
                    headers={"Cache-Control": "private, max-age=3600"})


@router.post("/api/admin/patches/{patch_id}/apply")
def api_patch_apply(patch_id: str, request: Request,
                    _: None = Depends(require_csrf)) -> dict:
    reason = busy_reason()
    if reason or not APPLY_LOCK.acquire(blocking=False):
        raise AdminError(409, "busy", reason or "patch apply in progress")
    who = actor(request)
    try:
        if FULL_BACKUP_LOCK.locked():
            raise AdminError(409, "busy", "full backup in progress")
        try:
            report = patch_apply.apply(patch_id, actor=who)
        except patch_apply.AlreadyApplied:
            raise AdminError(409, "already_applied", "patch is already applied") from None
        except patch_apply.PatchNotFound:
            raise AdminError(404, "not_found", "no such patch") from None
        except patch_apply.PatchApplyError as exc:
            raise AdminError(500, "apply_failed", str(exc)) from exc
    finally:
        APPLY_LOCK.release()
    audit("patch_apply", who, patch_id=patch_id)
    return report


@router.delete("/api/admin/patches/{patch_id}", status_code=204)
def api_patch_discard(patch_id: str, request: Request,
                      _: None = Depends(require_csrf)) -> Response:
    who = actor(request)
    try:
        patch_apply.discard(patch_id)
    except patch_apply.AlreadyApplied:
        raise AdminError(409, "already_applied", "applied patches cannot be discarded") from None
    except patch_apply.PatchNotFound:
        raise AdminError(404, "not_found", "no such patch") from None
    audit("patch_discard", who, patch_id=patch_id)
    return Response(status_code=204)


# ------------------------------------------------------------------------ cards


@router.get("/api/admin/cards")
def api_admin_cards(q: str = "", lang: str = "", limit: int = 20) -> dict:
    """Card search for the delete panel: rejected cards stay visible here."""
    conn = connect()
    try:
        items, total = search_cards(conn, query=q, lang=lang, limit=max(1, min(limit, 100)),
                                    include_rejected=True)
    finally:
        conn.close()
    return {"total": total, "items": items}


@router.delete("/api/admin/cards/{card_id}")
def api_card_delete(card_id: int, request: Request,
                    _: None = Depends(require_csrf)) -> dict:
    """Delete a card with its frames; a fresh share of the same image is processed again."""
    reason = busy_reason()
    if reason:
        raise AdminError(409, "busy", reason)
    who = actor(request)
    conn = connect()
    try:
        try:
            report = cards.delete_card(conn, card_id)
        except cards.CardNotFound:
            raise AdminError(404, "not_found", "no such card") from None
    finally:
        conn.close()
    patch_apply.start_reindex()
    audit("card_delete", who, card_id=card_id, files=len(report["removed"]),
          missing=len(report["missing"]), kept=len(report["kept"]))
    return report


@router.get("/api/admin/known-hashes")
def api_known_hashes(_: None = Depends(forbid_cross_site)) -> PlainTextResponse:
    conn = connect()
    try:
        hashes = patch_apply.known_hashes(conn)
    finally:
        conn.close()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    body = "\n".join([
        f"# duosave known-hashes v1 {patchfmt.utc_now_iso()} {len(hashes)}",
        *hashes,
    ]) + "\n"
    return PlainTextResponse(body, headers={
        "Content-Disposition": f'attachment; filename="duosave-known-hashes-{stamp}.txt"',
        "Cache-Control": "no-store",
    })
