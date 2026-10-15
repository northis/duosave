"""Version and commit info of the running copy (shown in the site header)."""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

from . import __version__
from .config import REPO

DEFAULT_REPO_URL = "https://github.com/northis/duosave"
SHORT_COMMIT_LEN = 7


def _env(name: str) -> str | None:
    """Environment value; empty strings are treated as absent (compose passes "")."""
    value = os.environ.get(name, "").strip()
    return value or None


def _git(*args: str) -> str | None:
    """Run a git command in the repository; None if git or the command is unavailable."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(REPO), *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = proc.stdout.strip()
    return output if proc.returncode == 0 and output else None


def _git_dir(path: Path) -> Path | None:
    """Git directory behind `path`: itself, or the target of a `gitdir:` pointer file."""
    if path.is_dir():
        return path
    try:
        pointer = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not pointer.startswith("gitdir:"):
        return None
    target = (path.parent / pointer[len("gitdir:"):].strip()).resolve()
    return target if target.is_dir() else None


def _packed_ref(path: Path, ref: str) -> str | None:
    """Commit of `ref` from `packed-refs`: `git pack-refs` moves loose refs there."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith(("#", "^")):
            continue
        commit, _, name = line.partition(" ")
        if name.strip() == ref:
            return commit.strip() or None
    return None


def head_commit(git_dir: Path) -> str | None:
    """Commit HEAD points at, read from the git directory without running git.

    The image has no git and only a trimmed `.git` (HEAD and refs — see .dockerignore), so a
    plain `docker compose up -d --build` still reports the commit it was built from. Detached
    HEAD, loose refs and packed refs are handled; anything else is None.
    """
    directory = _git_dir(git_dir)
    if directory is None:
        return None
    try:
        head = (directory / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return head or None
    ref = head[len("ref:"):].strip()
    try:
        loose = (directory / ref).read_text(encoding="utf-8").strip()
    except OSError:
        loose = ""
    return loose or _packed_ref(directory / "packed-refs", ref)


def normalize_repo_url(url: str) -> str:
    """Convert any git remote URL (https, ssh, git@host:path) to a browsable https URL."""
    url = url.strip()
    if url.startswith("git@") and ":" in url:
        host, path = url[len("git@"):].split(":", 1)
        url = f"https://{host}/{path}"
    elif url.startswith("ssh://git@"):
        url = "https://" + url[len("ssh://git@"):]
    elif url.startswith("git://"):
        url = "https://" + url[len("git://"):]
    return url.removesuffix(".git").rstrip("/")


@lru_cache(maxsize=1)
def build_info() -> dict:
    """Version, commit and commit URL of the running copy.

    Cached: the commit cannot change while the process is alive. `DUOSAVE_COMMIT`
    (or `GITHUB_SHA`) and `DUOSAVE_REPO_URL` override git discovery, which is useful
    for packaged builds without a checkout. Without git (the container) the commit comes
    from the `.git` copy the image was built with — see .dockerignore.
    """
    commit = (_env("DUOSAVE_COMMIT") or _env("GITHUB_SHA")
              or _git("rev-parse", "HEAD") or head_commit(REPO / ".git"))
    repo_url = normalize_repo_url(
        _env("DUOSAVE_REPO_URL")
        or _git("remote", "get-url", "origin")
        or DEFAULT_REPO_URL
    )
    commit_date = None
    if commit:
        commit_date = _git("show", "-s", "--format=%cI", commit) or _env("DUOSAVE_COMMIT_DATE")
    return {
        "version": __version__,
        "commit": commit,
        "short": commit[:SHORT_COMMIT_LEN] if commit else None,
        "commit_url": f"{repo_url}/commit/{commit}" if commit else None,
        "commit_date": commit_date,
        "dirty": bool(_git("status", "--porcelain")) if commit else False,
        "repo_url": repo_url,
        "tag": f"v{__version__}",
        "tag_url": f"{repo_url}/tree/v{__version__}",
    }
