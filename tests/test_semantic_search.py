"""Vector search: cosine ranking, pre-filters, matrix cache, stale statistics."""

from __future__ import annotations

import sqlite3

import numpy as np
import pytest

from duosave import db, semantic
from duosave.config import EMBEDDING_DIM, EMBEDDING_MODEL


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


def _stored_vector(conn: sqlite3.Connection, card_id: int) -> np.ndarray:
    row = conn.execute(
        "SELECT vector FROM card_embeddings WHERE card_id = ?", (card_id,)
    ).fetchone()
    return np.frombuffer(row["vector"], dtype="<f4").copy()


def _upsert_vector(conn: sqlite3.Connection, fake_embedder, card_id: int, text: str,
                   model: str = "other-model") -> None:
    db.upsert_embedding(
        conn,
        card_id=card_id,
        model=model,
        dim=EMBEDDING_DIM,
        vector=fake_embedder.vector_for(text).astype("<f4").tobytes(),
        text_hash=f"{model}-hash",
    )


def test_results_ranked_by_cosine(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    second = _insert_card(tmp_db, original="dwa", translation="two")
    semantic.reindex(tmp_db)

    fake_embedder.query_vector = _stored_vector(tmp_db, second)

    results = semantic.semantic_search(tmp_db, "dwa", "", "", 10)

    assert results[0][0] == second
    assert results[0][1] == pytest.approx(1.0, abs=1e-4)


def test_prefilter_excludes_rejected_and_foreign_language(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    polish = _insert_card(tmp_db, original="jeden", translation="one", language="pl")
    spanish = _insert_card(tmp_db, original="uno", translation="one", language="es")
    rejected = _insert_card(
        tmp_db, original="trzy", translation="three", language="pl", status="rejected"
    )
    semantic.reindex(tmp_db)
    # a rejected card may still carry a stale vector; the live status must win
    _upsert_vector(tmp_db, fake_embedder, rejected, "trzy\nthree", model=EMBEDDING_MODEL)
    tmp_db.commit()

    results = semantic.semantic_search(tmp_db, "one", "pl", "", 10)

    ids = [card_id for card_id, _ in results]
    assert polish in ids
    assert spanish not in ids
    assert rejected not in ids


def test_prefilter_maps_duolingo_group_and_exact_app(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    duolingo_card = _insert_card(
        tmp_db, original="jeden", translation="one", app="duolingo_card"
    )
    duolingo_app = _insert_card(
        tmp_db, original="dwa", translation="two", app="duolingo_app"
    )
    drops = _insert_card(tmp_db, original="trzy", translation="three", app="drops")
    semantic.reindex(tmp_db)

    def search(app: str) -> list[int]:
        return [
            card_id
            for card_id, _ in semantic.semantic_search(tmp_db, "query", "", app, 10)
        ]

    duolingo = search("duolingo")
    assert duolingo_card in duolingo
    assert duolingo_app in duolingo
    assert drops not in duolingo

    assert search("drops") == [drops]
    assert set(search("")) == {duolingo_card, duolingo_app, drops}


def test_limit_caps_results(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    for index in range(3):
        _insert_card(tmp_db, original=f"slow{index}", translation=f"word{index}")
    semantic.reindex(tmp_db)

    results = semantic.semantic_search(tmp_db, "query", "", "", 2)

    assert len(results) == 2


def test_empty_index_raises_unavailable(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    with pytest.raises(semantic.SemanticUnavailable) as excinfo:
        semantic.semantic_search(tmp_db, "query", "", "", 10)

    assert excinfo.value.reason == "index empty"


def test_missing_table_raises_unavailable(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    tmp_db.execute("DROP TABLE card_embeddings")
    tmp_db.commit()

    with pytest.raises(semantic.SemanticUnavailable) as excinfo:
        semantic.semantic_search(tmp_db, "query", "", "", 10)

    assert excinfo.value.reason == "index empty"


def test_foreign_model_rows_are_ignored(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    current = _insert_card(tmp_db, original="jeden", translation="one")
    semantic.reindex(tmp_db)
    foreign = _insert_card(tmp_db, original="dwa", translation="two")
    _upsert_vector(tmp_db, fake_embedder, foreign, "dwa\ntwo")
    tmp_db.commit()

    results = semantic.semantic_search(tmp_db, "query", "", "", 10)

    ids = [card_id for card_id, _ in results]
    assert current in ids
    assert foreign not in ids


def test_foreign_model_only_raises_unavailable(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    card = _insert_card(tmp_db, original="jeden", translation="one")
    _upsert_vector(tmp_db, fake_embedder, card, "jeden\none")
    tmp_db.commit()

    with pytest.raises(semantic.SemanticUnavailable) as excinfo:
        semantic.semantic_search(tmp_db, "query", "", "", 10)

    assert excinfo.value.reason == "index empty"


def test_matrix_cache_reloads_only_after_stats_change(
    tmp_db: sqlite3.Connection, fake_embedder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    semantic.reindex(tmp_db)

    loads: list[str] = []
    original_load = semantic.load_embeddings

    def counting_load(conn, model):
        loads.append(model)
        return original_load(conn, model)

    monkeypatch.setattr(semantic, "load_embeddings", counting_load)

    semantic.semantic_search(tmp_db, "query", "", "", 10)
    assert len(loads) == 1

    semantic.semantic_search(tmp_db, "query", "", "", 10)
    assert len(loads) == 1

    _insert_card(tmp_db, original="dwa", translation="two")
    semantic.reindex(tmp_db)

    semantic.semantic_search(tmp_db, "query", "", "", 10)
    assert len(loads) == 2


def test_query_embed_error_raises_embedding_error(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    semantic.reindex(tmp_db)
    fake_embedder.query_error = RuntimeError("boom")

    with pytest.raises(semantic.SemanticUnavailable) as excinfo:
        semantic.semantic_search(tmp_db, "query", "", "", 10)

    assert excinfo.value.reason == "embedding error"


def test_index_stats_reports_indexed_stale_model(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    stale = _insert_card(tmp_db, original="dwa", translation="two")
    _insert_card(tmp_db, original="trzy", translation="three", status="rejected")
    foreign = _insert_card(tmp_db, original="cztery", translation="four")
    semantic.reindex(tmp_db)

    db.update_card(tmp_db, stale, original="dwa2", translation="two2")
    db.delete_embeddings(tmp_db, [foreign])
    _upsert_vector(tmp_db, fake_embedder, foreign, "cztery\nfour")
    tmp_db.commit()

    stats = semantic.index_stats(tmp_db)

    assert set(stats) == {"indexed", "stale", "model"}
    assert stats["model"] == EMBEDDING_MODEL
    assert stats["indexed"] == 2
    assert stats["stale"] == 2


def test_index_stats_caches_stale_until_ttl(
    tmp_db: sqlite3.Connection, fake_embedder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    semantic.reindex(tmp_db)

    assert semantic.index_stats(tmp_db)["stale"] == 0

    _insert_card(tmp_db, original="dwa", translation="two")
    tmp_db.commit()

    assert semantic.index_stats(tmp_db)["stale"] == 0

    monkeypatch.setattr(semantic, "STALE_TTL", 0)

    assert semantic.index_stats(tmp_db)["stale"] == 1
