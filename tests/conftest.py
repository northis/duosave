"""Shared fixtures for the duosave test suite."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from duosave import db
from duosave.config import EMBEDDING_DIM
from duosave.recognize import Recognition


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


class FakeVision:
    """Deterministic vision recognizer: no network, no model, no HTTP call."""

    def __init__(self) -> None:
        self.available = True
        self.calls = 0
        self.media_types: list[str] = []
        self.result = Recognition()
        self.error: Exception | None = None


@pytest.fixture
def fake_vision(monkeypatch: pytest.MonkeyPatch) -> FakeVision:
    from duosave import vision

    fake = FakeVision()

    def available() -> bool:
        return fake.available

    async def recognize_bytes(data: bytes, media_type: str) -> Recognition:
        fake.calls += 1
        fake.media_types.append(media_type)
        if fake.error is not None:
            raise fake.error
        return fake.result

    monkeypatch.setattr(vision, "available", available)
    monkeypatch.setattr(vision, "recognize_bytes", recognize_bytes)
    return fake


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


@pytest.fixture
def tmp_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[SimpleNamespace]:
    """Temporary repository tree (pictures/, screens/, data/*) with an initialized DB.

    Paths are patched on the `config` module, so modules that read `config.X` at
    call time follow the fixture; `db` keeps its own copies of DB_PATH/DATA_DIR.
    """
    from duosave import config

    root = tmp_path / "repo"
    data = root / "data"
    pictures = root / "pictures"
    screens = root / "screens"
    (data / "media" / "drops").mkdir(parents=True)
    (data / "wordlists").mkdir(parents=True)
    pictures.mkdir()
    screens.mkdir()
    monkeypatch.setattr(config, "REPO", root)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MEDIA_DIR", data / "media")
    monkeypatch.setattr(config, "DROPS_MEDIA_DIR", data / "media" / "drops")
    monkeypatch.setattr(config, "PATCHES_DIR", data / "patches")
    monkeypatch.setattr(config, "BACKUPS_DIR", data / "backups")
    monkeypatch.setattr(config, "INBOX_DIR", root / "inbox")
    monkeypatch.setattr(config, "OUTBOX_DIR", root / "outbox")
    monkeypatch.setattr(db, "DB_PATH", data / "duosave.db")
    monkeypatch.setattr(db, "DATA_DIR", data)
    conn = db.connect()
    db.init_db(conn)
    try:
        yield SimpleNamespace(
            root=root, data=data, pictures=pictures, screens=screens, conn=conn
        )
    finally:
        conn.close()


@pytest.fixture
def client() -> TestClient:
    """Public listener: TestClient's default scope server is ("testserver", 80)."""
    from duosave.server.app import app

    return TestClient(app)


@pytest.fixture
def admin_client() -> TestClient:
    """Admin listener: base_url puts the admin port into scope["server"]."""
    from duosave import config
    from duosave.server.app import app

    return TestClient(app, base_url=f"http://127.0.0.1:{config.ADMIN_PORT}")
