#!/usr/bin/env python3
"""Pantheon Studios operational control hub.

Provides a menu for updating distribution strategy config and listing
intelligence logs in the current workspace.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import glob


CONFIG_FILE = "agent_config.md"


def prompt_non_empty(label: str) -> str:
    while True:
        value = input(label).strip()
        if value:
            return value
        print("Value cannot be empty. Please try again.")


def save_distribution_config(workspace: Path) -> Path:
    print("\nAdjust Distribution Strategy")
    print("-" * 30)

    strategy_name = prompt_non_empty("Strategy name: ")
    target_channels = prompt_non_empty("Target channels (comma-separated): ")
    cadence = prompt_non_empty("Distribution cadence (e.g., daily, weekly): ")
    notes = input("Optional notes: ").strip() or "N/A"

    content = f"""# Agent Distribution Configuration

- Updated At: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Strategy: {strategy_name}
- Channels: {target_channels}
- Cadence: {cadence}
- Notes: {notes}
"""
    path = workspace / CONFIG_FILE
    path.write_text(content, encoding="utf-8")
    return path


def list_intelligence_logs(workspace: Path) -> list[Path]:
    pattern = str(workspace / "intelligence_log_*.md")
    return sorted(Path(p) for p in glob.glob(pattern))


def display_logs(workspace: Path) -> None:
    logs = list_intelligence_logs(workspace)
    print("\nIntelligence Logs")
    print("-" * 17)
    if not logs:
        print("No intelligence logs found.")
        return

    for idx, file_path in enumerate(logs, start=1):
        print(f"{idx}. {file_path.name}")


def main() -> None:
    workspace = Path.cwd()

    while True:
        print("\nPantheon Studios - Agent Hub")
        print("=" * 29)
        print("1. Adjust distribution strategy")
        print("2. List intelligence logs")
        print("3. Exit")

        choice = input("Select an option (1-3): ").strip()

        if choice == "1":
            config_path = save_distribution_config(workspace)
            print(f"Configuration saved: {config_path.name}")
        elif choice == "2":
            display_logs(workspace)
        elif choice == "3":
            print("Exiting Agent Hub.")
            break
        else:
            print("Invalid option. Please choose 1, 2, or 3.")


if __name__ == "__main__":
    main()
