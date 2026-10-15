"""Review actions and the language combobox: accept, edit in place, merging and validation.

The combobox is the human override for a language the recognizer could not decide. An
accept or edit must move the existing card instead of creating a second one, and moving a
card to a language that already owns the pair must merge the two rather than violate the
unique key.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from duosave import db, patch_apply
from duosave.config import APP_CARD

SHOT = "pictures/shot.png"
SHA = "a" * 64


@pytest.fixture(autouse=True)
def _quiet_reindex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patch_apply, "start_reindex", lambda: None)


def _seed(tmp_repo, *, language: str = "unk", path: str = SHOT, sha256: str = SHA,
          original: str = "o gato", translation: str = "the cat") -> int:
    card_id = db.upsert_card(tmp_repo.conn, language=language, original=original,
                             translation=translation, kind="sentence", app=APP_CARD,
                             screen_type="share_card", status="auto",
                             original_folded=original, translation_folded=translation)
    db.add_source(tmp_repo.conn, card_id=card_id, path=path, sha256=sha256, app=APP_CARD,
                  screen_type="share_card", crop_path=None, agreement=None, recognizer="vision")
    db.set_file(tmp_repo.conn, path=path, sha256=sha256, size=1, mtime=1.0, status="review",
                reason="language_unknown", recognizer="vision")
    tmp_repo.conn.commit()
    return card_id


def _post(client: TestClient, **payload):
    return client.post("/api/review", json=payload)


def _card(tmp_repo, card_id: int) -> dict:
    return db.get_card(tmp_repo.conn, card_id)


def _file_status(tmp_repo, path: str = SHOT) -> str:
    row = tmp_repo.conn.execute("SELECT status FROM files WHERE path = ?", (path,)).fetchone()
    return row["status"]


# --------------------------------------------------------------------- accept


def test_accept_with_a_picked_language_moves_the_card(client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo)

    response = _post(client, path=SHOT, action="accept", language="pt")

    assert response.status_code == 200
    card = _card(tmp_repo, card_id)
    assert card["language"] == "pt"
    assert card["status"] == "manual"
    assert _file_status(tmp_repo) == "reviewed"


def test_accept_without_a_language_keeps_the_detected_one(client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo, language="pl")

    _post(client, path=SHOT, action="accept")

    assert _card(tmp_repo, card_id)["language"] == "pl"
    assert _card(tmp_repo, card_id)["status"] == "manual"


def test_accept_with_an_unknown_language_is_400(client: TestClient, tmp_repo) -> None:
    _seed(tmp_repo)

    response = _post(client, path=SHOT, action="accept", language="de")

    assert response.status_code == 400
    assert response.json()["error"] == "unknown_language"
    assert _file_status(tmp_repo) == "review"


def test_accept_merges_into_the_card_that_owns_the_pair(client: TestClient, tmp_repo) -> None:
    """Accepting with a language that already has the pair keeps one card, two sources."""
    merged_id = _seed(tmp_repo, language="pt", path="screens/other.png", sha256="b" * 64)
    _seed(tmp_repo)

    response = _post(client, path=SHOT, action="accept", language="pt")

    assert response.status_code == 200
    rows = tmp_repo.conn.execute("SELECT id, language, status FROM cards").fetchall()
    assert [(row["id"], row["language"], row["status"]) for row in rows] == [
        (merged_id, "pt", "manual"),
    ]
    assert db.get_card(tmp_repo.conn, merged_id)["source_count"] == 2
    assert _file_status(tmp_repo) == "reviewed"


# ----------------------------------------------------------------------- edit


def test_edit_updates_the_card_in_place(client: TestClient, tmp_repo) -> None:
    """Fixing the language must not leave the old card behind: one row, new language."""
    card_id = _seed(tmp_repo)

    response = _post(client, path=SHOT, action="edit", language="pt",
                     original="o gato", translation="the cat")

    assert response.status_code == 200
    rows = tmp_repo.conn.execute("SELECT id, language, status FROM cards").fetchall()
    assert [(row["id"], row["language"], row["status"]) for row in rows] == [
        (card_id, "pt", "manual"),
    ]
    assert _file_status(tmp_repo) == "reviewed"


def test_edit_merges_into_the_card_that_owns_the_pair(client: TestClient, tmp_repo) -> None:
    """The pair already exists under pt: the sources move there, the empty row goes."""
    merged_id = _seed(tmp_repo, language="pt", path="screens/other.png", sha256="b" * 64)
    _seed(tmp_repo)

    response = _post(client, path=SHOT, action="edit", language="pt",
                     original="o gato", translation="the cat")

    assert response.status_code == 200
    rows = tmp_repo.conn.execute("SELECT id, language FROM cards").fetchall()
    assert [(row["id"], row["language"]) for row in rows] == [(merged_id, "pt")]
    paths = [row["path"] for row in tmp_repo.conn.execute(
        "SELECT path FROM sources WHERE card_id = ?", (merged_id,))]
    assert sorted(paths) == ["pictures/shot.png", "screens/other.png"]


def test_edit_keeps_the_language_when_the_combobox_is_empty(client: TestClient, tmp_repo) -> None:
    card_id = _seed(tmp_repo, language="pl")

    _post(client, path=SHOT, action="edit", original="kot", translation="cat")

    card = _card(tmp_repo, card_id)
    assert card["language"] == "pl"
    assert card["original"] == "kot"


def test_edit_without_a_card_creates_one(client: TestClient, tmp_repo) -> None:
    db.set_file(tmp_repo.conn, path="screens/bare.png", sha256="c" * 64, size=1, mtime=1.0,
                status="review", reason="no_pair")
    tmp_repo.conn.commit()

    response = _post(client, path="screens/bare.png", action="edit", language="pt",
                     original="a casa", translation="the house")

    assert response.status_code == 200
    card = tmp_repo.conn.execute("SELECT * FROM cards").fetchone()
    assert (card["language"], card["original"], card["status"]) == ("pt", "a casa", "manual")
    source = tmp_repo.conn.execute(
        "SELECT recognizer FROM sources WHERE path = 'screens/bare.png'").fetchone()
    assert source["recognizer"] == "manual"
    assert _file_status(tmp_repo, "screens/bare.png") == "reviewed"


def test_edit_with_an_unknown_language_is_400(client: TestClient, tmp_repo) -> None:
    _seed(tmp_repo)

    response = _post(client, path=SHOT, action="edit", language="de",
                     original="o gato", translation="the cat")

    assert response.status_code == 400
    assert response.json()["error"] == "unknown_language"
    assert _file_status(tmp_repo) == "review"
