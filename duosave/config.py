"""Paths and constants for the duosave package."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DATA_DIR = REPO / "data"
DB_PATH = DATA_DIR / "duosave.db"
CACHE_DIR = DATA_DIR / "cache"
MEDIA_DIR = DATA_DIR / "media"
DROPS_MEDIA_DIR = MEDIA_DIR / "drops"
EXPORT_DIR = REPO / "exports"

# Frequency word lists (FrequencyWords). Kept next to the golden-set tooling.
WORDLIST_DIR = DATA_DIR / "wordlists"

# Image folders mapped to their source kind.
SOURCE_FOLDERS: dict[str, str] = {
    "pictures": "card",       # exported Duolingo share cards
    "screens": "auto",        # phone screenshots: Drops / Duolingo app / junk
    "screens_raw": "auto",    # inbox with fresh screenshots
}

LANGUAGES = ("pl", "es", "pt")
LANGUAGE_NAMES = {"pl": "Polish", "es": "Spanish", "pt": "Portuguese", "unk": "Unknown"}

# Bump when recognition logic changes so cached results are re-computed.
RECOGNIZER_VERSION = 1

APP_CARD = "duolingo_card"
APP_DUO = "duolingo_app"
APP_DROPS = "drops"
AUTO_APPS = {APP_CARD, APP_DROPS}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
