"""Agent-side patch building: scan, check, pack; the inbox is only ever read."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from duosave import __version__, config, patch_build, patchfmt

import patchkit
from helpers import png_bytes


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _inbox(root: Path, names: list[str]) -> Path:
    inbox = root / "inbox"
    for index, name in enumerate(names):
        _write(inbox / name, png_bytes(color=(index + 1, index * 3 + 2, 30)))
    return inbox


def _outbox(root: Path) -> Path:
    return root / "outbox"


def _tree(root: Path) -> dict:
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = (
                path.stat().st_size, path.stat().st_mtime_ns, patchfmt.sha256_file(path),
            )
    return snapshot


def _draft_lines(outbox: Path) -> list[tuple[Path, list[dict]]]:
    result = []
    for path in sorted((outbox / ".work").glob("slice-*.jsonl")):
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        result.append((path, lines))
    return result


def _fill(outbox: Path, index: int = 0, *, action: str = "set", folder: str = "screens",
          app: str = "drops", language: str = "pt", note: str = "",
          pairs: list | None = None) -> None:
    """Fill one draft record in place (agent step)."""
    for path, lines in _draft_lines(outbox):
        if index < len(lines):
            record = lines[index]
            record.update({
                "action": action, "folder": folder, "app": app, "screen_type": "drops_card",
                "language": language, "note": note,
                "pairs": pairs if pairs is not None else [
                    {"original": "o abacaxi", "translation": "pineapple", "kind": "word"},
                ],
            })
            path.write_text(
                "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
                encoding="utf-8",
            )
            return
        index -= len(lines)
    raise AssertionError("no draft with that index")


def _fill_all(outbox: Path, **kwargs) -> None:
    total = sum(len(lines) for _, lines in _draft_lines(outbox))
    for index in range(total):
        _fill(outbox, index, **kwargs)


# ------------------------------------------------------------------------ scan


def test_scan_creates_draft_slices(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, [
        "Screenshot_20261010-101010.png", "1760091234.png", "IMG 1 (copy).PNG",
    ])
    _write(inbox / "Screenshot_20261010-101011.png", (inbox / "Screenshot_20261010-101010.png").read_bytes())
    _write(inbox / "notes.txt", b"not an image")
    _write(inbox / "sub" / "nested.png", png_bytes())

    result = patch_build.scan(inbox, _outbox(tmp_path))

    records = [record for _, lines in _draft_lines(_outbox(tmp_path)) for record in lines]
    assert result.total == 4
    assert result.new == 3
    assert result.duplicates == 1
    assert len(records) == 4
    by_name = {Path(record["source"]).name: record for record in records}
    assert "notes.txt" not in by_name and "nested.png" not in by_name
    assert all(Path(record["source"]).is_absolute() for record in records)
    assert all("\\" not in record["source"] for record in records)
    assert by_name["IMG 1 (copy).PNG"]["safe_name"] == "IMG_1_copy_.png"
    assert by_name["Screenshot_20261010-101010.png"]["created_ts"] == int(
        datetime(2026, 10, 10, 10, 10, 10).timestamp()
    )
    assert by_name["1760091234.png"]["created_ts"] == 1760091234
    assert by_name["IMG 1 (copy).PNG"]["created_ts"] == int(
        (inbox / "IMG 1 (copy).PNG").stat().st_mtime
    )
    copy = by_name["Screenshot_20261010-101011.png"]
    assert copy["duplicate_of"] == by_name["Screenshot_20261010-101010.png"]["sha256"]
    assert all(record["action"] is None for record in records)


def test_scan_slices_by_size(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, [f"img_{index:03d}.png" for index in range(45)])

    patch_build.scan(inbox, _outbox(tmp_path), slice_size=20)

    slices = _draft_lines(_outbox(tmp_path))
    assert [len(lines) for _, lines in slices] == [20, 20, 5]
    assert [path.name for path, _ in slices] == ["slice-001.jsonl", "slice-002.jsonl", "slice-003.jsonl"]


def test_scan_is_idempotent_and_keeps_filled_records(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png", "b.png"])
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)
    _fill(outbox, 0)
    before = _tree(outbox / ".work")

    result = patch_build.scan(inbox, outbox)

    assert result.new == 0
    assert result.processed == 2
    assert _tree(outbox / ".work") == before


def test_scan_skips_known_hashes(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png", "b.png"])
    outbox = _outbox(tmp_path)
    known_sha = patchfmt.sha256_file(inbox / "a.png")
    _write(outbox / "known-hashes.txt",
           f"# duosave known-hashes v1 2026-10-12T10:20:00Z 1\n{known_sha}\n".encode())

    result = patch_build.scan(inbox, outbox)

    records = [record for _, lines in _draft_lines(outbox) for record in lines]
    assert result.known == 1
    assert [Path(record["source"]).name for record in records] == ["b.png"]


def test_scan_explicit_known_overrides_the_default(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png", "b.png"])
    outbox = _outbox(tmp_path)
    _write(outbox / "known-hashes.txt", (patchfmt.sha256_file(inbox / "a.png") + "\n").encode())
    explicit = _write(tmp_path / "known.txt", (patchfmt.sha256_file(inbox / "b.png") + "\n").encode())

    result = patch_build.scan(inbox, outbox, known=explicit)

    records = [record for _, lines in _draft_lines(outbox) for record in lines]
    assert result.known == 1
    assert [Path(record["source"]).name for record in records] == ["a.png"]


def test_scan_rejects_malformed_known_file(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    outbox = _outbox(tmp_path)
    _write(outbox / "known-hashes.txt", b"# header\nxyz\n")

    with pytest.raises(patchfmt.PatchError) as exc:
        patch_build.scan(inbox, outbox)

    assert "known-hashes.txt:2" in exc.value.errors[0]


def test_scan_skips_ledger_entries(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png", "b.png"])
    outbox = _outbox(tmp_path)
    entry = {
        "sha256": patchfmt.sha256_file(inbox / "a.png"), "source": "old/a.png",
        "outcome": "packed", "patch_id": "20261012T103105Z-3f9c2a1b-p1", "note": "",
        "at": "2026-10-12T10:31:05Z",
    }
    _write(outbox / "ledger.jsonl", (json.dumps(entry) + "\n").encode())

    result = patch_build.scan(inbox, outbox)

    assert result.processed == 1
    assert len(_draft_lines(outbox)[0][1]) == 1


def test_scan_rejects_malformed_ledger(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    outbox = _outbox(tmp_path)
    _write(outbox / "ledger.jsonl", b'{"sha256": "nope"}\n')

    with pytest.raises(patchfmt.PatchError) as exc:
        patch_build.scan(inbox, outbox)

    assert "ledger.jsonl:1" in exc.value.errors[0]


def test_inbox_is_never_modified(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png", "b.png"])
    outbox = _outbox(tmp_path)
    before = _tree(inbox)

    patch_build.scan(inbox, outbox)
    patch_build.check(outbox)
    _fill_all(outbox)
    patch_build.pack(outbox)

    assert _tree(inbox) == before


def test_read_only_inbox_is_processed(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    outbox = _outbox(tmp_path)
    read_only = inbox / "a.png"
    os.chmod(read_only, stat.S_IREAD)
    try:
        result = patch_build.scan(inbox, outbox)
        _fill_all(outbox)
        written = patch_build.pack(outbox)

        assert result.new == 1
        assert len(written) == 1
    finally:
        os.chmod(read_only, stat.S_IWRITE | stat.S_IREAD)


# ----------------------------------------------------------------------- check


def test_check_exit_codes(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)

    pending = patch_build.check(outbox)
    assert pending.exit_code == 2
    assert pending.pending == 1

    _fill(outbox, 0, pairs=[])
    broken = patch_build.check(outbox)
    assert broken.exit_code == 1
    assert "slice-001.jsonl:1" in broken.errors[0]

    _fill(outbox, 0)
    ready = patch_build.check(outbox)
    assert ready.exit_code == 0
    assert ready.done == 1


def test_check_accepts_unfilled_duplicates(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    _write(inbox / "copy.png", (inbox / "a.png").read_bytes())
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)

    result = patch_build.check(outbox)

    assert result.exit_code == 2
    assert result.pending == 1  # only the unique image needs an action


def test_check_detects_changed_source(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)
    _fill(outbox, 0)
    _write(inbox / "a.png", png_bytes(color=(9, 9, 9)))

    result = patch_build.check(outbox)

    assert result.exit_code == 1
    assert "changed" in result.errors[0]
    assert "a.png" in result.errors[0]


def test_check_reports_missing_source(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)
    _fill(outbox, 0)
    (inbox / "a.png").unlink()

    result = patch_build.check(outbox)

    assert result.exit_code == 1
    assert "missing" in result.errors[0]


# ------------------------------------------------------------------------ pack


def test_pack_refuses_when_check_fails(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)

    with pytest.raises(patchfmt.PatchError):
        patch_build.pack(outbox)

    assert list(outbox.glob("*.zip")) == []
    assert not (outbox / "ledger.jsonl").exists()
    assert len(_draft_lines(outbox)[0][1]) == 1


def test_pack_writes_valid_parts(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, [f"img_{index}.png" for index in range(6)])
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)
    _fill_all(outbox)
    one_image = (inbox / "img_0.png").stat().st_size

    written = patch_build.pack(outbox, max_bytes=2 * one_image + 1, agent="opencode · test")

    assert len(written) >= 2
    groups = set()
    for path in written:
        validated = patchfmt.validate_archive(path)
        assert validated.manifest.part.count == len(written)
        assert validated.manifest.counts.records <= 2
        assert validated.manifest.generator.agent == "opencode · test"
        assert validated.manifest.generator.tool == "duosave"
        assert validated.manifest.generator.version == __version__
        assert patchfmt.PATCH_ID_RE.match(validated.manifest.patch_id)
        groups.add(validated.manifest.part.group)
    assert len(groups) == 1
    indexes = sorted(patchfmt.validate_archive(path).manifest.part.index for path in written)
    assert indexes == list(range(1, len(written) + 1))
    names = {path.name for path in written}
    assert len(names) == len(written)


def test_pack_appends_ledger_and_archives_drafts(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png", "b.png", "c.png"])
    _write(inbox / "copy_of_a.png", (inbox / "a.png").read_bytes())
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)
    by_name = {}
    for _, lines in _draft_lines(outbox):
        for record in lines:
            by_name[Path(record["source"]).name] = record
    _fill(outbox, 0)                     # a.png -> set
    _fill(outbox, 1, action="review", app="duolingo_app", language="unk", pairs=[])
    _fill(outbox, 2, action="reject", note="bank app", folder=None, app=None, language=None,
          pairs=[])

    written = patch_build.pack(outbox, agent="tests")

    ledger = [json.loads(line) for line in (outbox / "ledger.jsonl").read_text(
        encoding="utf-8").splitlines()]
    outcomes = {entry["outcome"]: entry for entry in ledger}
    assert set(outcomes) == {"packed", "rejected", "duplicate"}
    assert outcomes["rejected"]["note"] == "bank app"
    assert outcomes["packed"]["patch_id"] == patchfmt.validate_archive(written[0]).manifest.patch_id
    assert outcomes["duplicate"]["sha256"] == by_name["a.png"]["sha256"]
    assert len(ledger) == 4
    group = patchfmt.validate_archive(written[0]).manifest.part.group
    assert not list((outbox / ".work").glob("slice-*.jsonl"))
    assert list((outbox / ".work" / "done" / group).glob("slice-*.jsonl"))

    again = patch_build.scan(inbox, outbox)
    assert again.processed == 4
    assert again.new == 0


def test_pack_excludes_rejected_and_duplicate_images(tmp_path: Path) -> None:
    inbox = _inbox(tmp_path, ["a.png", "b.png"])
    _write(inbox / "copy_of_a.png", (inbox / "a.png").read_bytes())
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)
    _fill(outbox, 0, action="reject", note="junk", folder=None, app=None, language=None, pairs=[])
    _fill(outbox, 1)

    written = patch_build.pack(outbox)

    validated = patchfmt.validate_archive(written[0])
    assert [record.file for record in validated.records] == ["screens/b.png"]
    assert validated.manifest.counts.records == 1


def test_pack_rejects_oversized_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inbox = _inbox(tmp_path, ["a.png"])
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)
    _fill_all(outbox)
    monkeypatch.setattr(config, "PATCH_MAX_MB", 0)

    with pytest.raises(patchfmt.PatchError) as exc:
        patch_build.pack(outbox)

    assert "server limit" in exc.value.errors[0]
    assert list(outbox.glob("*.zip")) == []


def test_pack_removes_partial_archives_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inbox = _inbox(tmp_path, ["a.png", "b.png"])
    outbox = _outbox(tmp_path)
    patch_build.scan(inbox, outbox)
    _fill_all(outbox)
    calls = {"count": 0}
    original = patch_build._write_part

    def failing(path, patch_id, records, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("boom")
        original(path, patch_id, records, **kwargs)

    monkeypatch.setattr(patch_build, "_write_part", failing)

    with pytest.raises(RuntimeError):
        patch_build.pack(outbox, max_bytes=1)

    assert list(outbox.glob("*.zip")) == []
    assert list(outbox.glob(".*.tmp")) == []
    assert not (outbox / "ledger.jsonl").exists()
    assert list((outbox / ".work").glob("slice-*.jsonl"))


# ------------------------------------------------------------------ lightweight


def test_patch_build_import_is_lightweight() -> None:
    repo = Path(__file__).resolve().parents[1]
    code = (
        "import sys, duosave.patch_build; "
        "bad = {m for m in ('fastapi', 'rapidocr', 'onnxruntime', 'fastembed', 'numpy',"
        " 'duosave.db', 'duosave.crops', 'duosave.semantic') if m in sys.modules}; "
        "assert not bad, bad"
    )

    result = subprocess.run([sys.executable, "-c", code], cwd=repo, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
