#!/usr/bin/env python3
"""Human-in-the-loop approval gate for Pantheon Studios queue management."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil


PENDING_DIR = Path("queue") / "pending"
APPROVED_DIR = Path("queue") / "approved"
REJECTED_DIR = Path("queue") / "rejected"


def ensure_queue_dirs() -> None:
    for directory in (PENDING_DIR, APPROVED_DIR, REJECTED_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def list_pending_items() -> list[Path]:
    ensure_queue_dirs()
    return sorted([p for p in PENDING_DIR.iterdir() if p.is_file()])


def choose_item(items: list[Path]) -> Path | None:
    if not items:
        print("No pending items in queue/pending/.")
        return None

    print("\nPending Queue Items")
    print("=" * 20)
    for idx, item in enumerate(items, start=1):
        print(f"{idx}. {item.name}")

    print("0. Exit")
    while True:
        raw = input("Select an item to review: ").strip()
        if raw == "0":
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("Invalid selection. Try again.")


def read_preview(item: Path, max_chars: int = 800) -> str:
    content = item.read_text(encoding="utf-8", errors="replace")
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n...[truncated]"


def move_item(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name

    counter = 1
    while destination.exists():
        destination = destination_dir / f"{source.stem}_{counter}{source.suffix}"
        counter += 1

    return Path(shutil.move(str(source), str(destination)))


def prompt_multiline_edit(original: str) -> str:
    print("\nCurrent content preview:")
    print("-" * 24)
    print(original)
    print("\nEnter new content. Type 'END' on a line by itself to finish.")

    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)

    edited = "\n".join(lines).strip()
    return edited if edited else original


def annotate_rejection(content: str, reason: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"<!-- Rejected at {timestamp} | Reason: {reason or 'No reason provided'} -->\n"
        f"{content}"
    )


def review_item(item: Path) -> None:
    content = item.read_text(encoding="utf-8", errors="replace")
    print("\nReviewing:", item.name)
    print("-" * 40)
    print(read_preview(item))

    print("\nActions")
    print("1. Approve")
    print("2. Edit then approve")
    print("3. Reject")
    print("4. Back")

    action = input("Choose action (1-4): ").strip()
    if action == "1":
        dest = move_item(item, APPROVED_DIR)
        print(f"Approved: {dest.as_posix()}")
    elif action == "2":
        edited = prompt_multiline_edit(content)
        item.write_text(edited + "\n", encoding="utf-8")
        dest = move_item(item, APPROVED_DIR)
        print(f"Edited and approved: {dest.as_posix()}")
    elif action == "3":
        reason = input("Optional rejection reason: ").strip()
        item.write_text(annotate_rejection(content, reason) + "\n", encoding="utf-8")
        dest = move_item(item, REJECTED_DIR)
        print(f"Rejected: {dest.as_posix()}")
    elif action == "4":
        return
    else:
        print("Invalid action.")


def main() -> None:
    ensure_queue_dirs()
    print("Pantheon Studios Approval Gate")
    print("=" * 30)

    while True:
        pending = list_pending_items()
        item = choose_item(pending)
        if item is None:
            print("Exiting approval gate.")
            break
        review_item(item)


if __name__ == "__main__":
    main()
