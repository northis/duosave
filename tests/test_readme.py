"""README: repository paths mentioned in backticks must exist in the clone."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text(encoding="utf-8")

PATH_RE = re.compile(
    r"`((?:duosave|deploy|tests|\.agents)[/\\][^`\s]*|requirements-agent\.txt|AGENTS\.md)`"
)


def test_readme_paths_exist() -> None:
    missing = []
    for match in PATH_RE.finditer(README):
        candidate = match.group(1).rstrip(".,;:)").split()[0]
        if any(marker in candidate for marker in ("*", "…", "<", "|", "(")):
            continue
        path = REPO / candidate.replace("\\", "/")
        if not path.exists():
            missing.append(candidate)

    assert not missing, missing
