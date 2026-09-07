"""Check the maintained documentation graph and project-status data."""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def check_docs(root: Path) -> dict:
    documents = list(root.glob("*.md"))
    documents += list((root / "docs").rglob("*.md"))
    documents += list((root / "lessons").glob("*.html"))
    documents += list((root / "reference").glob("*.html"))
    problems = []
    checked = 0
    for doc in documents:
        content = doc.read_text()
        links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", content)
        links += re.findall(r'(?:href|src)="([^\"]+)"', content)
        for link in links:
            parsed = urlsplit(link.strip("<>"))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (doc.parent / unquote(parsed.path)).resolve()
            checked += 1
            if not target.is_relative_to(root.resolve()) or not target.exists():
                problems.append(f"{doc.relative_to(root)}: missing local target {link}")
    project = json.loads((root / "docs/project.json").read_text())
    if sum(item["points"] for item in project["rubric"]) != 100:
        problems.append("Rubric weights must sum to 100")
    if project["phase"] == "preparation" and project["manipulation_available"]:
        problems.append("Preparation phase cannot claim manipulation availability")
    for item in project["milestones"]:
        if item["state"] not in {"complete", "in_progress", "pending", "blocked"}:
            problems.append(f"Unknown milestone state: {item['state']}")
    return {
        "outcome": "passed" if not problems else "failed",
        "links_checked": checked,
        "problems": problems,
    }
