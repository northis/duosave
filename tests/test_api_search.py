"""API search: mode parameter, semantic metadata, degradation, pagination."""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest
from fastapi.testclient import TestClient

from duosave import db, semantic
from duosave.server.app import app


def _insert_card(
    conn: sqlite3.Connection,
    *,
    original: str = "original",
    translation: str = "translation",
    language: str = "pl",
    status: str = "auto",
) -> int:
    card_id = db.upsert_card(
        conn,
        language=language,
        original=original,
        translation=translation,
        kind="sentence",
        app="duolingo_card",
        screen_type=None,
        status=status,
        original_folded=original.lower(),
        translation_folded=translation.lower(),
    )
    conn.commit()
    return card_id


def _attach_source(conn: sqlite3.Connection, card_id: int, path: str, created_ts: int) -> None:
    db.set_file(
        conn, path=path, sha256=path, size=0, mtime=0, status="processed", created_ts=created_ts
    )
    db.add_source(
        conn,
        card_id=card_id,
        path=path,
        sha256=path,
        app=None,
        screen_type=None,
        crop_path=None,
        agreement=None,
    )
    conn.commit()


def _stored_vector(conn: sqlite3.Connection, card_id: int) -> np.ndarray:
    row = conn.execute(
        "SELECT vector FROM card_embeddings WHERE card_id = ?", (card_id,)
    ).fetchone()
    return np.frombuffer(row["vector"], dtype="<f4").copy()


def _build_index(conn: sqlite3.Connection) -> None:
    semantic.reindex(conn)
    conn.commit()


def _ids(payload: dict) -> list[int]:
    return [item["id"] for item in payload["items"]]


def test_unknown_mode_returns_422(tmp_db: sqlite3.Connection) -> None:
    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": "jeden", "mode": "fuzzy"})

    assert response.status_code == 422


def test_default_mode_is_hybrid(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _build_index(tmp_db)

    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": "jeden"})

    assert response.status_code == 200
    data = response.json()
    assert data["semantic"] == {"available": True, "mode": "hybrid", "stale": 0, "reason": None}


def test_empty_query_uses_text_path_and_skips_embedder(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    first = _insert_card(tmp_db, original="jeden", translation="one")
    second = _insert_card(tmp_db, original="dwa", translation="two")
    _attach_source(tmp_db, first, "screens/a.png", 100)
    _attach_source(tmp_db, second, "screens/b.png", 200)

    with TestClient(app) as client:
        old = client.get("/api/search", params={"q": "", "sort": "old"}).json()
        new = client.get("/api/search", params={"q": "", "sort": "new"}).json()

    assert fake_embedder.query_calls == 0
    assert old["semantic"]["available"] is True
    assert old["semantic"]["mode"] == "text"
    assert old["semantic"]["reason"] is None
    assert _ids(old) == [first, second]
    assert _ids(new) == [second, first]


def test_text_mode_matches_text_search(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _insert_card(tmp_db, original="dwa", translation="two")
    _build_index(tmp_db)
    _insert_card(tmp_db, original="trzy", translation="three")

    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": "jeden", "mode": "text", "sort": "old"})

    expected, expected_total = db.search_cards(
        tmp_db, query="jeden", lang="", app="", limit=60, offset=0, sort="old"
    )
    data = response.json()
    assert data["items"] == expected
    assert data["total"] == expected_total
    assert data["semantic"] == {"available": True, "mode": "text", "stale": 1, "reason": None}


def test_hybrid_exact_match_above_semantic_only_match(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    exact = _insert_card(tmp_db, original="jeden", translation="one")
    semantic_only = _insert_card(tmp_db, original="dwa", translation="two")
    _build_index(tmp_db)
    fake_embedder.query_vector = _stored_vector(tmp_db, semantic_only)

    with TestClient(app) as client:
        data = client.get("/api/search", params={"q": "jeden", "mode": "hybrid"}).json()

    assert _ids(data) == [exact, semantic_only]


def test_hybrid_prefilter_applies_lang_to_vector_branch(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    polish = _insert_card(tmp_db, original="jeden", translation="one", language="pl")
    spanish = _insert_card(tmp_db, original="dwa", translation="two", language="es")
    _build_index(tmp_db)
    fake_embedder.query_vector = _stored_vector(tmp_db, spanish)

    with TestClient(app) as client:
        data = client.get("/api/search", params={"q": "jeden", "lang": "pl"}).json()

    assert data["semantic"]["mode"] == "hybrid"
    assert data["semantic"]["available"] is True
    assert spanish not in _ids(data)
    assert _ids(data) == [polish]


def test_semantic_mode_returns_pure_cosine_order(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    semantic_only = _insert_card(tmp_db, original="dwa", translation="two")
    _build_index(tmp_db)
    fake_embedder.query_vector = _stored_vector(tmp_db, semantic_only)

    with TestClient(app) as client:
        data = client.get("/api/search", params={"q": "jeden", "mode": "semantic"}).json()

    assert _ids(data)[0] == semantic_only
    assert data["semantic"]["mode"] == "semantic"


def test_hybrid_pagination_is_consistent(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    for index in range(5):
        _insert_card(tmp_db, original=f"slow{index}", translation=f"word{index}")
    _build_index(tmp_db)

    with TestClient(app) as client:
        pages = [
            client.get("/api/search", params={"q": "slow0", "limit": 2, "page": page}).json()
            for page in range(4)
        ]
        full = client.get("/api/search", params={"q": "slow0", "limit": 100}).json()

    assert {page["total"] for page in pages} == {5}
    paged = [item["id"] for page in pages for item in page["items"]]
    assert paged == _ids(full)
    assert len(full["items"]) == 5
    assert pages[3]["items"] == []


def test_stale_meta_counts_cards_without_current_vector(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _insert_card(tmp_db, original="dwa", translation="two")
    _build_index(tmp_db)
    _insert_card(tmp_db, original="trzy", translation="three")

    with TestClient(app) as client:
        data = client.get("/api/search", params={"q": "jeden"}).json()

    assert data["semantic"]["stale"] == 1


def test_stale_cache_does_not_refresh_before_ttl(
    tmp_db: sqlite3.Connection, fake_embedder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _build_index(tmp_db)

    with TestClient(app) as client:
        first = client.get("/api/search", params={"q": "jeden"}).json()
        assert first["semantic"]["stale"] == 0

        _insert_card(tmp_db, original="dwa", translation="two")
        cached = client.get("/api/search", params={"q": "jeden"}).json()
        assert cached["semantic"]["stale"] == 0

        monkeypatch.setattr(semantic, "STALE_TTL", 0)
        refreshed = client.get("/api/search", params={"q": "jeden"}).json()
        assert refreshed["semantic"]["stale"] == 1


def test_matrix_cache_picks_up_new_embeddings(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    first = _insert_card(tmp_db, original="jeden", translation="one")
    _build_index(tmp_db)
    fake_embedder.query_vector = _stored_vector(tmp_db, first)

    with TestClient(app) as client:
        before = client.get("/api/search", params={"q": "jeden", "mode": "semantic"}).json()
        assert _ids(before) == [first]

        second = _insert_card(tmp_db, original="dwa", translation="two")
        _build_index(tmp_db)
        fake_embedder.query_vector = _stored_vector(tmp_db, second)

        after = client.get("/api/search", params={"q": "jeden", "mode": "semantic"}).json()

    assert _ids(after)[0] == second
    assert first in _ids(after)


def test_unavailable_degrades_to_text_with_reason(
    tmp_db: sqlite3.Connection, fake_embedder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _build_index(tmp_db)

    def unavailable():
        raise semantic.SemanticUnavailable("fastembed not installed")

    monkeypatch.setattr(semantic, "get_embedder", unavailable)

    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": "jeden"})

    expected, expected_total = db.search_cards(
        tmp_db, query="jeden", lang="", app="", limit=60, offset=0, sort="new"
    )
    data = response.json()
    assert response.status_code == 200
    assert data["semantic"] == {
        "available": False,
        "mode": "text",
        "stale": None,
        "reason": "fastembed not installed",
    }
    assert data["items"] == expected
    assert data["total"] == expected_total


def test_embedding_error_degrades_to_text_with_reason(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _build_index(tmp_db)
    fake_embedder.query_error = RuntimeError("boom")

    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": "jeden"})

    data = response.json()
    assert response.status_code == 200
    assert data["semantic"] == {
        "available": False,
        "mode": "text",
        "stale": None,
        "reason": "embedding error",
    }


def test_empty_index_degrades_with_reason(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    card = _insert_card(tmp_db, original="jeden", translation="one")

    with TestClient(app) as client:
        response = client.get("/api/search", params={"q": "jeden"})

    data = response.json()
    assert response.status_code == 200
    assert data["semantic"] == {
        "available": False,
        "mode": "text",
        "stale": None,
        "reason": "index empty",
    }
    assert _ids(data) == [card]


def test_missing_embeddings_table_degrades_to_text(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    card = _insert_card(tmp_db, original="jeden", translation="one")

    with TestClient(app) as client:
        tmp_db.execute("DROP TABLE card_embeddings")
        tmp_db.commit()
        response = client.get("/api/search", params={"q": "jeden"})

    data = response.json()
    assert response.status_code == 200
    assert data["semantic"] == {
        "available": False,
        "mode": "text",
        "stale": None,
        "reason": "index empty",
    }
    assert _ids(data) == [card]


def test_lifespan_creates_embeddings_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "fresh.db")

    with TestClient(app):
        conn = db.connect()
        try:
            names = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
        finally:
            conn.close()

    assert "card_embeddings" in names
