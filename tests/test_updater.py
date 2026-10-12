"""Updater: check/update jobs, refusals, rollback, request handling, self-update."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from duosave import __version__, control, updater
from duosave.updater import Completed, Runner

SHA = "9c96590477f7437519264fce8aeb3f298b985961"
SHA12 = SHA[:12]
NEW = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
NEW12 = NEW[:12]
STRANGER = "c" * 40


class FakeCommandRunner:
    """Scenario runner: longest argv prefix wins; a list of results is consumed in order.

    A plain `Completed` answers every matching call; `[Completed(...), Completed(...)]`
    models a command that behaves differently the second time (for example
    `docker compose up` failing and then succeeding during a rollback).
    """

    def __init__(self, scenario: list[tuple[tuple[str, ...], Completed | list]]) -> None:
        self.scenario: list[tuple[tuple[str, ...], list[Completed]]] = []
        for prefix, result in scenario:
            results = result if isinstance(result, list) else [result]
            self.scenario.append((tuple(prefix), list(results)))
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, cwd=None, timeout=None) -> Completed:
        call = tuple(argv)
        self.calls.append(call)
        matches = [(len(prefix), index) for index, (prefix, results) in enumerate(self.scenario)
                   if results and call[:len(prefix)] == prefix]
        if not matches:
            raise AssertionError(f"unexpected command: {argv}")
        _, index = max(matches, key=lambda item: item[0])
        results = self.scenario[index][1]
        return results.pop(0) if len(results) > 1 else results[0]


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _runner(tmp_path: Path, scenario, clock: FakeClock | None = None,
            branch: str = "master") -> Runner:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    clock = clock or FakeClock()
    return Runner(repo, tmp_path / "data", branch=branch,
                  runner=FakeCommandRunner(scenario), clock=clock.time, sleep=clock.sleep)


def _check_scenario(behind: str = "3\t0", dirty: str = " M README.md",
                    deployed: str = f"{SHA}|running|duosave:latest") -> list:
    return [
        (("git", "fetch"), Completed(0)),
        (("git", "rev-parse", "HEAD"), Completed(0, SHA)),
        (("git", "rev-parse", "origin/master"), Completed(0, NEW)),
        (("git", "rev-list"), Completed(0, behind)),
        (("git", "status", "--porcelain"), Completed(0, dirty)),
        (("docker", "inspect", "duosave"), Completed(0, deployed)),
    ]


def _update_scenario(*, branch: str = "master", merge: Completed | None = None,
                     head: str = NEW, remote: str = NEW, docker_info: Completed | None = None,
                     deployed: str = f"{SHA}|running|duosave:latest",
                     snapshot: Completed | None = None, build: Completed | None = None,
                     compose: Completed | None = None, health: str = NEW,
                     diff: str = "", extra: list | None = None) -> list:
    return [
        (("git", "fetch"), Completed(0)),
        (("git", "symbolic-ref"), Completed(0, branch)),
        (("git", "merge"), merge or Completed(0)),
        (("git", "rev-parse", "HEAD"), Completed(0, head)),
        (("git", "rev-parse", "origin/master"), Completed(0, remote)),
        (("git", "rev-list"), Completed(0, "1\t0")),
        (("git", "status", "--porcelain"), Completed(0)),
        (("docker", "info"), docker_info or Completed(0)),
        (("docker", "inspect", "duosave"), Completed(0, deployed)),
        (("docker", "exec", "duosave", "python", "-m", "duosave", "snapshot"),
         snapshot or Completed(0)),
        (("git", "worktree", "add"), Completed(0)),
        (("docker", "image", "inspect"), Completed(0)),
        (("docker", "image", "tag"), Completed(0)),
        (("docker", "build"), build or Completed(0)),
        (("docker", "compose"), compose or Completed(0)),
        (("docker", "exec", "duosave", "python", "-c"), Completed(0, health)),
        (("git", "worktree", "remove"), Completed(0)),
        (("git", "worktree", "prune"), Completed(0)),
        (("docker", "image", "ls"), Completed(
            0, "latest\t2026-10-12 10:00:00\nprevious\t2026-10-11 10:00:00\n"
               "aaaaaaaaaaaa\t2026-10-10 10:00:00\nbbbbbbbbbbbb\t2026-10-09 10:00:00\n"
               "cccccccccccc\t2026-10-08 10:00:00\ndddddddddddd\t2026-10-07 10:00:00\n")),
        (("docker", "image", "rm"), Completed(0)),
        (("git", "show"), Completed(0, "2026-10-12T10:00:00+03:00")),
        (("git", "diff", "--name-only"), Completed(0, diff)),
    ] + (extra or [])


def _status(runner: Runner) -> dict:
    return json.loads(control.status_path(runner.data_dir).read_text(encoding="utf-8"))


def _index_of(calls: list[tuple[str, ...]], *prefix: str) -> int:
    return next(index for index, call in enumerate(calls) if call[:len(prefix)] == prefix)


# ---------------------------------------------------------------------- check


def test_check_job_updates_repo_and_deployed(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _check_scenario())
    runner.startup()

    job = runner.run_check()

    assert job["state"] == "succeeded"
    status = _status(runner)
    assert status["repo"]["head"] == SHA
    assert status["repo"]["remote"] == NEW
    assert status["repo"]["behind"] == 3
    assert status["repo"]["ahead"] == 0
    assert status["repo"]["dirty"] is True
    assert status["repo"]["fetched_at"]
    assert status["repo"]["fetch_error"] is None
    assert status["deployed"]["commit"] == SHA


def test_check_job_records_fetch_error(tmp_path: Path) -> None:
    scenario = _check_scenario()
    scenario[0] = (("git", "fetch"), Completed(1, "", "no network"))
    runner = _runner(tmp_path, scenario)
    runner.startup()

    job = runner.run_check()

    assert job["state"] == "succeeded"
    assert _status(runner)["repo"]["fetch_error"] == "no network"


# ------------------------------------------------------------------- refusals


def test_update_fetch_failed(tmp_path: Path) -> None:
    scenario = _update_scenario()
    scenario[0] = (("git", "fetch"), Completed(1, "", "no network"))
    runner = _runner(tmp_path, scenario)
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("failed", "fetch_failed")
    assert not any(call[:2] == ("git", "merge") for call in runner.runner.calls)


def test_update_wrong_branch(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(branch="feature"))
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("failed", "wrong_branch")
    assert not any(call[:2] == ("docker", "build") for call in runner.runner.calls)
    assert not any(call[:2] == ("docker", "compose") for call in runner.runner.calls)


def test_update_not_fast_forward(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(merge=Completed(1, "", "CONFLICT (content)")))
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("failed", "not_fast_forward")
    assert "CONFLICT" in job["message"]
    assert not any(call[:2] == ("docker", "build") for call in runner.runner.calls)
    assert not any(call[:2] == ("docker", "compose") for call in runner.runner.calls)


def test_update_unpushed_commits(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(head=SHA, remote=NEW))
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("failed", "unpushed_commits")


def test_update_docker_unavailable(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(docker_info=Completed(1, "", "no docker")))
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("failed", "docker_unavailable")
    assert not any(call[:2] == ("docker", "build") for call in runner.runner.calls)


def test_update_noop_when_deployed(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(head=NEW, remote=NEW,
                                                deployed=f"{NEW}|running|duosave:latest"))
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("noop", None)
    assert not any(call[:2] == ("docker", "build") for call in runner.runner.calls)
    assert not any(call[:3] == ("git", "worktree", "add") for call in runner.runner.calls)


# --------------------------------------------------------------------- success


def test_update_success_sequence(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario())
    runner.startup()

    job = runner.run_update()

    assert job["state"] == "succeeded"
    assert (job["from"], job["to"]) == (SHA, NEW)
    calls = runner.runner.calls
    order = [
        ("git", "fetch"),
        ("git", "symbolic-ref"),
        ("git", "merge"),
        ("docker", "info"),
        ("docker", "inspect", "duosave"),
        ("docker", "exec", "duosave", "python", "-m", "duosave", "snapshot"),
        ("git", "worktree", "add"),
        ("docker", "image", "tag"),
        ("docker", "build"),
        ("docker", "compose"),
        ("docker", "exec", "duosave", "python", "-c"),
        ("git", "worktree", "remove"),
        ("git", "worktree", "prune"),
    ]
    positions = [_index_of(calls, *prefix) for prefix in order]
    assert positions == sorted(positions)
    build = next(call for call in calls if call[:2] == ("docker", "build"))
    assert f"DUOSAVE_COMMIT={NEW}" in build
    assert f"DUOSAVE_COMMIT_DATE=2026-10-12T10:00:00+03:00" in build
    assert f"DUOSAVE_VERSION={__version__}" in build
    assert f"duosave:{NEW12}" in build
    removed = [call for call in calls if call[:3] == ("docker", "image", "rm")]
    # latest/previous are kept; the three newest <sha12> tags survive, older ones go
    assert [call[3] for call in removed] == ["duosave:dddddddddddd"]
    log = control.tail(control.log_path(runner.data_dir))
    assert any("update: succeeded" in line for line in log)
    assert _status(runner)["deployed"]["commit"] == NEW


def test_snapshot_failure_is_warning(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(snapshot=Completed(1, "", "no snapshot command")))
    runner.startup()

    job = runner.run_update()

    assert job["state"] == "succeeded"
    assert any("warning: snapshot failed" in line
               for line in control.tail(control.log_path(runner.data_dir)))


def test_build_failure_keeps_container(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(build=Completed(1, "", "build error")))
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("failed", "build_failed")
    assert not any(call[:2] == ("docker", "compose") for call in runner.runner.calls)
    assert any(call[:3] == ("git", "worktree", "remove") for call in runner.runner.calls)


def test_compose_failure_rolls_back(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(
        compose=[Completed(1, "", "compose error"), Completed(0)], health=SHA))
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("rolled_back", "compose_failed")
    assert any(call[:4] == ("docker", "image", "tag", "duosave:previous")
               for call in runner.runner.calls)
    assert sum(1 for call in runner.runner.calls if call[:2] == ("docker", "compose")) == 2


def test_unhealthy_rolls_back(tmp_path: Path) -> None:
    clock = FakeClock()
    runner = _runner(tmp_path, _update_scenario(health=SHA), clock=clock)
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("rolled_back", "unhealthy")
    assert clock.now - 1_000_000.0 >= updater.HEALTH_TIMEOUT


def test_rollback_failure(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(health=STRANGER))
    runner.startup()

    job = runner.run_update()

    assert (job["state"], job["reason"]) == ("rollback_failed", "rollback_failed")


def test_never_runs_destructive_git(tmp_path: Path) -> None:
    scenarios = [
        _update_scenario(),
        _update_scenario(build=Completed(1, "", "boom")),
        _update_scenario(compose=Completed(1, "", "boom")),
        _update_scenario(health=SHA),
        _update_scenario(branch="feature"),
        _check_scenario(),
    ]
    for index, scenario in enumerate(scenarios):
        runner = _runner(tmp_path / f"case{index}", scenario)
        runner.startup()
        if index == len(scenarios) - 1:
            runner.run_check()
        else:
            runner.run_update()

        for call in runner.runner.calls:
            if call[:1] == ("git",):
                assert call[1] not in updater.DESTRUCTIVE_GIT, call


def test_self_update_exits_75(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _update_scenario(diff="duosave/updater.py\n"))
    runner.startup()

    with pytest.raises(SystemExit) as exc:
        runner.run_update()

    assert exc.value.code == updater.SELF_UPDATE_EXIT
    assert _status(runner)["job"]["state"] == "succeeded"


# ------------------------------------------------------------------- requests


def test_tick_claims_request(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _check_scenario())
    runner.startup()
    control.write_json_atomic(control.request_path(runner.data_dir),
                              control.new_request("check", "owner@example.com"))

    runner.tick()

    assert not control.request_path(runner.data_dir).exists()
    assert not control.processing_path(runner.data_dir).exists()
    status = _status(runner)
    assert status["job"]["state"] == "succeeded"
    assert status["job"]["requested_by"] == "owner@example.com"
    assert status["runner"]["heartbeat_at"]


def test_tick_discards_invalid_request(tmp_path: Path) -> None:
    runner = _runner(tmp_path, _check_scenario())
    runner.startup()
    runner.tick()  # the periodic check runs first and records a job
    before = _status(runner)["job"]
    control.write_json_atomic(control.request_path(runner.data_dir),
                              {"id": "nope", "action": "rm -rf"})

    runner.tick()

    assert not control.request_path(runner.data_dir).exists()
    assert not control.processing_path(runner.data_dir).exists()
    assert _status(runner)["job"] == before
    assert any("discarded an invalid update request" in line
               for line in control.tail(control.log_path(runner.data_dir)))


def test_periodic_check_every_15_minutes(tmp_path: Path) -> None:
    clock = FakeClock()
    runner = _runner(tmp_path, _check_scenario(), clock=clock)
    runner.startup()

    runner.tick()
    fetches = [call for call in runner.runner.calls if call[:2] == ("git", "fetch")]
    assert len(fetches) == 1

    clock.now += 60
    runner.tick()
    assert len([call for call in runner.runner.calls if call[:2] == ("git", "fetch")]) == 1

    clock.now += updater.FETCH_INTERVAL
    runner.tick()
    assert len([call for call in runner.runner.calls if call[:2] == ("git", "fetch")]) == 2


def test_startup_marks_interrupted_job(tmp_path: Path) -> None:
    runner = _runner(tmp_path, [(("git", "worktree", "prune"), Completed(0))])
    control.write_json_atomic(control.status_path(runner.data_dir), {
        "runner": {"heartbeat_at": "2026-10-12T10:00:00Z"},
        "job": {"id": "a" * 32, "action": "update", "state": "running", "step": "build"},
    })

    runner.startup()

    job = _status(runner)["job"]
    assert (job["state"], job["reason"]) == ("failed", "interrupted")
    assert any(call[:3] == ("git", "worktree", "prune") for call in runner.runner.calls)


def test_single_instance_lock(tmp_path: Path) -> None:
    first = _runner(tmp_path, [])
    second = _runner(tmp_path, [])

    assert first.acquire_lock() is True
    assert second.acquire_lock() is False
    control.release_lock(first._lock)
    assert second.acquire_lock() is True


# ------------------------------------------------------------------------ cli


def test_data_dir_resolution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert updater.resolve_data_dir(None, repo) == repo / "data"

    (repo / ".env").write_text("# comment\nDUOSAVE_DATA_DIR=./custom\n", encoding="utf-8")
    assert updater.resolve_data_dir(None, repo) == (repo / "custom").resolve()
    assert updater.resolve_data_dir("D:/elsewhere", repo) == Path("D:/elsewhere")


def test_status_cli_prints_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = tmp_path / "data"
    control.write_json_atomic(control.status_path(data), {
        "runner": {"heartbeat_at": control.utc_now()},
        "job": None,
    })

    code = updater.main(["status", "--repo", str(tmp_path), "--data-dir", str(data)])

    output = capsys.readouterr().out
    lines = output.splitlines()
    assert code == 0
    assert json.loads("\n".join(lines[:-1]))["job"] is None
    assert "alive" in lines[-1]


def test_updater_import_is_stdlib_only() -> None:
    repo = Path(__file__).resolve().parents[1]
    code = ("import sys, duosave.updater; "
            "bad = {m for m in ('pydantic', 'fastapi', 'numpy', 'PIL') if m in sys.modules}; "
            "assert not bad, bad")

    result = subprocess.run([sys.executable, "-c", code], cwd=repo, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
