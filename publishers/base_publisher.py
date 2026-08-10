#!/usr/bin/env python3
"""Publisher abstraction for Pantheon Studios distribution modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass
class PublishItem:
    """Represents content that has cleared approval and is ready to publish."""

    title: str
    content: str
    source_file: Path | None = None
    metadata: Mapping[str, str] | None = None


class BasePublisher(ABC):
    """Abstract publisher interface for all platform extensions."""

    name: str = "base"

    @abstractmethod
    def publish(self, item: PublishItem) -> Path:
        """Publish content and return the output artifact path."""
        raise NotImplementedError
