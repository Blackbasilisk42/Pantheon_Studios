#!/usr/bin/env python3
"""Security, privacy, and request-hardening helpers for Pantheon Studios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import random
import re
import time


@dataclass(frozen=True)
class BrowserProfile:
    """Represents a realistic browser header profile."""

    name: str
    user_agent: str


class SecurityManager:
    """Provides request randomization and content sanitization utilities."""

    def __init__(self) -> None:
        self._profiles = [
            BrowserProfile(
                name="chrome_windows",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/128.0.0.0 Safari/537.36"
                ),
            ),
            BrowserProfile(
                name="firefox_windows",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) "
                    "Gecko/20100101 Firefox/129.0"
                ),
            ),
            BrowserProfile(
                name="safari_macos",
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.5 Safari/605.1.15"
                ),
            ),
        ]

    def random_browser_headers(self) -> dict[str, str]:
        """Return realistic browser-like headers for HTTP requests."""
        profile = random.choice(self._profiles)
        return {
            "User-Agent": profile.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def wait_with_jitter(self, min_seconds: int = 2, max_seconds: int = 7) -> float:
        """Pause between requests to reduce bursty traffic patterns."""
        if min_seconds < 0 or max_seconds < min_seconds:
            raise ValueError("Invalid jitter bounds")
        delay = random.uniform(float(min_seconds), float(max_seconds))
        time.sleep(delay)
        return delay

    def strip_sensitive_metadata(self, content: str) -> str:
        """Remove operational signatures and timestamp noise from outbound content.

        This utility is intended for privacy and cleanliness only, and should not
        be used to misrepresent source authorship or bypass disclosure policies.
        """
        patterns = [
            r"(?im)^\s*<\?xml[^\n]*\n?",
            r"(?im)^\s*(generated\s+by|generator\s*:)\s*[^\n]*\n?",
            r"(?im)^\s*(x-powered-by|x-generator)\s*:\s*[^\n]*\n?",
            r"(?im)^\s*(system\s+timestamp|created\s+at|updated\s+at)\s*:\s*[^\n]*\n?",
            r"(?im)^\s*(ai[-\s]?generated|language\s+model\s+output)\s*:?\s*[^\n]*\n?",
            r"(?is)<script\b[^>]*>.*?</script>",
        ]

        cleaned = content
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned)

        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def stamp_audit_note(self, text: str) -> str:
        """Attach an internal processing note for local auditability."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"<!-- sanitized_by=SecurityManager at {timestamp} -->\n{text}\n"
