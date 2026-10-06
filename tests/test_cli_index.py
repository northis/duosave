"""CLI indexing: `duosave index`, `sync --index`, stats output and exit codes."""

from __future__ import annotations

import sqlite3

import pytest

from duosave import db, semantic
from duosave.cli import build_parser
from duosave.config import EMBEDDING_MODEL
from duosave.sync import sync


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


def _embedded_card_ids(conn: sqlite3.Connection) -> set[int]:
    return {int(row["card_id"]) for row in db.load_embeddings(conn, EMBEDDING_MODEL)}


def _unavailable_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable():
        raise semantic.SemanticUnavailable("fastembed not installed")

    monkeypatch.setattr(semantic, "get_embedder", unavailable)


def test_index_embeds_cards_and_returns_zero(
    tmp_db: sqlite3.Connection, fake_embedder, capsys: pytest.CaptureFixture[str]
) -> None:
    kept = _insert_card(tmp_db, original="jeden", translation="one")
    _insert_card(tmp_db, original="dwa", translation="two", status="rejected")

    args = build_parser().parse_args(["index"])
    assert args.func(args) == 0

    assert _embedded_card_ids(tmp_db) == {kept}
    output = capsys.readouterr().out
    for key in ("added", "updated", "removed", "unchanged", "elapsed"):
        assert key in output


def test_index_full_reembeds_everything(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")
    args = build_parser().parse_args(["index"])
    assert args.func(args) == 0
    passage_calls = fake_embedder.passage_calls

    args = build_parser().parse_args(["index", "--full"])
    assert args.func(args) == 0

    assert fake_embedder.passage_calls > passage_calls


def test_index_returns_two_when_embedder_unavailable(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _unavailable_embedder(monkeypatch)

    args = build_parser().parse_args(["index"])
    assert args.func(args) == 2

    assert _embedded_card_ids(tmp_db) == set()
    assert "fastembed not installed" in capsys.readouterr().out


def test_sync_index_adds_index_stats_to_result(
    tmp_db: sqlite3.Connection, fake_embedder
) -> None:
    _insert_card(tmp_db, original="jeden", translation="one")

    result = sync(folders=["no_such_dir"], index=True, quiet=True)

    assert result["index_added"] == 1
    assert result["index_updated"] == 0
    assert result["index_removed"] == 0
    assert result["index_unchanged"] == 0
    assert isinstance(result["index_elapsed"], float)


def test_sync_index_unavailable_returns_two(
    tmp_db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _unavailable_embedder(monkeypatch)

    args = build_parser().parse_args(["sync", "--index", "--folders", "no_such_dir", "--quiet"])
    assert args.func(args) == 2

    assert _embedded_card_ids(tmp_db) == set()
    assert "fastembed not installed" in capsys.readouterr().out
