"""Shared fixtures for the duosave test suite."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from duosave import db
from duosave.config import EMBEDDING_DIM


class FakeEmbedder:
    """Deterministic embedder: no network, no model files, no fastembed import."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim
        self.query_calls = 0
        self.passage_calls = 0
        self.get_embedder_calls = 0
        self.query_vector: np.ndarray | None = None
        self.query_error: Exception | None = None

    def vector_for(self, text: str) -> np.ndarray:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")
        vector = np.random.default_rng(seed).random(self.dim, dtype=np.float32)
        return (vector / np.linalg.norm(vector)).astype(np.float32)

    def query_embed(self, texts: list[str]) -> Iterator[np.ndarray]:
        self.query_calls += 1
        if self.query_error is not None:
            raise self.query_error
        if self.query_vector is not None:
            return (self.query_vector for _ in texts)
        return (self.vector_for(text) for text in texts)

    def passage_embed(self, texts: list[str]) -> Iterator[np.ndarray]:
        self.passage_calls += 1
        return (self.vector_for(text) for text in texts)


@pytest.fixture
def tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[sqlite3.Connection]:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "duosave.db")
    conn = db.connect()
    db.init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def fake_embedder(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    from duosave import semantic

    fake = FakeEmbedder()

    def provider() -> FakeEmbedder:
        fake.get_embedder_calls += 1
        return fake

    monkeypatch.setattr(semantic, "get_embedder", provider)
    return fake


@pytest.fixture(autouse=True)
def reset_semantic_caches() -> None:
    from duosave import semantic

    semantic.reset_caches()
