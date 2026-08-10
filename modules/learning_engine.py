#!/usr/bin/env python3
"""Pantheon Studios Autonomous Continuous Learning & Guardrail Engine.

Three subsystems run in sequence:
  1. LocalFeedbackAnalyzer  — RLHF from queue/approved/ vs queue/rejected/
  2. TrendLearner           — structural signals from public web pages
  3. GuardrailValidator     — rejects any adjustment that touches a protected category

All validated adjustments are persisted to .learning_state.json and logged to
intelligence/learning_log_[timestamp].md.

No module in this file may publish content, move queue items, or write to any
security module — guardrail checks enforce this at runtime.
"""

from __future__ import annotations

import json
import re
import sys
import time
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure workspace root is on sys.path when run directly
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from modules.security_manager import SecurityManager
    from modules.system_state import abort_if_killed, is_killswitch_active
    from modules.activity_logger import emit_activity
except ModuleNotFoundError:
    from security_manager import SecurityManager  # type: ignore[no-redef]
    from system_state import abort_if_killed, is_killswitch_active  # type: ignore[no-redef]
    from activity_logger import emit_activity  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APPROVED_DIR = Path("queue") / "approved"
REJECTED_DIR = Path("queue") / "rejected"
INTELLIGENCE_DIR = Path("intelligence")
IMMUTABLE_RULES_PATH = Path("lore") / "immutable_rules.md"
LEARNING_STATE_FILE = Path(".learning_state.json")

# Public pages used for structural trend analysis (HTML fetched, not rendered)
_TREND_SOURCES = [
    "https://www.wikipedia.org/",
    "https://news.ycombinator.com/",
    "https://example.com/",
]

_LEARNING_RATE = 0.08       # max delta applied per feedback cycle
_WEIGHT_MIN = 0.10
_WEIGHT_MAX = 0.90


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class StyleWeights:
    """Mutable content-style preferences learned from feedback and trends."""

    bullet_lists: float = 0.50
    narrative_hooks: float = 0.50
    question_prompts: float = 0.50
    evidence_links: float = 0.50
    long_form: float = 0.50
    emotional_appeal: float = 0.50
    analytical_tone: float = 0.50
    conversational_tone: float = 0.50

    def clamp(self) -> None:
        for attr in self.__dataclass_fields__:
            setattr(self, attr, max(_WEIGHT_MIN, min(_WEIGHT_MAX, getattr(self, attr))))

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass
class WeightAdjustment:
    """A proposed change to one style weight, with provenance."""

    weight_name: str
    old_value: float
    new_value: float
    delta: float
    reason: str
    source: str  # "feedback" | "trend"


@dataclass
class GuardrailResult:
    passed: bool
    violations: list[str] = field(default_factory=list)


@dataclass
class LearningState:
    style_weights: StyleWeights = field(default_factory=StyleWeights)
    trend_learning_enabled: bool = True
    last_feedback_run: str | None = None
    last_trend_run: str | None = None
    total_approved_analyzed: int = 0
    total_rejected_analyzed: int = 0
    guardrail_blocks_total: int = 0
    last_log_path: str | None = None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load_state() -> LearningState:
    if not LEARNING_STATE_FILE.exists():
        return LearningState()
    try:
        raw: dict[str, Any] = json.loads(LEARNING_STATE_FILE.read_text(encoding="utf-8"))
        weights_raw = raw.get("style_weights", {})
        weights = StyleWeights(**{k: float(v) for k, v in weights_raw.items() if k in StyleWeights.__dataclass_fields__})
        return LearningState(
            style_weights=weights,
            trend_learning_enabled=bool(raw.get("trend_learning_enabled", True)),
            last_feedback_run=raw.get("last_feedback_run"),
            last_trend_run=raw.get("last_trend_run"),
            total_approved_analyzed=int(raw.get("total_approved_analyzed", 0)),
            total_rejected_analyzed=int(raw.get("total_rejected_analyzed", 0)),
            guardrail_blocks_total=int(raw.get("guardrail_blocks_total", 0)),
            last_log_path=raw.get("last_log_path"),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return LearningState()


def _save_state(state: LearningState) -> None:
    payload = {
        "style_weights": state.style_weights.as_dict(),
        "trend_learning_enabled": state.trend_learning_enabled,
        "last_feedback_run": state.last_feedback_run,
        "last_trend_run": state.last_trend_run,
        "total_approved_analyzed": state.total_approved_analyzed,
        "total_rejected_analyzed": state.total_rejected_analyzed,
        "guardrail_blocks_total": state.guardrail_blocks_total,
        "last_log_path": state.last_log_path,
    }
    LEARNING_STATE_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Feature extraction (pure text analysis, no external ML)
# ---------------------------------------------------------------------------

def _extract_features(text: str) -> dict[str, float]:
    """Return a 0–1 score for each style dimension present in text."""
    words = text.split()
    word_count = max(len(words), 1)
    lower = text.lower()

    bullet_lines = len(re.findall(r"^\s*[-*•]\s+", text, re.MULTILINE))
    numbered_lines = len(re.findall(r"^\s*\d+[.)]\s+", text, re.MULTILINE))
    questions = lower.count("?")
    urls = len(re.findall(r"https?://\S+", text))
    md_links = len(re.findall(r"\[.+?\]\(.+?\)", text))

    emotional_words = {"feel", "believe", "imagine", "dream", "hope", "fear",
                       "love", "hate", "wonder", "inspire", "passion", "heart"}
    analytical_words = {"data", "analysis", "evidence", "research", "study",
                        "statistics", "metric", "result", "finding", "trend"}
    conversational_words = {"you", "your", "we", "our", "let's", "lets",
                            "together", "think about", "consider", "imagine if"}

    def _word_density(vocab: set[str]) -> float:
        hits = sum(1 for w in words if w.strip(".,!?\"'") in vocab)
        return min(hits / word_count * 10, 1.0)

    hooks = len(re.findall(r"(?:^|\n)\s*\*\*[^*]+\*\*|(?:^|\n)#{1,3} ", text))

    return {
        "bullet_lists": min((bullet_lines + numbered_lines) / max(word_count / 50, 1), 1.0),
        "narrative_hooks": min(hooks / max(word_count / 100, 1), 1.0),
        "question_prompts": min(questions / max(word_count / 50, 1), 1.0),
        "evidence_links": min((urls + md_links) / max(word_count / 100, 1), 1.0),
        "long_form": min(word_count / 800, 1.0),
        "emotional_appeal": _word_density(emotional_words),
        "analytical_tone": _word_density(analytical_words),
        "conversational_tone": _word_density(conversational_words),
    }


def _avg_features(files: list[Path]) -> dict[str, float]:
    if not files:
        return {}
    totals: dict[str, float] = {}
    for path in files:
        feats = _extract_features(path.read_text(encoding="utf-8", errors="replace"))
        for k, v in feats.items():
            totals[k] = totals.get(k, 0.0) + v
    return {k: v / len(files) for k, v in totals.items()}


# ---------------------------------------------------------------------------
# Guardrail Validator
# ---------------------------------------------------------------------------

# Forbidden keywords extracted from lore/immutable_rules.md FORBIDDEN ACTIONS sections
_STATIC_FORBIDDEN = {
    "auto-publish", "autonomous publishing", "skip approval", "bypass queue",
    "bypass killswitch", "disable killswitch", "override killswitch", "ignore killswitch",
    "disclose personal data", "pii", "personal information", "transmit credentials",
    "api keys", "tokens", "passwords", "secrets",
    "modify security_manager", "rewrite security", "patch approval_gate",
    "alter system_state", "change killswitch", "edit immutable_rules",
    "override authority", "escalate privileges", "grant new permissions",
    "disable stealth", "disable header rotation", "disable pii scrubbing",
}


def _load_forbidden_patterns() -> set[str]:
    """Load forbidden-action phrases from lore/immutable_rules.md at runtime."""
    patterns = set(_STATIC_FORBIDDEN)
    if not IMMUTABLE_RULES_PATH.exists():
        return patterns
    content = IMMUTABLE_RULES_PATH.read_text(encoding="utf-8", errors="replace").lower()
    # Extract bullet items under FORBIDDEN ACTIONS sections
    for line in content.splitlines():
        line = line.strip().lstrip("-* ")
        if 10 < len(line) < 120 and not line.startswith("#") and not line.startswith(">"):
            patterns.add(line)
    return patterns


def validate_against_guardrails(adjustment: WeightAdjustment) -> GuardrailResult:
    """Return a GuardrailResult indicating whether the adjustment is safe."""
    forbidden = _load_forbidden_patterns()
    description = (adjustment.reason + " " + adjustment.weight_name + " " + adjustment.source).lower()
    violations = [pat for pat in forbidden if pat in description]
    return GuardrailResult(passed=not violations, violations=violations)


# ---------------------------------------------------------------------------
# Local Feedback Analyzer (RLHF)
# ---------------------------------------------------------------------------

def run_feedback_analysis(state: LearningState) -> tuple[list[WeightAdjustment], dict[str, Any]]:
    """Compare approved vs rejected queue items and propose style weight deltas."""
    emit_activity("System Thought", "learning_engine", "Reviewing feedback patterns")
    approved_files = sorted(APPROVED_DIR.glob("*.md")) if APPROVED_DIR.exists() else []
    rejected_files = sorted(REJECTED_DIR.glob("*.md")) if REJECTED_DIR.exists() else []

    metrics: dict[str, Any] = {
        "approved_count": len(approved_files),
        "rejected_count": len(rejected_files),
        "approved_features": {},
        "rejected_features": {},
    }

    if not approved_files and not rejected_files:
        return [], metrics

    approved_avg = _avg_features(approved_files)
    rejected_avg = _avg_features(rejected_files)
    metrics["approved_features"] = {k: round(v, 3) for k, v in approved_avg.items()}
    metrics["rejected_features"] = {k: round(v, 3) for k, v in rejected_avg.items()}

    adjustments: list[WeightAdjustment] = []
    current = state.style_weights.as_dict()

    for weight_name in StyleWeights.__dataclass_fields__:
        pos = approved_avg.get(weight_name, 0.5)
        neg = rejected_avg.get(weight_name, 0.5)
        delta = (pos - neg) * _LEARNING_RATE
        if abs(delta) < 0.002:
            continue
        old = current[weight_name]
        new = max(_WEIGHT_MIN, min(_WEIGHT_MAX, old + delta))
        if abs(new - old) < 0.001:
            continue
        adjustments.append(WeightAdjustment(
            weight_name=weight_name,
            old_value=round(old, 4),
            new_value=round(new, 4),
            delta=round(delta, 4),
            reason=f"Approved avg={pos:.3f}, rejected avg={neg:.3f}",
            source="feedback",
        ))

    return adjustments, metrics


# ---------------------------------------------------------------------------
# Trend Learner
# ---------------------------------------------------------------------------

def run_trend_learning(state: LearningState) -> tuple[list[WeightAdjustment], dict[str, Any]]:
    """Fetch public pages and extract structural content signals."""
    abort_if_killed()

    metrics: dict[str, Any] = {"sources_fetched": 0, "sources_failed": 0, "combined_features": {}}

    try:
        import requests  # type: ignore[import]
    except ImportError:
        metrics["error"] = "requests not installed — run: pip install requests"
        return [], metrics

    security = SecurityManager()
    all_features: list[dict[str, float]] = []

    for url in _TREND_SOURCES:
        abort_if_killed()
        try:
            headers = security.random_browser_headers()
            resp = requests.get(url, headers=headers, timeout=8)
            resp.raise_for_status()
            # Strip HTML tags for clean text analysis
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            all_features.append(_extract_features(text[:8000]))
            metrics["sources_fetched"] += 1
            time.sleep(1.5)  # polite delay between requests
        except Exception as exc:
            metrics["sources_failed"] += 1
            metrics[f"error_{url}"] = str(exc)

    if not all_features:
        return [], metrics

    combined = {k: sum(f.get(k, 0.5) for f in all_features) / len(all_features)
                for k in StyleWeights.__dataclass_fields__}
    metrics["combined_features"] = {k: round(v, 3) for k, v in combined.items()}

    current = state.style_weights.as_dict()
    adjustments: list[WeightAdjustment] = []
    trend_rate = _LEARNING_RATE * 0.5  # trends get half the learning rate of direct feedback

    for weight_name, trend_signal in combined.items():
        old = current[weight_name]
        delta = (trend_signal - old) * trend_rate
        if abs(delta) < 0.002:
            continue
        new = max(_WEIGHT_MIN, min(_WEIGHT_MAX, old + delta))
        adjustments.append(WeightAdjustment(
            weight_name=weight_name,
            old_value=round(old, 4),
            new_value=round(new, 4),
            delta=round(delta, 4),
            reason=f"Trend signal={trend_signal:.3f} across {len(all_features)} source(s)",
            source="trend",
        ))

    return adjustments, metrics


# ---------------------------------------------------------------------------
# Apply + log
# ---------------------------------------------------------------------------

def apply_validated_adjustments(
    state: LearningState,
    adjustments: list[WeightAdjustment],
) -> tuple[list[WeightAdjustment], list[WeightAdjustment]]:
    """Run each adjustment through guardrails; apply passing ones, discard the rest."""
    accepted: list[WeightAdjustment] = []
    rejected: list[WeightAdjustment] = []

    for adj in adjustments:
        result = validate_against_guardrails(adj)
        if result.passed:
            setattr(state.style_weights, adj.weight_name, adj.new_value)
            accepted.append(adj)
        else:
            state.guardrail_blocks_total += 1
            adj.reason += f" [BLOCKED: {'; '.join(result.violations[:3])}]"
            rejected.append(adj)

    state.style_weights.clamp()
    return accepted, rejected


def save_learning_log(
    timestamp: str,
    feedback_metrics: dict[str, Any],
    trend_metrics: dict[str, Any],
    accepted: list[WeightAdjustment],
    rejected: list[WeightAdjustment],
    state: LearningState,
) -> Path:
    INTELLIGENCE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = timestamp.replace(" ", "_").replace(":", "")
    path = INTELLIGENCE_DIR / f"learning_log_{safe_ts}.md"

    lines: list[str] = [
        "# Pantheon Studios Learning Engine Log",
        "",
        f"- **Run at:** {timestamp}",
        f"- **Adjustments accepted:** {len(accepted)}",
        f"- **Adjustments blocked by guardrails:** {len(rejected)}",
        f"- **Cumulative guardrail blocks:** {state.guardrail_blocks_total}",
        "",
        "## Feedback Analysis",
        "",
        f"- Approved files analyzed: {feedback_metrics.get('approved_count', 0)}",
        f"- Rejected files analyzed: {feedback_metrics.get('rejected_count', 0)}",
    ]
    if feedback_metrics.get("approved_features"):
        lines.append("\n### Approved Feature Averages\n")
        lines.append("| Feature | Score |")
        lines.append("|---------|-------|")
        for k, v in feedback_metrics["approved_features"].items():
            lines.append(f"| {k} | {v} |")
    if feedback_metrics.get("rejected_features"):
        lines.append("\n### Rejected Feature Averages\n")
        lines.append("| Feature | Score |")
        lines.append("|---------|-------|")
        for k, v in feedback_metrics["rejected_features"].items():
            lines.append(f"| {k} | {v} |")

    lines += [
        "",
        "## Trend Learning",
        "",
        f"- Sources fetched: {trend_metrics.get('sources_fetched', 0)}",
        f"- Sources failed: {trend_metrics.get('sources_failed', 0)}",
    ]
    if trend_metrics.get("error"):
        lines.append(f"- Error: {trend_metrics['error']}")

    if accepted:
        lines += ["", "## Accepted Adjustments", "", "| Weight | Old | New | Delta | Reason |",
                  "|--------|-----|-----|-------|--------|"]
        for a in accepted:
            lines.append(f"| {a.weight_name} | {a.old_value} | {a.new_value} | {a.delta:+.4f} | {a.reason} |")

    if rejected:
        lines += ["", "## Guardrail-Blocked Adjustments", "", "| Weight | Reason |",
                  "|--------|--------|"]
        for r in rejected:
            lines.append(f"| {r.weight_name} | {r.reason} |")

    lines += [
        "",
        "## Current Style Weights",
        "",
        "| Weight | Value |",
        "|--------|-------|",
    ]
    for k, v in state.style_weights.as_dict().items():
        lines.append(f"| {k} | {v:.4f} |")

    lines.append(f"\n---\n_Saved to: {path.as_posix()}_")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main engine class
# ---------------------------------------------------------------------------

class LearningEngine:
    """Orchestrates feedback analysis, trend learning, guardrail validation, and logging."""

    def __init__(self) -> None:
        self.state = _load_state()

    def run_full_cycle(self, run_trends: bool | None = None) -> dict[str, Any]:
        """Run feedback + optional trend learning, validate, persist, and log."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        do_trends = run_trends if run_trends is not None else self.state.trend_learning_enabled

        all_adjustments: list[WeightAdjustment] = []
        feedback_metrics: dict[str, Any] = {}
        trend_metrics: dict[str, Any] = {}

        # 1 — Local feedback
        fb_adj, feedback_metrics = run_feedback_analysis(self.state)
        self.state.total_approved_analyzed += feedback_metrics.get("approved_count", 0)
        self.state.total_rejected_analyzed += feedback_metrics.get("rejected_count", 0)
        self.state.last_feedback_run = timestamp
        all_adjustments.extend(fb_adj)

        # 2 — Trend learning (network; only if enabled and killswitch off)
        if do_trends and not is_killswitch_active():
            tr_adj, trend_metrics = run_trend_learning(self.state)
            self.state.last_trend_run = timestamp
            all_adjustments.extend(tr_adj)
        elif is_killswitch_active():
            trend_metrics = {"skipped": "Killswitch active"}
        else:
            trend_metrics = {"skipped": "Trend learning disabled"}

        # 3 — Guardrail validation and application
        accepted, blocked = apply_validated_adjustments(self.state, all_adjustments)

        # 4 — Persist state and write log
        log_path = save_learning_log(timestamp, feedback_metrics, trend_metrics, accepted, blocked, self.state)
        self.state.last_log_path = log_path.as_posix()
        _save_state(self.state)

        return {
            "timestamp": timestamp,
            "accepted": len(accepted),
            "blocked": len(blocked),
            "log_path": log_path.as_posix(),
            "feedback_metrics": feedback_metrics,
            "trend_metrics": trend_metrics,
            "current_weights": self.state.style_weights.as_dict(),
        }

    def toggle_trend_learning(self, enabled: bool) -> None:
        self.state.trend_learning_enabled = enabled
        _save_state(self.state)

    def get_status(self) -> dict[str, Any]:
        s = self.state
        return {
            "trend_learning_enabled": s.trend_learning_enabled,
            "last_feedback_run": s.last_feedback_run or "Never",
            "last_trend_run": s.last_trend_run or "Never",
            "total_approved_analyzed": s.total_approved_analyzed,
            "total_rejected_analyzed": s.total_rejected_analyzed,
            "guardrail_blocks_total": s.guardrail_blocks_total,
            "current_weights": s.style_weights.as_dict(),
        }


# ---------------------------------------------------------------------------
# Control panel adapter functions
# ---------------------------------------------------------------------------

def _weights_table_md(weights: dict[str, float]) -> str:
    lines = ["| Style Weight | Value | Bar |", "|-------------|-------|-----|"]
    for name, val in weights.items():
        bar = "█" * int(val * 10) + "░" * (10 - int(val * 10))
        lines.append(f"| {name.replace('_', ' ').title()} | {val:.3f} | `{bar}` |")
    return "\n".join(lines)


def get_learning_status_md() -> str:
    engine = LearningEngine()
    s = engine.get_status()
    killed = is_killswitch_active()
    trend_icon = "🟢 Enabled" if s["trend_learning_enabled"] and not killed else (
        "🔴 Halted (killswitch)" if killed else "⚪ Disabled"
    )
    header = (
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Trend learning | {trend_icon} |\n"
        f"| Last feedback run | {s['last_feedback_run']} |\n"
        f"| Last trend run | {s['last_trend_run']} |\n"
        f"| Approved analyzed | {s['total_approved_analyzed']} |\n"
        f"| Rejected analyzed | {s['total_rejected_analyzed']} |\n"
        f"| Guardrail blocks (total) | {s['guardrail_blocks_total']} |\n\n"
    )
    return header + _weights_table_md(s["current_weights"])


def run_feedback_only_ui() -> tuple[str, str]:
    engine = LearningEngine()
    result = engine.run_full_cycle(run_trends=False)
    log_text = Path(result["log_path"]).read_text(encoding="utf-8", errors="replace")
    status = get_learning_status_md()
    return status, log_text


def run_full_cycle_ui() -> tuple[str, str]:
    engine = LearningEngine()
    result = engine.run_full_cycle(run_trends=True)
    log_text = Path(result["log_path"]).read_text(encoding="utf-8", errors="replace")
    status = get_learning_status_md()
    return status, log_text


def toggle_trend_learning_ui(enabled: bool) -> str:
    engine = LearningEngine()
    engine.toggle_trend_learning(enabled)
    return get_learning_status_md()


def latest_learning_log_text() -> str:
    if not INTELLIGENCE_DIR.exists():
        return "No learning logs yet. Run a feedback analysis cycle to generate one."
    logs = sorted(INTELLIGENCE_DIR.glob("learning_log_*.md"), reverse=True)
    if not logs:
        return "No learning logs yet. Run a feedback analysis cycle to generate one."
    return logs[0].read_text(encoding="utf-8", errors="replace")
