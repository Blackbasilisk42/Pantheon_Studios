#!/usr/bin/env python3
"""Local markdown publisher for approved Pantheon Studios items."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from publishers.base_publisher import BasePublisher, PublishItem


def slugify(text: str, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    cleaned = re.sub(r"[\s_-]+", "-", cleaned).strip("-")
    return (cleaned or "untitled")[:max_length].rstrip("-")


class LocalMarkdownPublisher(BasePublisher):
    """Publishes approved items as markdown files in queue/approved/."""

    name = "local_markdown"

    def __init__(self, output_dir: Path | str = Path("queue") / "approved") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, item: PublishItem) -> Path:
        filename = f"{slugify(item.title)}.md"
        path = self.output_dir / filename

        suffix = 1
        while path.exists():
            path = self.output_dir / f"{slugify(item.title)}_{suffix}.md"
            suffix += 1

        metadata_lines = []
        metadata = dict(item.metadata or {})
        metadata["published_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        metadata["publisher"] = self.name
        if item.source_file:
            metadata["source_file"] = item.source_file.as_posix()

        for key, value in metadata.items():
            metadata_lines.append(f"- {key}: {value}")

        metadata_block = "\n".join(metadata_lines)

        document = (
            f"# {item.title}\n\n"
            "## Publication Metadata\n"
            f"{metadata_block}\n\n"
            "## Content\n"
            f"{item.content.rstrip()}\n"
        )

        path.write_text(document, encoding="utf-8")
        return path


def main() -> None:
    publisher = LocalMarkdownPublisher()
    sample = PublishItem(
        title="Sample Approved Item",
        content="This is a sample approved entry for local publishing.",
        metadata={"campaign": "launch-sequence"},
    )
    output = publisher.publish(sample)
    print(f"Published locally: {output.as_posix()}")


if __name__ == "__main__":
    main()
