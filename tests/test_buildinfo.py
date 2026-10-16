"""Build info: version, commit resolution, remote URL normalization, /api/version."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from duosave import __version__, buildinfo
from duosave.cli import build_parser
from duosave.server.app import app


@pytest.fixture(autouse=True)
def clear_build_info_cache():
    buildinfo.build_info.cache_clear()
    yield
    buildinfo.build_info.cache_clear()


def test_version_is_2_9_0() -> None:
    assert __version__ == "2.14.0"


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("https://github.com/northis/duosave.git", "https://github.com/northis/duosave"),
        ("https://github.com/northis/duosave", "https://github.com/northis/duosave"),
        ("git@github.com:northis/duosave.git", "https://github.com/northis/duosave"),
        ("ssh://git@github.com/northis/duosave.git", "https://github.com/northis/duosave"),
        ("git://github.com/northis/duosave.git", "https://github.com/northis/duosave"),
    ],
)
def test_normalize_repo_url(remote: str, expected: str) -> None:
    assert buildinfo.normalize_repo_url(remote) == expected


def test_env_override_commit_and_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(buildinfo, "_git", lambda *args: None)
    monkeypatch.setenv("DUOSAVE_COMMIT", "abcdef1234567890")
    monkeypatch.setenv("DUOSAVE_REPO_URL", "git@github.com:me/fork.git")

    info = buildinfo.build_info()

    assert info["version"] == __version__
    assert info["commit"] == "abcdef1234567890"
    assert info["short"] == "abcdef1"
    assert info["commit_url"] == "https://github.com/me/fork/commit/abcdef1234567890"
    assert info["commit_date"] is None
    assert info["dirty"] is False


def test_github_sha_used_as_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(buildinfo, "_git", lambda *args: None)
    monkeypatch.delenv("DUOSAVE_COMMIT", raising=False)
    monkeypatch.setenv("GITHUB_SHA", "deadbeefcafe")

    assert buildinfo.build_info()["commit"] == "deadbeefcafe"


COMMIT = "9c96590477f7437519264fce8aeb3f298b985961"


def _git_dir_with_head(tmp_path: Path, head: str) -> Path:
    """Git directory like the trimmed copy baked into the image: HEAD and refs, no objects."""
    directory = tmp_path / ".git"
    (directory / "refs" / "heads").mkdir(parents=True)
    (directory / "HEAD").write_text(head, encoding="utf-8")
    return directory


def test_head_commit_from_a_loose_ref(tmp_path: Path) -> None:
    directory = _git_dir_with_head(tmp_path, "ref: refs/heads/master\n")
    (directory / "refs" / "heads" / "master").write_text(f"{COMMIT}\n", encoding="utf-8")

    assert buildinfo.head_commit(directory) == COMMIT


def test_head_commit_from_packed_refs(tmp_path: Path) -> None:
    directory = _git_dir_with_head(tmp_path, "ref: refs/heads/master\n")
    (directory / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{'b' * 40} refs/remotes/origin/master\n"
        f"{COMMIT} refs/heads/master\n",
        encoding="utf-8",
    )

    assert buildinfo.head_commit(directory) == COMMIT


def test_head_commit_on_a_detached_head(tmp_path: Path) -> None:
    assert buildinfo.head_commit(_git_dir_with_head(tmp_path, COMMIT)) == COMMIT


def test_head_commit_follows_a_worktree_pointer(tmp_path: Path) -> None:
    directory = _git_dir_with_head(tmp_path / "main", "ref: refs/heads/master\n")
    (directory / "refs" / "heads" / "master").write_text(COMMIT, encoding="utf-8")
    pointer = tmp_path / "worktree" / ".git"
    pointer.parent.mkdir()
    pointer.write_text(f"gitdir: {directory}\n", encoding="utf-8")

    assert buildinfo.head_commit(pointer) == COMMIT


def test_head_commit_without_metadata(tmp_path: Path) -> None:
    assert buildinfo.head_commit(tmp_path / ".git") is None


def test_commit_from_the_baked_git_copy_when_git_is_unavailable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The container has neither git nor history: HEAD of the baked copy is the commit."""
    directory = _git_dir_with_head(tmp_path, "ref: refs/heads/master\n")
    (directory / "refs" / "heads" / "master").write_text(COMMIT, encoding="utf-8")
    monkeypatch.setattr(buildinfo, "REPO", tmp_path)
    monkeypatch.setattr(buildinfo, "_git", lambda *args: None)
    monkeypatch.delenv("DUOSAVE_COMMIT", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    info = buildinfo.build_info()

    assert info["commit"] == COMMIT
    assert info["short"] == COMMIT[:7]
    assert info["commit_url"] == f"https://github.com/northis/duosave/commit/{COMMIT}"
    assert info["dirty"] is False


def test_without_git_and_metadata_only_version_is_known(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(buildinfo, "REPO", tmp_path)  # no .git: a source archive, not a checkout
    monkeypatch.setattr(buildinfo, "_git", lambda *args: None)
    monkeypatch.delenv("DUOSAVE_COMMIT", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.delenv("DUOSAVE_REPO_URL", raising=False)

    assert buildinfo.build_info() == {
        "version": __version__,
        "commit": None,
        "short": None,
        "commit_url": None,
        "commit_date": None,
        "dirty": False,
        "repo_url": "https://github.com/northis/duosave",
        "tag": f"v{__version__}",
        "tag_url": f"https://github.com/northis/duosave/tree/v{__version__}",
    }


def test_baked_commit_date_used_without_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(buildinfo, "_git", lambda *args: None)
    monkeypatch.setenv("DUOSAVE_COMMIT", "abc1234567890")
    monkeypatch.setenv("DUOSAVE_COMMIT_DATE", "2026-10-12T10:00:00+03:00")

    info = buildinfo.build_info()

    assert info["commit_date"] == "2026-10-12T10:00:00+03:00"
    assert info["dirty"] is False


def test_empty_env_values_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(buildinfo, "_git", lambda *args: None)
    monkeypatch.setenv("DUOSAVE_COMMIT", "")
    monkeypatch.setenv("GITHUB_SHA", "cafe")
    monkeypatch.setenv("DUOSAVE_REPO_URL", "")
    monkeypatch.delenv("DUOSAVE_COMMIT_DATE", raising=False)

    info = buildinfo.build_info()

    assert info["commit"] == "cafe"
    assert info["repo_url"] == "https://github.com/northis/duosave"


def test_repo_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(buildinfo, "_git", lambda *args: None)
    monkeypatch.setenv("DUOSAVE_REPO_URL", "git@github.com:me/fork.git")

    assert buildinfo.build_info()["repo_url"] == "https://github.com/me/fork"


def test_api_version_endpoint(tmp_db: sqlite3.Connection) -> None:
    with TestClient(app) as client:
        response = client.get("/api/version")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == __version__
    assert set(data) == {
        "version", "commit", "short", "commit_url", "commit_date", "dirty", "repo_url",
        "tag", "tag_url",
    }
    assert data["repo_url"] == "https://github.com/northis/duosave"


def test_ui_version_badge_links_to_the_release_tag() -> None:
    """The version badge opens the release tag; the commit badge keeps the commit page."""
    static = Path(__file__).resolve().parents[1] / "duosave" / "server" / "static"
    js = (static / "app.js").read_text(encoding="utf-8")

    assert "buildInfo.tag_url" in js
    assert '"/tree/v" + buildInfo.version' in js
    assert "buildInfo.commit_url" in js


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"duosave {__version__}"
