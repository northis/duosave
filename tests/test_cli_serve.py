"""CLI serve: bind address resolution (containers run with DUOSAVE_HOST=0.0.0.0)."""

from __future__ import annotations

import pytest

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
