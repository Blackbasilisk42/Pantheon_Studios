#!/usr/bin/env python3
"""Preflight utility for automatic log pruning in the project logs directory."""

from __future__ import annotations

import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"
MAX_LOG_AGE_SECONDS = 24 * 60 * 60
MAX_LOGS_DIR_SIZE_BYTES = 50 * 1024 * 1024


def _log_files(logs_dir: Path) -> list[Path]:
    return sorted(path for path in logs_dir.glob("*.log") if path.is_file())


def _logs_dir_size_bytes(log_files: list[Path]) -> int:
    return sum(file.stat().st_size for file in log_files)


def prune_logs() -> int:
    """Prune old logs and enforce maximum logs directory size.

    Returns the number of deleted log files.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    deleted_count = 0
    now = time.time()
    log_files = _log_files(LOGS_DIR)

    # First pass: delete logs older than 24 hours.
    for file in list(log_files):
        age_seconds = now - file.stat().st_mtime
        if age_seconds > MAX_LOG_AGE_SECONDS:
            file.unlink(missing_ok=True)
            deleted_count += 1

    log_files = _log_files(LOGS_DIR)
    total_size = _logs_dir_size_bytes(log_files)

    # Second pass: if directory still exceeds 50 MB, delete oldest logs first.
    if total_size > MAX_LOGS_DIR_SIZE_BYTES:
        for file in sorted(log_files, key=lambda item: item.stat().st_mtime):
            if total_size <= MAX_LOGS_DIR_SIZE_BYTES:
                break
            file_size = file.stat().st_size
            file.unlink(missing_ok=True)
            total_size -= file_size
            deleted_count += 1

    return deleted_count


def main() -> int:
    deleted_count = prune_logs()
    if deleted_count > 0:
        print(f"[preflight] Log cleanup complete: removed {deleted_count} .log file(s).")
    else:
        print("[preflight] Log folder is healthy: no cleanup needed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
