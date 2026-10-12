"""Updater protocol files: atomic JSON, heartbeat, request parsing, log, lock."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from duosave import control


def _stamp(epoch: float) -> str:
    return (datetime.fromtimestamp(epoch, timezone.utc)
            .isoformat(timespec="seconds").replace("+00:00", "Z"))


def test_write_json_atomic(tmp_path: Path) -> None:
    path = tmp_path / "control" / "update-status.json"

    control.write_json_atomic(path, {"a": 1, "b": "ключ"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": "ключ"}
    assert list(tmp_path.rglob("*.tmp")) == []


def test_read_json_missing_and_broken(tmp_path: Path) -> None:
    assert control.read_json(tmp_path / "nope.json") is None

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert control.read_json(broken) is None

    not_an_object = tmp_path / "list.json"
    not_an_object.write_text("[1, 2]", encoding="utf-8")
    assert control.read_json(not_an_object) is None


def test_runner_alive() -> None:
    now = 1_000_000.0

    assert control.runner_alive({"runner": {"heartbeat_at": _stamp(now - 5)}}, now) is True
    assert control.runner_alive({"runner": {"heartbeat_at": _stamp(now - 61)}}, now) is False
    assert control.runner_alive(None, now) is False
    assert control.runner_alive({}, now) is False
    assert control.runner_alive({"runner": {}}, now) is False
    assert control.runner_alive({"runner": {"heartbeat_at": "yesterday"}}, now) is False


def test_parse_request() -> None:
    valid = {"id": "a" * 32, "action": "update", "requested_by": "owner@example.com"}

    assert control.parse_request(valid) == ("a" * 32, "update")
    assert control.parse_request({**valid, "action": "check"}) == ("a" * 32, "check")
    assert control.parse_request({**valid, "action": "rm -rf"}) is None
    assert control.parse_request({**valid, "id": "not-hex"}) is None
    assert control.parse_request({"request": valid}) is None
    assert control.parse_request("update") is None


def test_new_request_is_valid() -> None:
    request = control.new_request("update", "owner@example.com")

    assert control.parse_request(request) == (request["id"], "update")
    assert request["requested_by"] == "owner@example.com"
    assert request["requested_at"].endswith("Z")


def test_append_log_rotates(tmp_path: Path) -> None:
    path = tmp_path / "control" / "update.log"
    control.append_log(path, "first")
    path.write_text("x" * (control.LOG_MAX_BYTES + 1), encoding="utf-8")

    control.append_log(path, "second")

    rotated = path.with_name("update.log.1")
    assert rotated.exists()
    assert rotated.read_text(encoding="utf-8").startswith("x")
    assert "second" in path.read_text(encoding="utf-8")
    assert "first" not in path.read_text(encoding="utf-8")


def test_tail(tmp_path: Path) -> None:
    path = tmp_path / "update.log"
    for line in ("one", "two", "three"):
        control.append_log(path, line)

    assert len(control.tail(path, 2)) == 2
    assert control.tail(path, 2)[0].endswith("two")
    assert control.tail(path, 1)[0].endswith("three")
    assert control.tail(tmp_path / "nope.log") == []


def test_lock_is_exclusive(tmp_path: Path) -> None:
    path = tmp_path / "control" / "runner.lock"

    first = control.acquire_lock(path)
    assert first is not None
    try:
        assert control.acquire_lock(path) is None
    finally:
        control.release_lock(first)

    second = control.acquire_lock(path)
    assert second is not None
    control.release_lock(second)


def test_paths_live_under_control(tmp_path: Path) -> None:
    for path in (control.request_path(tmp_path), control.processing_path(tmp_path),
                 control.status_path(tmp_path), control.log_path(tmp_path),
                 control.lock_path(tmp_path)):
        assert path.parent == tmp_path / "control"
