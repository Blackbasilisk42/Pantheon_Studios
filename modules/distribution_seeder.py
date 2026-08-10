#!/usr/bin/env python3
"""Generate distribution briefs and dispatch approved drafts to configured channels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import re
import urllib.request
from typing import Any

try:
    from modules.security_manager import SecurityManager
    from modules.notifier import send_pending_review_alert
    from modules.system_state import abort_if_killed
    from modules.activity_logger import emit_activity
except ModuleNotFoundError:
    from security_manager import SecurityManager  # type: ignore[no-redef]
    from notifier import send_pending_review_alert  # type: ignore[no-redef]
    from system_state import abort_if_killed  # type: ignore[no-redef]
    from activity_logger import emit_activity  # type: ignore[no-redef]


PENDING_DIR = Path("queue") / "pending"
APPROVED_DIR = Path("queue") / "approved"
SYNTHESIS_FILE = Path("pantheon_synthesized_update.md")
INTELLIGENCE_GLOB = "intelligence_log_*.md"
CONFIG_PATH = Path("config") / "distribution_targets.json"
RECEIPTS_DIR = Path("intelligence") / "distribution_receipts"
DISTRIBUTION_LOG_GLOB = "distribution_log_*.md"
PUBLIC_POLICY_DISCLAIMER = (
    "\n\n---\nPublic-policy disclaimer: This draft is for review and approval only. "
    "Do not publish or distribute without human review and compliance confirmation."
)


@dataclass
class SeedArtifact:
    kind: str
    title: str
    body: str


class DistributionSeeder:
    """Builds draft briefs, stages them for review, and dispatches approved assets."""

    def __init__(self, workspace: Path | None = None, security: SecurityManager | None = None) -> None:
        self.workspace = workspace or Path.cwd()
        self.security = security or SecurityManager()
        self.pending_dir = self.workspace / PENDING_DIR
        self.approved_dir = self.workspace / APPROVED_DIR
        self.receipts_dir = self.workspace / RECEIPTS_DIR
        self.intelligence_dir = self.workspace / "intelligence"
        self.config_path = self.workspace / CONFIG_PATH
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.approved_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.intelligence_dir.mkdir(parents=True, exist_ok=True)

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

        return [
            SeedArtifact(kind="community_brief", title="Community Brief", body=community_brief),
            SeedArtifact(kind="press_kit", title="Press Kit", body=press_kit),
            SeedArtifact(kind="pitch_sheet", title="Pitch Sheet", body=pitch_sheet),
        ]

    def stage_pending(self) -> list[Path]:
        abort_if_killed()
        created: list[Path] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for artifact in self.build_briefs():
            sanitized = self.security.strip_sensitive_metadata(artifact.body)
            filename = f"seed_{artifact.kind}_{timestamp}.md"
            output = self.pending_dir / filename
            output.write_text(sanitized.rstrip() + "\n", encoding="utf-8")
            created.append(output)
            try:
                send_pending_review_alert(artifact.title)
            except Exception as exc:  # noqa: BLE001 — notification failure must not block staging
                print(f"[notifier] Warning: could not send SMS alert for '{artifact.title}': {exc}")

        return created

    def load_targets(self) -> list[dict[str, Any]]:
        if not self.config_path.exists():
            return [
                {
                    "name": "local_dry_run",
                    "channel": "local",
                    "kind": "dry_run",
                    "active": True,
                    "jitter_enabled": False,
                    "jitter_min": 0,
                    "jitter_max": 0,
                    "format": "markdown",
                }
            ]

        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                return payload.get("targets", [])
        except (OSError, json.JSONDecodeError):
            return []
        return []

    def _extract_title(self, content: str, fallback: str) -> str:
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return fallback

    def _render_for_target(self, title: str, body: str, target: dict[str, Any]) -> str:
        content = self.security.strip_sensitive_metadata(body).rstrip()
        if target.get("channel") == "social":
            teaser = " ".join(content.split())
            teaser = teaser[:220].rstrip() + ("..." if len(teaser) > 220 else "")
            return f"{title}\n\n{teaser}{PUBLIC_POLICY_DISCLAIMER}"
        if target.get("channel") == "rss":
            return f"<article><h1>{title}</h1><p>{content}</p></article>{PUBLIC_POLICY_DISCLAIMER}"
        if target.get("channel") == "email":
            return f"Subject: {title}\n\n{content}{PUBLIC_POLICY_DISCLAIMER}"
        return f"{title}\n\n{content}{PUBLIC_POLICY_DISCLAIMER}"

    def _write_receipt(self, title: str, target: dict[str, Any], status: str, content: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "approved-draft"
        receipt_path = self.receipts_dir / f"{timestamp}_{slug}.md"
        receipt_path.write_text(
            "\n".join(
                [
                    f"# Distribution Receipt: {title}",
                    "",
                    f"- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"- Target: {target.get('name', 'unknown')}",
                    f"- Channel: {target.get('channel', 'unknown')}",
                    f"- Status: {status}",
                    "- Included: public-policy disclaimer",
                    "",
                    "## Payload",
                    "",
                    content,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        ledger_path = self.intelligence_dir / f"distribution_log_{timestamp}.md"
        ledger_path.write_text(
            "\n".join(
                [
                    f"# Distribution Log: {title}",
                    "",
                    f"- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"- Platform: {target.get('channel', 'unknown')}",
                    f"- Status: {status}",
                    f"- Summary: {title}",
                    f"- URL/Path: {receipt_path.as_posix()}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return receipt_path

    def dispatch_approved_items(self, limit: int | None = None) -> dict[str, Any]:
        abort_if_killed()
        items = sorted(self.approved_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
        if limit is not None:
            items = items[-limit:]

        targets = [target for target in self.load_targets() if target.get("active", False)]
        if not targets:
            return {"dispatched_count": 0, "receipts": [], "targets": []}

        receipts: list[str] = []
        dispatched_count = 0

        for item_path in items:
            content = item_path.read_text(encoding="utf-8", errors="replace")
            title = self._extract_title(content, item_path.stem)
            for target in targets:
                if target.get("jitter_enabled"):
                    self.security.wait_with_jitter(
                        int(target.get("jitter_min", 0) or 0),
                        int(target.get("jitter_max", 0) or 0),
                    )

                emit_activity("Formatting for Reddit/Discord", "distribution_seeder", f"Formatting {title} for {target.get('channel', 'unknown')}")
                rendered = self._render_for_target(title, content, target)
                status = "queued"
                if target.get("kind") in {"dry_run", "local"}:
                    status = "queued"
                elif target.get("url"):
                    try:
                        body = json.dumps({"title": title, "body": rendered}).encode("utf-8")
                        request = urllib.request.Request(
                            target["url"],
                            data=body,
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
                            response.read()
                        emit_activity("Posting Asset", "distribution_seeder", f"Posted {title} to {target.get('name', 'unknown')}")
                        status = "posted"
                    except Exception as exc:  # noqa: BLE001
                        status = f"failed: {exc}"
                receipt = self._write_receipt(title, target, status, rendered)
                receipts.append(receipt.as_posix())
            dispatched_count += 1

        return {
            "dispatched_count": dispatched_count,
            "receipts": receipts,
            "targets": [target.get("name", "unknown") for target in targets],
        }

    def build_distribution_ledger(self) -> list[dict[str, str]]:
        ledger: list[dict[str, str]] = []
        source_paths = sorted(self.intelligence_dir.glob(DISTRIBUTION_LOG_GLOB))
        if not source_paths:
            source_paths = sorted(self.receipts_dir.glob("*.md"))
        for path in source_paths:
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            title = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("# Distribution") or line.startswith("# Distribution Log:")), path.stem)
            timestamp = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("- Timestamp:")), "unknown")
            platform = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("- Platform:")), "unknown")
            status = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("- Status:")), "pending")
            url_or_path = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("- URL/Path:")), path.as_posix())
            ledger.append(
                {
                    "timestamp": timestamp,
                    "platform": platform,
                    "title": title,
                    "status": status,
                    "url_or_path": url_or_path,
                }
            )
        return ledger

    def distribution_status_md(self) -> str:
        approved_files = sorted(self.approved_dir.glob("*.md"))
        receipt_files = sorted(self.receipts_dir.glob("*.md"))
        active_targets = [target.get("name", "unknown") for target in self.load_targets() if target.get("active", False)]
        return (
            "| Metric | Value |\n"
            "|--------|-------|\n"
            f"| Approved items | {len(approved_files)} |\n"
            f"| Receipt files | {len(receipt_files)} |\n"
            f"| Active targets | {', '.join(active_targets) or 'None'} |\n"
        )


def main() -> None:
    seeder = DistributionSeeder()
    outputs = seeder.stage_pending()
    print("Generated pending seed artifacts:")
    for path in outputs:
        print(f"- {path.as_posix()}")


if __name__ == "__main__":
    main()
