"""Determine the capture time of an image from its name or filesystem metadata."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

UNIX_RE = re.compile(r"^(\d{10})(?:\D.*)?$")                 # 1680466748.png
SHOT_RE = re.compile(r"^Screenshot[_-](\d{8})[-_](\d{6})")   # Screenshot_20250922-114333.png
DATETIME_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})[ _-](\d{2})[.-](\d{2})[.-](\d{2})")


def created_ts(path: Path, fallback: float | None = None) -> int | None:
    """Best-effort capture time: UNIX stem, Screenshot_YYYYMMDD-HHMMSS, else fallback."""
    stem = path.stem

    match = UNIX_RE.match(stem)
    if match:
        value = int(match.group(1))
        if 946684800 <= value <= 4102444800:  # 2000-01-01 .. 2100-01-01
            return value

    match = SHOT_RE.match(stem)
    if match:
        try:
            return int(datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").timestamp())
        except ValueError:
            pass

    match = DATETIME_RE.search(stem)
    if match:
        try:
            return int(datetime(*[int(part) for part in match.groups()]).timestamp())
        except ValueError:
            pass

    if fallback is not None:
        return int(fallback)
    return None
