"""CLI serve: bind address resolution (containers run with DUOSAVE_HOST=0.0.0.0)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from duosave import cli
from duosave.cli import build_parser


def test_serve_defaults_to_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUOSAVE_HOST", raising=False)

    args = build_parser().parse_args(["serve"])

    assert args.host == "127.0.0.1"
    assert args.port == 8765


def test_serve_host_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUOSAVE_HOST", "0.0.0.0")

    assert build_parser().parse_args(["serve"]).host == "0.0.0.0"


def test_serve_host_flag_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUOSAVE_HOST", "0.0.0.0")

    assert build_parser().parse_args(["serve", "--host", "127.0.0.1"]).host == "127.0.0.1"


def test_serve_admin_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUOSAVE_ADMIN_HOST", raising=False)
    monkeypatch.delenv("DUOSAVE_ADMIN_PORT", raising=False)

    args = build_parser().parse_args(["serve"])

    assert args.admin_host == "127.0.0.1"
    assert args.admin_port == 8766


def test_serve_admin_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUOSAVE_ADMIN_HOST", "0.0.0.0")
    monkeypatch.setenv("DUOSAVE_ADMIN_PORT", "9000")

    args = build_parser().parse_args(["serve"])

    assert (args.admin_host, args.admin_port) == ("0.0.0.0", 9000)


def test_serve_admin_flags_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUOSAVE_ADMIN_HOST", "0.0.0.0")
    monkeypatch.setenv("DUOSAVE_ADMIN_PORT", "9000")

    args = build_parser().parse_args(
        ["serve", "--admin-host", "10.77.77.21", "--admin-port", "8766"]
    )

    assert (args.admin_host, args.admin_port) == ("10.77.77.21", 8766)


def test_serve_admin_port_zero_disables_the_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUOSAVE_ADMIN_PORT", raising=False)

    assert build_parser().parse_args(["serve", "--admin-port", "0"]).admin_port == 0


def test_cmd_serve_rejects_the_same_port(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def must_not_bind(*_args) -> None:
        pytest.fail("sockets must not be bound when the ports collide")

    monkeypatch.setattr(cli, "_bind", must_not_bind)
    args = SimpleNamespace(host="127.0.0.1", port=8766, admin_host="127.0.0.1",
                           admin_port=8766, open=False)

    assert cli.cmd_serve(args) == 2
    assert "must differ" in capsys.readouterr().out


def test_bind_returns_a_listening_socket() -> None:
    sock = cli._bind("127.0.0.1", 0)
    try:
        host, port = sock.getsockname()[:2]
        assert host == "127.0.0.1"
        assert port > 0
    finally:
        sock.close()
