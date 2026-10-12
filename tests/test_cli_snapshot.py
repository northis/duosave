"""CLI snapshot command (used by the updater through docker exec)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from duosave import cli


def test_snapshot_command_writes_and_prints(
    tmp_repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["duosave", "snapshot", "--label", "manual"])

    assert cli.main() == 0

    path = Path(capsys.readouterr().out.strip())
    assert path.exists()
    assert path.parent == tmp_repo.data / "backups"
    assert path.name.startswith("manual-")


def test_snapshot_label_defaults_to_manual(
    tmp_repo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["duosave", "snapshot"])

    assert cli.main() == 0

    assert Path(capsys.readouterr().out.strip()).name.startswith("manual-")
