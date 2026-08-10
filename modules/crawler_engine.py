#!/usr/bin/env python3
"""Hardened crawler request engine with randomized headers and jitter."""

from __future__ import annotations

from dataclasses import dataclass

import requests

try:
    from modules.security_manager import SecurityManager
    from modules.system_state import abort_if_killed
    from modules.activity_logger import emit_activity
except ModuleNotFoundError:
    from security_manager import SecurityManager  # type: ignore[no-redef]
    from system_state import abort_if_killed  # type: ignore[no-redef]
    from activity_logger import emit_activity  # type: ignore[no-redef]


@dataclass
class CrawlResponse:
    """Response wrapper with traceability metadata."""

    response: requests.Response
    used_headers: dict[str, str]
    delay_seconds: float


class CrawlerEngine:
    """Executes HTTP GET requests with baseline safety controls."""

    def __init__(self, timeout_seconds: int = 20, security: SecurityManager | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.security = security or SecurityManager()

    def fetch(self, url: str) -> CrawlResponse:
        abort_if_killed()
        emit_activity("Crawler Scanning Target", "crawler_engine", f"Scanning {url}")
        headers = self.security.random_browser_headers()
        delay = self.security.wait_with_jitter(min_seconds=2, max_seconds=7)
        response = requests.get(url, headers=headers, timeout=self.timeout_seconds)
        response.raise_for_status()
        emit_activity("Crawler Scanning Target", "crawler_engine", f"Completed scan for {url}")
        return CrawlResponse(response=response, used_headers=headers, delay_seconds=delay)
