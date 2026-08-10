#!/usr/bin/env python3
"""Pantheon Studios content creator CLI.

Prompts for a title and post body, then saves a clean Markdown file locally.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


def slugify(value: str, max_length: int = 80) -> str:
    """Convert text to a filesystem-safe slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", value).strip().lower()
    cleaned = re.sub(r"[\s_-]+", "-", cleaned)
    slug = cleaned.strip("-") or "untitled-post"
    return slug[:max_length].rstrip("-")


def prompt_multiline(prompt: str, sentinel: str = "END") -> str:
    """Capture multi-line input until the sentinel is entered on its own line."""
    print(prompt)
    print(f"Type '{sentinel}' on a new line when you are done.\n")
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


def build_markdown(title: str, content: str) -> str:
    """Create a clean Markdown representation of the post."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"# {title}\n\n"
        f"_Created: {timestamp}_\n\n"
        f"## Content\n\n"
        f"{content}\n"
    )


def save_post(title: str, content: str, workspace: Path) -> Path:
    """Save the generated markdown post and return its path."""
    slug = slugify(title)
    path = workspace / f"{slug}.md"

    # Avoid accidental overwrite by adding a numeric suffix if needed.
    suffix = 1
    while path.exists():
        path = workspace / f"{slug}_{suffix}.md"
        suffix += 1

    path.write_text(build_markdown(title, content), encoding="utf-8")
    return path


def main() -> None:
    workspace = Path.cwd()
    print("Pantheon Studios - Post Creator")
    print("=" * 33)

    while True:
        title = input("Enter post title: ").strip()
        if title:
            break
        print("Title cannot be empty. Please try again.")

    content = prompt_multiline("Enter your post content:")
    if not content:
        print("No content provided. Exiting without creating a file.")
        return

    path = save_post(title=title, content=content, workspace=workspace)
    print(f"\nPost saved successfully: {path.name}")


if __name__ == "__main__":
    main()
