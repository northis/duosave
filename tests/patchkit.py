"""Build valid (or deliberately broken) patch archives for tests.

Mirrors what `duosave patch pack` produces; every hook exists to break one rule of
contracts/patch-format.md at a time.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from duosave import patchfmt

DEFAULT_PATCH_ID = "20261012T103105Z-3f9c2a1b-p1"
GENERATOR = {"tool": "duosave", "version": "2.2.0", "commit": None, "agent": "tests"}


def make_record(**overrides) -> dict:
    """A valid `set` record for a Drops screenshot."""
    record = {
        "file": "screens/Screenshot_20261010-101010.png",
        "sha256": "0" * 64,
        "created_ts": 1760090410,
        "action": "set",
        "app": "drops",
        "screen_type": "drops_card",
        "language": "pt",
        "pairs": [{"original": "o abacaxi", "translation": "pineapple", "kind": "word"}],
        "note": "",
    }
    record.update(overrides)
    return record


def _counts(records: list[dict], files: int) -> dict:
    return {
        "records": len(records),
        "files": files,
        "set": sum(1 for record in records if record.get("action") == "set"),
        "review": sum(1 for record in records if record.get("action") == "review"),
        "pairs": sum(len(record.get("pairs") or []) for record in records),
    }


def _write_member(zf: zipfile.ZipFile, name: str, data: bytes,
                  compress: dict | None, member_overrides: dict | None) -> None:
    info = zipfile.ZipInfo(name)
    info.compress_type = (compress or {}).get(name, zipfile.ZIP_STORED)
    for key, value in (member_overrides or {}).get(name, {}).items():
        setattr(info, key, value)
    zf.writestr(info, data)


def build_patch(path: Path, records: list[dict], images: dict[str, bytes], *,
                manifest_overrides: dict | None = None,
                extra_members: dict[str, bytes] | None = None,
                member_overrides: dict[str, dict] | None = None,
                compress: dict[str, int] | None = None,
                patch_id: str = DEFAULT_PATCH_ID) -> Path:
    """Write a patch archive; `images` keys are record `file` values."""
    record_lines = [json.dumps(record, ensure_ascii=False) for record in records]
    records_body = ("\n".join(record_lines) + "\n" if record_lines else "").encode("utf-8")
    file_entries = {
        patchfmt.FILE_PREFIX + name: {
            "sha256": patchfmt.sha256_bytes(data), "size": len(data),
        }
        for name, data in images.items()
    }
    manifest = {
        "format": patchfmt.FORMAT,
        "format_version": patchfmt.FORMAT_VERSION,
        "patch_id": patch_id,
        "created_at": "2026-10-12T10:31:05Z",
        "generator": dict(GENERATOR),
        "part": {"group": patch_id.rsplit("-p", 1)[0], "index": 1, "count": 1},
        "counts": _counts(records, len(file_entries)),
        "records_sha256": patchfmt.sha256_bytes(records_body),
        "files": file_entries,
    }
    manifest.update(manifest_overrides or {})

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
                    compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("records.jsonl", records_body, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in images.items():
            _write_member(zf, patchfmt.FILE_PREFIX + name, data, compress, member_overrides)
        for name, data in (extra_members or {}).items():
            _write_member(zf, name, data, compress, member_overrides)
    return path
