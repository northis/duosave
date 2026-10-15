"""Host-side console update: `deploy/windows/update.ps1` (text checks, no Docker, no git calls).

2.3 dropped the self-update daemon (`duosave/updater.py` + `data/control/`): the site no
longer requests updates, and the host pulls, builds and restarts from the console instead.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = (REPO / "deploy" / "windows" / "update.ps1").read_text(encoding="utf-8")
README = (REPO / "README.md").read_text(encoding="utf-8")
AGENTS = (REPO / "AGENTS.md").read_text(encoding="utf-8")


def test_the_self_update_daemon_is_gone() -> None:
    for name in ("duosave/updater.py", "duosave/control.py", "tests/test_updater.py",
                 "tests/test_control.py", "tests/test_api_admin_update.py",
                 "deploy/windows/install-updater.ps1"):
        assert not (REPO / name).exists(), name


def test_script_fast_forwards_and_never_rewrites_the_working_copy() -> None:
    # --tags: a fetch with an explicit refspec does not follow tags, and the release tag
    # must land locally for the version check below (see test_script_fetches_release_tags).
    assert '"fetch", "--prune", "--tags", "origin", $Branch' in SCRIPT
    assert '"merge", "--ff-only"' in SCRIPT
    assert 'Set-StrictMode -Version Latest' in SCRIPT
    assert '$ErrorActionPreference = "Stop"' in SCRIPT
    for destructive in ('"reset"', '"clean"', '"stash"', '"checkout"'):
        assert destructive not in SCRIPT, destructive


def test_script_fetches_release_tags() -> None:
    """`git fetch <remote> <branch>` updates origin/<branch> but follows no tags: without
    --tags the release tag never reaches the working copy, so the version check warns on
    every release (and the operator sees a tag that was never pulled)."""
    fetch = next(line for line in SCRIPT.splitlines() if '"fetch"' in line)

    assert '"--tags"' in fetch
    assert '"tag", "--points-at", $target' in SCRIPT


def test_powershell_scripts_stay_ascii_only() -> None:
    """Windows PowerShell 5.1 decodes a BOM-less script with the system codepage.

    A UTF-8 em dash (E2 80 94) becomes three characters whose last one is a smart quote
    (U+201D); PowerShell accepts smart quotes as string delimiters, so the string ends
    early and the rest of the line is parsed and run as commands: the warning text
    "(see AGENTS.md)" once ran a command named `see` and aborted the update right after
    the fast-forward. A BOM would fix the decoding, an ASCII-only file cannot break.
    """
    for path in sorted(REPO.rglob("*.ps1")):
        if ".git" in path.parts:
            continue
        assert path.read_bytes().isascii(), f"{path} must stay ASCII-only"


def test_script_builds_from_a_clean_worktree_with_baked_metadata() -> None:
    assert '"worktree", "add", "--detach"' in SCRIPT
    assert '"worktree", "remove", "--force"' in SCRIPT
    assert '"build", "-t", "${Image}:latest", "-t", "${Image}:$short"' in SCRIPT
    for build_arg in ("DUOSAVE_COMMIT=$target", "DUOSAVE_COMMIT_DATE=$commitDate",
                      "DUOSAVE_VERSION=$version", "DUOSAVE_CREATED=$created"):
        assert f'"--build-arg", "{build_arg}"' in SCRIPT
    assert "Get-Version" in SCRIPT and "duosave/__init__.py" in SCRIPT


def test_script_restarts_waits_for_health_and_rolls_back() -> None:
    assert '"compose", "--project-directory", $Repo' in SCRIPT
    assert '"up", "-d", "--no-build", $Container' in SCRIPT
    assert "api/version" in SCRIPT and "Wait-ContainerReady" in SCRIPT
    assert '"image", "tag", "${Image}:previous", "${Image}:latest"' in SCRIPT
    assert "Restore-PreviousImage" in SCRIPT
    assert "-Rollback" in SCRIPT and '"snapshot", "--label", "pre-update"' in SCRIPT
    assert '"image", "rm"' in SCRIPT  # old duosave:<sha> images are pruned


def test_script_warns_when_the_commit_has_no_version_tag() -> None:
    assert '"tag", "--points-at", $target' in SCRIPT
    assert 'not tagged v$version' in SCRIPT


def test_docs_point_at_the_script() -> None:
    assert "deploy\\windows\\update.ps1" in README
    assert "deploy\\windows\\update.ps1" in AGENTS


def test_agents_document_the_version_and_tag_rules() -> None:
    assert "## Versioning" in AGENTS
    assert "duosave/__init__.py" in AGENTS
    assert "git tag -a v" in AGENTS
    assert "--follow-tags" in AGENTS
