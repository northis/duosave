"""Duosave patch format v1: models, safe names and archive validation.

Single source of truth for the format (contracts/patch-format.md); used by the agent
CLI (`duosave.patch_build`) and by the server (`duosave.patch_apply`). Imports only
stdlib, pydantic and Pillow: the agent machine has no database, FastAPI or ML stack.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import warnings
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

FORMAT = "duosave-patch"
FORMAT_VERSION = 1

# Limits (contracts/patch-format.md).
MAX_MEMBERS = 2000
MAX_UNPACKED_BYTES = 512 * 1024 * 1024
MAX_JSON_RATIO = 100
MAX_PIXELS = 40_000_000
MAX_PAIRS = 10
MAX_TEXT = 500
MAX_NOTE = 500
MAX_ERRORS = 50
MAX_SAFE_NAME = 120
MIN_TS = 946684800      # 2000-01-01
MAX_TS = 4102444800     # 2100-01-01

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
PATCH_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}(-p\d{1,3})?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}
FOLDERS = ("pictures", "screens")
APPS = {"duolingo_card", "duolingo_app", "drops"}
SCREEN_TYPES = {"share_card", "drops_card", "meaning", "answer_panel", "tiles",
                "select_image", "unknown"}
KINDS = {"word", "phrase", "sentence"}
LANGS = {"pl", "es", "pt"}
MANIFEST_NAME = "manifest.json"
RECORDS_NAME = "records.jsonl"
FILE_PREFIX = "files/"

_ARCHIVE_MEMBERS = {MANIFEST_NAME, RECORDS_NAME}


class PatchError(Exception):
    """One or more format violations (up to MAX_ERRORS), rendered as 422 by the server."""

    def __init__(self, errors: Iterable[str]) -> None:
        self.errors = list(errors)
        super().__init__("; ".join(self.errors) or "invalid patch")


@dataclass
class ValidatedPatch:
    manifest: "Manifest"
    records: list["Record"]
    archive_sha256: str
    path: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --------------------------------------------------------------------------- models


class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: str
    translation: str
    kind: Literal["word", "phrase", "sentence"] = "sentence"

    @field_validator("original", "translation")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        if len(value) > MAX_TEXT:
            raise ValueError(f"must be at most {MAX_TEXT} characters")
        if any(ord(char) < 32 for char in value):
            raise ValueError("must not contain control characters")
        return value


def _clean_note(value: str) -> str:
    value = value.strip()
    if len(value) > MAX_NOTE:
        raise ValueError(f"must be at most {MAX_NOTE} characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError("must not contain control characters")
    return value


class Record(BaseModel):
    """One image plus its recognized pairs (`records.jsonl` line)."""

    model_config = ConfigDict(extra="forbid")

    file: str
    sha256: str
    created_ts: int | None = None
    action: Literal["set", "review"]
    app: Literal["duolingo_card", "duolingo_app", "drops"]
    screen_type: Literal["share_card", "drops_card", "meaning", "answer_panel",
                         "tiles", "select_image", "unknown"] | None = None
    language: Literal["pl", "es", "pt", "unk"]
    pairs: list[Pair] = []
    note: str = ""

    @field_validator("file")
    @classmethod
    def _check_file(cls, value: str) -> str:
        folder, _, name = value.partition("/")
        if folder not in FOLDERS or "/" in name or "\\" in name:
            raise ValueError("must be <pictures|screens>/<safe-name>")
        if not NAME_RE.match(name) or not name.lower().endswith(IMAGE_SUFFIXES):
            raise ValueError("name must be a safe image name")
        return value

    @field_validator("sha256")
    @classmethod
    def _check_sha(cls, value: str) -> str:
        if not SHA_RE.match(value):
            raise ValueError("must be 64 lowercase hex characters")
        return value

    @field_validator("created_ts")
    @classmethod
    def _check_ts(cls, value: int | None) -> int | None:
        if value is not None and not MIN_TS <= value <= MAX_TS:
            raise ValueError(f"must be within {MIN_TS}..{MAX_TS} or null")
        return value

    @field_validator("note")
    @classmethod
    def _check_note(cls, value: str) -> str:
        return _clean_note(value)

    @model_validator(mode="after")
    def _check_folder_app_and_pairs(self) -> "Record":
        folder = self.file.split("/", 1)[0]
        if folder == "pictures" and self.app != "duolingo_card":
            raise ValueError("pictures/ requires app=duolingo_card")
        if folder == "screens" and self.app == "duolingo_card":
            raise ValueError("screens/ requires app=duolingo_app or drops")
        if len(self.pairs) > MAX_PAIRS:
            raise ValueError(f"must contain at most {MAX_PAIRS} pairs")
        if self.action == "set":
            if not self.pairs:
                raise ValueError("set requires at least one pair")
            if self.language == "unk":
                raise ValueError("set requires a known language (pl, es or pt)")
        return self


class Generator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    version: str
    commit: str | None = None
    agent: str | None = None

    @field_validator("tool", "version")
    @classmethod
    def _short(cls, value: str) -> str:
        if not value or len(value) > 40:
            raise ValueError("must be 1..40 characters")
        return value

    @field_validator("commit")
    @classmethod
    def _commit(cls, value: str | None) -> str | None:
        if value is not None and not HEX40_RE.match(value):
            raise ValueError("must be 40 lowercase hex characters or null")
        return value

    @field_validator("agent")
    @classmethod
    def _agent(cls, value: str | None) -> str | None:
        if value is not None and (not value or len(value) > 120):
            raise ValueError("must be 1..120 characters or null")
        return value


class Part(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: str
    index: int
    count: int

    @model_validator(mode="after")
    def _check(self) -> "Part":
        if not 1 <= self.index <= self.count <= 999:
            raise ValueError("must satisfy 1 <= index <= count <= 999")
        return self


class Counts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: int
    files: int
    set: int
    review: int
    pairs: int


class FileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str
    size: int

    @field_validator("sha256")
    @classmethod
    def _check_sha(cls, value: str) -> str:
        if not SHA_RE.match(value):
            raise ValueError("must be 64 lowercase hex characters")
        return value


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["duosave-patch"]
    format_version: int
    patch_id: str
    created_at: str
    generator: Generator
    part: Part
    counts: Counts
    records_sha256: str
    files: dict[str, FileEntry]

    @field_validator("patch_id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        if not PATCH_ID_RE.match(value):
            raise ValueError("must look like 20261012T103105Z-3f9c2a1b-p1")
        return value

    @field_validator("records_sha256")
    @classmethod
    def _check_sha(cls, value: str) -> str:
        if not SHA_RE.match(value):
            raise ValueError("must be 64 lowercase hex characters")
        return value

    @model_validator(mode="after")
    def _check_part_group(self) -> "Manifest":
        expected = re.sub(r"-p\d{1,3}$", "", self.patch_id)
        if self.part.group != expected:
            raise ValueError(f"part.group must be {expected}")
        return self


class WorkRecord(BaseModel):
    """Agent draft (`outbox/.work/slice-NNN.jsonl`): action is null until filled in."""

    model_config = ConfigDict(extra="forbid")

    source: str
    sha256: str
    size: int
    created_ts: int | None = None
    safe_name: str
    duplicate_of: str | None = None
    action: Literal["set", "review", "reject"] | None = None
    folder: Literal["pictures", "screens"] | None = None
    app: Literal["duolingo_card", "duolingo_app", "drops"] | None = None
    screen_type: Literal["share_card", "drops_card", "meaning", "answer_panel",
                         "tiles", "select_image", "unknown"] | None = None
    language: Literal["pl", "es", "pt", "unk"] | None = None
    pairs: list[Pair] = []
    note: str = ""

    @field_validator("sha256")
    @classmethod
    def _check_sha(cls, value: str) -> str:
        if not SHA_RE.match(value):
            raise ValueError("must be 64 lowercase hex characters")
        return value

    @field_validator("safe_name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not NAME_RE.match(value) or not value.lower().endswith(IMAGE_SUFFIXES):
            raise ValueError("must be a safe image name")
        return value

    @field_validator("note")
    @classmethod
    def _check_note(cls, value: str) -> str:
        return _clean_note(value)

    @model_validator(mode="after")
    def _validate_by_action(self) -> "WorkRecord":
        if self.action in ("set", "review"):
            try:
                self.to_record()
            except (ValidationError, ValueError) as exc:
                raise ValueError(str(exc)) from exc
        return self

    def to_record(self) -> Record:
        """Convert a filled draft into a patch record (raises for drafts)."""
        if self.action not in ("set", "review"):
            raise ValueError("action must be set or review to become a record")
        if self.folder is None or self.app is None or self.language is None:
            raise ValueError("folder, app and language are required")
        return Record(
            file=f"{self.folder}/{self.safe_name}",
            sha256=self.sha256,
            created_ts=self.created_ts,
            action=self.action,
            app=self.app,
            screen_type=self.screen_type,
            language=self.language,
            pairs=self.pairs,
            note=self.note,
        )


class LedgerEntry(BaseModel):
    """`outbox/ledger.jsonl` line: what happened to one source image."""

    model_config = ConfigDict(extra="forbid")

    sha256: str
    source: str
    outcome: Literal["packed", "rejected", "duplicate"]
    patch_id: str | None = None
    note: str = ""
    at: str

    @field_validator("sha256")
    @classmethod
    def _check_sha(cls, value: str) -> str:
        if not SHA_RE.match(value):
            raise ValueError("must be 64 lowercase hex characters")
        return value

    @field_validator("note")
    @classmethod
    def _check_note(cls, value: str) -> str:
        return _clean_note(value)


# ----------------------------------------------------------------------- helpers


def safe_name(name: str) -> str:
    """Turn any file name into `^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$` + an image suffix."""
    stem = Path(name).stem
    suffix = Path(name).suffix.lower()
    if suffix not in IMAGE_SUFFIXES:
        suffix = ".png"
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
    if not cleaned or not cleaned[0].isalnum():
        cleaned = "f" + cleaned
    return cleaned[: MAX_SAFE_NAME - len(suffix)] + suffix


def parse_known_hashes(text: str) -> set[str]:
    """Read `known-hashes.txt` (comments start with #); malformed lines are an error."""
    hashes: set[str] = set()
    errors: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if not SHA_RE.match(value):
            errors.append(f"known-hashes.txt:{number}: expected 64 lowercase hex characters")
            continue
        hashes.add(value)
    if errors:
        raise PatchError(errors)
    return hashes


def records_to_jsonl(records: Iterable[Record]) -> bytes:
    """Canonical `records.jsonl` body (one record per line, UTF-8)."""
    lines = [json.dumps(record.model_dump(), ensure_ascii=False) for record in records]
    return ("\n".join(lines) + "\n" if lines else "").encode("utf-8")


def build_manifest(*, patch_id: str, records: list[Record], files: dict,
                   generator: dict | Generator, part: dict | Part,
                   created_at: str | None = None) -> dict:
    """Build manifest.json content (used by `pack` and by tests/patchkit)."""
    body = records_to_jsonl(records)
    counts = Counts(
        records=len(records),
        files=len(files),
        set=sum(1 for record in records if record.action == "set"),
        review=sum(1 for record in records if record.action == "review"),
        pairs=sum(len(record.pairs) for record in records),
    )
    manifest = Manifest(
        format=FORMAT,
        format_version=FORMAT_VERSION,
        patch_id=patch_id,
        created_at=created_at or utc_now_iso(),
        generator=generator if isinstance(generator, Generator) else Generator(**generator),
        part=part if isinstance(part, Part) else Part(**part),
        counts=counts,
        records_sha256=hashlib.sha256(body).hexdigest(),
        files={name: entry if isinstance(entry, FileEntry) else FileEntry(**entry)
               for name, entry in files.items()},
    )
    return manifest.model_dump()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _sha256_member(zf: zipfile.ZipFile, name: str, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with zf.open(name) as member:
        while block := member.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _format_errors(prefix: str, exc: ValidationError) -> list[str]:
    result = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item["loc"])
        result.append(f"{prefix}: {location}: {item['msg']}" if location else f"{prefix}: {item['msg']}")
    return result


@contextmanager
def _bomb_guard(limit: int) -> Iterator[None]:
    """Temporarily lower Pillow's pixel limit and turn the bomb warning into an error."""
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = limit
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            yield
    finally:
        Image.MAX_IMAGE_PIXELS = previous


# ------------------------------------------------------------------- validation


def _check_member(info: zipfile.ZipInfo, errors: list[str]) -> None:
    name = info.filename
    if info.is_dir():
        errors.append(f"archive: {name}: directory entries are not allowed")
        return
    if name.startswith("/") or "\\" in name or ".." in name.split("/"):
        errors.append(f"archive: {name}: unsafe path")
        return
    if name not in _ARCHIVE_MEMBERS:
        if not name.startswith(FILE_PREFIX):
            errors.append(f"archive: {name}: unknown element")
            return
        folder, _, file_name = name[len(FILE_PREFIX):].partition("/")
        if folder not in FOLDERS or "/" in file_name:
            errors.append(f"archive: {name}: must be files/<pictures|screens>/<safe-name>")
            return
        if not NAME_RE.match(file_name) or not file_name.lower().endswith(IMAGE_SUFFIXES):
            errors.append(f"archive: {name}: name must be a safe image name")
    if info.flag_bits & 0x1:
        errors.append(f"archive: {name}: encrypted entries are not allowed")
    if (info.external_attr >> 16) & 0o170000 == 0o120000:
        errors.append(f"archive: {name}: symlinks are not allowed")
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        errors.append(f"archive: {name}: compression method {info.compress_type} is not allowed")


def _check_manifest(zf: zipfile.ZipFile, errors: list[str]) -> Manifest | None:
    try:
        raw = zf.read(MANIFEST_NAME)
    except KeyError:
        errors.append("archive: manifest.json is missing")
        return None
    try:
        manifest = Manifest.model_validate_json(raw)
    except ValidationError as exc:
        errors.extend(_format_errors(MANIFEST_NAME, exc))
        return None
    if manifest.format_version > FORMAT_VERSION:
        errors.append(
            f"{MANIFEST_NAME}: format_version {manifest.format_version} is newer than this site"
            f" supports ({FORMAT_VERSION}) — патч новее сайта, обновите сайт"
        )
    elif manifest.format_version != FORMAT_VERSION:
        errors.append(f"{MANIFEST_NAME}: unsupported format_version {manifest.format_version}")
    return manifest


def _check_records(zf: zipfile.ZipFile, manifest: Manifest,
                   errors: list[str]) -> list[Record]:
    try:
        raw = zf.read(RECORDS_NAME)
    except KeyError:
        errors.append(f"archive: {RECORDS_NAME} is missing")
        return []
    if sha256_bytes(raw) != manifest.records_sha256:
        errors.append(f"{RECORDS_NAME}: sha256 does not match manifest.records_sha256")
    records: list[Record] = []
    seen_files: set[str] = set()
    seen_hashes: set[str] = set()
    for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = Record.model_validate_json(line)
        except ValidationError as exc:
            errors.extend(_format_errors(f"{RECORDS_NAME}:{number}", exc))
            continue
        if record.file in seen_files:
            errors.append(f"{RECORDS_NAME}:{number}: duplicate file {record.file}")
        if record.sha256 in seen_hashes:
            errors.append(f"{RECORDS_NAME}:{number}: duplicate sha256")
        seen_files.add(record.file)
        seen_hashes.add(record.sha256)
        records.append(record)
    expected = Counts(
        records=len(records),
        files=len(manifest.files),
        set=sum(1 for record in records if record.action == "set"),
        review=sum(1 for record in records if record.action == "review"),
        pairs=sum(len(record.pairs) for record in records),
    )
    if manifest.counts != expected:
        errors.append(
            f"{MANIFEST_NAME}: counts {manifest.counts.model_dump()} do not match"
            f" {expected.model_dump()}"
        )
    return records


def _check_files(zf: zipfile.ZipFile, manifest: Manifest, records: list[Record],
                 members: dict[str, zipfile.ZipInfo], errors: list[str]) -> None:
    manifest_files = set(manifest.files)
    archive_files = set(members)
    record_files = {FILE_PREFIX + record.file for record in records}
    if manifest_files != archive_files:
        errors.append(f"{MANIFEST_NAME}: files list does not match the archive contents")
    if record_files != archive_files:
        errors.append(f"{RECORDS_NAME}: files do not match the archive contents")
    for name, entry in manifest.files.items():
        info = members.get(name)
        if info is None:
            continue
        if entry.size != info.file_size:
            errors.append(f"{MANIFEST_NAME}: files[{name}]: size {entry.size} != {info.file_size}")
        if entry.sha256 != _sha256_member(zf, name):
            errors.append(f"{MANIFEST_NAME}: files[{name}]: sha256 does not match")


def _check_images(zf: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo],
                  errors: list[str]) -> None:
    for name in sorted(members):
        try:
            data = zf.read(name)
        except (zipfile.BadZipFile, OSError) as exc:
            errors.append(f"archive: {name}: cannot be read ({exc})")
            continue
        try:
            with _bomb_guard(MAX_PIXELS):
                with Image.open(io.BytesIO(data)) as image:
                    image.verify()
                    image_format = image.format
        except (Image.DecompressionBombWarning, Image.DecompressionBombError):
            errors.append(f"archive: {name}: image is larger than {MAX_PIXELS} pixels")
            continue
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            errors.append(f"archive: {name}: broken image ({exc})")
            continue
        if image_format not in IMAGE_FORMATS:
            errors.append(f"archive: {name}: format {image_format} is not PNG/JPEG/WEBP")


def validate_archive(path: Path, *, max_bytes: int | None = None) -> ValidatedPatch:
    """Validate a patch archive; all violations are collected into one PatchError."""
    if max_bytes is not None and path.stat().st_size > max_bytes:
        raise PatchError([f"archive: larger than {max_bytes} bytes"])
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PatchError([f"archive: not a zip archive ({exc})"]) from exc

    with zf:
        infos = zf.infolist()
        errors: list[str] = []
        if len(infos) > MAX_MEMBERS:
            errors.append(f"archive: more than {MAX_MEMBERS} members")
        names = [info.filename for info in infos]
        if len(set(names)) != len(names):
            errors.append("archive: duplicate member names")
        total_unpacked = sum(info.file_size for info in infos)
        if total_unpacked > MAX_UNPACKED_BYTES:
            errors.append(f"archive: unpacked size {total_unpacked} exceeds {MAX_UNPACKED_BYTES}")
        for info in infos:
            _check_member(info, errors)
            if info.filename in _ARCHIVE_MEMBERS and info.compress_size:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_JSON_RATIO:
                    errors.append(f"archive: {info.filename}: compression ratio {ratio:.0f} is too high")
        if errors:
            raise PatchError(errors[:MAX_ERRORS])

        members = {info.filename: info for info in infos if info.filename.startswith(FILE_PREFIX)}
        manifest = _check_manifest(zf, errors)
        records: list[Record] = []
        if manifest is not None:
            records = _check_records(zf, manifest, errors)
            _check_files(zf, manifest, records, members, errors)
            _check_images(zf, members, errors)
        if errors:
            raise PatchError(errors[:MAX_ERRORS])

        assert manifest is not None  # no errors means the manifest parsed
        return ValidatedPatch(
            manifest=manifest,
            records=records,
            archive_sha256=sha256_file(path),
            path=path,
        )
