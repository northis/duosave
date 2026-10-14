"""Public upload endpoint: raw image bytes in, a stored frame or a duplicate out.

One image per request, no multipart and no temp files: the body goes to the
vision call as is, then the final frame is placed into `pictures/`/`screens/`
through the shared `store` invariants and stored in one transaction. A vision
failure falls back to the local OCR in the same request; a known sha256 is
answered before the vision call is made.
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
import warnings
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from .. import config, db, patchfmt, recognize, store, sync, vision
from ..recognize import Recognition
from .security import AdminError, actor, audit, require_csrf

STATIC = Path(__file__).resolve().parent / "static"

_MEDIA_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}
_SUFFIXES = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
# Contract statuses: the review queue is `reviewed`/`pending`, a dropped frame is `rejected`.
_STATUSES = {"auto": "auto", "review": "review", "skipped": "skipped",
             "reviewed": "review", "pending": "review", "rejected": "skipped"}

router = APIRouter()


@router.post("/api/upload")
async def api_upload(request: Request, _: None = Depends(require_csrf)) -> dict:
    """Store one raw image; duplicates are answered before the vision call."""
    declared = request.headers.get("content-length")
    if not declared or not declared.isdigit():
        raise AdminError(411, "length_required", "Content-Length is required")
    if int(declared) > config.VISION_MAX_MB * 1024 * 1024:
        raise AdminError(413, "too_large", f"image is larger than {config.VISION_MAX_MB} MB",
                         limit_mb=config.VISION_MAX_MB)
    body = await request.body()
    _validate_body(request.headers, body)
    image_format, media_type, size = _check_image(body)
    sha256 = hashlib.sha256(body).hexdigest()
    who = actor(request)

    duplicate = await run_in_threadpool(_duplicate, sha256)
    if duplicate is not None:
        audit("upload", who, path=duplicate["path"], outcome="duplicate",
              status=duplicate["status"], recognizer=duplicate["recognizer"],
              reason=duplicate["reason"], vision="", renamed=False)
        return duplicate

    vision_reason = ""
    recognition = None
    if vision.available():
        try:
            recognition = await vision.recognize_bytes(body, media_type)
        except vision.VisionUnavailable as exc:
            vision_reason = exc.reason
    else:
        vision_reason = "no_token"

    if recognition is None:
        folder = _folder_for(None, size)
        rel_path, renamed = await run_in_threadpool(
            _place_image, folder, _name_for(sha256, image_format), body, sha256)
        recognition, _cache = await run_in_threadpool(
            recognize.recognize_image, config.REPO / rel_path, config.SOURCE_FOLDERS[folder])
        recognizer = "ocr"
    else:
        folder = _folder_for(recognition.app, size)
        rel_path, renamed = await run_in_threadpool(
            _place_image, folder, _name_for(sha256, image_format), body, sha256)
        recognizer = "vision"

    try:
        card_id = await run_in_threadpool(
            _store, rel_path, config.REPO / rel_path, sha256, recognition, recognizer)
    except AdminError as exc:
        if exc.code == "busy":
            audit("upload", who, path=rel_path, outcome="busy", status="",
                  recognizer="", reason="", vision="", renamed=renamed)
        raise
    audit("upload", who, path=rel_path, outcome="stored", status=recognition.status,
          recognizer=recognizer, reason=recognition.reason, vision=vision_reason,
          renamed=renamed)
    return {
        "outcome": "stored",
        "path": rel_path,
        "card_id": card_id,
        "app": recognition.app,
        "screen_type": recognition.screen_type,
        "language": recognition.language,
        "pairs": [{"original": pair.original, "translation": pair.translation,
                   "kind": pair.kind} for pair in recognition.pairs],
        "status": recognition.status,
        "reason": recognition.reason,
        "recognizer": recognizer,
        "elapsed": round(recognition.elapsed, 2),
    }


@router.get("/share")
def share_page() -> FileResponse:
    """The share outcome page: everything it shows comes from the URL, not the database."""
    return FileResponse(STATIC / "share.html")


@router.post("/share")
def share_fallback() -> RedirectResponse:
    """Safety net for an install with no active service worker: the body is never read."""
    return RedirectResponse("/share?error=sw", status_code=303)


def _validate_body(headers: Headers, body: bytes) -> None:
    """Content-Type, when given, must be an image; the body must fit the size limit."""
    content_type = headers.get("content-type", "")
    if content_type and not content_type.startswith("image/"):
        raise AdminError(415, "unsupported_media_type", "Content-Type must be image/*")
    if len(body) > config.VISION_MAX_MB * 1024 * 1024:
        raise AdminError(413, "too_large", f"image is larger than {config.VISION_MAX_MB} MB",
                         limit_mb=config.VISION_MAX_MB)


def _check_image(body: bytes) -> tuple[str, str, tuple[int, int]]:
    """Pillow decides the format and the pixel count; anything else is a 422."""
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = patchfmt.MAX_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(body)) as image:
                image_format = image.format
                size = image.size
                image.verify()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise AdminError(422, "not_an_image",
                         f"image is larger than {patchfmt.MAX_PIXELS} pixels") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise AdminError(422, "not_an_image", "body is not a PNG/JPEG/WEBP image") from None
    finally:
        Image.MAX_IMAGE_PIXELS = previous
    if image_format not in patchfmt.IMAGE_FORMATS:
        raise AdminError(422, "not_an_image", f"format {image_format} is not PNG/JPEG/WEBP")
    return image_format, _MEDIA_TYPES[image_format], (size[0], size[1])


def _name_for(sha256: str, image_format: str) -> str:
    """The server-side name: content hash plus the extension of the real format."""
    return f"{sha256[:16]}{_SUFFIXES[image_format]}"


def _folder_for(app: str | None, size: tuple[int, int]) -> str:
    """Folder by the vision `app`; without it, by the frame proportions."""
    if app == config.APP_CARD:
        return "pictures"
    if app in (config.APP_DUO, config.APP_DROPS, "other"):
        return "screens"
    width, height = size
    return "pictures" if abs(width / height - 1) <= 0.1 else "screens"


def _duplicate(sha256: str) -> dict | None:
    """Answer for an already known sha256: the existing file and card, or None."""
    conn = db.connect()
    try:
        row = db.file_by_sha(conn, sha256)
        if row is None:
            return None
        path = row["path"]
        source = conn.execute(
            "SELECT app, screen_type, card_id FROM sources WHERE path = ? LIMIT 1", (path,)
        ).fetchone()
        card = db.get_card(conn, int(source["card_id"])) if source is not None else None
        pairs = []
        if card is not None:
            pairs = [{"original": card["original"], "translation": card["translation"],
                      "kind": card["kind"]}]
        return {
            "outcome": "duplicate",
            "path": path,
            "card_id": int(card["id"]) if card is not None else None,
            "app": source["app"] if source is not None else None,
            "screen_type": source["screen_type"] if source is not None else None,
            "language": card["language"] if card is not None else None,
            "pairs": pairs,
            "status": _STATUSES.get(row["status"], "review"),
            "reason": row["reason"] or "",
            "recognizer": row["recognizer"],
            "elapsed": 0.0,
        }
    finally:
        conn.close()


def _place_image(folder: str, name: str, data: bytes, sha256: str) -> tuple[str, bool]:
    """Write the frame into its source folder (own connection, thread pool)."""
    conn = db.connect()
    try:
        return store.place_image(conn, folder, name, data, sha256)
    finally:
        conn.close()


def _store(rel_path: str, path: Path, sha256: str, recognition: Recognition,
           recognizer: str) -> int | None:
    """One transaction for the whole result; a busy database means 503."""
    conn = db.connect()
    try:
        try:
            conn.execute("BEGIN IMMEDIATE")
            sync.store_recognition(conn, rel_path, path, sha256, recognition.to_cache(),
                                   recognizer=recognizer)
            card_id = None
            if recognition.usable and recognition.pairs:
                card = db.card_by_key(conn, recognition.language or "unk",
                                      recognition.pairs[0].original,
                                      recognition.pairs[0].translation)
                card_id = int(card["id"]) if card is not None else None
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            raise AdminError(503, "busy", "database is busy, retry the upload") from exc
    finally:
        conn.close()
    return card_id
