"""Local site: search, card details, review queue, stats."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..buildinfo import build_info
from ..config import MEDIA_DIR, REPO, SOURCE_FOLDERS
from ..db import (
    add_source,
    connect,
    get_card,
    init_db,
    review_files,
    set_file,
    stats,
    update_card,
    upsert_card,
)
from ..semantic import hybrid_search
from ..text import fold_text

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    conn = connect()
    try:
        init_db(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="Duosave", lifespan=lifespan)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
# original screenshots, so the UI can link "source: screens/...png"
for _folder in SOURCE_FOLDERS:
    _dir = REPO / _folder
    if _dir.exists():
        app.mount(f"/src/{_folder}", StaticFiles(directory=_dir), name=f"src-{_folder}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/review")
def review_page() -> FileResponse:
    return FileResponse(STATIC / "review.html")


@app.get("/api/search")
def api_search(q: str = "", lang: str = "", app: str = "", page: int = 0, limit: int = 60,
               sort: str = "new", mode: Literal["hybrid", "semantic", "text"] = "hybrid"):
    conn = connect()
    try:
        items, total, meta = hybrid_search(conn, query=q, lang=lang, app=app, limit=limit,
                                           offset=page * limit, sort=sort, mode=mode)
    finally:
        conn.close()
    return {"total": total, "items": items, "semantic": meta}


@app.get("/api/cards/{card_id}")
def api_card(card_id: int):
    conn = connect()
    try:
        card = get_card(conn, card_id)
    finally:
        conn.close()
    if card is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return card


@app.get("/api/review")
def api_review(page: int = 0, limit: int = 40):
    conn = connect()
    try:
        items, total = review_files(conn, limit=limit, offset=page * limit)
    finally:
        conn.close()
    return {"total": total, "items": items}


class ReviewAction(BaseModel):
    path: str
    action: str  # accept | reject | edit
    original: str | None = None
    translation: str | None = None
    language: str | None = None


@app.post("/api/review")
def api_review_action(payload: ReviewAction):
    conn = connect()
    try:
        row = conn.execute(
            "SELECT f.sha256, s.card_id FROM files f LEFT JOIN sources s ON s.path = f.path "
            "WHERE f.path = ?",
            (payload.path,),
        ).fetchone()
        if row is None:
            return JSONResponse({"error": "file not found"}, status_code=404)
        if payload.action == "reject":
            set_file(conn, path=payload.path, sha256=row["sha256"] or "", size=0, mtime=0,
                     status="rejected", reason="rejected in review")
        elif payload.action == "accept":
            if row["card_id"] is not None:
                update_card(conn, row["card_id"], status="manual", notes="accepted in review")
            set_file(conn, path=payload.path, sha256=row["sha256"] or "", size=0, mtime=0,
                     status="reviewed", reason="accepted")
        elif payload.action == "edit":
            if not payload.original or not payload.translation:
                return JSONResponse({"error": "original and translation required"}, status_code=400)
            language = payload.language or "unk"
            card_id = upsert_card(
                conn,
                language=language,
                original=payload.original,
                translation=payload.translation,
                kind="sentence",
                app=None,
                screen_type=None,
                status="manual",
                notes="edited in review",
                original_folded=fold_text(payload.original),
                translation_folded=fold_text(payload.translation),
            )
            add_source(conn, card_id=card_id, path=payload.path, sha256=row["sha256"] or "",
                       app=None, screen_type=None, crop_path=None, agreement=None,
                       recognizer="manual")
            set_file(conn, path=payload.path, sha256=row["sha256"] or "", size=0, mtime=0,
                     status="reviewed", reason="edited")
        else:
            return JSONResponse({"error": "unknown action"}, status_code=400)
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.get("/api/stats")
def api_stats():
    conn = connect()
    try:
        data = stats(conn)
    finally:
        conn.close()
    return data


@app.get("/api/version")
def api_version() -> dict:
    return build_info()
