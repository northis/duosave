"""Version and commit info of the running copy (shown in the site header)."""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache

from . import __version__
from .config import REPO

DEFAULT_REPO_URL = "https://github.com/northis/duosave"
SHORT_COMMIT_LEN = 7


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
    for packaged builds without a checkout.
    """
    commit = (
        os.environ.get("DUOSAVE_COMMIT")
        or os.environ.get("GITHUB_SHA")
        or _git("rev-parse", "HEAD")
    )
    repo_url = normalize_repo_url(
        os.environ.get("DUOSAVE_REPO_URL")
        or _git("remote", "get-url", "origin")
        or DEFAULT_REPO_URL
    )
    return {
        "version": __version__,
        "commit": commit,
        "short": commit[:SHORT_COMMIT_LEN] if commit else None,
        "commit_url": f"{repo_url}/commit/{commit}" if commit else None,
        "commit_date": _git("show", "-s", "--format=%cI", commit) if commit else None,
        "dirty": bool(_git("status", "--porcelain")) if commit else False,
    }
