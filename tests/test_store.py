"""Common image placement invariants: safe names, collisions, atomic writes."""

from __future__ import annotations

from pathlib import Path

from duosave import db, patchfmt, store

from helpers import png_bytes

PNG = png_bytes(color=(10, 20, 30))
SHA = patchfmt.sha256_bytes(PNG)


def test_target_path_keeps_a_free_name(tmp_repo) -> None:
    assert store.target_path(tmp_repo.conn, "screens", "shot_1.png", SHA) == (
        "screens/shot_1.png", False)


def test_target_path_sanitizes_unsafe_names(tmp_repo) -> None:
    rel, renamed = store.target_path(tmp_repo.conn, "screens", "../my shot.png", SHA)

    name = Path(rel).name
    assert rel == f"screens/{name}"
    assert patchfmt.NAME_RE.match(name)
    assert ".." not in name
    assert name.endswith(".png")
    assert renamed is False


def test_target_path_renames_when_a_files_row_holds_other_content(tmp_repo) -> None:
    db.set_file(tmp_repo.conn, path="screens/shot_1.png", sha256="f" * 64, size=1,
                mtime=1, status="reviewed")
    tmp_repo.conn.commit()

    assert store.target_path(tmp_repo.conn, "screens", "shot_1.png", SHA) == (
        f"screens/shot_1-{SHA[:8]}.png", True)


def test_target_path_renames_when_only_the_file_on_disk_differs(tmp_repo) -> None:
    (tmp_repo.screens / "shot_1.png").write_bytes(png_bytes(color=(1, 2, 3)))

    assert store.target_path(tmp_repo.conn, "screens", "shot_1.png", SHA) == (
        f"screens/shot_1-{SHA[:8]}.png", True)


def test_target_path_keeps_the_name_for_the_same_sha(tmp_repo) -> None:
    db.set_file(tmp_repo.conn, path="screens/shot_1.png", sha256=SHA, size=len(PNG),
                mtime=1, status="reviewed")
    tmp_repo.conn.commit()

    assert store.target_path(tmp_repo.conn, "screens", "shot_1.png", SHA) == (
        "screens/shot_1.png", False)


def test_place_image_writes_the_bytes_without_a_partial_file(tmp_repo) -> None:
    result = store.place_image(tmp_repo.conn, "screens", "shot_1.png", PNG, SHA)

    assert result == ("screens/shot_1.png", False)
    assert (tmp_repo.root / "screens" / "shot_1.png").read_bytes() == PNG
    assert list(tmp_repo.root.rglob("*.partial")) == []


def test_place_image_returns_the_renamed_path(tmp_repo) -> None:
    (tmp_repo.screens / "shot_1.png").write_bytes(png_bytes(color=(1, 2, 3)))

    rel, renamed = store.place_image(tmp_repo.conn, "screens", "shot_1.png", PNG, SHA)

    assert (rel, renamed) == (f"screens/shot_1-{SHA[:8]}.png", True)
    assert (tmp_repo.root / rel).read_bytes() == PNG
