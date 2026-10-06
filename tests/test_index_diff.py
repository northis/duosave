"""Diff indexing: added/updated/removed/unchanged, full rebuild, failure modes."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import types
from pathlib import Path

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


def _embedding_rows(conn: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    return {int(row["card_id"]): row for row in db.load_embeddings(conn, EMBEDDING_MODEL)}


def test_new_cards_are_added(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    first = _insert_card(tmp_db, original="jeden", translation="one", language="unk", status="review")
    second = _insert_card(tmp_db, original="dwa", translation="two", language="pl", status="auto")

    result = semantic.reindex(tmp_db)

    assert set(result) == {"added", "updated", "removed", "unchanged", "elapsed"}
    assert result["added"] == 2
    assert result["updated"] == 0
    assert result["removed"] == 0
    assert result["unchanged"] == 0
    assert isinstance(result["elapsed"], float)

    rows = _embedding_rows(tmp_db)
    assert set(rows) == {first, second}
    assert rows[first]["text_hash"] == semantic.text_hash("jeden", "one")
    assert rows[second]["text_hash"] == semantic.text_hash("dwa", "two")
    assert fake_embedder.passage_calls == 1


def test_second_run_is_unchanged(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _insert_card(tmp_db, original="dwa", translation="two")
    semantic.reindex(tmp_db)
    passage_calls = fake_embedder.passage_calls
    get_embedder_calls = fake_embedder.get_embedder_calls

    result = semantic.reindex(tmp_db)

    assert result["added"] == 0
    assert result["updated"] == 0
    assert result["removed"] == 0
    assert result["unchanged"] == 2
    assert fake_embedder.passage_calls == passage_calls
    assert fake_embedder.get_embedder_calls == get_embedder_calls + 1


def test_changed_text_is_updated(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    card_id = _insert_card(tmp_db, original="jeden", translation="one")
    semantic.reindex(tmp_db)

    db.update_card(tmp_db, card_id, original="dwa", translation="two")
    tmp_db.commit()

    result = semantic.reindex(tmp_db)

    assert result["added"] == 0
    assert result["updated"] == 1
    assert result["removed"] == 0
    assert result["unchanged"] == 0
    assert _embedding_rows(tmp_db)[card_id]["text_hash"] == semantic.text_hash("dwa", "two")


def test_language_or_status_change_without_text_is_unchanged(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    card_id = _insert_card(tmp_db, original="jeden", translation="one", language="pl", status="auto")
    semantic.reindex(tmp_db)
    passage_calls = fake_embedder.passage_calls

    db.update_card(tmp_db, card_id, language="es", status="review")
    tmp_db.commit()

    result = semantic.reindex(tmp_db)

    assert result["added"] == 0
    assert result["updated"] == 0
    assert result["removed"] == 0
    assert result["unchanged"] == 1
    assert fake_embedder.passage_calls == passage_calls


def test_rejected_card_is_removed(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    card_id = _insert_card(tmp_db, original="jeden", translation="one")
    semantic.reindex(tmp_db)

    db.update_card(tmp_db, card_id, status="rejected")
    tmp_db.commit()

    result = semantic.reindex(tmp_db)

    assert result["added"] == 0
    assert result["updated"] == 0
    assert result["removed"] == 1
    assert result["unchanged"] == 0
    assert _embedding_rows(tmp_db) == {}


def test_deleted_card_embedding_is_cascaded(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    card_id = _insert_card(tmp_db, original="jeden", translation="one")
    semantic.reindex(tmp_db)

    tmp_db.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    tmp_db.commit()
    assert _embedding_rows(tmp_db) == {}

    result = semantic.reindex(tmp_db)

    assert result["added"] == 0
    assert result["updated"] == 0
    assert result["removed"] == 0
    assert result["unchanged"] == 0


def test_full_reembeds_unchanged_cards(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    _insert_card(tmp_db, original="dwa", translation="two")
    semantic.reindex(tmp_db)
    passage_calls = fake_embedder.passage_calls

    result = semantic.reindex(tmp_db, full=True)

    assert result["added"] == 0
    assert result["updated"] == 2
    assert result["removed"] == 0
    assert result["unchanged"] == 0
    assert fake_embedder.passage_calls == passage_calls + 1
    assert len(_embedding_rows(tmp_db)) == 2


def test_foreign_model_row_is_reembedded(tmp_db: sqlite3.Connection, fake_embedder) -> None:
    card_id = _insert_card(tmp_db, original="jeden", translation="one")
    db.upsert_embedding(
        tmp_db,
        card_id=card_id,
        model="other-model",
        dim=EMBEDDING_DIM,
        vector=np.zeros(EMBEDDING_DIM, dtype=np.float32).tobytes(),
        text_hash="foreign-hash",
    )
    tmp_db.commit()

    result = semantic.reindex(tmp_db)

    assert result["added"] == 1
    assert result["updated"] == 0
    assert result["removed"] == 1
    assert result["unchanged"] == 0
    row = _embedding_rows(tmp_db)[card_id]
    assert row["model"] == EMBEDDING_MODEL
    assert row["text_hash"] == semantic.text_hash("jeden", "one")


def test_unavailable_embedder_leaves_db_untouched(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")

    def unavailable():
        raise semantic.SemanticUnavailable("fastembed not installed")

    monkeypatch.setattr(semantic, "get_embedder", unavailable)

    with pytest.raises(semantic.SemanticUnavailable) as excinfo:
        semantic.reindex(tmp_db)

    assert excinfo.value.reason == "fastembed not installed"
    assert tmp_db.execute("SELECT COUNT(*) FROM card_embeddings").fetchone()[0] == 0


def test_get_embedder_reports_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "fastembed", None)

    with pytest.raises(semantic.SemanticUnavailable) as excinfo:
        semantic.get_embedder()

    assert excinfo.value.reason == "fastembed not installed"


def test_get_embedder_reports_model_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = types.ModuleType("fastembed")

    class _FailingTextEmbedding:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("model files missing")

    stub.TextEmbedding = _FailingTextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", stub)

    with pytest.raises(semantic.SemanticUnavailable) as excinfo:
        semantic.get_embedder()

    assert excinfo.value.reason == "model not downloaded"


def test_module_import_does_not_import_fastembed() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    code = "import duosave.semantic, sys; assert 'fastembed' not in sys.modules"
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
