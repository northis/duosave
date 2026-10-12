"""CLI patch commands: parser wiring, inbox resolution, exit codes, counters."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from duosave import cli, config, patch_build

from helpers import png_bytes


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_parser_knows_patch_commands() -> None:
    parser = cli.build_parser()

    assert parser.parse_args(["patch", "scan"]).func is cli.cmd_patch_scan
    assert parser.parse_args(["patch", "check"]).func is cli.cmd_patch_check
    assert parser.parse_args(["patch", "pack"]).func is cli.cmd_patch_pack


def test_scan_defaults() -> None:
    args = cli.build_parser().parse_args(["patch", "scan"])

    assert args.inbox is None
    assert args.known is None
    assert args.slice_size == 20
    assert args.outbox is None


def test_pack_defaults() -> None:
    args = cli.build_parser().parse_args(["patch", "pack"])

    assert args.max_mb == config.PATCH_PART_MB
    assert args.agent is None


def test_inbox_priority(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DUOSAVE_INBOX", str(tmp_path / "env"))
    monkeypatch.setattr(config, "INBOX_DIR", tmp_path / "default")

    assert patch_build.resolve_inbox(str(tmp_path / "arg")) == tmp_path / "arg"
    assert patch_build.resolve_inbox(None) == tmp_path / "env"

    monkeypatch.delenv("DUOSAVE_INBOX")
    assert patch_build.resolve_inbox(None) == tmp_path / "default"


def test_scan_prints_counters_and_check_propagates_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inbox = tmp_path / "inbox"
    _write(inbox / "a.png", png_bytes())
    outbox = tmp_path / "outbox"

    monkeypatch.setattr(sys, "argv", [
        "duosave", "patch", "scan", "--inbox", str(inbox), "--outbox", str(outbox),
    ])
    assert cli.main() == 0
    output = capsys.readouterr().out
    for label in ("new", "known", "processed", "duplicates", "total"):
        assert label in output

    monkeypatch.setattr(sys, "argv", ["duosave", "patch", "check", "--outbox", str(outbox)])
    assert cli.main() == 2
    assert "pending" in capsys.readouterr().out


def test_check_reports_errors_as_code_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inbox = tmp_path / "inbox"
    _write(inbox / "a.png", png_bytes())
    outbox = tmp_path / "outbox"
    monkeypatch.setattr(sys, "argv", [
        "duosave", "patch", "scan", "--inbox", str(inbox), "--outbox", str(outbox),
    ])
    assert cli.main() == 0
    slice_path = next((outbox / ".work").glob("slice-*.jsonl"))
    slice_path.write_text('{"source": "x", "sha256": "nope"}\n', encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["duosave", "patch", "check", "--outbox", str(outbox)])

    assert cli.main() == 1
    assert "slice-001.jsonl:1" in capsys.readouterr().out


def test_scan_prints_patch_errors_and_returns_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inbox = tmp_path / "inbox"
    _write(inbox / "a.png", png_bytes())
    outbox = tmp_path / "outbox"
    _write(outbox / "known-hashes.txt", b"xyz\n")
    monkeypatch.setattr(sys, "argv", [
        "duosave", "patch", "scan", "--inbox", str(inbox), "--outbox", str(outbox),
    ])

    assert cli.main() == 1
    assert "known-hashes.txt:1" in capsys.readouterr().out


def test_pack_prints_written_archives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inbox = tmp_path / "inbox"
    _write(inbox / "a.png", png_bytes())
    outbox = tmp_path / "outbox"
    monkeypatch.setattr(sys, "argv", [
        "duosave", "patch", "scan", "--inbox", str(inbox), "--outbox", str(outbox),
    ])
    assert cli.main() == 0
    capsys.readouterr()  # drop the scan counters
    slice_path = next((outbox / ".work").glob("slice-*.jsonl"))
    record = json.loads(slice_path.read_text(encoding="utf-8").splitlines()[0])
    record.update({"action": "set", "folder": "screens", "app": "drops", "language": "pt",
                   "screen_type": "drops_card",
                   "pairs": [{"original": "o abacaxi", "translation": "pineapple"}]})
    slice_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", [
        "duosave", "patch", "pack", "--outbox", str(outbox), "--agent", "tests",
    ])

    assert cli.main() == 0
    written = Path(capsys.readouterr().out.strip())
    assert written.exists()
    assert written.name.startswith("duosave-patch-")
