#!/usr/bin/env python3
"""Thread-safe activity logger for Pantheon Studios background services."""

from __future__ import annotations

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class ActivityLogger:
    """Persist and tail a shared execution stream for the control panel."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or Path("intelligence") / "system_activity.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)
        self._lock = threading.RLock()
        self._buffer: list[str] = []

    def log(self, category: str, source: str, message: str) -> str:
        entry = f"{datetime.now().isoformat()} | {category} | {source} | {message}"
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > 200:
                self._buffer = self._buffer[-200:]
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(entry + "\n")
        return entry

    def tail(self, lines: int = 50) -> list[str]:
        with self._lock:
            if self.log_path.exists():
                content = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                return content[-lines:] if lines else content
            return list(self._buffer[-lines:])

    def snapshot(self) -> str:
        return "\n".join(self.tail(80))


_ACTIVITY_LOGGER = ActivityLogger()


def get_activity_logger() -> ActivityLogger:
    return _ACTIVITY_LOGGER


def emit_activity(category: str, source: str, message: str) -> str:
    return get_activity_logger().log(category=category, source=source, message=message)
