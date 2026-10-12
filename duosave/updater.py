"""Host-side updater: polls `<data>/control/`, runs git/docker, writes status and log.

stdlib only, runs on the host Python (the container never gets docker.sock). Every
external command goes through `CommandRunner`, so tests replace it with a fake.
Protocol: contracts/updater-protocol.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from . import __version__, control

POLL_INTERVAL = 5
FETCH_INTERVAL = 15 * 60
FETCH_TIMEOUT = 120
BUILD_TIMEOUT = 30 * 60
HEALTH_TIMEOUT = 120
HEALTH_INTERVAL = 3
HEALTH_COMMAND_TIMEOUT = 15
KEEP_IMAGES = 3
SELF_UPDATE_EXIT = 75
CONTAINER = "duosave"
IMAGE = "duosave"
WATCHED_FILES = ("duosave/updater.py", "duosave/control.py")
DESTRUCTIVE_GIT = {"reset", "clean", "stash", "checkout", "restore", "switch"}

HEALTH_CODE = ("import json,urllib.request;"
               "print(json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/version',"
               "timeout=3))['commit'] or '')")


@dataclass
class Completed:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(self, argv: list[str], cwd: Path | None, timeout: int | None) -> Completed:
        ...


class SubprocessRunner:
    """Real runner: subprocess.run, no shell, no console window on Windows."""

    def run(self, argv: list[str], cwd: Path | None, timeout: int | None) -> Completed:
        kwargs: dict = {"capture_output": True, "text": True, "check": False}
        if cwd is not None:
            kwargs["cwd"] = str(cwd)
        if timeout is not None:
            kwargs["timeout"] = timeout
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.run(argv, **kwargs)
        except FileNotFoundError as exc:
            return Completed(127, "", str(exc))
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            return Completed(124, stdout, "timeout")
        return Completed(proc.returncode, proc.stdout or "", proc.stderr or "")


class _Fail(Exception):
    """A step that must stop the job with a protocol reason."""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason
        self.message = message


class Runner:
    """The updater state machine: one tick polls the request file, one job runs at a time."""

    def __init__(self, repo: Path, data_dir: Path, branch: str = "master",
                 runner: CommandRunner | None = None, clock=time.time, sleep=time.sleep) -> None:
        self.repo = Path(repo)
        self.data_dir = Path(data_dir)
        self.branch = branch
        self.runner = runner or SubprocessRunner()
        self.clock = clock
        self.sleep = sleep
        self._lock = None
        self._status: dict = {}
        self._last_check = float("-inf")

    # ------------------------------------------------------------------ protocol

    def acquire_lock(self) -> bool:
        self._lock = control.acquire_lock(control.lock_path(self.data_dir))
        return self._lock is not None

    def read_status(self) -> dict | None:
        return control.read_json(control.status_path(self.data_dir))

    def write_status(self) -> None:
        control.write_json_atomic(control.status_path(self.data_dir), self._status)

    def log(self, message: str) -> None:
        control.append_log(control.log_path(self.data_dir), message)

    def startup(self) -> None:
        """Load the status, fail an interrupted job, record this process."""
        status = self.read_status() or {}
        job = status.get("job")
        if isinstance(job, dict) and job.get("state") == "running":
            job.update({"state": "failed", "reason": "interrupted", "step": None,
                        "finished_at": control.utc_now(), "message": "previous process died"})
            self.log("job interrupted: marked as failed")
            self._run(["git", "worktree", "prune"])
        self._status = status
        self._status["job"] = job
        self._status.setdefault("repo", {})
        self._status.setdefault("deployed", {})
        runner = self._status.setdefault("runner", {})
        runner.update({"pid": os.getpid(), "version": __version__, "branch": self.branch,
                       "started_at": control.utc_now(), "heartbeat_at": control.utc_now()})
        self.write_status()

    def tick(self) -> None:
        """One loop iteration: heartbeat, claim a request, run the periodic check."""
        self._status.setdefault("runner", {})["heartbeat_at"] = control.utc_now()
        if control.request_path(self.data_dir).exists():
            self._claim_request()
        else:
            self.write_status()
        if self.clock() - self._last_check >= FETCH_INTERVAL:
            self.run_check()

    def run_forever(self) -> int:
        if not self.acquire_lock():
            print("duosave.updater: already running")
            return 0
        self.startup()
        while True:
            self.tick()
            self.sleep(POLL_INTERVAL)

    # --------------------------------------------------------------------- steps

    def _run(self, argv: list[str], timeout: int | None = None) -> Completed:
        return self.runner.run(list(argv), self.repo, timeout)

    def _git(self, *args: str) -> str | None:
        result = self._run(["git", *args])
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _job(self, action: str, request: dict | None = None) -> dict:
        job = {"id": (request or {}).get("id"), "action": action, "state": "running",
               "step": None, "from": None, "to": None,
               "requested_by": (request or {}).get("requested_by"),
               "started_at": control.utc_now(), "finished_at": None, "reason": None,
               "message": ""}
        self._status["job"] = job
        return job

    def _step(self, job: dict, step: str, message: str = "") -> None:
        job["step"] = step
        job["message"] = message or step
        self.log(f"{job['action']}: {step} {message}".rstrip())
        self.write_status()

    def _finish(self, job: dict, state: str, reason: str | None = None,
                message: str = "") -> None:
        job.update({"state": state, "reason": reason, "step": None,
                    "message": message or job.get("message", ""),
                    "finished_at": control.utc_now()})
        self.write_status()
        suffix = f" ({reason})" if reason else ""
        self.log(f"{job['action']}: {state}{suffix}")

    def _docker_inspect(self) -> dict:
        result = self._run(["docker", "inspect", CONTAINER, "--format",
                            '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
                            "|{{.State.Status}}|{{.Config.Image}}"])
        if result.returncode != 0:
            return {"revision": None, "running": False, "image": None}
        revision, _, rest = result.stdout.strip().partition("|")
        status, _, image = rest.partition("|")
        return {"revision": revision or None, "running": status.strip() == "running",
                "image": image.strip() or None}

    def _refresh_repo(self, repo: dict) -> None:
        head = self._git("rev-parse", "HEAD")
        remote = self._git("rev-parse", f"origin/{self.branch}")
        repo["head"] = head
        repo["remote"] = remote
        behind = ahead = 0
        counts = self._git("rev-list", "--left-right", "--count",
                           f"HEAD...origin/{self.branch}")
        if counts:
            parts = counts.split()
            if len(parts) == 2 and all(part.isdigit() for part in parts):
                behind, ahead = int(parts[0]), int(parts[1])
        repo["behind"] = behind
        repo["ahead"] = ahead
        repo["dirty"] = bool(self._git("status", "--porcelain"))

    def _refresh_deployed(self) -> None:
        deployed = self._status.setdefault("deployed", {})
        info = self._docker_inspect()
        deployed["commit"] = info["revision"]
        deployed["image"] = info["image"]
        deployed["checked_at"] = control.utc_now()

    # --------------------------------------------------------------------- jobs

    def run_check(self, job: dict | None = None) -> dict:
        """fetch + refresh repo/deployed; errors are warnings, not failures."""
        job = job or self._job("check")
        self._step(job, "fetch", f"git fetch --prune origin {self.branch}")
        fetch = self._run(["git", "fetch", "--prune", "origin", self.branch],
                          timeout=FETCH_TIMEOUT)
        self._last_check = self.clock()
        repo = self._status.setdefault("repo", {})
        repo["fetched_at"] = control.utc_now()
        repo["fetch_error"] = None
        if fetch.returncode != 0:
            repo["fetch_error"] = fetch.stderr.strip() or "git fetch failed"
            self.log(f"warning: {repo['fetch_error']}")
        self._refresh_repo(repo)
        self._refresh_deployed()
        self._finish(job, "succeeded")
        return job

    def _claim_request(self) -> None:
        request_file = control.request_path(self.data_dir)
        processing = control.processing_path(self.data_dir)
        request = control.read_json(request_file)
        try:
            os.replace(request_file, processing)
        except OSError:
            return
        parsed = control.parse_request(request)
        if parsed is None:
            self.log("discarded an invalid update request")
            processing.unlink(missing_ok=True)
            self.write_status()
            return
        request_id, action = parsed
        self.log(f"request {request_id}: {action}")
        try:
            if action == "update":
                self.run_update(self._job("update", request))
            else:
                self.run_check(self._job("check", request))
        finally:
            processing.unlink(missing_ok=True)

    def _wait_healthy(self, expected: str | None) -> bool:
        if not expected:
            return False
        deadline = self.clock() + HEALTH_TIMEOUT
        while self.clock() < deadline:
            commit = self._container_commit()
            if commit and commit.startswith(expected[:12]):
                return True
            self.sleep(HEALTH_INTERVAL)
        return False

    def _container_commit(self) -> str | None:
        result = self._run(["docker", "exec", CONTAINER, "python", "-c", HEALTH_CODE],
                           timeout=HEALTH_COMMAND_TIMEOUT)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _prune_images(self) -> None:
        listing = self._run(["docker", "image", "ls", IMAGE, "--format",
                             "{{.Tag}}\t{{.CreatedAt}}"])
        if listing.returncode != 0:
            return
        rows = []
        for line in listing.stdout.splitlines():
            tag, _, created = line.partition("\t")
            tag = tag.strip()
            if re.fullmatch(r"[0-9a-f]{12}", tag):
                rows.append((created.strip(), tag))
        rows.sort(reverse=True)
        for _, tag in rows[KEEP_IMAGES:]:
            self.log(f"cleanup: removing image {IMAGE}:{tag}")
            self._run(["docker", "image", "rm", f"{IMAGE}:{tag}"])

    def _self_update_needed(self, job: dict) -> bool:
        source, target = job.get("from"), job.get("to")
        if not source or not target or source == target:
            return False
        result = self._run(["git", "diff", "--name-only", source, target, "--",
                            *WATCHED_FILES])
        return result.returncode == 0 and bool(result.stdout.strip())

    def _rollback(self, job: dict, fail: _Fail) -> None:
        self._step(job, "rollback", fail.message)
        self._run(["docker", "image", "tag", f"{IMAGE}:previous", f"{IMAGE}:latest"])
        compose = self._run(["docker", "compose", "--project-directory", str(self.repo),
                             "up", "-d", "--no-build", CONTAINER])
        if compose.returncode == 0 and self._wait_healthy(job.get("from")):
            self._finish(job, "rolled_back", fail.reason, fail.message)
        else:
            self._finish(job, "rollback_failed", "rollback_failed",
                         "rollback container did not become healthy")

    def run_update(self, job: dict | None = None) -> dict:
        """The `update` job: ff-merge, build from a clean worktree, restart, verify."""
        job = job or self._job("update")
        temporary: Path | None = None
        try:
            self._step(job, "fetch", f"git fetch --prune origin {self.branch}")
            fetch = self._run(["git", "fetch", "--prune", "origin", self.branch],
                              timeout=FETCH_TIMEOUT)
            self._last_check = self.clock()
            if fetch.returncode != 0:
                raise _Fail("fetch_failed", fetch.stderr.strip() or "git fetch failed")

            self._step(job, "verify", "branch")
            branch = self._run(["git", "symbolic-ref", "--short", "HEAD"])
            if branch.returncode != 0 or branch.stdout.strip() != self.branch:
                raise _Fail("wrong_branch", branch.stdout.strip() or "detached HEAD")

            self._step(job, "merge", f"git merge --ff-only origin/{self.branch}")
            merge = self._run(["git", "merge", "--ff-only", f"origin/{self.branch}"])
            if merge.returncode != 0:
                raise _Fail("not_fast_forward", merge.stderr.strip() or merge.stdout.strip())

            head = self._git("rev-parse", "HEAD")
            remote = self._git("rev-parse", f"origin/{self.branch}")
            if not head or head != remote:
                raise _Fail("unpushed_commits", f"HEAD {head} != origin/{self.branch} {remote}")

            self._step(job, "compare", "docker inspect")
            info = self._run(["docker", "info"])
            if info.returncode != 0:
                raise _Fail("docker_unavailable", info.stderr.strip() or "docker is not running")
            deployed = self._docker_inspect()
            job["from"] = deployed["revision"]
            job["to"] = head
            self._refresh_repo(self._status.setdefault("repo", {}))
            self._status.setdefault("deployed", {}).update(
                {"commit": deployed["revision"], "image": deployed["image"],
                 "checked_at": control.utc_now()})
            if deployed["revision"] == head and deployed["running"]:
                self._finish(job, "noop", None, "already running this commit")
                return job

            self._step(job, "snapshot", "docker exec snapshot --label pre-update")
            snapshot = self._run(["docker", "exec", CONTAINER, "python", "-m", "duosave",
                                  "snapshot", "--label", "pre-update"])
            if snapshot.returncode != 0:
                self.log(f"warning: snapshot failed: {snapshot.stderr.strip()}")

            short = head[:12]
            temporary = Path(tempfile.gettempdir()) / f"duosave-build-{short}"
            shutil.rmtree(temporary, ignore_errors=True)
            self._step(job, "worktree", f"git worktree add --detach {temporary} {short}")
            worktree = self._run(["git", "worktree", "add", "--detach", str(temporary), head],
                                 timeout=FETCH_TIMEOUT)
            if worktree.returncode != 0:
                raise _Fail("build_failed", worktree.stderr.strip() or "git worktree add failed")

            self._step(job, "build", "docker build")
            if self._run(["docker", "image", "inspect", f"{IMAGE}:latest"]).returncode == 0:
                self._run(["docker", "image", "tag", f"{IMAGE}:latest", f"{IMAGE}:previous"])
            date = self._git("show", "-s", "--format=%cI", head) or control.utc_now()
            build = self._run([
                "docker", "build", "-t", f"{IMAGE}:latest", "-t", f"{IMAGE}:{short}",
                "--build-arg", f"DUOSAVE_COMMIT={head}",
                "--build-arg", f"DUOSAVE_COMMIT_DATE={date}",
                "--build-arg", f"DUOSAVE_VERSION={__version__}",
                "--build-arg", f"DUOSAVE_CREATED={control.utc_now()}",
                str(temporary),
            ], timeout=BUILD_TIMEOUT)
            if build.returncode != 0:
                raise _Fail("build_failed", build.stderr.strip() or "docker build failed")

            self._step(job, "restart", "docker compose up -d --no-build")
            compose = self._run(["docker", "compose", "--project-directory", str(self.repo),
                                 "up", "-d", "--no-build", CONTAINER])
            if compose.returncode != 0:
                raise _Fail("compose_failed", compose.stderr.strip() or "docker compose failed")

            self._step(job, "health", "waiting for the new container")
            if not self._wait_healthy(head):
                raise _Fail("unhealthy", "the new container did not become healthy")
            self._status.setdefault("deployed", {}).update(
                {"commit": head, "checked_at": control.utc_now()})
            self._finish(job, "succeeded")
        except _Fail as fail:
            if fail.reason in ("compose_failed", "unhealthy"):
                self._rollback(job, fail)
            else:
                self._finish(job, "failed", fail.reason, fail.message)
        finally:
            if temporary is not None:
                self._run(["git", "worktree", "remove", "--force", str(temporary)])
                self._run(["git", "worktree", "prune"])
            self._prune_images()
        if self._self_update_needed(job):
            self.log("updater code changed: exiting 75 so the task restarts it")
            raise SystemExit(SELF_UPDATE_EXIT)
        return job


def _env_value(path: Path, key: str) -> str | None:
    """Read KEY=VALUE from a dotenv file (comments and blanks ignored)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() == key:
            return value.strip().strip('"').strip("'") or None
    return None


def resolve_data_dir(arg: str | None, repo: Path) -> Path:
    """--data-dir > DUOSAVE_DATA_DIR from <repo>/.env > <repo>/data."""
    repo = Path(repo)
    value = arg or _env_value(repo / ".env", "DUOSAVE_DATA_DIR")
    if not value:
        return repo / "data"
    path = Path(value)
    return path if path.is_absolute() else (repo / path).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m duosave.updater",
                                     description="Duosave host-side updater")
    parser.add_argument("command", choices=["run", "update", "check", "status"])
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--branch", default="master")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    data_dir = resolve_data_dir(args.data_dir, repo)

    if args.command == "status":
        status = control.read_json(control.status_path(data_dir))
        print(json.dumps(status, ensure_ascii=False, indent=2) if status else "{}")
        print("runner: alive" if control.runner_alive(status) else "runner: not responding")
        return 0

    runner = Runner(repo, data_dir, branch=args.branch)
    if args.command == "run":
        return runner.run_forever()
    if not runner.acquire_lock():
        print("duosave.updater: already running")
        return 0
    runner.startup()
    job = runner.run_update() if args.command == "update" else runner.run_check()
    return 0 if job.get("state") in ("succeeded", "noop") else 1


if __name__ == "__main__":
    sys.exit(main())
