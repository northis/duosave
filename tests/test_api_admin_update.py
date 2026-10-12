"""Admin update API: runner status, request writing, snapshots, local-only gate."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from duosave import __version__, control
from duosave.server import admin

CSRF = {"X-Duosave-Request": "1"}


def _status(runner: bool = True, job_state: str | None = None) -> dict:
    status = {
        "runner": {"pid": 1, "version": "2.2.0", "started_at": control.utc_now(),
                   "heartbeat_at": control.utc_now(), "branch": "master"},
        "repo": {"head": "9c96590477f7437519264fce8aeb3f298b985961",
                 "remote": "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678", "behind": 1, "ahead": 0,
                 "dirty": False, "fetched_at": control.utc_now(), "fetch_error": None},
        "deployed": {"commit": "9c96590477f7437519264fce8aeb3f298b985961",
                     "image": "duosave:latest", "checked_at": control.utc_now()},
        "job": None,
    }
    if not runner:
        status["runner"]["heartbeat_at"] = "2020-01-01T00:00:00Z"
    if job_state:
        status["job"] = {"id": "a" * 32, "action": "update", "state": job_state, "step": "build",
                         "from": None, "to": None, "requested_by": None,
                         "started_at": control.utc_now(), "finished_at": None, "reason": None,
                         "message": ""}
    return status


def _write_status(tmp_repo, **kwargs) -> None:
    control.write_json_atomic(control.status_path(tmp_repo.data), _status(**kwargs))


def _post(client: TestClient, body: dict, headers: dict | None = None):
    return client.post("/api/admin/update", json=body, headers=headers or CSRF)


# ---------------------------------------------------------------------- status


def test_status_without_runner(admin_client: TestClient, tmp_repo) -> None:
    payload = admin_client.get("/api/admin/update").json()

    assert payload["runner_alive"] is False
    assert payload["status"] is None
    assert payload["pending"] is False
    assert payload["site"]["version"] == __version__
    assert payload["site"]["commit"]
    assert payload["log_tail"] == []


def test_status_with_live_runner(admin_client: TestClient, tmp_repo) -> None:
    _write_status(tmp_repo)
    control.append_log(control.log_path(tmp_repo.data), "check: succeeded")

    payload = admin_client.get("/api/admin/update").json()

    assert payload["runner_alive"] is True
    assert payload["status"]["repo"]["behind"] == 1
    assert payload["log_tail"][-1].endswith("check: succeeded")


def test_status_reports_pending(admin_client: TestClient, tmp_repo) -> None:
    control.write_json_atomic(control.request_path(tmp_repo.data),
                              control.new_request("update", None))

    assert admin_client.get("/api/admin/update").json()["pending"] is True


# -------------------------------------------------------------------- requests


def test_update_request_writes_file_and_snapshot(admin_client: TestClient, tmp_repo) -> None:
    _write_status(tmp_repo)

    response = _post(admin_client, {"action": "update"},
                     {**CSRF, "Cf-Access-Authenticated-User-Email": "owner@example.com"})

    assert response.status_code == 202
    payload = response.json()
    assert payload["action"] == "update"
    request = control.read_json(control.request_path(tmp_repo.data))
    assert request["id"] == payload["id"]
    assert request["requested_by"] == "owner@example.com"
    assert request["requested_at"]
    assert list((tmp_repo.data / "backups").glob("pre-update-*.db"))


def test_check_request_skips_snapshot(admin_client: TestClient, tmp_repo) -> None:
    _write_status(tmp_repo)

    assert _post(admin_client, {"action": "check"}).status_code == 202

    assert not list((tmp_repo.data / "backups").glob("pre-update-*.db"))


def test_default_action_is_update(admin_client: TestClient, tmp_repo) -> None:
    _write_status(tmp_repo)

    assert _post(admin_client, {}).json()["action"] == "update"


def test_unknown_action_is_422(admin_client: TestClient, tmp_repo) -> None:
    _write_status(tmp_repo)

    assert _post(admin_client, {"action": "deploy"}).status_code == 422


def test_request_without_csrf_is_403(admin_client: TestClient, tmp_repo) -> None:
    _write_status(tmp_repo)

    assert admin_client.post("/api/admin/update", json={"action": "update"}).status_code == 403


def test_offline_runner_is_503(admin_client: TestClient, tmp_repo) -> None:
    _write_status(tmp_repo, runner=False)

    response = _post(admin_client, {"action": "update"})

    assert response.status_code == 503
    assert response.json()["error"] == "runner_offline"
    assert not control.request_path(tmp_repo.data).exists()


def test_missing_status_is_503(admin_client: TestClient, tmp_repo) -> None:
    assert _post(admin_client, {"action": "check"}).status_code == 503


@pytest.mark.parametrize("kind", ["request", "processing", "running"])
def test_pending_request_is_409(admin_client: TestClient, tmp_repo, kind: str) -> None:
    _write_status(tmp_repo, job_state="running" if kind == "running" else None)
    if kind == "request":
        control.write_json_atomic(control.request_path(tmp_repo.data),
                                  control.new_request("update", None))
    elif kind == "processing":
        control.write_json_atomic(control.processing_path(tmp_repo.data),
                                  control.new_request("update", None))

    response = _post(admin_client, {"action": "update"})

    assert response.status_code == 409
    assert response.json()["error"] == "pending"


@pytest.mark.parametrize("lock_name", ["APPLY_LOCK", "FULL_BACKUP_LOCK"])
def test_busy_operation_is_409(admin_client: TestClient, tmp_repo, lock_name: str) -> None:
    _write_status(tmp_repo)
    lock = getattr(admin, lock_name)
    assert lock.acquire(blocking=False)
    try:
        response = _post(admin_client, {"action": "check"})
    finally:
        lock.release()

    assert response.status_code == 409
    assert response.json()["error"] == "busy"


def test_request_is_audited(admin_client: TestClient, tmp_repo,
                            caplog: pytest.LogCaptureFixture) -> None:
    _write_status(tmp_repo)

    with caplog.at_level(logging.INFO, logger="duosave.admin"):
        _post(admin_client, {"action": "check"},
              {**CSRF, "Cf-Access-Authenticated-User-Email": "owner@example.com"})

    assert "update_request actor=owner@example.com request_action=check" in caplog.text


def test_public_listener_hides_the_update_api(client: TestClient, tmp_repo) -> None:
    _write_status(tmp_repo)

    assert client.get("/api/admin/update").status_code == 404
    assert _post(client, {"action": "check"}).status_code == 404
