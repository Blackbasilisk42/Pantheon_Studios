#!/usr/bin/env python3
"""Autonomous Lore Synthesis & Background Content Orchestrator for Pantheon Studios.

The orchestrator evaluates the combined lore corpus, decides whether enough context
exists to justify a new release/media-kit draft, stages a pending draft when the
context is sufficiently rich, and alerts operators without spamming low-quality
material when the corpus is fragmented or incomplete.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from modules.notifier import send_pending_review_alert
    from modules.system_state import abort_if_killed, get_state, is_killswitch_active
    from modules.activity_logger import emit_activity
except ModuleNotFoundError:  # pragma: no cover
    from notifier import send_pending_review_alert  # type: ignore[no-redef]
    from system_state import abort_if_killed, get_state, is_killswitch_active  # type: ignore[no-redef]
    from activity_logger import emit_activity  # type: ignore[no-redef]

LORE_DIR = Path("lore")
PENDING_DIR = Path("queue") / "pending"
INTELLIGENCE_DIR = Path("intelligence")
LOG_PATH = INTELLIGENCE_DIR / "synthesis_log.json"


@dataclass
class SynthesisDecision:
    ready: bool
    score: int
    reason: str
    summary: str
    draft_title: str | None = None


@dataclass
class OrchestrationState:
    enabled: bool = True
    last_run: str | None = None
    last_status: str | None = None
    drafts_staged: int = 0
    alerts_sent: int = 0


class OrchestratorEngine:
    """Evaluate lore context and stage new content when enough context exists."""

    def __init__(self) -> None:
        self.state = self._load_state()

    def _load_state(self) -> OrchestrationState:
        if not LOG_PATH.exists():
            return OrchestrationState()
        try:
            payload = json.loads(LOG_PATH.read_text(encoding="utf-8"))
            return OrchestrationState(
                enabled=bool(payload.get("enabled", True)),
                last_run=payload.get("last_run"),
                last_status=payload.get("last_status"),
                drafts_staged=int(payload.get("drafts_staged", 0)),
                alerts_sent=int(payload.get("alerts_sent", 0)),
            )
        except (json.JSONDecodeError, OSError):
            return OrchestrationState()

    def _save_state(self) -> None:
        INTELLIGENCE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "enabled": self.state.enabled,
            "last_run": self.state.last_run,
            "last_status": self.state.last_status,
            "drafts_staged": self.state.drafts_staged,
            "alerts_sent": self.state.alerts_sent,
        }
        LOG_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def _scan_entries(self) -> list[dict[str, Any]]:
        if not LORE_DIR.exists():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(LORE_DIR.glob("*.md")):
            content = path.read_text(encoding="utf-8", errors="replace")
            entries.append({
                "path": path.as_posix(),
                "title": path.stem,
                "content": content,
            })
        return entries

    def evaluate_context(self, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        records = entries if entries is not None else self._scan_entries()
        if not records:
            return {"ready": False, "score": 0, "reason": "No lore entries yet", "summary": "No lore context available."}

        texts = [str(item.get("content", "")) for item in records]
        combined = "\n\n".join(texts)
        lower = combined.lower()

        score = 0
        if len(records) >= 2:
            score += 10
        if len(records) >= 3:
            score += 20
        if len(re.findall(r"\b(faction|keeper|archive|eclipse|bridge|star|city|capital|lantern|gate|river)\b", lower)) >= 3:
            score += 20
        if len(re.findall(r"\b(character|world|rule|note|timeline|plot|story|journal|spirit)\b", lower)) >= 2:
            score += 15
        if len(re.findall(r"\b(guard|fear|sacred|relic|journal|spirit|watch|moon|keepers)\b", lower)) >= 3:
            score += 20
        if len(combined.split()) >= 100:
            score += 15

        ready = score >= 60
        reason = "Sufficient context available for a release draft" if ready else "Context remains fragmented or incomplete"
        summary = (
            f"Scanned {len(records)} lore entries with a combined context score of {score}."
        )
        draft_title = None
        if ready:
            draft_title = f"Autonomous Draft {datetime.now().strftime('%Y%m%d_%H%M%S')}"
        return {"ready": ready, "score": score, "reason": reason, "summary": summary, "draft_title": draft_title}

    def _write_pending_draft(self, title: str) -> Path:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = PENDING_DIR / f"{timestamp}_{title.lower().replace(' ', '-')}.md"
        content = (
            f"# {title}\n\n"
            f"- **Status:** Autonomous draft staged by orchestrator\n"
            f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"## Summary\n\n"
            f"This draft was generated from the accumulated lore corpus when the context threshold was satisfied.\n"
        )
        path.write_text(content, encoding="utf-8")
        return path

    def run_cycle(self, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not self.state.enabled:
            return {"status": "disabled", "message": "Orchestrator disabled."}
        abort_if_killed()

        decision = self.evaluate_context(entries)
        self.state.last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.state.last_status = decision["reason"]

        if not decision["ready"]:
            emit_activity("System Thought", "orchestrator", f"Context insufficient for synthesis: {decision['score']}")
            self._save_state()
            return {
                "status": "quiet",
                "message": "Insufficient context; no draft staged.",
                "decision": decision,
            }

        draft_title = decision.get("draft_title") or "Autonomous Draft"
        emit_activity("Synthesizing Lore", "orchestrator", f"Staging draft {draft_title}")
        draft_path = self._write_pending_draft(draft_title)
        self.state.drafts_staged += 1
        self.state.alerts_sent += 1

        try:
            send_pending_review_alert(draft_title)
        except Exception:
            self.state.alerts_sent = max(0, self.state.alerts_sent - 1)

        self._save_state()
        return {
            "status": "staged",
            "draft_path": draft_path.as_posix(),
            "decision": decision,
            "alerts_sent": self.state.alerts_sent,
        }


def run_orchestrator_ui() -> str:
    engine = OrchestratorEngine()
    result = engine.run_cycle()
    if result.get("status") == "staged":
        return f"Staged draft: {result['draft_path']}"
    return result.get("message", "No action taken.")


def orchestrator_status_md() -> str:
    engine = OrchestratorEngine()
    state = engine.state
    status = "🟢 Enabled" if state.enabled else "🔴 Disabled"
    return (
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Orchestrator | {status} |\n"
        f"| Last run | {state.last_run or 'Never'} |\n"
        f"| Last status | {state.last_status or 'Idle'} |\n"
        f"| Drafts staged | {state.drafts_staged} |\n"
        f"| Alerts sent | {state.alerts_sent} |\n"
    )


def toggle_orchestrator(enabled: bool) -> str:
    engine = OrchestratorEngine()
    engine.state.enabled = enabled
    engine._save_state()
    return orchestrator_status_md()


if __name__ == "__main__":
    engine = OrchestratorEngine()
    print(json.dumps(engine.run_cycle(), indent=2))
