#!/usr/bin/env python3
"""Generate human-reviewable distribution briefs from local intelligence files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

try:
    from modules.security_manager import SecurityManager
except ModuleNotFoundError:
    from security_manager import SecurityManager


PENDING_DIR = Path("queue") / "pending"
SYNTHESIS_FILE = Path("pantheon_synthesized_update.md")
INTELLIGENCE_GLOB = "intelligence_log_*.md"


@dataclass
class SeedArtifact:
    kind: str
    title: str
    body: str


class DistributionSeeder:
    """Builds draft briefs and stages them to the pending approval queue."""

    def __init__(self, workspace: Path | None = None, security: SecurityManager | None = None) -> None:
        self.workspace = workspace or Path.cwd()
        self.security = security or SecurityManager()
        self.pending_dir = self.workspace / PENDING_DIR
        self.pending_dir.mkdir(parents=True, exist_ok=True)

    def load_source_text(self) -> str:
        parts: list[str] = []

        synthesis_path = self.workspace / SYNTHESIS_FILE
        if synthesis_path.exists():
            parts.append(synthesis_path.read_text(encoding="utf-8", errors="replace"))

        for path in sorted(self.workspace.glob(INTELLIGENCE_GLOB)):
            parts.append(path.read_text(encoding="utf-8", errors="replace"))

        if not parts:
            return "No intelligence data found yet. Add intelligence logs before seeding briefs."
        return "\n\n".join(parts)

    def _extract_key_points(self, text: str, max_points: int = 6) -> list[str]:
        sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
        candidates = [s.strip() for s in sentences if len(s.strip()) > 60]
        return candidates[:max_points] or ["Emerging narrative signals remain under active review."]

    def build_briefs(self) -> list[SeedArtifact]:
        source = self.load_source_text()
        key_points = self._extract_key_points(source)
        bullets = "\n".join(f"- {point}" for point in key_points)

        community_brief = f"""# Community Brief: Narrative Signals Watch

## Summary
Independent creators are tracking several converging story themes and audience questions.

## Highlights
{bullets}

## Suggested Discussion Prompt
Which narrative thread deserves a deeper long-form breakdown next?
"""

        press_kit = f"""# Press Kit Draft: Story Intelligence Snapshot

## Editorial Angle
A curated summary of current story-world signals, creator speculation, and market-facing hooks.

## Key Observations
{bullets}

## Suggested Packaging
- Long-form post with evidence links
- Threaded social teaser set
- Interview-style Q&A recap
"""

        pitch_sheet = f"""# Pitch Sheet: Investigative Story Memo

## Working Thesis
Multiple narrative signals point to a coordinated evolution in tone, stakes, and character strategy.

## Evidence Notes
{bullets}

## Intended Outlets
Substack, Medium, Reddit writing communities, and independent creator newsletters.

## Editorial Guardrail
This draft is for human review and approval before any external distribution.
"""

        artifacts = [
            SeedArtifact(kind="community_brief", title="Community Brief", body=community_brief),
            SeedArtifact(kind="press_kit", title="Press Kit", body=press_kit),
            SeedArtifact(kind="pitch_sheet", title="Pitch Sheet", body=pitch_sheet),
        ]
        return artifacts

    def stage_pending(self) -> list[Path]:
        created: list[Path] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for artifact in self.build_briefs():
            sanitized = self.security.strip_sensitive_metadata(artifact.body)
            filename = f"seed_{artifact.kind}_{timestamp}.md"
            output = self.pending_dir / filename
            output.write_text(sanitized.rstrip() + "\n", encoding="utf-8")
            created.append(output)

        return created


def main() -> None:
    seeder = DistributionSeeder()
    outputs = seeder.stage_pending()
    print("Generated pending seed artifacts:")
    for path in outputs:
        print(f"- {path.as_posix()}")


if __name__ == "__main__":
    main()
