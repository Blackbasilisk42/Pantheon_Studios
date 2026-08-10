#!/usr/bin/env python3
"""Pantheon Studios automated diagnostics, testing, and self-healing engine.

Run directly:
    python modules/diagnostics.py              # audit only
    python modules/diagnostics.py --auto-repair  # audit + auto-fix missing dirs/state

Imported by control_panel.py for the in-browser diagnostics tab.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

# When executed directly (`python modules/diagnostics.py`), the workspace root
# is not on sys.path — add it so sibling module imports resolve correctly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

Status = Literal["pass", "warn", "fail"]

_ICON: dict[str, str] = {"pass": "✅", "warn": "⚠️", "fail": "❌"}


@dataclass
class CheckResult:
    name: str
    status: Status
    message: str
    remediation: str = ""


@dataclass
class DiagnosticReport:
    timestamp: str
    results: list[CheckResult] = field(default_factory=list)
    receipt_path: Path | None = None

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.status == "warn")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def overall_status(self) -> Status:
        if self.failed > 0:
            return "fail"
        if self.warned > 0:
            return "warn"
        return "pass"

    def subsystem_table_md(self) -> str:
        """Compact per-subsystem health summary for the control panel status strip."""
        subsystems = {
            "Killswitch": ["system_state.json", "Pipeline: Killswitch enforcement"],
            "Crawlers": ["Pipeline: CrawlerEngine init", "Network connectivity"],
            "Lore": ["Dir: lore", "Pipeline: Lore ingest"],
            "Queue": ["Dir: queue/pending", "Dir: queue/approved", "Dir: queue/rejected"],
            "Notifier": [".env: ALERT_PHONE_NUMBER", "Pipeline: Notifier config"],
            "Security": ["File: modules/security_manager.py", "Header rotation"],
            "Publishers": ["Pipeline: Publisher init", "File: publishers/base_publisher.py"],
        }
        lookup = {r.name: r for r in self.results}
        lines = ["| Subsystem | Status | Detail |", "|-----------|--------|--------|"]
        for sub, check_names in subsystems.items():
            relevant = [lookup[n] for n in check_names if n in lookup]
            if not relevant:
                continue
            worst = "fail" if any(r.status == "fail" for r in relevant) else (
                "warn" if any(r.status == "warn" for r in relevant) else "pass"
            )
            detail = "; ".join(r.message for r in relevant if r.status != "pass") or "All checks passed"
            lines.append(f"| **{sub}** | {_ICON[worst]} {worst.upper()} | {detail} |")
        return "\n".join(lines)

    def full_receipt_text(self) -> str:
        """Full markdown receipt suitable for saving or displaying in the browser."""
        sections: list[str] = []
        sections.append(f"# Pantheon Studios Diagnostic Receipt\n")
        sections.append(f"- **Run at:** {self.timestamp}")
        sections.append(
            f"- **Summary:** {self.passed} passed / {self.warned} warned / {self.failed} failed"
        )
        overall_icon = _ICON[self.overall_status]
        sections.append(f"- **Overall:** {overall_icon} {self.overall_status.upper()}\n")

        categories = {
            "Environment Audit": [],
            "Network & Security": [],
            "Pipeline Integration": [],
        }
        for r in self.results:
            if r.name.startswith(("Dir:", "File:", ".env", "system_state", "python-dotenv")):
                categories["Environment Audit"].append(r)
            elif r.name.startswith(("Network", "Header")):
                categories["Network & Security"].append(r)
            else:
                categories["Pipeline Integration"].append(r)

        for section_name, checks in categories.items():
            if not checks:
                continue
            sections.append(f"## {section_name}\n")
            sections.append("| Check | Status | Message | Remediation |")
            sections.append("|-------|--------|---------|-------------|")
            for r in checks:
                rem = r.remediation or "—"
                sections.append(f"| {r.name} | {_ICON[r.status]} {r.status} | {r.message} | {rem} |")
            sections.append("")

        if self.receipt_path:
            sections.append(f"---\n_Saved to: {self.receipt_path.as_posix()}_")

        return "\n".join(sections)


# ---------------------------------------------------------------------------
# Required assets
# ---------------------------------------------------------------------------

REQUIRED_DIRS = [
    "lore",
    "queue/pending",
    "queue/approved",
    "queue/rejected",
    "intelligence",
    "publishers",
    "dist",
]

REQUIRED_FILES = [
    "modules/system_state.py",
    "modules/security_manager.py",
    "modules/crawler_engine.py",
    "modules/distribution_seeder.py",
    "modules/approval_gate.py",
    "modules/notifier.py",
    "modules/orchestrator.py",
    "publishers/base_publisher.py",
]

ENV_KEYS = [
    "ALERT_PHONE_NUMBER",
    "TWILIO_ACCOUNT_SID",
    "SMS_AUTH_TOKEN",
]

_PLACEHOLDER_VALUES = {
    "replace_me",
    "your_twilio_account_sid_here",
    "your_twilio_auth_token_here",
    "your_email@example.com",
    "your_email_app_password_here",
}

INTELLIGENCE_DIR = Path("intelligence")


# ---------------------------------------------------------------------------
# Environment audit checks
# ---------------------------------------------------------------------------

def _check_required_directories(auto_repair: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    for dir_str in REQUIRED_DIRS:
        p = Path(dir_str)
        if p.exists() and p.is_dir():
            results.append(CheckResult(f"Dir: {dir_str}", "pass", "Exists"))
        elif auto_repair:
            p.mkdir(parents=True, exist_ok=True)
            results.append(CheckResult(
                f"Dir: {dir_str}", "warn",
                "Missing — created automatically",
                remediation=f"mkdir -p {dir_str}",
            ))
        else:
            results.append(CheckResult(
                f"Dir: {dir_str}", "fail",
                "Missing (run --auto-repair to create)",
            ))
    return results


def _check_required_files() -> list[CheckResult]:
    return [
        CheckResult(f"File: {f}", "pass", "Present")
        if Path(f).exists()
        else CheckResult(f"File: {f}", "fail", "Missing")
        for f in REQUIRED_FILES
    ]


def _check_system_state(auto_repair: bool) -> CheckResult:
    # Import lazily so this module is importable before system_state exists
    from modules.system_state import STATE_FILE, _DEFAULTS, _write  # type: ignore[attr-defined]

    if not STATE_FILE.exists():
        if auto_repair:
            _write(dict(_DEFAULTS))
            return CheckResult(
                "system_state.json", "warn",
                "Missing — created with safe defaults",
                remediation="Created .system_state.json with KILLSWITCH_ACTIVE=False",
            )
        return CheckResult(
            "system_state.json", "warn",
            "Not found — will be auto-created on first use",
        )

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        if auto_repair:
            _write(dict(_DEFAULTS))
            return CheckResult(
                "system_state.json", "fail",
                f"Corrupted JSON ({exc}) — reset to safe defaults",
                remediation="Overwrote corrupted .system_state.json",
            )
        return CheckResult("system_state.json", "fail", f"Corrupted JSON: {exc}")

    if "KILLSWITCH_ACTIVE" not in data:
        if auto_repair:
            _write({**_DEFAULTS, **data})
            return CheckResult(
                "system_state.json", "warn",
                "KILLSWITCH_ACTIVE key absent — repaired",
                remediation="Injected KILLSWITCH_ACTIVE=False",
            )
        return CheckResult("system_state.json", "warn", "KILLSWITCH_ACTIVE key absent")

    return CheckResult(
        "system_state.json", "pass",
        f"Valid — KILLSWITCH_ACTIVE={data['KILLSWITCH_ACTIVE']}",
    )


def _check_env_file() -> list[CheckResult]:
    results: list[CheckResult] = []
    env_path = Path(".env")
    if not env_path.exists():
        results.append(CheckResult(
            ".env file", "warn",
            "Not found — copy .env.example to .env and fill in credentials",
        ))
        return results

    results.append(CheckResult(".env file", "pass", "Present"))

    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv(override=False)
        for key in ENV_KEYS:
            val = os.environ.get(key, "").strip()
            if not val or val in _PLACEHOLDER_VALUES:
                results.append(CheckResult(
                    f".env: {key}", "warn",
                    "Placeholder or empty value — configure in .env",
                ))
            else:
                results.append(CheckResult(f".env: {key}", "pass", "Configured"))
    except ImportError:
        results.append(CheckResult(
            "python-dotenv", "warn",
            "Not installed — run: pip install python-dotenv",
        ))

    return results


# ---------------------------------------------------------------------------
# Network & security checks
# ---------------------------------------------------------------------------

def _check_header_rotation() -> CheckResult:
    try:
        from modules.security_manager import SecurityManager
        sm = SecurityManager()
        seen: set[str] = set()
        for _ in range(12):
            seen.add(sm.random_browser_headers()["User-Agent"])
        if len(seen) > 1:
            return CheckResult(
                "Header rotation", "pass",
                f"{len(seen)} distinct User-Agent profiles across 12 samples",
            )
        return CheckResult("Header rotation", "warn", "Only 1 User-Agent profile observed in 12 samples")
    except Exception as exc:
        return CheckResult("Header rotation", "fail", str(exc))


def _check_network_connectivity() -> CheckResult:
    try:
        import requests  # type: ignore[import]
        from modules.security_manager import SecurityManager
        headers = SecurityManager().random_browser_headers()
        t0 = time.monotonic()
        resp = requests.get("https://example.com", headers=headers, timeout=8)
        latency = time.monotonic() - t0
        if resp.status_code == 200 and latency < 5.0:
            return CheckResult(
                "Network connectivity", "pass",
                f"HTTP 200 from example.com in {latency:.2f}s",
            )
        return CheckResult(
            "Network connectivity", "warn",
            f"HTTP {resp.status_code} from example.com in {latency:.2f}s",
        )
    except Exception as exc:
        return CheckResult(
            "Network connectivity", "warn",
            f"Unreachable: {exc}",
        )


# ---------------------------------------------------------------------------
# Pipeline integration dry-run
# ---------------------------------------------------------------------------

def _pipeline_check_crawler() -> CheckResult:
    try:
        from modules.crawler_engine import CrawlerEngine
        engine = CrawlerEngine()
        assert hasattr(engine, "fetch")
        return CheckResult("Pipeline: CrawlerEngine init", "pass", "OK")
    except Exception as exc:
        return CheckResult("Pipeline: CrawlerEngine init", "fail", str(exc))


def _pipeline_check_lore() -> CheckResult:
    try:
        from modules.lore_ingest import save_entry
        test_path = save_entry("_DIAGNOSTICS_TEST_", "Misc", ["_test_"], "_diagnostic_probe_")
        test_path.unlink(missing_ok=True)
        return CheckResult("Pipeline: Lore ingest", "pass", "Write + cleanup OK")
    except Exception as exc:
        return CheckResult("Pipeline: Lore ingest", "fail", str(exc))


def _pipeline_check_seeder() -> CheckResult:
    try:
        from modules.distribution_seeder import DistributionSeeder
        seeder = DistributionSeeder()
        assert hasattr(seeder, "stage_pending")
        return CheckResult("Pipeline: DistributionSeeder init", "pass", "OK")
    except Exception as exc:
        return CheckResult("Pipeline: DistributionSeeder init", "fail", str(exc))


def _pipeline_check_notifier() -> CheckResult:
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv(override=False)
    except ImportError:
        pass

    has_twilio = bool(os.environ.get("TWILIO_ACCOUNT_SID", "").strip()) and \
                 os.environ.get("TWILIO_ACCOUNT_SID", "") not in _PLACEHOLDER_VALUES
    has_smtp = bool(os.environ.get("SMTP_HOST", "").strip())
    if has_twilio or has_smtp:
        transport = "Twilio" if has_twilio else "SMTP"
        return CheckResult("Pipeline: Notifier config", "pass", f"{transport} transport credentials present")
    return CheckResult(
        "Pipeline: Notifier config", "warn",
        "No SMS transport configured — notifications will be skipped",
    )


def _pipeline_check_publisher() -> CheckResult:
    try:
        from publishers.local_markdown_publisher import LocalMarkdownPublisher
        pub = LocalMarkdownPublisher()
        assert hasattr(pub, "publish")
        return CheckResult("Pipeline: Publisher init", "pass", "LocalMarkdownPublisher OK")
    except Exception as exc:
        return CheckResult("Pipeline: Publisher init", "fail", str(exc))


def _pipeline_check_orchestrator() -> CheckResult:
    try:
        from modules.orchestrator import OrchestratorEngine
        engine = OrchestratorEngine()
        assert hasattr(engine, "run_cycle")
        return CheckResult("Pipeline: Orchestrator init", "pass", "OrchestratorEngine OK")
    except Exception as exc:
        return CheckResult("Pipeline: Orchestrator init", "fail", str(exc))


def _pipeline_check_activity_logger() -> CheckResult:
    try:
        from modules.activity_logger import ActivityLogger
        logger = ActivityLogger(log_path=Path("intelligence") / "system_activity.log")
        logger.log("System Thought", "diagnostics", "probe")
        if (Path("intelligence") / "system_activity.log").exists():
            return CheckResult("Pipeline: ActivityLogger init", "pass", "Activity logger is persistent")
        return CheckResult("Pipeline: ActivityLogger init", "warn", "Activity logger file missing")
    except Exception as exc:
        return CheckResult("Pipeline: ActivityLogger init", "fail", str(exc))


def _pipeline_check_distribution_ledger() -> CheckResult:
    try:
        from modules.distribution_seeder import DistributionSeeder
        seeder = DistributionSeeder()
        ledger = seeder.build_distribution_ledger()
        return CheckResult("Pipeline: Distribution ledger", "pass", f"Ledger entries: {len(ledger)}")
    except Exception as exc:
        return CheckResult("Pipeline: Distribution ledger", "fail", str(exc))


def _pipeline_check_killswitch() -> CheckResult:
    try:
        from modules.system_state import abort_if_killed, is_killswitch_active, set_killswitch
        original = is_killswitch_active()
        set_killswitch(True)
        raised = False
        try:
            abort_if_killed()
        except RuntimeError:
            raised = True
        finally:
            set_killswitch(original)

        if raised:
            return CheckResult(
                "Pipeline: Killswitch enforcement", "pass",
                "abort_if_killed() correctly raises RuntimeError when active",
            )
        return CheckResult(
            "Pipeline: Killswitch enforcement", "fail",
            "abort_if_killed() did NOT raise — killswitch is broken",
        )
    except Exception as exc:
        return CheckResult("Pipeline: Killswitch enforcement", "fail", str(exc))


# ---------------------------------------------------------------------------
# Receipt persistence
# ---------------------------------------------------------------------------

def _save_receipt(report: DiagnosticReport) -> Path:
    INTELLIGENCE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = report.timestamp.replace(" ", "_").replace(":", "")
    path = INTELLIGENCE_DIR / f"diagnostic_receipt_{safe_ts}.md"
    path.write_text(report.full_receipt_text(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class DiagnosticsEngine:
    """Orchestrates all diagnostic checks and optionally applies auto-repairs."""

    def __init__(self, auto_repair: bool = False) -> None:
        self.auto_repair = auto_repair

    def run(self) -> DiagnosticReport:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = DiagnosticReport(timestamp=timestamp)

        # 1 — Environment audit
        report.results.extend(_check_required_directories(self.auto_repair))
        report.results.extend(_check_required_files())
        report.results.append(_check_system_state(self.auto_repair))
        report.results.extend(_check_env_file())

        # 2 — Network & security
        report.results.append(_check_header_rotation())
        report.results.append(_check_network_connectivity())

        # 3 — Pipeline integration dry-run
        report.results.append(_pipeline_check_crawler())
        report.results.append(_pipeline_check_lore())
        report.results.append(_pipeline_check_seeder())
        report.results.append(_pipeline_check_notifier())
        report.results.append(_pipeline_check_publisher())
        report.results.append(_pipeline_check_orchestrator())
        report.results.append(_pipeline_check_activity_logger())
        report.results.append(_pipeline_check_distribution_ledger())
        report.results.append(_pipeline_check_killswitch())

        # Persist receipt
        try:
            report.receipt_path = _save_receipt(report)
        except Exception as exc:
            report.results.append(CheckResult(
                "Receipt save", "warn", f"Could not write receipt: {exc}",
            ))

        return report


# ---------------------------------------------------------------------------
# Control panel adapter (imported by control_panel.py)
# ---------------------------------------------------------------------------

def run_diagnostics_ui(auto_repair: bool = True) -> tuple[str, str]:
    """Return (subsystem_table_md, full_receipt_text) for the Gradio UI."""
    try:
        engine = DiagnosticsEngine(auto_repair=auto_repair)
        report = engine.run()
        return report.subsystem_table_md(), report.full_receipt_text()
    except Exception:
        tb = traceback.format_exc()
        return "❌ Diagnostics crashed — see receipt below.", tb


def latest_receipt_text() -> str:
    """Return the text of the most recent diagnostic receipt, or a placeholder."""
    if not INTELLIGENCE_DIR.exists():
        return "No diagnostic receipts found yet. Click **Run Diagnostics** to generate one."
    receipts = sorted(INTELLIGENCE_DIR.glob("diagnostic_receipt_*.md"), reverse=True)
    if not receipts:
        return "No diagnostic receipts found yet. Click **Run Diagnostics** to generate one."
    return receipts[0].read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        prog="diagnostics",
        description="Pantheon Studios environment audit and self-healing tool",
    )
    parser.add_argument(
        "--auto-repair",
        action="store_true",
        help="Automatically create missing directories and repair .system_state.json",
    )
    args = parser.parse_args()

    engine = DiagnosticsEngine(auto_repair=args.auto_repair)
    report = engine.run()

    # Print summary to terminal
    print(f"\nPantheon Studios Diagnostics — {report.timestamp}")
    print("=" * 55)
    for r in report.results:
        icon = _ICON[r.status]
        rem = f"  → {r.remediation}" if r.remediation else ""
        print(f"  {icon}  {r.name}: {r.message}{rem}")

    print()
    overall_icon = _ICON[report.overall_status]
    print(
        f"Result: {overall_icon} {report.overall_status.upper()}  "
        f"({report.passed} passed, {report.warned} warned, {report.failed} failed)"
    )
    if report.receipt_path:
        print(f"Receipt: {report.receipt_path.as_posix()}")

    sys.exit(0 if report.overall_status != "fail" else 1)


if __name__ == "__main__":
    _cli()
