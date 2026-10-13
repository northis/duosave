"""Deployment files: baked commit, OCI labels, published ports (text checks, no Docker)."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCKERFILE = (REPO / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
ENV_EXAMPLE = (REPO / ".env.example").read_text(encoding="utf-8")


def test_build_args_come_after_the_dependency_layer() -> None:
    assert DOCKERFILE.index("pip install -r requirements.txt") < DOCKERFILE.index("ARG DUOSAVE_COMMIT")


def test_dockerfile_bakes_commit_and_labels() -> None:
    assert 'ARG DUOSAVE_COMMIT=""' in DOCKERFILE
    assert 'ARG DUOSAVE_COMMIT_DATE=""' in DOCKERFILE
    assert "DUOSAVE_COMMIT=${DUOSAVE_COMMIT}" in DOCKERFILE
    assert "DUOSAVE_COMMIT_DATE=${DUOSAVE_COMMIT_DATE}" in DOCKERFILE
    for label in (
        "org.opencontainers.image.source",
        "org.opencontainers.image.revision",
        "org.opencontainers.image.version",
        "org.opencontainers.image.created",
    ):
        assert label in DOCKERFILE


def test_dockerfile_exposes_both_ports() -> None:
    assert "EXPOSE 8765 8766" in DOCKERFILE


def test_compose_build_args_and_no_runtime_commit() -> None:
    assert "DUOSAVE_COMMIT" in COMPOSE.split("environment:")[0]  # build.args
    assert 'DUOSAVE_COMMIT: "${DUOSAVE_COMMIT:-}"' in COMPOSE
    assert "DUOSAVE_COMMIT:" not in COMPOSE.split("environment:")[1]
    assert 'DUOSAVE_ADMIN_HOST: 0.0.0.0' in COMPOSE


def test_compose_publishes_two_ports() -> None:
    assert '"${DUOSAVE_BIND_ADDR:-0.0.0.0}:${DUOSAVE_PORT:-8765}:8765"' in COMPOSE
    assert '"${DUOSAVE_ADMIN_BIND_ADDR:-10.77.77.21}:${DUOSAVE_ADMIN_PORT:-8766}:8766"' in COMPOSE


def test_env_example_documents_bind_addresses() -> None:
    assert "DUOSAVE_BIND_ADDR" in ENV_EXAMPLE
    assert "DUOSAVE_ADMIN_BIND_ADDR" in ENV_EXAMPLE
    assert "DUOSAVE_ADMIN_PORT" in ENV_EXAMPLE


def test_dockerignore_excludes_agent_and_deploy_files() -> None:
    dockerignore = (REPO / ".dockerignore").read_text(encoding="utf-8")

    for entry in ("inbox/", "outbox/", ".agents/", "AGENTS.md", "deploy/",
                  "requirements-agent.txt"):
        assert entry in dockerignore


def test_dockerignore_sends_only_git_head_and_refs() -> None:
    """Without DUOSAVE_COMMIT the builder stamps the commit from the checkout's HEAD."""
    dockerignore = (REPO / ".dockerignore").read_text(encoding="utf-8")

    assert ".git/*" in dockerignore
    for kept in (".git/HEAD", ".git/packed-refs", ".git/refs/"):
        assert f"!{kept}" in dockerignore
    assert ".git/objects" not in dockerignore  # history is never sent to the builder


def test_gitattributes_pins_ps1_line_endings() -> None:
    assert "*.ps1 text eol=crlf" in (REPO / ".gitattributes").read_text(encoding="utf-8")
