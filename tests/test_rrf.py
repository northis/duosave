"""Hybrid search: RRF fusion, mode selection, degradation to the text path."""

from __future__ import annotations

import sqlite3

import pytest

from duosave import db, semantic
from duosave.config import SEMANTIC_CANDIDATES


def _insert_card(
    conn: sqlite3.Connection,
    *,
    original: str = "original",
    translation: str = "translation",
    language: str = "pl",
    status: str = "auto",
    app: str = "duolingo_card",
) -> int:
    return db.upsert_card(
        conn,
        language=language,
        original=original,
        translation=translation,
        kind="sentence",
        app=app,
        screen_type=None,
        status=status,
        original_folded=original.lower(),
        translation_folded=translation.lower(),
    )


def _patch_branches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    text_ids: list[int] | None = None,
    vector_ids: list[int] | None = None,
    vector_error: Exception | None = None,
) -> dict[str, list[dict]]:
    """Replace both search branches with fixed rankings and record their calls.

    ``text_ids=None`` keeps the real text search; ``vector_ids`` sets the vector branch.
    """
    calls: dict[str, list[dict]] = {"text": [], "vector": []}
    real_search = semantic.search_cards

    def fake_search(conn, query="", lang="", app="", limit=60, offset=0, sort="new"):
        calls["text"].append(
            {
                "query": query,
                "lang": lang,
                "app": app,
                "limit": limit,
                "offset": offset,
                "sort": sort,
            }
        )
        if text_ids is None:
            return real_search(
                conn, query=query, lang=lang, app=app, limit=limit, offset=offset, sort=sort
            )
        return db.get_cards_by_ids(conn, list(text_ids)), len(text_ids)

    def fake_semantic(conn, query, lang, app, limit):
        calls["vector"].append({"query": query, "lang": lang, "app": app, "limit": limit})
        if vector_error is not None:
            raise vector_error
        return [(card_id, 1.0) for card_id in (vector_ids or [])]

    monkeypatch.setattr(semantic, "search_cards", fake_search)
    monkeypatch.setattr(semantic, "semantic_search", fake_semantic)
    return calls


def test_cards_in_both_branches_rank_above_single_branch(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    both = _insert_card(tmp_db, original="both", translation="oba")
    text_only = _insert_card(tmp_db, original="text", translation="tekst")
    vector_only = _insert_card(tmp_db, original="vector", translation="wektor")
    _patch_branches(
        monkeypatch, text_ids=[both, text_only], vector_ids=[both, vector_only]
    )

    items, total, _ = semantic.hybrid_search(tmp_db, "query", "", "", 10, 0, "new", "hybrid")

    ids = [item["id"] for item in items]
    assert ids[0] == both
    assert text_only in ids
    assert vector_only in ids
    assert total == 3


def test_exact_match_ranked_first_in_both_branches_wins(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    exact = _insert_card(tmp_db, original="exact", translation="dokladny")
    other = _insert_card(tmp_db, original="other", translation="inny")
    _patch_branches(monkeypatch, text_ids=[exact, other], vector_ids=[exact, other])

    items, _, _ = semantic.hybrid_search(tmp_db, "query", "", "", 10, 0, "new", "hybrid")

    assert [item["id"] for item in items] == [exact, other]


def test_ties_break_by_text_rank_then_id_desc(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    better_text_rank = _insert_card(tmp_db, original="first", translation="pierwszy")
    larger_id = _insert_card(tmp_db, original="second", translation="drugi")
    assert larger_id > better_text_rank
    _patch_branches(
        monkeypatch,
        text_ids=[better_text_rank, larger_id],
        vector_ids=[larger_id, better_text_rank],
    )

    items, _, _ = semantic.hybrid_search(tmp_db, "query", "", "", 10, 0, "new", "hybrid")

    assert [item["id"] for item in items] == [better_text_rank, larger_id]


def test_duplicate_ids_are_fused_once(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = _insert_card(tmp_db, original="shared", translation="wspolny")
    text_only = _insert_card(tmp_db, original="text", translation="tekst")
    _patch_branches(monkeypatch, text_ids=[shared, text_only], vector_ids=[shared])

    items, total, _ = semantic.hybrid_search(tmp_db, "query", "", "", 10, 0, "new", "hybrid")

    ids = [item["id"] for item in items]
    assert ids.count(shared) == 1
    assert len(ids) == len(set(ids))
    assert total == 2


def test_page_slice_and_total_follow_fused_order(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _insert_card(tmp_db, original="first", translation="pierwszy")
    second = _insert_card(tmp_db, original="second", translation="drugi")
    third = _insert_card(tmp_db, original="third", translation="trzeci")
    fourth = _insert_card(tmp_db, original="fourth", translation="czwarty")
    _patch_branches(monkeypatch, text_ids=[first, second, third, fourth], vector_ids=[first])

    items, total, _ = semantic.hybrid_search(tmp_db, "query", "", "", 2, 1, "new", "hybrid")

    assert [item["id"] for item in items] == [second, third]
    assert total == 4

    empty, empty_total, _ = semantic.hybrid_search(tmp_db, "query", "", "", 2, 10, "new", "hybrid")
    assert empty == []
    assert empty_total == 4


def test_semantic_mode_skips_text_branch(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _insert_card(tmp_db, original="first", translation="pierwszy")
    second = _insert_card(tmp_db, original="second", translation="drugi")
    calls = _patch_branches(monkeypatch, text_ids=[first], vector_ids=[second, first])

    items, total, meta = semantic.hybrid_search(tmp_db, "query", "", "", 10, 0, "new", "semantic")

    assert calls["text"] == []
    assert [item["id"] for item in items] == [second, first]
    assert total == 2
    assert meta["available"] is True
    assert meta["mode"] == "semantic"
    assert meta["reason"] is None


def test_empty_query_skips_semantic_and_keeps_sort(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _insert_card(tmp_db, original="dwa", translation="two")
    calls = _patch_branches(monkeypatch)

    items, total, meta = semantic.hybrid_search(tmp_db, "", "", "", 10, 0, "new", "hybrid")
    expected, expected_total = db.search_cards(
        tmp_db, query="", lang="", app="", limit=10, offset=0, sort="new"
    )

    assert calls["vector"] == []
    assert items == expected
    assert total == expected_total
    assert meta == {"available": True, "mode": "text", "stale": 2, "reason": None}

    items_old, _, _ = semantic.hybrid_search(tmp_db, "", "", "", 10, 0, "old", "hybrid")
    assert calls["text"][-1]["sort"] == "old"
    assert items_old == db.search_cards(
        tmp_db, query="", lang="", app="", limit=10, offset=0, sort="old"
    )[0]


def test_text_mode_skips_semantic(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _insert_card(tmp_db, original="dwa", translation="two")
    calls = _patch_branches(monkeypatch, vector_ids=[1])

    items, total, meta = semantic.hybrid_search(tmp_db, "jeden", "", "", 10, 0, "new", "text")
    expected, expected_total = db.search_cards(
        tmp_db, query="jeden", lang="", app="", limit=10, offset=0, sort="new"
    )

    assert calls["vector"] == []
    assert items == expected
    assert total == expected_total
    assert meta == {"available": True, "mode": "text", "stale": 2, "reason": None}


def test_hybrid_candidate_branch_ignores_requested_sort(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = _insert_card(tmp_db, original="jeden", translation="one")
    calls = _patch_branches(monkeypatch, text_ids=[card], vector_ids=[card])

    semantic.hybrid_search(tmp_db, "query", "pl", "drops", 5, 0, "old", "hybrid")

    assert calls["text"][0] == {
        "query": "query",
        "lang": "pl",
        "app": "drops",
        "limit": SEMANTIC_CANDIDATES,
        "offset": 0,
        "sort": "new",
    }
    assert calls["vector"][0]["limit"] == SEMANTIC_CANDIDATES


def test_unavailable_semantic_falls_back_to_text(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _insert_card(tmp_db, original="dwa", translation="two")
    calls = _patch_branches(
        monkeypatch, vector_error=semantic.SemanticUnavailable("index empty")
    )

    items, total, meta = semantic.hybrid_search(tmp_db, "jeden", "", "", 10, 0, "new", "hybrid")
    expected, expected_total = db.search_cards(
        tmp_db, query="jeden", lang="", app="", limit=10, offset=0, sort="new"
    )

    assert items == expected
    assert total == expected_total
    assert meta == {"available": False, "mode": "text", "stale": None, "reason": "index empty"}
    assert calls["text"][-1]["limit"] == 10
    assert calls["text"][-1]["offset"] == 0
    assert calls["text"][-1]["sort"] == "new"


def test_embedding_error_falls_back_to_text(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    calls = _patch_branches(monkeypatch, vector_error=RuntimeError("boom"))

    items, total, meta = semantic.hybrid_search(tmp_db, "jeden", "", "", 10, 0, "new", "hybrid")

    assert items == db.search_cards(
        tmp_db, query="jeden", lang="", app="", limit=10, offset=0, sort="new"
    )[0]
    assert total == 1
    assert meta == {"available": False, "mode": "text", "stale": None, "reason": "embedding error"}
    assert calls["text"][-1]["sort"] == "new"
