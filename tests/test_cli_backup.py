"""CLI backup command: the first run needs --since, later runs continue from the state."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from duosave import cli

from helpers import png_bytes


def _picture(tmp_repo) -> Path:
    path = tmp_repo.pictures / "a.png"
    path.write_bytes(png_bytes())
    stamp = datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_backup_command_needs_since_first(
    tmp_repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _picture(tmp_repo)
    monkeypatch.setattr(sys, "argv", ["duosave", "backup"])

    assert cli.main() == 1

    assert "--since" in capsys.readouterr().err


def test_backup_command_writes_and_prints(
    tmp_repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _picture(tmp_repo)
    monkeypatch.setattr(
        sys, "argv", ["duosave", "backup", "--since", "2026-01-01T00:00:00+00:00"]
    )

    assert cli.main() == 0

    out = capsys.readouterr().out.splitlines()
    path = Path(out[0])
    assert path.exists()
    assert path.parent == tmp_repo.data / "backups" / "incremental"
    assert path.name.startswith("duosave-backup-incremental-")
    assert out[1] == "files newer than 2026-01-01T00:00:00+00:00: 1"
