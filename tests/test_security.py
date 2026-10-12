"""Admin guards: CSRF, cross-site downloads, local-listener check, actor."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from duosave import config
from duosave.server import security
from duosave.server.security import AdminError, admin_error_handler

app = FastAPI()
app.add_exception_handler(AdminError, admin_error_handler)


@app.post("/x")
def post_x(_: None = Depends(security.require_csrf)) -> dict:
    return {"ok": True}


@app.get("/d")
def get_d(_: None = Depends(security.forbid_cross_site)) -> dict:
    return {"ok": True}


def _request(server: Any = None, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers or [],
                    "server": server})


def _actor_request(value: str | None) -> Request:
    header = security.ACTOR_HEADER.lower().encode()
    headers = [] if value is None else [(header, value.encode("utf-8"))]
    return _request(headers=headers)


def test_post_without_header_is_403() -> None:
    response = TestClient(app).post("/x")

    assert response.status_code == 403
    assert response.json()["detail"] == "missing header"


def test_post_with_header_and_no_origin_passes() -> None:
    response = TestClient(app).post("/x", headers={security.CSRF_HEADER: "1"})

    assert response.status_code == 200


def test_origin_matching_host_passes() -> None:
    response = TestClient(app).post(
        "/x", headers={security.CSRF_HEADER: "1", "Origin": "http://testserver"}
    )

    assert response.status_code == 200


def test_origin_matching_forwarded_host_passes() -> None:
    response = TestClient(app, base_url="http://10.77.77.21:8765").post(
        "/x",
        headers={
            security.CSRF_HEADER: "1",
            "Origin": "https://duosave.example.com",
            "X-Forwarded-Host": "duosave.example.com",
        },
    )

    assert response.status_code == 200


def test_origin_mismatch_is_403() -> None:
    response = TestClient(app).post(
        "/x", headers={security.CSRF_HEADER: "1", "Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "origin mismatch"


def test_origin_null_is_403() -> None:
    response = TestClient(app).post(
        "/x", headers={security.CSRF_HEADER: "1", "Origin": "null"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "origin mismatch"


def test_default_ports_are_ignored() -> None:
    response = TestClient(app, base_url="http://h.example").post(
        "/x", headers={security.CSRF_HEADER: "1", "Origin": "https://h.example:443"}
    )

    assert response.status_code == 200


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_sec_fetch_site_same_origin_or_none_passes(site: str) -> None:
    response = TestClient(app).post(
        "/x", headers={security.CSRF_HEADER: "1", "Sec-Fetch-Site": site}
    )

    assert response.status_code == 200


def test_sec_fetch_site_cross_site_is_403() -> None:
    response = TestClient(app).post(
        "/x", headers={security.CSRF_HEADER: "1", "Sec-Fetch-Site": "cross-site"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "cross-site"


def test_download_without_header_passes() -> None:
    assert TestClient(app).get("/d").status_code == 200


def test_download_same_origin_passes() -> None:
    response = TestClient(app).get("/d", headers={"Sec-Fetch-Site": "same-origin"})

    assert response.status_code == 200


def test_download_cross_site_is_403() -> None:
    response = TestClient(app).get("/d", headers={"Sec-Fetch-Site": "cross-site"})

    assert response.status_code == 403
    assert response.json()["detail"] == "cross-site"


def test_actor_reads_email() -> None:
    assert security.actor(_actor_request("owner@example.com")) == "owner@example.com"


def test_actor_strips_control_and_non_ascii() -> None:
    assert security.actor(_actor_request("ow\x00ner@ex\nample.com\u00e9")) == "owner@example.com"


def test_actor_truncates_to_254() -> None:
    assert security.actor(_actor_request("a" * 300)) == "a" * 254


def test_actor_missing_is_none() -> None:
    assert security.actor(_actor_request(None)) is None


def test_is_local_admin_by_listener_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ADMIN_PORT", 8766)

    assert security.is_local_admin(_request(("127.0.0.1", 8766))) is True
    assert security.is_local_admin(_request(("127.0.0.1", 8765))) is False
    assert security.is_local_admin(_request(None)) is False
    assert security.is_local_admin(_request(("127.0.0.1",))) is False

    monkeypatch.setattr(config, "ADMIN_PORT", 0)
    assert security.is_local_admin(_request(("127.0.0.1", 8766))) is False


def test_require_local_rejects_public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ADMIN_PORT", 8766)

    with pytest.raises(security.AdminError) as exc:
        security.require_local(_request(("127.0.0.1", 8765)))

    assert exc.value.status == 404
    assert exc.value.code == "not_found"


def test_require_local_allows_admin_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ADMIN_PORT", 8766)

    security.require_local(_request(("127.0.0.1", 8766)))


def test_audit_writes_to_journal(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="duosave.admin"):
        security.audit("patch_apply", "owner@example.com", patch_id="p1")

    assert "patch_apply actor=owner@example.com patch_id=p1" in caplog.text
