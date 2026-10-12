"""Admin patch API: upload, preview, apply, discard, known-hashes, local-only gate."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duosave import patchfmt
from duosave.server import admin

import patchkit
from helpers import png_bytes

PNG = png_bytes(color=(10, 20, 30))
SCREEN = "screens/Screenshot_20261010-101010.png"
HEADERS = {"Content-Type": "application/zip", "X-Duosave-Request": "1"}
UNKNOWN_ID = "20261012T103105Z-00000000-p9"


@pytest.fixture(autouse=True)
def offline_embedder(monkeypatch: pytest.MonkeyPatch):
    """Never load the real fastembed model from a test (tests are offline by contract)."""
    from duosave import semantic

    def unavailable():
        raise semantic.SemanticUnavailable("tests: fastembed disabled")

    monkeypatch.setattr(semantic, "get_embedder", unavailable)


@pytest.fixture(autouse=True)
def wait_for_reindex():
    yield
    admin.patch_apply.wait_reindex(10)


def _archive(tmp_path: Path, **kwargs) -> bytes:
    records = kwargs.pop("records", None)
    images = kwargs.pop("images", None)
    if records is None:
        records = [patchkit.make_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG))]
    if images is None:
        images = {SCREEN: PNG}
    path = patchkit.build_patch(tmp_path / "patch.zip", records, images, **kwargs)
    return path.read_bytes()


def _upload(client: TestClient, data: bytes, headers: dict | None = None):
    return client.post("/api/admin/patches", content=data, headers=headers or HEADERS)


# --------------------------------------------------------------------- upload


def test_upload_returns_preview(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    response = _upload(admin_client, _archive(tmp_path))

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"patch_id", "state", "already_applied", "uploaded_at", "uploaded_by",
                            "archive_sha256", "generator", "part", "summary", "items"}
    assert payload["state"] == "staged"
    assert payload["summary"]["records"] == 1
    assert payload["items"][0]["outcome"] == "new"
    assert payload["items"][0]["target"] == SCREEN

    listing = admin_client.get("/api/admin/patches").json()
    assert [item["patch_id"] for item in listing["staged"]] == [payload["patch_id"]]


def test_upload_without_csrf_header_is_403(admin_client: TestClient, tmp_repo,
                                           tmp_path: Path) -> None:
    response = _upload(admin_client, _archive(tmp_path), {"Content-Type": "application/zip"})

    assert response.status_code == 403
    assert response.json()["detail"] == "missing header"


def test_upload_wrong_content_type_is_415(admin_client: TestClient, tmp_repo,
                                          tmp_path: Path) -> None:
    response = _upload(admin_client, _archive(tmp_path),
                       {"Content-Type": "text/plain", "X-Duosave-Request": "1"})

    assert response.status_code == 415


def test_upload_declared_too_large_is_413(admin_client: TestClient, tmp_repo, tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin.patch_apply, "max_upload_bytes", lambda: 10)

    response = _upload(admin_client, _archive(tmp_path))

    assert response.status_code == 413
    assert response.json() == {"error": "too_large", "detail": "patch is larger than 100 MB",
                               "limit_mb": 100}


def test_upload_streamed_too_large_is_413(admin_client: TestClient, tmp_repo,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(admin.patch_apply, "max_upload_bytes", lambda: 5)

    response = admin_client.post("/api/admin/patches", content=iter([b"x" * 10]), headers=HEADERS)

    assert response.status_code == 413
    assert response.json()["error"] == "too_large"


def test_upload_invalid_archive_is_422(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    data = _archive(tmp_path, manifest_overrides={"format_version": 2})

    response = _upload(admin_client, data)

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "invalid_patch"
    assert any("новее сайта" in error for error in payload["errors"])


def test_upload_not_a_zip_is_422(admin_client: TestClient, tmp_repo) -> None:
    response = _upload(admin_client, b"definitely not a zip")

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_patch"


# -------------------------------------------------------------------- listing


def test_get_staged_then_applied(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]

    staged = admin_client.get(f"/api/admin/patches/{patch_id}")
    assert staged.status_code == 200
    assert staged.json()["state"] == "staged"

    admin_client.post(f"/api/admin/patches/{patch_id}/apply", headers={"X-Duosave-Request": "1"})

    applied = admin_client.get(f"/api/admin/patches/{patch_id}")
    assert applied.json()["state"] == "applied"
    assert admin_client.get(f"/api/admin/patches/{UNKNOWN_ID}").status_code == 404


def test_preview_image(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]

    response = admin_client.get(f"/api/admin/patches/{patch_id}/files/screens/{Path(SCREEN).name}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG
    assert admin_client.get(
        f"/api/admin/patches/{patch_id}/files/screens/../secret.png"
    ).status_code == 404


# ---------------------------------------------------------------------- apply


def test_apply_reports_and_moves_the_archive(admin_client: TestClient, tmp_repo,
                                             tmp_path: Path) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]

    response = admin_client.post(f"/api/admin/patches/{patch_id}/apply",
                                 headers={"X-Duosave-Request": "1"})

    assert response.status_code == 200
    report = response.json()
    assert report["state"] == "applied"
    assert report["report"]["files_written"] == 1
    assert report["report"]["cards_new"] == 1
    assert report["reindex"]["state"] == "running"
    assert (tmp_repo.data / "patches" / "applied" / f"{patch_id}.zip").exists()
    listing = admin_client.get("/api/admin/patches").json()
    assert listing["staged"] == []
    assert [item["patch_id"] for item in listing["applied"]] == [patch_id]


def test_apply_twice_is_409(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]
    admin_client.post(f"/api/admin/patches/{patch_id}/apply", headers={"X-Duosave-Request": "1"})

    response = admin_client.post(f"/api/admin/patches/{patch_id}/apply",
                                 headers={"X-Duosave-Request": "1"})

    assert response.status_code == 409
    assert response.json()["error"] == "already_applied"


def test_apply_unknown_is_404(admin_client: TestClient, tmp_repo) -> None:
    response = admin_client.post(f"/api/admin/patches/{UNKNOWN_ID}/apply",
                                 headers={"X-Duosave-Request": "1"})

    assert response.status_code == 404


def test_apply_without_csrf_is_403(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]

    assert admin_client.post(f"/api/admin/patches/{patch_id}/apply").status_code == 403


@pytest.mark.parametrize("lock_name", ["APPLY_LOCK", "FULL_BACKUP_LOCK"])
def test_apply_busy_is_409(admin_client: TestClient, tmp_repo, tmp_path: Path,
                           lock_name: str) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]
    lock = getattr(admin, lock_name)
    assert lock.acquire(blocking=False)
    try:
        response = admin_client.post(f"/api/admin/patches/{patch_id}/apply",
                                     headers={"X-Duosave-Request": "1"})
    finally:
        lock.release()

    assert response.status_code == 409
    assert response.json()["error"] == "busy"


# -------------------------------------------------------------------- discard


def test_discard_staged(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]

    assert admin_client.delete(f"/api/admin/patches/{patch_id}",
                               headers={"X-Duosave-Request": "1"}).status_code == 204
    assert admin_client.delete(f"/api/admin/patches/{patch_id}",
                               headers={"X-Duosave-Request": "1"}).status_code == 404


def test_discard_applied_is_409(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]
    admin_client.post(f"/api/admin/patches/{patch_id}/apply", headers={"X-Duosave-Request": "1"})

    response = admin_client.delete(f"/api/admin/patches/{patch_id}",
                                   headers={"X-Duosave-Request": "1"})

    assert response.status_code == 409
    assert response.json()["error"] == "already_applied"


# --------------------------------------------------------------------- journal


def test_journal_records_the_actor(admin_client: TestClient, tmp_repo, tmp_path: Path,
                                   caplog: pytest.LogCaptureFixture) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]
    headers = {"X-Duosave-Request": "1", "Cf-Access-Authenticated-User-Email": "owner@example.com"}

    with caplog.at_level(logging.INFO, logger="duosave.admin"):
        admin_client.post(f"/api/admin/patches/{patch_id}/apply", headers=headers)

    assert f"patch_apply actor=owner@example.com patch_id={patch_id}" in caplog.text


# ---------------------------------------------------------------- known hashes


def test_known_hashes(admin_client: TestClient, tmp_repo, tmp_path: Path) -> None:
    patch_id = _upload(admin_client, _archive(tmp_path)).json()["patch_id"]
    admin_client.post(f"/api/admin/patches/{patch_id}/apply", headers={"X-Duosave-Request": "1"})

    response = admin_client.get("/api/admin/known-hashes")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "duosave-known-hashes-" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    lines = response.text.splitlines()
    assert lines[0].startswith("# duosave known-hashes v1 ")
    assert lines[0].endswith(" 1")
    assert lines[1] == patchfmt.sha256_bytes(PNG)


def test_known_hashes_cross_site_is_403(admin_client: TestClient, tmp_repo) -> None:
    response = admin_client.get("/api/admin/known-hashes",
                                headers={"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == 403


# ------------------------------------------------------------------ public gate


def test_public_listener_hides_the_patch_api(client: TestClient, tmp_repo,
                                             tmp_path: Path) -> None:
    data = _archive(tmp_path)

    assert client.post("/api/admin/patches", content=data, headers=HEADERS).status_code == 404
    assert client.get("/api/admin/patches").status_code == 404
    assert client.get(f"/api/admin/patches/{UNKNOWN_ID}").status_code == 404
    assert client.get("/api/admin/known-hashes").status_code == 404
    assert client.delete(f"/api/admin/patches/{UNKNOWN_ID}",
                         headers={"X-Duosave-Request": "1"}).status_code == 404
