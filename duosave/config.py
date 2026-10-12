"""Paths and constants for the duosave package."""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DATA_DIR = REPO / "data"
DB_PATH = DATA_DIR / "duosave.db"
CACHE_DIR = DATA_DIR / "cache"
MEDIA_DIR = DATA_DIR / "media"
DROPS_MEDIA_DIR = MEDIA_DIR / "drops"
EXPORT_DIR = REPO / "exports"

# Maintenance (2.2): agent inbox/outbox, staged patches, DB snapshots, updater control files.
INBOX_DIR = REPO / "inbox"
OUTBOX_DIR = REPO / "outbox"
PATCHES_DIR = DATA_DIR / "patches"
BACKUPS_DIR = DATA_DIR / "backups"
CONTROL_DIR = DATA_DIR / "control"

PATCH_MAX_MB = int(os.environ.get("DUOSAVE_PATCH_MAX_MB") or 100)
PATCH_PART_MB = 50
SNAPSHOT_KEEP = 10
STAGED_TTL_DAYS = 7

# Admin listener: a second socket of the same uvicorn process, published only on the local
# network (VPN/LAN). 0 disables it; the admin router requires requests to arrive on it.
ADMIN_HOST = os.environ.get("DUOSAVE_ADMIN_HOST") or "127.0.0.1"
ADMIN_PORT = int(os.environ.get("DUOSAVE_ADMIN_PORT") or 8766)

# Frequency word lists (FrequencyWords). Kept next to the golden-set tooling.
WORDLIST_DIR = DATA_DIR / "wordlists"

# Image folders mapped to their source kind.
SOURCE_FOLDERS: dict[str, str] = {
    "pictures": "card",       # exported Duolingo share cards
    "screens": "auto",        # phone screenshots: Drops / Duolingo app / junk
    "screens_raw": "auto",    # legacy dump, kept for old setups; new images arrive via patches
}

LANGUAGES = ("pl", "es", "pt")
LANGUAGE_NAMES = {"pl": "Polish", "es": "Spanish", "pt": "Portuguese", "unk": "Unknown"}

# Bump when recognition logic changes so cached results are re-computed.
RECOGNIZER_VERSION = 1

# Embedding constants for semantic search (see duosave/semantic.py).
EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM: int = 384
EMBEDDING_VERSION: int = 1
MODEL_CACHE_DIR: Path = DATA_DIR / "models"
SEMANTIC_CANDIDATES: int = 200
RRF_K: int = 60

APP_CARD = "duolingo_card"
APP_DUO = "duolingo_app"
APP_DROPS = "drops"
AUTO_APPS = {APP_CARD, APP_DROPS}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
