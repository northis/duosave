"""Local semantic search: embedding model, document text, diff indexing."""

from __future__ import annotations

import hashlib
import sqlite3
import time

import numpy as np

from .config import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    MODEL_CACHE_DIR,
    RRF_K,
    SEMANTIC_CANDIDATES,
)
from .db import (
    delete_embeddings,
    embedding_index_stats,
    get_cards_by_ids,
    load_embeddings,
    search_cards,
    upsert_embedding,
)

EMBED_BATCH_SIZE = 256
STALE_TTL = 60

_embedder = None
_matrix_key: tuple[int, str | None] | None = None
_matrix_ids: np.ndarray | None = None
_matrix: np.ndarray | None = None
_stale_at: float | None = None
_stale_value: int | None = None


class SemanticUnavailable(Exception):
    """Semantic path cannot run; callers fall back to text search."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def doc_text(original: str, translation: str) -> str:
    return f"{original}\n{translation}"


def text_hash(original: str, translation: str) -> str:
    payload = f"{EMBEDDING_VERSION}|{EMBEDDING_MODEL}|{doc_text(original, translation)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def get_embedder():
    """Load the fastembed model lazily and cache it for the process lifetime."""
    global _embedder
    if _embedder is not None:
        return _embedder
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise SemanticUnavailable("fastembed not installed") from exc
    try:
        _embedder = TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=MODEL_CACHE_DIR)
    except Exception as exc:
        raise SemanticUnavailable("model not downloaded") from exc
    return _embedder


def _normalized_blob(vector: np.ndarray) -> bytes:
    normalized = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(normalized))
    if norm > 0:
        normalized = normalized / norm
    return normalized.astype("<f4").tobytes()


def reindex(conn: sqlite3.Connection, full: bool = False) -> dict:
    """Embed missing/changed/stale cards and drop embeddings that no longer apply."""
    started = time.monotonic()
    embedder = get_embedder()

    card_rows = conn.execute(
        "SELECT id, original, translation FROM cards WHERE status != 'rejected'"
    ).fetchall()
    cards = {int(row["id"]): (row["original"], row["translation"]) for row in card_rows}

    stored = {
        int(row["card_id"]): row
        for row in conn.execute("SELECT card_id, model, text_hash FROM card_embeddings")
    }

    to_embed: list[tuple[int, str, str]] = []
    to_delete: list[int] = []
    added = 0
    updated = 0
    for card_id, (original, translation) in cards.items():
        row = stored.get(card_id)
        if row is not None and row["model"] != EMBEDDING_MODEL:
            to_delete.append(card_id)
            row = None
        if row is None:
            to_embed.append((card_id, original, translation))
            added += 1
        elif full or row["text_hash"] != text_hash(original, translation):
            to_embed.append((card_id, original, translation))
            updated += 1
    for card_id in stored:
        if card_id not in cards:
            to_delete.append(card_id)

    removed = 0
    if to_delete:
        removed = delete_embeddings(conn, to_delete)
        conn.commit()

    for start in range(0, len(to_embed), EMBED_BATCH_SIZE):
        batch = to_embed[start:start + EMBED_BATCH_SIZE]
        vectors = embedder.passage_embed([doc_text(original, translation) for _, original, translation in batch])
        for (card_id, original, translation), vector in zip(batch, vectors):
            upsert_embedding(
                conn,
                card_id=card_id,
                model=EMBEDDING_MODEL,
                dim=EMBEDDING_DIM,
                vector=_normalized_blob(vector),
                text_hash=text_hash(original, translation),
            )
        conn.commit()

    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "unchanged": len(cards) - len(to_embed),
        "elapsed": round(time.monotonic() - started, 1),
    }


def reset_caches() -> None:
    """Drop the process-wide vector matrix and stale-count caches."""
    global _matrix_key, _matrix_ids, _matrix, _stale_at, _stale_value
    _matrix_key = None
    _matrix_ids = None
    _matrix = None
    _stale_at = None
    _stale_value = None


def semantic_search(
    conn: sqlite3.Connection, query: str, lang: str, app: str, limit: int
) -> list[tuple[int, float]]:
    """Rank non-rejected cards by cosine similarity to the query text."""
    global _matrix_key, _matrix_ids, _matrix

    try:
        key = embedding_index_stats(conn)
    except sqlite3.OperationalError as exc:
        raise SemanticUnavailable("index empty") from exc

    if key != _matrix_key:
        rows = load_embeddings(conn, EMBEDDING_MODEL)
        if not rows:
            raise SemanticUnavailable("index empty")
        _matrix_ids = np.array([int(row["card_id"]) for row in rows], dtype=np.int64)
        _matrix = np.vstack([np.frombuffer(row["vector"], dtype="<f4") for row in rows])
        _matrix_key = key

    try:
        query_vector = next(iter(get_embedder().query_embed([query])))
    except SemanticUnavailable:
        raise
    except Exception as exc:
        raise SemanticUnavailable("embedding error") from exc
    query_vector = np.asarray(query_vector, dtype=np.float32)
    norm = float(np.linalg.norm(query_vector))
    if norm > 0:
        query_vector = query_vector / norm

    clauses = ["status != 'rejected'"]
    params: list[str] = []
    if lang:
        clauses.append("language = ?")
        params.append(lang)
    if app == "duolingo":
        clauses.append("app IN ('duolingo_card', 'duolingo_app')")
    elif app:
        clauses.append("app = ?")
        params.append(app)
    allowed = {
        int(row["id"])
        for row in conn.execute(f"SELECT id FROM cards WHERE {' AND '.join(clauses)}", params)
    }

    mask = np.array([int(card_id) in allowed for card_id in _matrix_ids], dtype=bool)
    scores = _matrix[mask] @ query_vector
    ids = _matrix_ids[mask]
    order = np.lexsort((-ids, -scores))[:limit]
    return [(int(ids[index]), float(scores[index])) for index in order]


def index_stats(conn: sqlite3.Connection) -> dict:
    """Report how many current-model vectors exist and how many cards lag behind."""
    global _stale_at, _stale_value

    indexed = int(
        conn.execute(
            "SELECT COUNT(*) FROM card_embeddings WHERE model = ?", (EMBEDDING_MODEL,)
        ).fetchone()[0]
    )

    now = time.monotonic()
    if _stale_at is None or now - _stale_at >= STALE_TTL:
        cards = conn.execute(
            "SELECT id, original, translation FROM cards WHERE status != 'rejected'"
        ).fetchall()
        stored = {
            int(row["card_id"]): row["text_hash"]
            for row in conn.execute(
                "SELECT card_id, text_hash FROM card_embeddings WHERE model = ?",
                (EMBEDDING_MODEL,),
            )
        }
        _stale_value = sum(
            1
            for row in cards
            if stored.get(int(row["id"])) != text_hash(row["original"], row["translation"])
        )
        _stale_at = now

    return {"indexed": indexed, "stale": _stale_value, "model": EMBEDDING_MODEL}


def _fuse_rrf(text_ids: list[int], vector_ids: list[int]) -> list[int]:
    """Merge two ranked id lists with reciprocal rank fusion."""
    rrf: dict[int, float] = {}
    text_rank: dict[int, int] = {}
    for rank, card_id in enumerate(text_ids):
        rrf[card_id] = rrf.get(card_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        text_rank[card_id] = rank
    for rank, card_id in enumerate(vector_ids):
        rrf[card_id] = rrf.get(card_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(
        rrf,
        key=lambda card_id: (
            -rrf[card_id],
            text_rank.get(card_id, float("inf")),
            -card_id,
        ),
    )


def _text_fallback(
    conn: sqlite3.Connection,
    query: str,
    lang: str,
    app: str,
    limit: int,
    offset: int,
    sort: str,
    reason: str,
) -> tuple[list[dict], int, dict]:
    items, total = search_cards(
        conn, query=query, lang=lang, app=app, limit=limit, offset=offset, sort=sort
    )
    return items, total, {"available": False, "mode": "text", "stale": None, "reason": reason}


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    lang: str,
    app: str,
    limit: int,
    offset: int,
    sort: str,
    mode: str,
) -> tuple[list[dict], int, dict]:
    """Fuse text and vector rankings with RRF, degrading to text search on any failure."""
    if not query or mode == "text":
        items, total = search_cards(
            conn, query=query, lang=lang, app=app, limit=limit, offset=offset, sort=sort
        )
        try:
            stale = index_stats(conn)["stale"]
        except sqlite3.OperationalError:
            stale = None
        return items, total, {"available": True, "mode": "text", "stale": stale, "reason": None}

    try:
        text_ids: list[int] = []
        if mode != "semantic":
            candidates, _ = search_cards(
                conn,
                query=query,
                lang=lang,
                app=app,
                limit=SEMANTIC_CANDIDATES,
                offset=0,
                sort="new",
            )
            text_ids = [int(card["id"]) for card in candidates]
        vector_hits = semantic_search(conn, query, lang, app, SEMANTIC_CANDIDATES)
        fused = _fuse_rrf(text_ids, [card_id for card_id, _ in vector_hits])
        items = get_cards_by_ids(conn, fused[offset:offset + limit])
        stale = index_stats(conn)["stale"]
    except SemanticUnavailable as exc:
        return _text_fallback(conn, query, lang, app, limit, offset, sort, exc.reason)
    except Exception:
        return _text_fallback(conn, query, lang, app, limit, offset, sort, "embedding error")

    return items, len(fused), {"available": True, "mode": mode, "stale": stale, "reason": None}
