"""Public upload API: dedup, limits, folder choice, OCR fallback and the journal."""

from __future__ import annotations

import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from duosave import config, db, patch_apply, patchfmt, recognize, sync
from duosave.config import APP_CARD, APP_DROPS, APP_DUO
from duosave.recognize import Pair, Recognition
from duosave.vision import VisionUnavailable

from helpers import png_bytes, sha256_hex

PNG = png_bytes(color=(10, 20, 30))
HEADERS = {"X-Duosave-Request": "1", "Content-Type": "image/png"}
ACTOR_HEADERS = {**HEADERS, "Cf-Access-Authenticated-User-Email": "owner@example.com"}


def _upload(client: TestClient, body: bytes = PNG, headers: dict | None = None):
    return client.post("/api/upload", content=body, headers=headers or HEADERS)


def _recognition(**overrides) -> Recognition:
    """A vision-style result; tests override only what they pin."""
    values = {
        "usable": True,
        "app": APP_CARD,
        "screen_type": "share_card",
        "language": "pl",
        "pairs": [Pair("Czy masz czas?", "Do you have time?")],
        "status": "auto",
        "reason": "",
        "elapsed": 2.414,
    }
    values.update(overrides)
    return Recognition(**values)


def _fake_ocr(monkeypatch: pytest.MonkeyPatch, calls: list[str] | None = None,
              **overrides):
    """Replace the lazy OCR engine with a recording stub."""

    def fake_recognize(path, kind_hint: str = "auto"):
        if calls is not None:
            calls.append(kind_hint)
        recognition = _recognition(**overrides)
        return recognition, recognition.to_cache()

    monkeypatch.setattr(recognize, "recognize_image", fake_recognize)


def _row(conn: sqlite3.Connection, table: str, path: str):
    return conn.execute(f"SELECT * FROM {table} WHERE path = ?", (path,)).fetchone()


@pytest.fixture(autouse=True)
def _quiet_reindex(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uploads trigger a background index rebuild: tests pin the trigger, not the run."""
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: None)


# ----------------------------------------------------------------------- stored


def test_upload_stores_a_card_recognized_by_vision(client: TestClient, tmp_repo,
                                                   fake_vision) -> None:
    fake_vision.result = _recognition()

    response = _upload(client)

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"outcome", "path", "card_id", "app", "screen_type", "language",
                            "pairs", "status", "reason", "recognizer", "elapsed"}
    assert payload["outcome"] == "stored"
    assert payload["status"] == "auto"
    assert payload["recognizer"] == "vision"
    assert payload["app"] == APP_CARD
    assert payload["screen_type"] == "share_card"
    assert payload["language"] == "pl"
    assert payload["reason"] == ""
    assert payload["pairs"] == [{"original": "Czy masz czas?", "translation": "Do you have time?",
                                 "kind": "sentence"}]
    assert payload["elapsed"] == 2.41
    assert isinstance(payload["card_id"], int)
    assert fake_vision.calls == 1

    file_row = _row(tmp_repo.conn, "files", payload["path"])
    assert file_row["status"] == "auto"
    assert file_row["recognizer"] == "vision"
    source_row = _row(tmp_repo.conn, "sources", payload["path"])
    assert source_row["recognizer"] == "vision"
    assert source_row["card_id"] == payload["card_id"]
    card_row = tmp_repo.conn.execute("SELECT * FROM cards WHERE id = ?",
                                     (payload["card_id"],)).fetchone()
    assert card_row["language"] == "pl"
    assert card_row["original"] == "Czy masz czas?"


def test_upload_card_frame_lands_in_pictures(client: TestClient, tmp_repo, fake_vision) -> None:
    fake_vision.result = _recognition()

    payload = _upload(client).json()

    assert payload["path"].startswith("pictures/")
    assert (tmp_repo.root / payload["path"]).read_bytes() == PNG


def test_upload_screenshot_lands_in_screens(client: TestClient, tmp_repo, fake_vision) -> None:
    jpeg = png_bytes(color=(30, 20, 10), fmt="JPEG")
    fake_vision.result = _recognition(app=APP_DUO, status="review", reason="app_screen")

    payload = _upload(client, jpeg).json()

    assert payload["path"].startswith("screens/")
    assert payload["path"].endswith(".jpg")
    assert fake_vision.media_types == ["image/jpeg"]
    assert (tmp_repo.root / payload["path"]).read_bytes() == jpeg


def test_upload_drops_writes_the_crop(client: TestClient, tmp_repo, fake_vision) -> None:
    body = png_bytes(color=(200, 120, 40), size=(60, 60))
    fake_vision.result = _recognition(app=APP_DROPS, pairs=[Pair("kot", "cat", "word")])

    payload = _upload(client, body).json()

    assert payload["path"].startswith("screens/")
    crop = tmp_repo.data / "media" / "drops" / f"{sha256_hex(body)[:16]}.jpg"
    assert crop.exists()


def test_upload_file_row_matches_the_disk(client: TestClient, tmp_repo, fake_vision) -> None:
    fake_vision.result = _recognition()

    payload = _upload(client).json()

    stat = (tmp_repo.root / payload["path"]).stat()
    row = tmp_repo.conn.execute("SELECT size, mtime FROM files WHERE path = ?",
                                (payload["path"],)).fetchone()
    assert row["size"] == stat.st_size
    assert row["mtime"] == float(stat.st_mtime_ns)


# -------------------------------------------------------------------- duplicate


def test_upload_duplicate_skips_the_api(client: TestClient, tmp_repo, fake_vision) -> None:
    fake_vision.result = _recognition()
    first = _upload(client).json()

    second = _upload(client).json()

    assert second["outcome"] == "duplicate"
    assert second["path"] == first["path"]
    assert second["card_id"] == first["card_id"]
    assert fake_vision.calls == 1
    assert len(list(tmp_repo.pictures.iterdir()) + list(tmp_repo.screens.iterdir())) == 1
    for table in ("files", "sources", "cards"):
        assert tmp_repo.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] == 1


def test_upload_duplicate_mirrors_the_existing_row(client: TestClient, tmp_repo,
                                                   fake_vision) -> None:
    body = png_bytes(color=(5, 6, 7))
    sha = sha256_hex(body)
    db.set_file(tmp_repo.conn, path="screens/old.png", sha256=sha, size=len(body), mtime=1.0,
                status="reviewed", reason="accepted", recognizer="vision")
    card_id = db.upsert_card(tmp_repo.conn, language="pl", original="kot", translation="cat",
                             kind="word", app=APP_CARD, screen_type="share_card",
                             status="manual", original_folded="kot", translation_folded="cat")
    db.add_source(tmp_repo.conn, card_id=card_id, path="screens/old.png", sha256=sha,
                  app=APP_CARD, screen_type="share_card", crop_path=None, agreement=None,
                  recognizer="vision")
    tmp_repo.conn.commit()

    payload = _upload(client, body).json()

    assert payload == {
        "outcome": "duplicate",
        "path": "screens/old.png",
        "card_id": card_id,
        "app": APP_CARD,
        "screen_type": "share_card",
        "language": "pl",
        "pairs": [{"original": "kot", "translation": "cat", "kind": "word"}],
        "status": "review",
        "reason": "accepted",
        "recognizer": "vision",
        "elapsed": 0.0,
    }
    assert fake_vision.calls == 0

    bare = png_bytes(color=(8, 9, 10))
    db.set_file(tmp_repo.conn, path="screens/bare.png", sha256=sha256_hex(bare), size=len(bare),
                mtime=1.0, status="rejected", reason="rejected in review")
    tmp_repo.conn.commit()

    bare_payload = _upload(client, bare).json()

    assert bare_payload["outcome"] == "duplicate"
    assert bare_payload["path"] == "screens/bare.png"
    assert bare_payload["card_id"] is None
    assert bare_payload["app"] is None
    assert bare_payload["screen_type"] is None
    assert bare_payload["language"] is None
    assert bare_payload["pairs"] == []
    assert bare_payload["status"] == "skipped"
    assert bare_payload["recognizer"] == "ocr"


# ----------------------------------------------------------------------- errors


def test_upload_without_csrf_header_is_403(client: TestClient, tmp_repo) -> None:
    response = client.post("/api/upload", content=PNG, headers={"Content-Type": "image/png"})

    assert response.status_code == 403
    assert response.json()["error"] == "csrf"


def test_upload_wrong_content_type_is_415(client: TestClient, tmp_repo) -> None:
    response = _upload(client, headers={"X-Duosave-Request": "1", "Content-Type": "text/plain"})

    assert response.status_code == 415
    assert response.json()["error"] == "unsupported_media_type"


def test_upload_without_content_length_is_411(client: TestClient, tmp_repo) -> None:
    response = client.post("/api/upload", content=iter([PNG]), headers=HEADERS)

    assert response.status_code == 411
    assert response.json()["error"] == "length_required"


def test_upload_declared_too_large_is_413(client: TestClient, tmp_repo,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "VISION_MAX_MB", 0)

    response = _upload(client)

    assert response.status_code == 413
    assert response.json() == {"error": "too_large", "detail": "image is larger than 0 MB",
                               "limit_mb": 0}


def test_upload_not_an_image_is_422(client: TestClient, tmp_repo) -> None:
    response = _upload(client, b"definitely not an image")

    assert response.status_code == 422
    assert response.json()["error"] == "not_an_image"


def test_upload_unknown_image_format_is_422(client: TestClient, tmp_repo) -> None:
    response = _upload(client, png_bytes(fmt="GIF"))

    assert response.status_code == 422
    assert response.json()["error"] == "not_an_image"


def test_upload_too_many_pixels_is_422(client: TestClient, tmp_repo,
                                       monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patchfmt, "MAX_PIXELS", 100)

    response = _upload(client)

    assert response.status_code == 422
    assert response.json()["error"] == "not_an_image"


def test_upload_busy_is_503(client: TestClient, tmp_repo, fake_vision,
                            monkeypatch: pytest.MonkeyPatch,
                            caplog: pytest.LogCaptureFixture) -> None:
    fake_vision.result = _recognition()

    def busy(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(sync, "store_recognition", busy)

    with caplog.at_level(logging.INFO, logger="duosave.admin"):
        response = _upload(client, headers=ACTOR_HEADERS)

    assert response.status_code == 503
    assert response.json()["error"] == "busy"
    assert tmp_repo.conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] == 0
    assert (tmp_repo.pictures / f"{sha256_hex(PNG)[:16]}.png").exists()
    assert (f"upload actor=owner@example.com path=pictures/{sha256_hex(PNG)[:16]}.png"
            f" outcome=busy status= recognizer= reason= vision= vision_status= vision_detail="
            f" renamed=False"
            in caplog.text)


# --------------------------------------------------------------------- fallback


def test_upload_vision_failure_falls_back_to_ocr(client: TestClient, tmp_repo, fake_vision,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    body = png_bytes(size=(40, 40))
    fake_vision.error = VisionUnavailable("http_429")
    calls: list[str] = []
    _fake_ocr(monkeypatch, calls, status="review", reason="app_screen")

    payload = _upload(client, body).json()

    assert payload["recognizer"] == "ocr"
    assert payload["status"] == "review"
    assert payload["path"].startswith("pictures/")
    assert fake_vision.calls == 1
    assert calls == ["card"]


def test_upload_without_a_key_uses_proportions(client: TestClient, tmp_repo, fake_vision,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    fake_vision.available = False
    calls: list[str] = []
    _fake_ocr(monkeypatch, calls, status="review", reason="no_pair")

    square = _upload(client, png_bytes(size=(40, 40))).json()
    wide = _upload(client, png_bytes(color=(1, 2, 3), size=(60, 30))).json()

    assert square["path"].startswith("pictures/")
    assert wide["path"].startswith("screens/")
    assert calls == ["card", "auto"]
    assert fake_vision.calls == 0


# ---------------------------------------------------------------- kept frames


def test_upload_review_frame_keeps_the_file(client: TestClient, tmp_repo, fake_vision) -> None:
    fake_vision.result = _recognition(usable=False, app=APP_DUO, pairs=[],
                                      status="review", reason="vision_no_pair")

    payload = _upload(client).json()

    assert payload["outcome"] == "stored"
    assert payload["card_id"] is None
    assert payload["status"] == "review"
    assert payload["reason"] == "vision_no_pair"
    assert (tmp_repo.root / payload["path"]).exists()
    assert _row(tmp_repo.conn, "files", payload["path"])["recognizer"] == "vision"
    assert tmp_repo.conn.execute("SELECT COUNT(*) AS n FROM files").fetchone()["n"] == 1
    assert tmp_repo.conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"] == 0


def test_upload_skipped_frame_keeps_the_file(client: TestClient, tmp_repo, fake_vision) -> None:
    fake_vision.result = _recognition(usable=False, app="other", pairs=[],
                                      status="skipped", reason="vision_no_pair")

    payload = _upload(client).json()

    assert payload["outcome"] == "stored"
    assert payload["card_id"] is None
    assert payload["status"] == "skipped"
    assert payload["path"].startswith("screens/")
    assert (tmp_repo.root / payload["path"]).exists()
    assert _row(tmp_repo.conn, "files", payload["path"])["recognizer"] == "vision"
    assert tmp_repo.conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"] == 0


# --------------------------------------------------------------------- journal


def test_upload_journal_line_carries_actor_and_vision_reason(
    client: TestClient, tmp_repo, fake_vision, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_vision.error = VisionUnavailable("http_429", status=429, detail="Rate limit exceeded")
    _fake_ocr(monkeypatch, status="review", reason="app_screen")

    with caplog.at_level(logging.INFO, logger="duosave.admin"):
        payload = _upload(client, headers=ACTOR_HEADERS).json()

    assert (f"upload actor=owner@example.com path={payload['path']} outcome=stored"
            f" status=review recognizer=ocr reason=app_screen vision=http_429"
            f" vision_status=429 vision_detail=Rate limit exceeded renamed=False"
            in caplog.text)
    assert "Czy masz czas?" not in caplog.text


def test_upload_duplicate_is_journalled(client: TestClient, tmp_repo, fake_vision,
                                        caplog: pytest.LogCaptureFixture) -> None:
    fake_vision.result = _recognition()
    first = _upload(client, headers=ACTOR_HEADERS).json()

    with caplog.at_level(logging.INFO, logger="duosave.admin"):
        second = _upload(client, headers=ACTOR_HEADERS).json()

    assert second["outcome"] == "duplicate"
    assert (f"upload actor=owner@example.com path={first['path']} outcome=duplicate"
            f" status=auto recognizer=vision reason= vision= vision_status= vision_detail="
            in caplog.text)


# --------------------------------------------------------------------- reindex


def test_upload_starts_a_background_reindex(client: TestClient, tmp_repo, fake_vision,
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """A stored card must reach semantic search without a manual index run."""
    fake_vision.result = _recognition()
    started: list[str] = []
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: started.append("reindex"))

    payload = _upload(client).json()

    assert payload["card_id"] is not None
    assert started == ["reindex"]


def test_upload_without_a_card_does_not_reindex(client: TestClient, tmp_repo, fake_vision,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    fake_vision.result = _recognition(usable=False, app=APP_DUO, pairs=[],
                                      status="review", reason="vision_no_pair")
    started: list[str] = []
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: started.append("reindex"))

    payload = _upload(client).json()

    assert payload["card_id"] is None
    assert started == []


def test_upload_duplicate_does_not_reindex(client: TestClient, tmp_repo, fake_vision,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    fake_vision.result = _recognition()
    _upload(client)
    started: list[str] = []
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: started.append("reindex"))

    payload = _upload(client).json()

    assert payload["outcome"] == "duplicate"
    assert started == []


# The autouse no-op above hides the real trigger; this reference keeps it reachable.
REAL_START_REINDEX = patch_apply.start_reindex


def test_upload_indexes_the_new_card(client: TestClient, tmp_repo, fake_vision, fake_embedder,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """A stored card reaches the semantic index through the real background reindex."""
    fake_vision.result = _recognition()
    monkeypatch.setattr(patch_apply, "start_reindex", REAL_START_REINDEX)

    payload = _upload(client).json()
    state = patch_apply.wait_reindex(5)

    assert state["state"] == "done", state
    assert state["result"]["added"] == 1
    row = tmp_repo.conn.execute("SELECT card_id FROM card_embeddings").fetchone()
    assert row["card_id"] == payload["card_id"]


# ------------------------------------------------------------------- provenance


def test_review_action_keeps_the_recognizer(client: TestClient, tmp_repo, fake_vision) -> None:
    fake_vision.result = _recognition()
    payload = _upload(client).json()

    accepted = client.post("/api/review", json={"path": payload["path"], "action": "accept"})

    assert accepted.status_code == 200
    row = tmp_repo.conn.execute("SELECT recognizer, status FROM files WHERE path = ?",
                                (payload["path"],)).fetchone()
    assert row["status"] == "reviewed"
    assert row["recognizer"] == "vision"


def test_review_action_starts_a_background_reindex(client: TestClient, tmp_repo, fake_vision,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """Accepting a card changes the card set, so the semantic index follows."""
    fake_vision.result = _recognition()
    payload = _upload(client).json()
    started: list[str] = []
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: started.append("reindex"))

    accepted = client.post("/api/review", json={"path": payload["path"], "action": "accept"})

    assert accepted.status_code == 200
    assert started == ["reindex"]
