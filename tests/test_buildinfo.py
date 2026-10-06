"""Build info: version, commit resolution, remote URL normalization, /api/version."""

from __future__ import annotations

import sqlite3

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


def test_version_is_2_1_0() -> None:
    assert __version__ == "2.1.0"


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


def test_without_git_only_version_is_known(monkeypatch: pytest.MonkeyPatch) -> None:
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
    }


def test_api_version_endpoint(tmp_db: sqlite3.Connection) -> None:
    with TestClient(app) as client:
        response = client.get("/api/version")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == __version__
    assert set(data) == {"version", "commit", "short", "commit_url", "commit_date", "dirty"}


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"duosave {__version__}"
