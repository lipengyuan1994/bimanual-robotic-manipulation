#!/usr/bin/env python3
"""Synchronize README status sections from the versioned project record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

STATUS_START = "<!-- README-STATUS:START -->"
STATUS_END = "<!-- README-STATUS:END -->"
LEARNING_START = "<!-- README-LEARNING:START -->"
LEARNING_END = "<!-- README-LEARNING:END -->"


def replace_section(content: str, start: str, end: str, replacement: str) -> str:
    start_index = content.find(start)
    end_index = content.find(end)
    if start_index < 0 or end_index < 0 or end_index < start_index:
        raise ValueError(f"README is missing a valid generated section: {start}")
    before = content[: start_index + len(start)]
    after = content[end_index:]
    return f"{before}\n{replacement}\n{after}"


def status_section(project: dict) -> str:
    blockers = ", ".join(item["id"] for item in project["blockers"]) or "none"
    availability = "available" if project["manipulation_available"] else "not available"
    intel = "validated" if project["intel_validated"] else "not validated"
    return "\n".join(
        [
            f"**Current release: {project['phase_label']}.**",
            "",
            f"- Challenge manipulation: {availability}",
            f"- Intel target: {intel}",
            f"- Active blockers: {blockers}",
            f"- Status data updated: {project['updated_at']}",
            "",
            "The complete evidence and handoff record is in [docs/STATUS.md](docs/STATUS.md).",
        ]
    )


def learning_section(project: dict) -> str:
    lines = ["- [Public learning site](https://lipengyuan1994.github.io/bimanual-robotic-manipulation/)"]
    for lesson in project["lessons"]:
        href = lesson["href"].removeprefix("/read/")
        lines.append(
            f"- [Lesson {lesson['number']}: {lesson['title']}]({href}) — {lesson['duration']}"
        )
    lines.extend(
        [
            "- [Robotics vocabulary](reference/glossary.html)",
            "- [Learning mission](MISSION.md) · [Primary resources](RESOURCES.md)",
        ]
    )
    return "\n".join(lines)


def rendered_readme(root: Path) -> str:
    readme = (root / "README.md").read_text()
    project = json.loads((root / "docs/project.json").read_text())
    readme = replace_section(readme, STATUS_START, STATUS_END, status_section(project))
    return replace_section(readme, LEARNING_START, LEARNING_END, learning_section(project))


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize generated README status sections")
    parser.add_argument("--check", action="store_true", help="Fail if README needs synchronization")
    parser.add_argument("--write", action="store_true", help="Write generated sections to README")
    args = parser.parse_args()
    if args.check == args.write:
        parser.error("choose exactly one of --check or --write")

    root = Path(__file__).resolve().parents[1]
    readme_path = root / "README.md"
    expected = rendered_readme(root)
    actual = readme_path.read_text()
    if actual == expected:
        print("README generated sections are synchronized with docs/project.json.")
        return 0
    if args.write:
        readme_path.write_text(expected)
        print("Updated README generated sections from docs/project.json.")
        return 0
    print("README is stale. Run: python3 scripts/sync_readme.py --write")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
