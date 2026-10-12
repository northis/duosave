"""One uvicorn process on two sockets: the admin port is the only place admin exists."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn

from duosave import cli, config
from duosave.server.app import app


def _get(port: int, path: str, attempts: int = 6) -> tuple[int, dict | str]:
    """GET with retries: Windows resets rapid back-to-back urllib connections (any uvicorn)."""
    last: Exception | None = None
    for attempt in range(attempts):
        url = f"http://127.0.0.1:{port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")
        except OSError as exc:
            last = exc
            time.sleep(0.1 * (attempt + 1))
    raise AssertionError(f"no response from {port}{path}: {last!r}")


def _wait_until_ready(port: int, deadline: float) -> None:
    while time.monotonic() < deadline:
        try:
            if _get(port, "/api/session", attempts=1)[0] == 200:
                return
        except (AssertionError, OSError):
            pass
        time.sleep(0.05)
    pytest.fail(f"server on port {port} did not start")


def test_run_servers_binds_public_and_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = cli._bind("127.0.0.1", 0), cli._bind("127.0.0.1", 0)
    sockets = iter([first, second])
    monkeypatch.setattr(cli, "_bind", lambda host, port: next(sockets))
    captured: dict = {}

    def fake_run(self, sockets=None):  # noqa: ANN001 - uvicorn.Server.run replacement
        captured["sockets"] = sockets

    monkeypatch.setattr(uvicorn.Server, "run", fake_run)

    cli._run_servers(object(), ("127.0.0.1", 0), ("127.0.0.1", 0))

    assert captured["sockets"] == [first, second]
    assert first.fileno() == -1  # closed in the finally block
    assert second.fileno() == -1


def test_two_sockets_split_public_and_admin(
    monkeypatch: pytest.MonkeyPatch, tmp_repo
) -> None:
    sockets = [cli._bind("127.0.0.1", 0), cli._bind("127.0.0.1", 0)]
    public_port = sockets[0].getsockname()[1]
    admin_port = sockets[1].getsockname()[1]
    monkeypatch.setattr(config, "ADMIN_PORT", admin_port)
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": sockets}, daemon=True)
    thread.start()
    try:
        _wait_until_ready(public_port, time.monotonic() + 10)
        public_session = _get(public_port, "/api/session")
        admin_session = _get(admin_port, "/api/session")
        public_admin = _get(public_port, "/admin")
        admin_page = _get(admin_port, "/admin")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        for sock in sockets:
            sock.close()

    assert not thread.is_alive()
    assert json.loads(public_session[1]) == {"local_admin": False}
    assert json.loads(admin_session[1]) == {"local_admin": True}
    assert public_admin[0] == 404
    assert admin_page[0] == 200
    assert 'id="admin"' in admin_page[1]
