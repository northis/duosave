"""Admin backup endpoints: streamed download, limits, locking, local-only gate."""

from __future__ import annotations

import zipfile
from io import BytesIO

from fastapi.testclient import TestClient

from duosave.server import admin


def test_db_backup_download(admin_client: TestClient, tmp_repo) -> None:
    response = admin_client.get("/api/admin/backup", params={"kind": "db"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="duosave-backup-db-')
    assert disposition.endswith('.zip"')
    assert response.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        assert zf.testzip() is None
        assert zf.namelist() == ["data/duosave.db", "backup-manifest.json"]


def test_unknown_kind_is_422(admin_client: TestClient, tmp_repo) -> None:
    assert admin_client.get("/api/admin/backup", params={"kind": "bogus"}).status_code == 422


def test_cross_site_download_is_403(admin_client: TestClient, tmp_repo) -> None:
    response = admin_client.get(
        "/api/admin/backup", params={"kind": "db"}, headers={"Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "cross-site"


def test_second_full_backup_is_busy(admin_client: TestClient, tmp_repo) -> None:
    assert admin.FULL_BACKUP_LOCK.acquire(blocking=False)
    try:
        response = admin_client.get("/api/admin/backup", params={"kind": "full"})

        assert response.status_code == 409
        assert response.json() == {"error": "busy", "detail": "full backup in progress"}
        assert admin_client.get("/api/admin/backup", params={"kind": "db"}).status_code == 200
    finally:
        admin.FULL_BACKUP_LOCK.release()


def test_full_backup_releases_the_lock(admin_client: TestClient, tmp_repo) -> None:
    assert admin_client.get("/api/admin/backup", params={"kind": "full"}).status_code == 200

    assert not admin.FULL_BACKUP_LOCK.locked()


def test_estimate_endpoint(admin_client: TestClient, tmp_repo) -> None:
    payload = admin_client.get("/api/admin/backup/estimate").json()

    assert set(payload) == {"db", "full", "computed_at"}
    assert payload["db"] > 0
    assert payload["full"] >= payload["db"]


def test_public_listener_hides_backup(client: TestClient, tmp_repo) -> None:
    response = client.get("/api/admin/backup", params={"kind": "db"})

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
