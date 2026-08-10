#!/usr/bin/env python3
"""Publisher that moves approved queue items into local distribution media kits."""

from __future__ import annotations

from pathlib import Path
import re

try:
    from publishers.base_publisher import BasePublisher, PublishItem
    from modules.system_state import abort_if_killed
except ModuleNotFoundError:
    from base_publisher import BasePublisher, PublishItem  # type: ignore[no-redef]
    from modules.system_state import abort_if_killed  # type: ignore[no-redef]


APPROVED_DIR = Path("queue") / "approved"
MEDIA_KITS_DIR = Path("dist") / "media_kits"
PUBLIC_POLICY_PATH = Path("dist") / "PUBLIC_POLICY.md"


def slugify(text: str, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\\s-]", "", text).strip().lower()
    cleaned = re.sub(r"[\\s_-]+", "-", cleaned).strip("-")
    return (cleaned or "untitled")[:max_length].rstrip("-")


class AnonymousFeedPublisher(BasePublisher):
    """Stages human-approved content into the local media kits distribution folder."""

    name = "anonymous_feed"

    def __init__(self, output_dir: Path | str = MEDIA_KITS_DIR) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.public_policy_path = PUBLIC_POLICY_PATH
        self._ensure_public_policy()

    def _ensure_public_policy(self) -> None:
        """Ensure dist/PUBLIC_POLICY.md exists in the public output folder."""
        self.public_policy_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.public_policy_path.exists():
            self.public_policy_path.write_text(
                "# Public Policy\n\n"
                "[Placeholder]\n\n"
                "Paste the approved public-facing policy text here.\n",
                encoding="utf-8",
            )

    def _disclaimer_footer(self) -> str:
        return (
            "\n\n---\n"
            "Legal Disclaimer: This briefing is provided for editorial review and "
            "public discussion. For policy, usage, and rights guidance, see "
            "../PUBLIC_POLICY.md.\n"
        )

    def publish(self, item: PublishItem) -> Path:
        abort_if_killed()
        self._ensure_public_policy()
        filename = f"{slugify(item.title)}.md"
        destination = self.output_dir / filename

        counter = 1
        while destination.exists():
            destination = self.output_dir / f"{destination.stem}_{counter}.md"
            counter += 1

        source_hint = item.source_file.as_posix() if item.source_file else "manual"
        content = (
            f"# {item.title}\n\n"
            "## Distribution Record\n"
            f"- Publisher: {self.name}\n"
            f"- Source: {source_hint}\n"
            "- Approval: human-reviewed\n\n"
            "## Brief\n"
            f"{item.content.rstrip()}\n"
            f"{self._disclaimer_footer()}"
        )

        destination.write_text(content, encoding="utf-8")
        return destination

    def publish_approved_file(self, approved_file: Path) -> Path:
        """Publish one approved markdown file into dist/media_kits/."""
        approved_file = Path(approved_file)
        expected_root = APPROVED_DIR.resolve()

        if not approved_file.exists() or not approved_file.is_file():
            raise FileNotFoundError(f"Approved file not found: {approved_file}")

        if expected_root not in approved_file.resolve().parents:
            raise ValueError("Only files from queue/approved/ may be published")

        content = approved_file.read_text(encoding="utf-8", errors="replace")
        item = PublishItem(
            title=approved_file.stem.replace("_", " ").title(),
            content=content,
            source_file=approved_file,
        )
        return self.publish(item)

    def publish_all_approved(self) -> list[Path]:
        """Publish all approved markdown files into dist/media_kits/."""
        outputs: list[Path] = []
        for approved_file in sorted(APPROVED_DIR.glob("*.md")):
            outputs.append(self.publish_approved_file(approved_file))
        return outputs


def main() -> None:
    publisher = AnonymousFeedPublisher()
    approved_files = sorted(APPROVED_DIR.glob("*.md"))
    if not approved_files:
        print("No approved files found in queue/approved/.")
        return

    outputs = publisher.publish_all_approved()
    print(f"Published {len(outputs)} media kit(s) to {MEDIA_KITS_DIR.as_posix()}")


if __name__ == "__main__":
    main()
