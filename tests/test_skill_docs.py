"""Skill docs stay in sync with the code: examples validate, commands parse."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

from duosave import patchfmt
from duosave.cli import build_parser

REPO = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO / ".agents" / "skills" / "duosave-inbox"
SKILL = SKILL_DIR / "SKILL.md"
PATCH_FORMAT = SKILL_DIR / "references" / "patch-format.md"
RECOGNITION_GUIDE = SKILL_DIR / "references" / "recognition-guide.md"
AGENTS = REPO / "AGENTS.md"

EXAMPLE_MODELS = {"draft": patchfmt.WorkRecord, "record": patchfmt.Record,
                  "ledger": patchfmt.LedgerEntry}
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MARKER_RE = re.compile(r"^<!-- example: (\w+) -->\s*$")
COMMAND_RE = re.compile(r"python -m duosave ([^\n`]+)")


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n"), "SKILL.md must start with YAML frontmatter"
    end = text.index("\n---", 4)
    fields = {}
    for line in text[4:end].splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _marked_blocks(text: str) -> list[tuple[str | None, list[str]]]:
    """(marker, lines) for every fenced block; the marker is the comment line above it."""
    blocks: list[tuple[str | None, list[str]]] = []
    marker: str | None = None
    in_block = False
    lines: list[str] = []
    for line in text.splitlines():
        match = MARKER_RE.match(line)
        if match:
            marker = match.group(1)
            continue
        if line.startswith("```"):
            if in_block:
                blocks.append((marker, lines))
                in_block, lines, marker = False, [], None
            else:
                in_block = True
            continue
        if in_block:
            lines.append(line)
    return blocks


def test_skill_frontmatter_and_directory_name() -> None:
    fields = _frontmatter(SKILL.read_text(encoding="utf-8"))

    assert fields.get("name")
    assert fields.get("description")
    assert SLUG_RE.match(SKILL_DIR.name), SKILL_DIR.name


def test_skill_commands_parse() -> None:
    text = SKILL.read_text(encoding="utf-8")
    commands = COMMAND_RE.findall(text)

    assert commands, "SKILL.md must contain python -m duosave commands"
    for command in commands:
        args = shlex.split(command.strip())
        assert build_parser().parse_args(args), command


def test_marked_json_examples_validate() -> None:
    text = PATCH_FORMAT.read_text(encoding="utf-8")
    blocks = _marked_blocks(text)
    seen = set()

    for marker, lines in blocks:
        if marker not in EXAMPLE_MODELS:
            continue
        seen.add(marker)
        model = EXAMPLE_MODELS[marker]
        assert lines, f"empty example block for {marker}"
        for line in lines:
            if not line.strip():
                continue
            payload = json.loads(line)
            assert isinstance(payload, dict), line
            model.model_validate(payload)

    assert seen == set(EXAMPLE_MODELS)


def test_known_example_parses() -> None:
    blocks = _marked_blocks(PATCH_FORMAT.read_text(encoding="utf-8"))
    known = [lines for marker, lines in blocks if marker == "known"]

    assert len(known) == 1
    hashes = patchfmt.parse_known_hashes("\n".join(known[0]))

    assert len(hashes) == 2


def test_agent_docs_reference_the_skill() -> None:
    text = AGENTS.read_text(encoding="utf-8")

    assert ".agents/skills/duosave-inbox/SKILL.md" in text
    assert "python -m pytest -q" in text
    assert RECOGNITION_GUIDE.exists()
