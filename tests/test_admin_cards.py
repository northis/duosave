"""Admin card deletion: the API, the files on disk, the guards and the journal.

Deleting a card is a hard delete: the card row (sources and embeddings cascade), the
frames it was recognized from, the Drops crop, the recognition cache and the `files` row
all go, so a fresh share of the same image is recognized again instead of answering
"duplicate". A frame still used by another card is kept.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from duosave import db, patch_apply
from duosave.config import APP_CARD
from duosave.server import admin

SHOT = "pictures/shot.png"
SHA = "d" * 64
CSRF = {"X-Duosave-Request": "1"}
ACTOR = {**CSRF, "Cf-Access-Authenticated-User-Email": "owner@example.com"}


@pytest.fixture(autouse=True)
def _quiet_reindex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: None)


def _write(path, data: bytes = b"png") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _seed(tmp_repo, *, path: str = SHOT, sha256: str = SHA, language: str = "pt",
          crop: str | None = None, image: bool = True) -> int:
    """One card with a source, a `files` row, an image on disk and a recognition cache."""
    if image:
        _write(tmp_repo.root / path)
    if crop:
        _write(tmp_repo.root / crop, b"crop")
    _write(tmp_repo.data / "cache" / f"{sha256}.json", b"{}")
    card_id = db.upsert_card(tmp_repo.conn, language=language, original="o gato",
                             translation="the cat", kind="sentence", app=APP_CARD,
                             screen_type="share_card", status="manual",
                             original_folded="o gato", translation_folded="the cat")
    db.add_source(tmp_repo.conn, card_id=card_id, path=path, sha256=sha256, app=APP_CARD,
                  screen_type="share_card", crop_path=crop, agreement=None, recognizer="vision")
    db.set_file(tmp_repo.conn, path=path, sha256=sha256, size=3, mtime=1.0, status="reviewed",
                reason="accepted", recognizer="vision")
    tmp_repo.conn.commit()
    return card_id


def _counts(tmp_repo) -> dict:
    return {
        table: tmp_repo.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        for table in ("cards", "sources", "files")
    }


def test_delete_removes_the_card_and_the_frame(
    admin_client: TestClient, tmp_repo, caplog: pytest.LogCaptureFixture
) -> None:
    crop = "data/media/drops/dddd.jpg"
    card_id = _seed(tmp_repo, crop=crop)

    with caplog.at_level(logging.INFO, logger="duosave.admin"):
        response = admin_client.delete(f"/api/admin/cards/{card_id}", headers=ACTOR)

    assert response.status_code == 200
    report = response.json()
    assert report["card_id"] == card_id
    assert report["original"] == "o gato"
    assert report["removed"] == [SHOT]
    assert report["missing"] == [] and report["kept"] == []
    assert _counts(tmp_repo) == {"cards": 0, "sources": 0, "files": 0}
    assert not (tmp_repo.root / SHOT).exists()
    assert not (tmp_repo.root / crop).exists()
    assert not (tmp_repo.data / "cache" / f"{SHA}.json").exists()
    assert (f"card_delete actor=owner@example.com card_id={card_id} files=1 missing=0 kept=0"
            in caplog.text)


def test_delete_reports_a_frame_that_is_already_gone(admin_client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo, image=False)

    report = admin_client.delete(f"/api/admin/cards/{card_id}", headers=CSRF).json()

    assert report["missing"] == [SHOT]
    assert report["removed"] == []
    assert _counts(tmp_repo) == {"cards": 0, "sources": 0, "files": 0}


def test_delete_keeps_a_frame_another_card_still_uses(admin_client: TestClient, tmp_repo) -> None:
    other_id = _seed(tmp_repo, path="screens/other.png", sha256="e" * 64, language="pl")
    card_id = _seed(tmp_repo)
    db.add_source(tmp_repo.conn, card_id=other_id, path=SHOT, sha256=SHA, app=APP_CARD,
                  screen_type="share_card", crop_path=None, agreement=None, recognizer="vision")
    tmp_repo.conn.commit()

    report = admin_client.delete(f"/api/admin/cards/{card_id}", headers=CSRF).json()

    assert report["kept"] == [SHOT]
    assert (tmp_repo.root / SHOT).exists()
    assert db.get_card(tmp_repo.conn, other_id)["source_count"] == 2
    row = tmp_repo.conn.execute("SELECT status FROM files WHERE path = ?", (SHOT,)).fetchone()
    assert row["status"] == "reviewed"


def test_delete_starts_a_background_reindex(admin_client: TestClient, tmp_repo,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    card_id = _seed(tmp_repo)
    started: list[str] = []
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: started.append("reindex"))

    admin_client.delete(f"/api/admin/cards/{card_id}", headers=CSRF)

    assert started == ["reindex"]


def test_delete_unknown_card_is_404(admin_client: TestClient, tmp_repo) -> None:
    response = admin_client.delete("/api/admin/cards/999", headers=CSRF)

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_delete_requires_the_csrf_header(admin_client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo)

    response = admin_client.delete(f"/api/admin/cards/{card_id}")

    assert response.status_code == 403
    assert response.json()["error"] == "csrf"
    assert _counts(tmp_repo)["cards"] == 1


def test_delete_is_hidden_on_the_public_listener(client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo)

    response = client.delete(f"/api/admin/cards/{card_id}", headers=CSRF)

    assert response.status_code == 404
    assert _counts(tmp_repo)["cards"] == 1


def test_delete_is_refused_while_another_operation_runs(
    admin_client: TestClient, tmp_repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    card_id = _seed(tmp_repo)
    monkeypatch.setattr(admin, "busy_reason", lambda: "patch apply in progress")

    response = admin_client.delete(f"/api/admin/cards/{card_id}", headers=CSRF)

    assert response.status_code == 409
    assert response.json()["error"] == "busy"
    assert _counts(tmp_repo)["cards"] == 1


def test_admin_search_finds_cards_the_site_hides(client: TestClient, admin_client: TestClient,
                                                 tmp_repo) -> None:
    """A rejected card is invisible in search but still deletable from the admin page."""
    card_id = _seed(tmp_repo)
    db.update_card(tmp_repo.conn, card_id, status="rejected", notes="rejected in review")
    tmp_repo.conn.commit()

    hidden = client.get("/api/search").json()
    found = admin_client.get("/api/admin/cards", params={"q": "gato"}).json()

    assert hidden["total"] == 0
    assert found["total"] == 1
    assert found["items"][0]["id"] == card_id
    assert found["items"][0]["language"] == "pt"
    assert found["items"][0]["original"] == "o gato"
