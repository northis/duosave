"""Updater protocol files in `<data>/control/`: atomic JSON, heartbeat, log, lock.

Shared by the site (`/api/admin/update`) and by the host-side runner
(`python -m duosave.updater`). stdlib only: the runner runs on the host Python.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

REQUEST_NAME = "update-request.json"
PROCESSING_NAME = "update-request.processing"
STATUS_NAME = "update-status.json"
LOG_NAME = "update.log"
LOCK_NAME = "runner.lock"

HEARTBEAT_MAX_AGE = 60
LOG_MAX_BYTES = 1024 * 1024
ACTIONS = ("update", "check")
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str) -> float | None:
    """UNIX timestamp of an ISO-8601 string, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def control_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "control"


def request_path(data_dir: Path) -> Path:
    return control_dir(data_dir) / REQUEST_NAME


def processing_path(data_dir: Path) -> Path:
    return control_dir(data_dir) / PROCESSING_NAME


def status_path(data_dir: Path) -> Path:
    return control_dir(data_dir) / STATUS_NAME


def log_path(data_dir: Path) -> Path:
    return control_dir(data_dir) / LOG_NAME


def lock_path(data_dir: Path) -> Path:
    return control_dir(data_dir) / LOCK_NAME


def write_json_atomic(path: Path, payload: dict) -> None:
    """Temporary file in the same folder + os.replace: readers never see half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict | None:
    """Missing or broken file reads as None."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def runner_alive(status: dict | None, now: float | None = None,
                 max_age: int = HEARTBEAT_MAX_AGE) -> bool:
    """The site trusts the runner only while its heartbeat is fresh."""
    if not isinstance(status, dict):
        return False
    heartbeat = parse_iso((status.get("runner") or {}).get("heartbeat_at"))
    if heartbeat is None:
        return False
    return (now if now is not None else time.time()) - heartbeat <= max_age


def parse_request(payload: object) -> tuple[str, str] | None:
    """(id, action) for a valid request, None otherwise; everything else is ignored."""
    if not isinstance(payload, dict):
        return None
    request_id = payload.get("id")
    action = payload.get("action")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.match(request_id):
        return None
    if action not in ACTIONS:
        return None
    return request_id, action


def new_request(action: str, actor: str | None = None) -> dict:
    return {"id": uuid4().hex, "action": action, "requested_at": utc_now(),
            "requested_by": actor}


def append_log(path: Path, line: str) -> None:
    """Append one line; rotate to `update.log.1` once the file exceeds 1 MiB."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists() and path.stat().st_size > LOG_MAX_BYTES:
            os.replace(path, path.with_name(path.name + ".1"))
    except OSError:
        pass
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("a", encoding="utf-8") as log:
        log.write(f"{stamp} {line}\n")


def tail(path: Path, lines: int = 200) -> list[str]:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-lines:]


def acquire_lock(path: Path):
    """Single-instance OS lock; returns an open handle to keep, or None when taken."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0)
        handle.write(b"1")
        handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def release_lock(handle) -> None:
    if handle is None:
        return
    try:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        handle.close()
