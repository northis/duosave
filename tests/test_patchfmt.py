"""Patch format v1: happy path, every rejection rule, safe names, draft model."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from duosave import patchfmt

import patchkit
from helpers import png_bytes

PNG = png_bytes()
PNG2 = png_bytes(color=(200, 10, 10))
SCREEN = "screens/Screenshot_20261010-101010.png"
PICTURE = "pictures/1760091234.png"


def _set_record(**overrides) -> dict:
    return patchkit.make_record(**overrides)


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


def _valid_archive(tmp_path: Path, **kwargs) -> Path:
    records = kwargs.pop("records", None)
    images = kwargs.pop("images", None)
    if records is None:
        records = [
            _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG)),
            _review_record(),
        ]
    if images is None:
        images = {SCREEN: PNG, "screens/b.png": PNG2}
    return patchkit.build_patch(tmp_path / "patch.zip", records, images, **kwargs)


def _errors(path: Path, **kwargs) -> list[str]:
    with pytest.raises(patchfmt.PatchError) as exc:
        patchfmt.validate_archive(path, **kwargs)
    return exc.value.errors


def _assert_error(path: Path, needle: str, **kwargs) -> None:
    errors = _errors(path, **kwargs)
    assert any(needle in error for error in errors), errors


def test_valid_archive_passes(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path)

    validated = patchfmt.validate_archive(path)

    assert validated.manifest.format == "duosave-patch"
    assert validated.manifest.counts.records == 2
    assert validated.manifest.counts.set == 1
    assert validated.manifest.counts.review == 1
    assert [record.action for record in validated.records] == ["set", "review"]
    assert validated.records[1].pairs == []
    assert validated.archive_sha256 == patchfmt.sha256_file(path)


def test_archive_sha256_is_reported(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path)

    assert patchfmt.validate_archive(path).archive_sha256 == patchfmt.sha256_file(path)


# ---------------------------------------------------------------- archive layout


def test_unsafe_relative_path_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, extra_members={"../x.png": PNG})

    _assert_error(path, "unsafe path")


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, extra_members={"/etc/passwd": b"x"})

    _assert_error(path, "unsafe path")


def test_backslash_in_name_is_rejected() -> None:
    # zipfile normalizes os.sep to "/" when reading on Windows, so check the rule directly.
    info = zipfile.ZipInfo(patchfmt.FILE_PREFIX + "screens/a.png")
    info.filename = "files\\screens\\a.png"
    errors: list[str] = []

    patchfmt._check_member(info, errors)

    assert any("unsafe path" in error for error in errors)


def test_symlink_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, member_overrides={
        patchfmt.FILE_PREFIX + SCREEN: {"external_attr": 0o120777 << 16},
    })

    _assert_error(path, "symlinks are not allowed")


def test_directory_entry_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, extra_members={"files/screens/": b""})

    _assert_error(path, "directory entries are not allowed")


def test_unknown_element_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, extra_members={"readme.txt": b"hi"})

    _assert_error(path, "unknown element")


def test_extra_file_in_files_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, extra_members={patchfmt.FILE_PREFIX + "screens/extra.png": PNG})

    _assert_error(path, "do not match the archive contents")


def test_record_file_missing_from_archive_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, images={SCREEN: PNG})

    _assert_error(path, "do not match the archive contents")


def test_manifest_files_sha_mismatch_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, manifest_overrides={
        "files": {patchfmt.FILE_PREFIX + SCREEN: {"sha256": "0" * 64, "size": 1},
                  patchfmt.FILE_PREFIX + "screens/b.png": {"sha256": "0" * 64, "size": 1}},
    })

    _assert_error(path, "size 1 !=")


def test_records_sha256_mismatch_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, manifest_overrides={"records_sha256": "0" * 64})

    _assert_error(path, "records.jsonl: sha256 does not match")


def test_counts_mismatch_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, manifest_overrides={
        "counts": {"records": 9, "files": 9, "set": 9, "review": 9, "pairs": 9},
    })

    _assert_error(path, "counts")


def test_too_many_members_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patchfmt, "MAX_MEMBERS", 2)

    path = _valid_archive(tmp_path)

    _assert_error(path, "members")


def test_unpacked_size_limit_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patchfmt, "MAX_UNPACKED_BYTES", 10)

    path = _valid_archive(tmp_path)

    _assert_error(path, "unpacked size")


def test_json_compression_ratio_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, manifest_overrides={"pad": "a" * 200_000})

    _assert_error(path, "compression ratio")


def test_bzip2_member_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, compress={patchfmt.FILE_PREFIX + SCREEN: zipfile.ZIP_BZIP2})

    _assert_error(path, "compression method")


# ---------------------------------------------------------------------- manifest


def test_wrong_format_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, manifest_overrides={"format": "other"})

    _assert_error(path, "format")


def test_newer_format_version_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, manifest_overrides={"format_version": 2})

    _assert_error(path, "новее сайта")


def test_extra_manifest_field_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, manifest_overrides={"unexpected": True})

    _assert_error(path, "unexpected")


def test_extra_record_field_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG), oops=1),
        _review_record(),
    ])

    _assert_error(path, "oops")


def test_bad_patch_id_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, manifest_overrides={"patch_id": "not-an-id"})

    _assert_error(path, "patch_id")


# ----------------------------------------------------------------------- records


def test_set_without_pairs_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG), pairs=[]),
        _review_record(),
    ])

    _assert_error(path, "set requires at least one pair")


def test_set_with_unknown_language_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG), language="unk"),
        _review_record(),
    ])

    _assert_error(path, "set requires a known language")


def test_unknown_language_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG), language="de"),
        _review_record(),
    ])

    _assert_error(path, "language")


def test_pictures_with_drops_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=PICTURE, sha256=patchfmt.sha256_bytes(PNG), app="drops"),
        _review_record(),
    ])

    _assert_error(path, "pictures/ requires app=duolingo_card")


def test_screens_with_share_card_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG), app="duolingo_card"),
        _review_record(),
    ])

    _assert_error(path, "screens/ requires app=duolingo_app or drops")


def test_duplicate_file_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG)),
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG2)),
    ], images={SCREEN: PNG, "screens/b.png": PNG2})

    _assert_error(path, "duplicate file")


def test_duplicate_sha256_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG)),
        _set_record(file="screens/b.png", sha256=patchfmt.sha256_bytes(PNG)),
    ], images={SCREEN: PNG, "screens/b.png": PNG2})

    _assert_error(path, "duplicate sha256")


def test_created_ts_out_of_range_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG), created_ts=1),
        _review_record(),
    ])

    _assert_error(path, "created_ts")


@pytest.mark.parametrize("original", ["   ", "a\x00b", "x" * 501])
def test_bad_pair_text_is_rejected(tmp_path: Path, original: str) -> None:
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG),
                    pairs=[{"original": original, "translation": "pineapple", "kind": "word"}]),
        _review_record(),
    ])

    _assert_error(path, "original")


def test_too_many_pairs_is_rejected(tmp_path: Path) -> None:
    pairs = [{"original": f"word{i}", "translation": f"w{i}", "kind": "word"} for i in range(11)]
    path = _valid_archive(tmp_path, records=[
        _set_record(file=SCREEN, sha256=patchfmt.sha256_bytes(PNG), pairs=pairs),
        _review_record(),
    ])

    _assert_error(path, "at most 10 pairs")


def test_errors_are_collected_up_to_50(tmp_path: Path) -> None:
    records = [
        _set_record(file=f"screens/bad{index}.png", sha256=patchfmt.sha256_bytes(PNG),
                    action="nope")
        for index in range(60)
    ]
    path = _valid_archive(tmp_path, records=records, images={})

    errors = _errors(path)

    assert len(errors) == patchfmt.MAX_ERRORS


# ------------------------------------------------------------------------ images


def test_broken_image_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, images={SCREEN: b"definitely not an image", "screens/b.png": PNG2})

    _assert_error(path, "broken image")


def test_gif_is_rejected(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path, images={SCREEN: png_bytes(fmt="GIF"), "screens/b.png": PNG2})

    _assert_error(path, "is not PNG/JPEG/WEBP")


def test_huge_image_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(patchfmt, "MAX_PIXELS", 100)

    path = _valid_archive(tmp_path)

    _assert_error(path, "larger than 100 pixels")


def test_not_a_zip_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "patch.zip"
    path.write_bytes(b"definitely not a zip")

    _assert_error(path, "not a zip archive")


def test_max_bytes_is_enforced(tmp_path: Path) -> None:
    path = _valid_archive(tmp_path)

    _assert_error(path, "larger than 10 bytes", max_bytes=10)


# ------------------------------------------------------------------- safe names


def test_safe_name() -> None:
    assert patchfmt.safe_name("IMG 2026 (1).PNG") == "IMG_2026_1_.png"
    assert patchfmt.safe_name("zdjęcie.png") == "zdj_cie.png"
    long_name = "a" * 200 + ".png"
    assert patchfmt.safe_name(long_name) == "a" * (patchfmt.MAX_SAFE_NAME - 4) + ".png"
    assert patchfmt.safe_name("_hidden.png") == "f_hidden.png"
    for name in ("IMG 2026 (1).PNG", "zdjęcie.png", long_name, "_hidden.png"):
        assert patchfmt.NAME_RE.match(patchfmt.safe_name(name))


# ------------------------------------------------------------------ work records


def _draft(**overrides) -> dict:
    draft = {
        "source": "D:/Phone/Screenshots/IMG_20261010_101010.png",
        "sha256": patchfmt.sha256_bytes(PNG),
        "size": len(PNG),
        "created_ts": 1760090410,
        "safe_name": "IMG_20261010_101010.png",
        "duplicate_of": None,
        "action": None,
        "folder": None,
        "app": None,
        "screen_type": None,
        "language": None,
        "pairs": [],
        "note": "",
    }
    draft.update(overrides)
    return draft


def test_work_record_model() -> None:
    draft = patchfmt.WorkRecord.model_validate(_draft())
    assert draft.action is None

    reject = patchfmt.WorkRecord.model_validate(_draft(action="reject", note="bank app"))
    assert reject.note == "bank app"

    with pytest.raises(ValidationError):
        patchfmt.WorkRecord.model_validate(_draft(action="set", folder="screens", app="drops"))
    with pytest.raises(ValidationError):
        patchfmt.WorkRecord.model_validate(_draft(action="review", folder=None))

    filled = patchfmt.WorkRecord.model_validate(_draft(
        action="set", folder="screens", app="drops", screen_type="drops_card", language="pt",
        pairs=[{"original": "o abacaxi", "translation": "pineapple", "kind": "word"}],
    ))
    record = filled.to_record()
    assert record.file == "screens/IMG_20261010_101010.png"
    assert record.action == "set"
    assert record.language == "pt"


def test_work_record_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        patchfmt.WorkRecord.model_validate(_draft(unexpected=1))
