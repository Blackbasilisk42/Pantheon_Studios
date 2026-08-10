#!/usr/bin/env python3
"""Pantheon Studios intelligence synthesizer.

Aggregates all intelligence logs and produces a consolidated workspace update.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


OUTPUT_FILE = "pantheon_synthesized_update.md"


def extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return fallback


def extract_snippet(content: str, fallback_length: int = 500) -> str:
    match = re.search(r"## Content Snippet\s*(.+)", content, flags=re.DOTALL)
    if match:
        raw = match.group(1).strip()
        return raw[:fallback_length] + ("..." if len(raw) > fallback_length else "")

    cleaned = re.sub(r"\s+", " ", content).strip()
    return cleaned[:fallback_length] + ("..." if len(cleaned) > fallback_length else "")


def collect_logs(workspace: Path) -> list[Path]:
    return sorted(workspace.glob("intelligence_log_*.md"))


def compile_report(workspace: Path, logs: list[Path]) -> Path:
    lines: list[str] = []
    lines.append("# Pantheon Synthesized Intelligence Update")
    lines.append("")
    lines.append(f"- Generated At: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- Logs Processed: {len(logs)}")
    lines.append("")

    if not logs:
        lines.append("No intelligence logs were found in the workspace.")
    else:
        for idx, log_file in enumerate(logs, start=1):
            content = log_file.read_text(encoding="utf-8", errors="replace")
            title = extract_title(content, fallback=log_file.stem)
            snippet = extract_snippet(content)

            lines.append(f"## {idx}. {title}")
            lines.append(f"- Source File: {log_file.name}")
            lines.append("")
            lines.append("### Snippet")
            lines.append(snippet)
            lines.append("")

    output_path = workspace / OUTPUT_FILE
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    workspace = Path.cwd()
    logs = collect_logs(workspace)
    output_path = compile_report(workspace, logs)
    print(f"Synthesis complete: {output_path.name}")


if __name__ == "__main__":
    main()
