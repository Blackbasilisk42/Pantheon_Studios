#!/usr/bin/env python3
"""Pantheon Studios lore ingestion CLI.

An interactive command-line tool for quickly capturing lore notes, universe
rules, and story ideas. Each session saves a timestamped Markdown file into
lore/ so the generator engine can consume it automatically.

Usage:
    python -m modules.lore_ingest
    python modules/lore_ingest.py
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

LORE_DIR = Path("lore")

CATEGORIES = [
    "Universe Rule",
    "Character Note",
    "World-Building",
    "Story Idea",
    "Plot Thread",
    "Faction / Group",
    "Timeline Event",
    "Misc",
]


def slugify(value: str, max_length: int = 60) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", value).strip().lower()
    cleaned = re.sub(r"[\s_-]+", "-", cleaned).strip("-")
    return (cleaned or "lore-entry")[:max_length].rstrip("-")


def choose_category() -> str:
    print("\nCategory")
    print("-" * 10)
    for idx, cat in enumerate(CATEGORIES, start=1):
        print(f"  {idx}. {cat}")
    while True:
        raw = input("Choose a category (number or name) [8]: ").strip()
        if not raw:
            return CATEGORIES[-1]
        if raw.isdigit() and 1 <= int(raw) <= len(CATEGORIES):
            return CATEGORIES[int(raw) - 1]
        # Accept partial text match
        matches = [c for c in CATEGORIES if raw.lower() in c.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print(f"Ambiguous — did you mean: {', '.join(matches)}?")
            continue
        print(f"Unrecognized. Enter a number between 1 and {len(CATEGORIES)}.")


def prompt_multiline(sentinel: str = "END") -> str:
    print(f"(Type '{sentinel}' on its own line when finished)\n")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == sentinel:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def build_entry(title: str, category: str, tags: list[str], body: str, timestamp: str) -> str:
    tag_line = ", ".join(tags) if tags else "none"
    return (
        f"# {title}\n\n"
        f"- **Category:** {category}\n"
        f"- **Tags:** {tag_line}\n"
        f"- **Recorded:** {timestamp}\n\n"
        f"## Notes\n\n"
        f"{body}\n"
    )


def save_entry(title: str, category: str, tags: list[str], body: str) -> Path:
    LORE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    slug = slugify(title)
    filename = f"{file_ts}_{slug}.md"
    path = LORE_DIR / filename

    # Avoid collision (unlikely given second-resolution timestamp)
    counter = 1
    while path.exists():
        path = LORE_DIR / f"{file_ts}_{slug}_{counter}.md"
        counter += 1

    path.write_text(build_entry(title, category, tags, body, timestamp), encoding="utf-8")
    return path


def run_session() -> None:
    """Run one lore capture session and save the result."""
    print("\nPantheon Studios - Lore Ingest")
    print("=" * 32)

    # Title
    while True:
        title = input("Entry title: ").strip()
        if title:
            break
        print("Title cannot be empty.")

    # Category
    category = choose_category()

    # Tags (optional)
    raw_tags = input("Tags (comma-separated, optional): ").strip()
    tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []

    # Body
    print("\nLore notes / content:")
    body = prompt_multiline()

    if not body:
        print("No content entered — entry discarded.")
        return

    path = save_entry(title, category, tags, body)
    print(f"\nLore entry saved: {path.as_posix()}")


def main() -> None:
    while True:
        run_session()
        again = input("\nCapture another entry? [y/N]: ").strip().lower()
        if again not in ("y", "yes"):
            print("Lore ingest session complete.")
            break


if __name__ == "__main__":
    main()
