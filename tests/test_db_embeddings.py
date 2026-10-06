"""card_embeddings storage: roundtrip, upsert/delete, stats, ordered card fetch."""

from __future__ import annotations

import sqlite3

import numpy as np

from duosave import db
from duosave.config import EMBEDDING_DIM, EMBEDDING_MODEL


def _insert_card(
    conn: sqlite3.Connection,
    *,
    original: str = "original",
    translation: str = "translation",
    language: str = "pl",
    status: str = "auto",
) -> int:
    return db.upsert_card(
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


def _vector(seed: int, dim: int = EMBEDDING_DIM) -> np.ndarray:
    return np.random.default_rng(seed).random(dim, dtype=np.float32)


def test_embedding_roundtrip_preserves_float32_vector(tmp_db: sqlite3.Connection) -> None:
    card_id = _insert_card(tmp_db)
    vector = _vector(7)

    db.upsert_embedding(
        tmp_db,
        card_id=card_id,
        model=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        vector=vector.tobytes(),
        text_hash="hash-1",
    )

    rows = db.load_embeddings(tmp_db, EMBEDDING_MODEL)
    assert len(rows) == 1
    row = rows[0]
    assert row["card_id"] == card_id
    assert row["model"] == EMBEDDING_MODEL
    assert row["dim"] == EMBEDDING_DIM
    assert row["text_hash"] == "hash-1"

    restored = np.frombuffer(row["vector"], dtype="<f4")
    assert restored.dtype == np.float32
    assert np.array_equal(restored, vector)


def test_upsert_embedding_replaces_existing_row(tmp_db: sqlite3.Connection) -> None:
    card_id = _insert_card(tmp_db)
    old_updated_at = "2020-01-01T00:00:00+00:00"

    db.upsert_embedding(
        tmp_db,
        card_id=card_id,
        model="old-model",
        dim=128,
        vector=_vector(1, dim=128).tobytes(),
        text_hash="old-hash",
    )
    tmp_db.execute(
        "UPDATE card_embeddings SET updated_at = ? WHERE card_id = ?",
        (old_updated_at, card_id),
    )
    tmp_db.commit()

    new_vector = _vector(2)
    db.upsert_embedding(
        tmp_db,
        card_id=card_id,
        model=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        vector=new_vector.tobytes(),
        text_hash="new-hash",
    )
    tmp_db.commit()

    rows = tmp_db.execute("SELECT * FROM card_embeddings").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["card_id"] == card_id
    assert row["model"] == EMBEDDING_MODEL
    assert row["dim"] == EMBEDDING_DIM
    assert bytes(row["vector"]) == new_vector.tobytes()
    assert row["text_hash"] == "new-hash"
    assert row["updated_at"] != old_updated_at


def test_load_embeddings_returns_only_requested_model(tmp_db: sqlite3.Connection) -> None:
    current = _insert_card(tmp_db, original="alpha")
    foreign = _insert_card(tmp_db, original="beta")

    db.upsert_embedding(
        tmp_db,
        card_id=current,
        model=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        vector=_vector(1).tobytes(),
        text_hash="hash-current",
    )
    db.upsert_embedding(
        tmp_db,
        card_id=foreign,
        model="other-model",
        dim=EMBEDDING_DIM,
        vector=_vector(2).tobytes(),
        text_hash="hash-foreign",
    )

    rows = db.load_embeddings(tmp_db, EMBEDDING_MODEL)
    assert [row["card_id"] for row in rows] == [current]


def test_delete_embeddings_returns_removed_count(tmp_db: sqlite3.Connection) -> None:
    ids = [_insert_card(tmp_db, original=f"card-{n}") for n in range(3)]
    for n, card_id in enumerate(ids):
        db.upsert_embedding(
            tmp_db,
            card_id=card_id,
            model=EMBEDDING_MODEL,
            dim=EMBEDDING_DIM,
            vector=_vector(n).tobytes(),
            text_hash=f"hash-{n}",
        )

    removed = db.delete_embeddings(tmp_db, [ids[0], ids[2]])
    assert removed == 2
    remaining = db.load_embeddings(tmp_db, EMBEDDING_MODEL)
    assert [row["card_id"] for row in remaining] == [ids[1]]


def test_delete_embeddings_accepts_empty_list(tmp_db: sqlite3.Connection) -> None:
    card_id = _insert_card(tmp_db)
    db.upsert_embedding(
        tmp_db,
        card_id=card_id,
        model=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        vector=_vector(1).tobytes(),
        text_hash="hash",
    )

    assert db.delete_embeddings(tmp_db, []) == 0
    assert len(db.load_embeddings(tmp_db, EMBEDDING_MODEL)) == 1


def test_embedding_index_stats_reports_count_and_max_updated_at(tmp_db: sqlite3.Connection) -> None:
    assert db.embedding_index_stats(tmp_db) == (0, None)

    first = _insert_card(tmp_db, original="first")
    second = _insert_card(tmp_db, original="second")
    db.upsert_embedding(
        tmp_db,
        card_id=first,
        model=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        vector=_vector(1).tobytes(),
        text_hash="hash-1",
    )
    db.upsert_embedding(
        tmp_db,
        card_id=second,
        model=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        vector=_vector(2).tobytes(),
        text_hash="hash-2",
    )
    tmp_db.execute(
        "UPDATE card_embeddings SET updated_at = '2020-01-01T00:00:00+00:00' WHERE card_id = ?",
        (first,),
    )
    tmp_db.execute(
        "UPDATE card_embeddings SET updated_at = '2021-02-03T04:05:06+00:00' WHERE card_id = ?",
        (second,),
    )
    tmp_db.commit()

    assert db.embedding_index_stats(tmp_db) == (2, "2021-02-03T04:05:06+00:00")


def test_get_cards_by_ids_preserves_requested_order(tmp_db: sqlite3.Connection) -> None:
    first = _insert_card(tmp_db, original="alpha")
    second = _insert_card(tmp_db, original="beta")
    third = _insert_card(tmp_db, original="gamma")

    cards = db.get_cards_by_ids(tmp_db, [third, first, second])
    assert [card["id"] for card in cards] == [third, first, second]


def test_get_cards_by_ids_computed_fields_match_search(tmp_db: sqlite3.Connection) -> None:
    first = _insert_card(tmp_db, original="alpha")
    second = _insert_card(tmp_db, original="beta")
    db.set_file(tmp_db, path="a.png", sha256="sha-a", size=10, mtime=1.0,
                status="done", created_ts=111)
    db.set_file(tmp_db, path="b.png", sha256="sha-b", size=20, mtime=2.0,
                status="done", created_ts=222)
    db.add_source(tmp_db, card_id=first, path="a.png", sha256="sha-a", app="duolingo_card",
                  screen_type=None, crop_path=None, agreement=None)
    db.add_source(tmp_db, card_id=first, path="b.png", sha256="sha-b", app="duolingo_card",
                  screen_type=None, crop_path=None, agreement=None)
    tmp_db.commit()

    items, _ = db.search_cards(tmp_db, limit=10)
    expected = {item["id"]: item for item in items}

    cards = db.get_cards_by_ids(tmp_db, [second, first])
    assert [card["id"] for card in cards] == [second, first]
    for card in cards:
        reference = expected[card["id"]]
        assert card["card_time"] == reference["card_time"]
        assert card["source_count"] == reference["source_count"]


def test_deleting_card_cascades_to_embedding(tmp_db: sqlite3.Connection) -> None:
    card_id = _insert_card(tmp_db)
    db.upsert_embedding(
        tmp_db,
        card_id=card_id,
        model=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        vector=_vector(1).tobytes(),
        text_hash="hash",
    )
    tmp_db.commit()

    tmp_db.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    tmp_db.commit()

    assert db.load_embeddings(tmp_db, EMBEDDING_MODEL) == []
