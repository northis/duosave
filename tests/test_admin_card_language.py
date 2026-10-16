"""Admin card language change: in place, merging, validation, guards and the journal.

Changing the language is metadata maintenance: the card keeps its status and notes, and
when the pair already exists under the target language the frames move to that card and
the emptied row is dropped — the unique key (language, original, translation) never
leaves a duplicate behind.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from duosave import db, patch_apply
from duosave.config import APP_CARD

SHOT = "pictures/shot.png"
OTHER = "screens/other.png"
SHA = "d" * 64
CSRF = {"X-Duosave-Request": "1"}
ACTOR = {**CSRF, "Cf-Access-Authenticated-User-Email": "owner@example.com"}


@pytest.fixture(autouse=True)
def _quiet_reindex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: None)


def _seed(tmp_repo, *, path: str = SHOT, sha256: str = SHA, language: str = "pt",
          status: str = "review", notes: str = "") -> int:
    """One card with a source and a `files` row; nothing is written to disk."""
    card_id = db.upsert_card(tmp_repo.conn, language=language, original="o gato",
                             translation="the cat", kind="sentence", app=APP_CARD,
                             screen_type="share_card", status=status, notes=notes,
                             original_folded="o gato", translation_folded="the cat")
    db.add_source(tmp_repo.conn, card_id=card_id, path=path, sha256=sha256, app=APP_CARD,
                  screen_type="share_card", crop_path=None, agreement=None, recognizer="vision")
    db.set_file(tmp_repo.conn, path=path, sha256=sha256, size=3, mtime=1.0, status="review",
                reason="dictionary", recognizer="vision")
    tmp_repo.conn.commit()
    return card_id


def _change(client: TestClient, card_id: int, language: str, headers: dict = CSRF):
    return client.patch(f"/api/admin/cards/{card_id}", json={"language": language},
                        headers=headers)


def test_change_language_updates_the_card(
    admin_client: TestClient, tmp_repo, caplog: pytest.LogCaptureFixture
) -> None:
    card_id = _seed(tmp_repo)

    with caplog.at_level(logging.INFO, logger="duosave.admin"):
        response = _change(admin_client, card_id, "pl", headers=ACTOR)

    assert response.status_code == 200
    assert response.json() == {
        "card_id": card_id, "language": "pl", "original": "o gato",
        "translation": "the cat", "merged_into": None, "changed": True,
    }
    card = db.get_card(tmp_repo.conn, card_id)
    assert card["language"] == "pl"
    assert card["status"] == "review"  # a language fix is not a review decision
    assert card["source_count"] == 1
    assert (f"card_language actor=owner@example.com card_id={card_id} language=pl merged=-"
            in caplog.text)


def test_change_language_merges_into_the_card_that_owns_the_pair(
    admin_client: TestClient, tmp_repo
) -> None:
    owner_id = _seed(tmp_repo, path=OTHER, sha256="e" * 64)
    card_id = _seed(tmp_repo, language="pl")

    response = _change(admin_client, card_id, "pt")

    assert response.status_code == 200
    assert response.json()["merged_into"] == owner_id
    rows = tmp_repo.conn.execute("SELECT id FROM cards").fetchall()
    assert [row["id"] for row in rows] == [owner_id]
    owner = db.get_card(tmp_repo.conn, owner_id)
    assert owner["language"] == "pt" and owner["status"] == "review"
    assert sorted(source["path"] for source in owner["sources"]) == sorted([SHOT, OTHER])
    files = tmp_repo.conn.execute("SELECT path FROM files ORDER BY path").fetchall()
    assert [row["path"] for row in files] == sorted([SHOT, OTHER])


def test_change_language_to_the_same_language_changes_nothing(
    admin_client: TestClient, tmp_repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    card_id = _seed(tmp_repo)
    started: list[str] = []
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: started.append("reindex"))

    response = _change(admin_client, card_id, "pt")

    assert response.status_code == 200
    assert response.json()["changed"] is False
    assert started == []
    card = db.get_card(tmp_repo.conn, card_id)
    assert card["language"] == "pt" and card["status"] == "review"


def test_change_language_to_unknown_is_allowed(admin_client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo)

    response = _change(admin_client, card_id, "unk")

    assert response.status_code == 200
    assert db.get_card(tmp_repo.conn, card_id)["language"] == "unk"


def test_change_language_starts_a_background_reindex(
    admin_client: TestClient, tmp_repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    card_id = _seed(tmp_repo)
    started: list[str] = []
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: started.append("reindex"))

    _change(admin_client, card_id, "pl")

    assert started == ["reindex"]


def test_change_language_with_an_unknown_code_is_400(admin_client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo)

    response = _change(admin_client, card_id, "de")

    assert response.status_code == 400
    assert response.json()["error"] == "unknown_language"
    assert db.get_card(tmp_repo.conn, card_id)["language"] == "pt"


def test_change_language_of_an_unknown_card_is_404(admin_client: TestClient, tmp_repo) -> None:
    response = _change(admin_client, 999, "pl")

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_change_language_requires_the_csrf_header(admin_client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo)

    response = _change(admin_client, card_id, "pl", headers={})

    assert response.status_code == 403
    assert response.json()["error"] == "csrf"
    assert db.get_card(tmp_repo.conn, card_id)["language"] == "pt"


def test_change_language_is_hidden_on_the_public_listener(client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo)

    response = _change(client, card_id, "pl")

    assert response.status_code == 404
    assert db.get_card(tmp_repo.conn, card_id)["language"] == "pt"


def test_admin_search_offers_the_language_targets(admin_client: TestClient, tmp_repo) -> None:
    _seed(tmp_repo)

    data = admin_client.get("/api/admin/cards", params={"q": "gato"}).json()

    assert data["languages"] == [
        {"code": "pt", "name": "Portuguese"},
        {"code": "pl", "name": "Polish"},
        {"code": "es", "name": "Spanish"},
        {"code": "unk", "name": "Unknown"},
    ]
