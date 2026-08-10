#!/usr/bin/env python3
"""Lore management utilities for Pantheon Studios.

Loads Markdown lore files and provides merged context for generators.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class LoreDocument:
    """Represents one lore file loaded from disk."""

    path: Path
    title: str
    content: str


class LoreManager:
    """Loads lore documents from the workspace lore directory."""

    def __init__(self, lore_dir: Path | str = "lore") -> None:
        self.lore_dir = Path(lore_dir)

    def list_lore_files(self) -> list[Path]:
        if not self.lore_dir.exists():
            return []
        return sorted(self.lore_dir.glob("*.md"))

    def load_documents(self) -> list[LoreDocument]:
        documents: list[LoreDocument] = []
        for file_path in self.list_lore_files():
            content = file_path.read_text(encoding="utf-8", errors="replace").strip()
            title = self._title_from_content(content, fallback=file_path.stem)
            documents.append(LoreDocument(path=file_path, title=title, content=content))
        return documents

    def build_context(self, max_chars: int = 8000) -> str:
        """Build a single context block from all lore docs."""
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")

        docs = self.load_documents()
        if not docs:
            return "No lore files found."

        sections: list[str] = []
        for doc in docs:
            sections.append(f"## {doc.title}\nSource: {doc.path.as_posix()}\n\n{doc.content}")

        merged = "\n\n---\n\n".join(sections)
        return merged[:max_chars].rstrip() + ("\n...[truncated]" if len(merged) > max_chars else "")

    def iter_context_chunks(self, chunk_size: int = 2000) -> Iterable[str]:
        """Yield lore context in fixed-size chunks for token-limited pipelines."""
        context = self.build_context(max_chars=500000)
        for idx in range(0, len(context), chunk_size):
            yield context[idx : idx + chunk_size]

    @staticmethod
    def _title_from_content(content: str, fallback: str) -> str:
        for line in content.splitlines():
            if line.startswith("# "):
                return line.removeprefix("# ").strip()
        return fallback


def main() -> None:
    manager = LoreManager()
    files = manager.list_lore_files()
    print(f"Lore files discovered: {len(files)}")
    for file_path in files:
        print(f"- {file_path.as_posix()}")

    print("\nCombined Context Preview\n" + "=" * 24)
    print(manager.build_context(max_chars=1200))


if __name__ == "__main__":
    main()
