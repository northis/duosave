"""Server-side patch application: staging, preview, apply, history, reindex."""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from duosave import config, db, patch_apply, patchfmt

import patchkit
from helpers import png_bytes

PNG = png_bytes(color=(10, 20, 30))
PNG2 = png_bytes(color=(99, 20, 30))
SCREEN = "screens/Screenshot_20261010-101010.png"
PICTURE = "pictures/1760091234.png"
PAIR = {"original": "o abacaxi", "translation": "pineapple", "kind": "word"}


@pytest.fixture(autouse=True)
def offline_embedder(monkeypatch: pytest.MonkeyPatch):
    """Never load the real fastembed model from a test (tests are offline by contract)."""
    from duosave import semantic

    def unavailable():
        raise semantic.SemanticUnavailable("tests: fastembed disabled")

    monkeypatch.setattr(semantic, "get_embedder", unavailable)


@pytest.fixture(autouse=True)
def reset_reindex():
    patch_apply._set_reindex("idle")
    yield
    patch_apply.wait_reindex(10)
    patch_apply._set_reindex("idle")


def _chunks(path: Path):
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            yield chunk


def _set_record(**overrides) -> dict:
    return patchkit.make_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG), **overrides)


def _review_record(file: str = "screens/b.png", sha256: str | None = None, **overrides) -> dict:
    record = {
        "file": file,
        "sha256": sha256 or patchfmt.sha256_bytes(PNG2),
        "created_ts": None,
        "action": "review",
        "app": "duolingo_app",
        "screen_type": "unknown",
        "language": "unk",
        "pairs": [],
        "note": "unclear",
    }
    record.update(overrides)
    return record


def _stage(tmp_path: Path, records=None, images=None, actor="owner@example.com") -> dict:
    if records is None:
        records = [_set_record(), _review_record()]
    if images is None:
        images = {SCREEN: PNG, "screens/b.png": PNG2}
    path = patchkit.build_patch(tmp_path / "patch.zip", records, images)
    return patch_apply.stage(_chunks(path), actor=actor)


def _staged(tmp_repo) -> Path:
    return tmp_repo.data / "patches" / "staged"


def _applied(tmp_repo) -> Path:
    return tmp_repo.data / "patches" / "applied"


def _incoming(tmp_repo) -> Path:
    return tmp_repo.data / "patches" / "incoming"


# --------------------------------------------------------------------- staging


def test_stage_valid_patch(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)

    assert (payload["patch_id"]) == patchfmt.validate_archive(
        _staged(tmp_repo) / f"{payload['patch_id']}.zip"
    ).manifest.patch_id
    assert (payload["state"], payload["already_applied"]) == ("staged", False)
    assert payload["uploaded_by"] == "owner@example.com"
    assert payload["archive_sha256"]
    assert payload["summary"]["records"] == 2
    assert payload["summary"]["new_files"] == 2
    assert payload["summary"]["set"] == 1
    assert payload["summary"]["review"] == 1
    assert [_item["outcome"] for _item in payload["items"]] == ["new", "new"]
    assert not list(_incoming(tmp_repo).iterdir())


def test_stage_too_large(tmp_repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patch_apply, "max_upload_bytes", lambda: 10)

    with pytest.raises(patch_apply.PatchTooLarge) as exc:
        _stage(tmp_path)

    assert exc.value.limit_mb == config.PATCH_MAX_MB
    assert not list(_incoming(tmp_repo).iterdir())
    assert not _staged(tmp_repo).exists() or not list(_staged(tmp_repo).iterdir())


def test_stage_invalid_patch(tmp_repo, tmp_path: Path) -> None:
    path = patchkit.build_patch(tmp_path / "patch.zip", [_set_record()], {SCREEN: PNG},
                                manifest_overrides={"format_version": 2})

    with pytest.raises(patchfmt.PatchError):
        patch_apply.stage(_chunks(path), actor=None)

    assert not list(_incoming(tmp_repo).iterdir())
    assert not _staged(tmp_repo).exists() or not list(_staged(tmp_repo).iterdir())


# -------------------------------------------------------------------- preview


def test_preview_duplicate_by_sha(tmp_repo, tmp_path: Path) -> None:
    db.set_file(tmp_repo.conn, path="screens/other.png", sha256=patchfmt.sha256_bytes(PNG),
                size=len(PNG), mtime=1, status="reviewed")
    tmp_repo.conn.commit()

    payload = _stage(tmp_path)

    item = payload["items"][0]
    assert item["outcome"] == "duplicate"
    assert item["existing_path"] == "screens/other.png"
    assert payload["summary"]["duplicates"] == 1
    assert payload["summary"]["new_files"] == 1


def test_preview_renamed_when_name_taken(tmp_repo, tmp_path: Path) -> None:
    (tmp_repo.screens / Path(SCREEN).name).write_bytes(png_bytes(color=(1, 1, 1)))

    payload = _stage(tmp_path)

    item = payload["items"][0]
    assert item["outcome"] == "renamed"
    assert item["target"] == f"screens/Screenshot_20261010-101010-{patchfmt.sha256_bytes(PNG)[:8]}.png"


def test_preview_renamed_when_only_files_row_exists(tmp_repo, tmp_path: Path) -> None:
    db.set_file(tmp_repo.conn, path=SCREEN, sha256="f" * 64, size=1, mtime=1, status="pending")
    tmp_repo.conn.commit()

    payload = _stage(tmp_path)

    assert payload["items"][0]["outcome"] == "renamed"


def test_preview_marks_existing_cards(tmp_repo, tmp_path: Path) -> None:
    db.upsert_card(tmp_repo.conn, language="pt", original=PAIR["original"],
                   translation=PAIR["translation"], kind="word", app="drops", screen_type=None,
                   status="manual", original_folded="o abacaxi", translation_folded="pineapple")
    tmp_repo.conn.commit()

    payload = _stage(tmp_path)

    assert payload["items"][0]["pairs"][0]["card"] == "existing"
    assert payload["summary"]["existing_cards"] == 1
    assert payload["summary"]["new_cards"] == 0


# ---------------------------------------------------------------------- apply


def test_apply_set_drops_record(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)

    result = patch_apply.apply(payload["patch_id"], actor="owner@example.com")

    target = tmp_repo.root / SCREEN
    assert target.read_bytes() == PNG
    card = tmp_repo.conn.execute("SELECT * FROM cards").fetchone()
    assert (card["language"], card["original"], card["translation"]) == ("pt", "o abacaxi", "pineapple")
    assert card["status"] == "manual"
    source = tmp_repo.conn.execute("SELECT * FROM sources").fetchone()
    assert source["recognizer"] == "agent"
    assert source["path"] == SCREEN
    assert (tmp_repo.root / source["crop_path"]).exists()
    row = tmp_repo.conn.execute("SELECT * FROM files WHERE path = ?", (SCREEN,)).fetchone()
    stat = target.stat()
    assert row["status"] == "reviewed"
    assert row["reason"] == f"patch {payload['patch_id']}"
    assert row["size"] == stat.st_size
    assert row["mtime"] == float(stat.st_mtime_ns)  # REAL column: compare in float domain
    assert row["created_ts"] == 1760090410  # taken from the record, not from the name
    patch_row = tmp_repo.conn.execute("SELECT * FROM patches").fetchone()
    assert patch_row["applied_by"] == "owner@example.com"
    assert result["report"]["files_written"] == 2
    assert (tmp_repo.data / "patches" / "applied" / f"{payload['patch_id']}.zip").exists()
    assert not (_staged(tmp_repo) / f"{payload['patch_id']}.json").exists()
    snapshot = tmp_repo.data / "backups" / f"pre-patch-{payload['patch_id']}-"
    assert list((tmp_repo.data / "backups").glob(f"{snapshot.name}*.db"))
    assert result["state"] == "applied"
    assert result["snapshot"].startswith("data/backups/pre-patch-")


def test_sync_would_skip_applied_files(tmp_repo, tmp_path: Path) -> None:
    from duosave import sync

    payload = _stage(tmp_path)
    patch_apply.apply(payload["patch_id"], actor=None)

    row = tmp_repo.conn.execute(
        "SELECT mtime, size, status FROM files WHERE path = ?", (SCREEN,)
    ).fetchone()
    stat = (tmp_repo.root / SCREEN).stat()

    assert row["status"] == "reviewed"
    assert sync._unchanged(row, stat)  # exactly the condition sync.sync uses to skip


def test_apply_review_with_pairs(tmp_repo, tmp_path: Path) -> None:
    record = _review_record(language="pl", app="duolingo_app", screen_type="tiles",
                            pairs=[{"original": "Zły chłopiec pije kawę.",
                                    "translation": "The bad boy is drinking coffee.",
                                    "kind": "sentence"}], note="unsure")
    payload = _stage(tmp_path, records=[record], images={"screens/b.png": PNG2})

    patch_apply.apply(payload["patch_id"], actor=None)

    card = tmp_repo.conn.execute("SELECT * FROM cards").fetchone()
    assert card["status"] == "review"
    assert card["notes"] == "unsure"
    items, total = db.review_files(tmp_repo.conn)
    assert total == 1
    assert items[0]["path"] == "screens/b.png"


def test_apply_review_keeps_existing_card_status(tmp_repo, tmp_path: Path) -> None:
    card_id = db.upsert_card(tmp_repo.conn, language="pl", original="Zły chłopiec pije kawę.",
                             translation="The bad boy is drinking coffee.", kind="sentence",
                             app="duolingo_app", screen_type=None, status="manual",
                             original_folded="zły chłopiec pije kawę",
                             translation_folded="the bad boy is drinking coffee.")
    tmp_repo.conn.commit()
    record = _review_record(language="pl", app="duolingo_app",
                            pairs=[{"original": "Zły chłopiec pije kawę.",
                                    "translation": "The bad boy is drinking coffee.",
                                    "kind": "sentence"}])
    payload = _stage(tmp_path, records=[record], images={"screens/b.png": PNG2})

    patch_apply.apply(payload["patch_id"], actor=None)

    card = tmp_repo.conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
    assert card["status"] == "manual"
    assert tmp_repo.conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1


def test_apply_review_without_pairs(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path, records=[_review_record(note="no text")],
                     images={"screens/b.png": PNG2})

    patch_apply.apply(payload["patch_id"], actor=None)

    row = tmp_repo.conn.execute("SELECT * FROM files WHERE path = ?", ("screens/b.png",)).fetchone()
    assert row["status"] == "review"
    assert row["reason"] == "no_pair: no text"
    assert tmp_repo.conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0


def test_created_ts_fallbacks(tmp_repo, tmp_path: Path) -> None:
    custom = _review_record(file="screens/custom_name.png", sha256=patchfmt.sha256_bytes(PNG2),
                            created_ts=None)
    named = _set_record(created_ts=None)
    payload = _stage(tmp_path, records=[named, custom],
                     images={SCREEN: PNG, "screens/custom_name.png": PNG2})
    started = time.time()

    patch_apply.apply(payload["patch_id"], actor=None)

    named_row = tmp_repo.conn.execute("SELECT created_ts FROM files WHERE path = ?",
                                      (SCREEN,)).fetchone()
    custom_row = tmp_repo.conn.execute("SELECT created_ts FROM files WHERE path = ?",
                                       ("screens/custom_name.png",)).fetchone()
    assert named_row["created_ts"] == int(datetime(2026, 10, 10, 10, 10, 10).timestamp())
    assert started - 5 <= custom_row["created_ts"] <= time.time() + 5


def test_apply_is_idempotent(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)
    patch_apply.apply(payload["patch_id"], actor=None)

    with pytest.raises(patch_apply.AlreadyApplied):
        patch_apply.apply(payload["patch_id"], actor=None)

    again = _stage(tmp_path)
    assert again["already_applied"] is True


def test_apply_recomputes_plan(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)
    db.set_file(tmp_repo.conn, path="screens/other.png", sha256=patchfmt.sha256_bytes(PNG),
                size=len(PNG), mtime=1, status="reviewed")
    tmp_repo.conn.commit()

    result = patch_apply.apply(payload["patch_id"], actor=None)

    assert result["report"]["duplicates"] == 1
    assert not (tmp_repo.root / SCREEN).exists()
    assert result["report"]["files_written"] == 1


def test_apply_rolls_back_on_error(tmp_repo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    records = [_set_record(pairs=[PAIR, {"original": "a maçã", "translation": "the apple",
                                         "kind": "word"}])]
    payload = _stage(tmp_path, records=records, images={SCREEN: PNG})
    calls = {"count": 0}
    original = patch_apply.upsert_card

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:
            raise RuntimeError("boom")
        return original(*args, **kwargs)

    monkeypatch.setattr(patch_apply, "upsert_card", flaky)

    with pytest.raises(patch_apply.PatchApplyError):
        patch_apply.apply(payload["patch_id"], actor=None)

    assert calls["count"] == 2
    assert not (tmp_repo.root / SCREEN).exists()
    assert list(tmp_repo.screens.rglob("*.partial")) == []
    assert list(tmp_repo.pictures.rglob("*.partial")) == []
    assert tmp_repo.conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
    assert tmp_repo.conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0
    assert tmp_repo.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 0
    assert tmp_repo.conn.execute("SELECT COUNT(*) FROM patches").fetchone()[0] == 0
    assert (_staged(tmp_repo) / f"{payload['patch_id']}.zip").exists()


def test_discard(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)

    patch_apply.discard(payload["patch_id"])

    assert not (_staged(tmp_repo) / f"{payload['patch_id']}.zip").exists()
    with pytest.raises(patch_apply.PatchNotFound):
        patch_apply.discard(payload["patch_id"])

    applied = _stage(tmp_path)
    patch_apply.apply(applied["patch_id"], actor=None)
    with pytest.raises(patch_apply.AlreadyApplied):
        patch_apply.discard(applied["patch_id"])


def test_listing_expires_old_staged(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)
    json_path = _staged(tmp_repo) / f"{payload['patch_id']}.json"
    old = time.time() - (config.STAGED_TTL_DAYS + 1) * 86400
    os.utime(json_path, (old, old))

    listing = patch_apply.listing(tmp_repo.conn)

    assert listing["staged"] == []
    assert not json_path.exists()
    assert not (_staged(tmp_repo) / f"{payload['patch_id']}.zip").exists()


def test_listing_reports_staged_and_applied(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)
    patch_apply.apply(payload["patch_id"], actor="owner@example.com")
    second = _stage(tmp_path)

    listing = patch_apply.listing(tmp_repo.conn)

    assert [item["patch_id"] for item in listing["staged"]] == [second["patch_id"]]
    assert listing["applied"][0]["patch_id"] == payload["patch_id"]
    assert listing["applied"][0]["applied_by"] == "owner@example.com"
    assert listing["reindex"]["state"] in {"idle", "running", "done", "unavailable", "failed"}


def test_get_returns_staged_then_applied(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)

    assert patch_apply.get(tmp_repo.conn, payload["patch_id"])["state"] == "staged"

    patch_apply.apply(payload["patch_id"], actor=None)

    applied = patch_apply.get(tmp_repo.conn, payload["patch_id"])
    assert applied["state"] == "applied"
    with pytest.raises(patch_apply.PatchNotFound):
        patch_apply.get(tmp_repo.conn, "20261012T103105Z-00000000-p9")


def test_image_from_staged_archive(tmp_repo, tmp_path: Path) -> None:
    payload = _stage(tmp_path)

    data = patch_apply.image(payload["patch_id"], "screens", Path(SCREEN).name)
    assert data == PNG

    for folder, name in (("pictures", "x.png"), ("../x", "x.png"), ("screens", "../x.png"),
                         ("screens", "no-such.png")):
        with pytest.raises(patch_apply.PatchNotFound):
            patch_apply.image(payload["patch_id"], folder, name)


def test_reindex_runs_after_apply(tmp_repo, tmp_path: Path, fake_embedder) -> None:
    payload = _stage(tmp_path)

    patch_apply.apply(payload["patch_id"], actor=None)
    state = patch_apply.wait_reindex(5)

    assert state["state"] == "done", state
    assert state["result"]["added"] >= 1


def test_reindex_reports_unavailable(tmp_repo, tmp_path: Path,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from duosave import semantic

    def unavailable():
        raise semantic.SemanticUnavailable("fastembed not installed")

    monkeypatch.setattr(semantic, "get_embedder", unavailable)
    payload = _stage(tmp_path)

    patch_apply.apply(payload["patch_id"], actor=None)
    state = patch_apply.wait_reindex(5)

    assert state["state"] == "unavailable"
    assert "fastembed" in state["detail"]


def test_known_hashes(tmp_repo) -> None:
    for path, sha, status in (("screens/a.png", "b" * 64, "reviewed"),
                              ("screens/b.png", "a" * 64, "rejected"),
                              ("screens/c.png", "a" * 64, "pending")):
        db.set_file(tmp_repo.conn, path=path, sha256=sha, size=1, mtime=1, status=status)
    tmp_repo.conn.commit()

    assert patch_apply.known_hashes(tmp_repo.conn) == ["a" * 64, "b" * 64]


# ------------------------------------------------------------------ idempotency


def _apply_one(tmp_path: Path, name: str, record: dict, image: bytes, patch_id: str) -> dict:
    path = patchkit.build_patch(tmp_path / f"{patch_id}.zip", [record], {record["file"]: image},
                                patch_id=patch_id)
    payload = patch_apply.stage(_chunks(path), actor=None)
    return patch_apply.apply(payload["patch_id"])


def test_reimport_of_the_same_phrase_replaces_the_image(tmp_repo, tmp_path: Path) -> None:
    later = "screens/Screenshot_20261011-101010.png"
    _apply_one(tmp_path, "a", _set_record(), PNG, "20261012T103105Z-3f9c2a1b-p1")
    result = _apply_one(tmp_path, "b", patchkit.make_record(
        file=later, sha256=patchfmt.sha256_bytes(PNG2), created_ts=1760176810),
        PNG2, "20261012T103106Z-3f9c2a1c-p1")

    conn = tmp_repo.conn
    assert conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    assert [row["path"] for row in conn.execute("SELECT path FROM sources")] == [later]
    assert conn.execute("SELECT * FROM files WHERE path = ?", (SCREEN,)).fetchone() is None
    assert not (tmp_repo.root / SCREEN).exists()
    assert result["report"]["superseded"] == [SCREEN]


def test_reimport_of_the_same_image_moves_the_date(tmp_repo, tmp_path: Path) -> None:
    _apply_one(tmp_path, "a", _set_record(created_ts=1760090410), PNG,
               "20261012T103105Z-3f9c2a1b-p1")
    result = _apply_one(tmp_path, "b", _set_record(created_ts=1760999999), PNG,
                        "20261012T103106Z-3f9c2a1c-p1")

    row = tmp_repo.conn.execute("SELECT * FROM files WHERE path = ?", (SCREEN,)).fetchone()
    assert row["created_ts"] == 1760999999
    assert result["report"]["touched"] == 1
