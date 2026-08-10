#!/usr/bin/env python3
"""Pantheon Studios System Synchronization & Readiness Manager.

Run directly:
    python modules/sync_manager.py --verify

Imported by control_panel.py for the Sync & System Readiness tab.
"""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

INTELLIGENCE_DIR = Path("intelligence")
POLICIES_DIR = Path("policies")
LORE_DIR = Path("lore")
DIST_DIR = Path("dist")

POLICY_SOURCE = POLICIES_DIR / "privacy_and_copyright.md"
POLICY_MIRROR = DIST_DIR / "PUBLIC_POLICY.md"
IMMUTABLE_RULES = LORE_DIR / "immutable_rules.md"
STATE_FILE = Path(".system_state.json")

REQUIRED_DIRS = [
    "lore",
    "queue/pending",
    "queue/approved",
    "queue/rejected",
    "intelligence",
    "modules",
    "publishers",
    "dist/media_kits",
]

# State keys required in .system_state.json
REQUIRED_STATE_KEYS: dict[str, object] = {
    "KILLSWITCH_ACTIVE": False,
    "LEARNING_ENABLED": True,
    "LAST_SYNC_TIMESTAMP": None,
}

# Modules that must import without error
PIPELINE_MODULES = [
    "modules.security_manager",
    "modules.crawler_engine",
    "modules.distribution_seeder",
    "modules.lore_ingest",
    "modules.approval_gate",
    "modules.notifier",
    "modules.learning_engine",
    "modules.diagnostics",
    "modules.orchestrator",
    "modules.activity_logger",
    "publishers.anonymous_feed_publisher",
]

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

Status = Literal["pass", "warn", "fail"]
_ICON: dict[str, str] = {"pass": "✅", "warn": "⚠️", "fail": "❌"}


@dataclass
class SyncCheck:
    name: str
    status: Status
    message: str
    remediation: str = ""


@dataclass
class SyncReport:
    timestamp: str
    checks: list[SyncCheck] = field(default_factory=list)
    receipt_path: Path | None = None

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def warned(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def overall(self) -> Status:
        if self.failed:
            return "fail"
        if self.warned:
            return "warn"
        return "pass"

    @property
    def readiness_label(self) -> str:
        if self.overall == "pass":
            return "✅ 100% READY FOR LIVE TESTING"
        if self.overall == "warn":
            return "⚠️ READY WITH WARNINGS — review before live testing"
        return "❌ NOT READY — resolve failures before live testing"

    def receipt_text(self) -> str:
        lines = [
            "# Pantheon Studios — System Sync Report",
            "",
            f"- **Run at:** {self.timestamp}",
            f"- **Checks:** {self.passed} passed / {self.warned} warned / {self.failed} failed",
            f"- **Status:** {self.readiness_label}",
            "",
        ]

        sections: dict[str, list[SyncCheck]] = {
            "Directory & File Integrity": [],
            "Policy & Guardrail Sync": [],
            "State File Validation": [],
            "Pipeline Import Audit": [],
        }
        for c in self.checks:
            if c.name.startswith("Dir:") or c.name.startswith("File:"):
                sections["Directory & File Integrity"].append(c)
            elif c.name.startswith("Policy") or c.name.startswith("Guardrail") or c.name.startswith("Immutable"):
                sections["Policy & Guardrail Sync"].append(c)
            elif c.name.startswith("State"):
                sections["State File Validation"].append(c)
            else:
                sections["Pipeline Import Audit"].append(c)

        for section, items in sections.items():
            if not items:
                continue
            lines += [f"## {section}", "", "| Check | Status | Message | Remediation |",
                      "|-------|--------|---------|-------------|"]
            for c in items:
                lines.append(
                    f"| {c.name} | {_ICON[c.status]} {c.status} | {c.message} | {c.remediation or '—'} |"
                )
            lines.append("")

        if self.receipt_path:
            lines.append(f"---\n_Saved to: {self.receipt_path.as_posix()}_")
        return "\n".join(lines)

    def summary_md(self) -> str:
        return (
            f"| Sync Metric | Value |\n"
            f"|-------------|-------|\n"
            f"| **Readiness** | {self.readiness_label} |\n"
            f"| **Checks passed** | {self.passed} |\n"
            f"| **Warnings** | {self.warned} |\n"
            f"| **Failures** | {self.failed} |\n"
            f"| **Run at** | {self.timestamp} |\n"
        )


# ---------------------------------------------------------------------------
# Check: required directories
# ---------------------------------------------------------------------------

def _check_directories() -> list[SyncCheck]:
    results: list[SyncCheck] = []
    for d in REQUIRED_DIRS:
        p = Path(d)
        if p.exists():
            results.append(SyncCheck(f"Dir: {d}", "pass", "Exists"))
        else:
            p.mkdir(parents=True, exist_ok=True)
            results.append(SyncCheck(
                f"Dir: {d}", "warn", "Missing — created",
                remediation=f"mkdir -p {d}",
            ))
    return results


# ---------------------------------------------------------------------------
# Check: required files
# ---------------------------------------------------------------------------

def _check_files() -> list[SyncCheck]:
    required = [
        "modules/security_manager.py",
        "modules/system_state.py",
        "modules/approval_gate.py",
        "modules/activity_logger.py",
        "lore/immutable_rules.md",
        "policies/privacy_and_copyright.md",
    ]
    return [
        SyncCheck(f"File: {f}", "pass", "Present") if Path(f).exists()
        else SyncCheck(f"File: {f}", "fail", "Missing")
        for f in required
    ]


# ---------------------------------------------------------------------------
# Check: policy mirror
# ---------------------------------------------------------------------------

def _check_activity_logger() -> SyncCheck:
    log_path = Path("intelligence") / "system_activity.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists():
        return SyncCheck("Activity logger persistence", "pass", f"{log_path} present")
    return SyncCheck("Activity logger persistence", "warn", "Activity logger file missing")


def _check_policy_mirror() -> list[SyncCheck]:
    results: list[SyncCheck] = []

    if not POLICY_SOURCE.exists():
        results.append(SyncCheck(
            "Policy source", "fail",
            f"{POLICY_SOURCE} not found — cannot mirror",
        ))
        return results

    results.append(SyncCheck("Policy source", "pass", f"{POLICY_SOURCE} present"))

    DIST_DIR.mkdir(parents=True, exist_ok=True)

    if not POLICY_MIRROR.exists():
        shutil.copy2(str(POLICY_SOURCE), str(POLICY_MIRROR))
        results.append(SyncCheck(
            "Policy mirror (dist/PUBLIC_POLICY.md)", "warn",
            "Missing — copied from source",
            remediation=f"cp {POLICY_SOURCE} {POLICY_MIRROR}",
        ))
        return results

    # Compare content
    src_text = POLICY_SOURCE.read_text(encoding="utf-8", errors="replace")
    dst_text = POLICY_MIRROR.read_text(encoding="utf-8", errors="replace")
    if src_text == dst_text:
        results.append(SyncCheck(
            "Policy mirror (dist/PUBLIC_POLICY.md)", "pass",
            "In sync with source",
        ))
    else:
        shutil.copy2(str(POLICY_SOURCE), str(POLICY_MIRROR))
        results.append(SyncCheck(
            "Policy mirror (dist/PUBLIC_POLICY.md)", "warn",
            "Out of sync — re-synced from source",
            remediation=f"Overwrote {POLICY_MIRROR} with current {POLICY_SOURCE}",
        ))

    return results


def _check_immutable_rules() -> SyncCheck:
    if not IMMUTABLE_RULES.exists():
        return SyncCheck(
            "Immutable rules", "fail",
            f"{IMMUTABLE_RULES} not found — create lore/immutable_rules.md",
        )
    try:
        content = IMMUTABLE_RULES.read_text(encoding="utf-8")
        if "KILLSWITCH" in content and "Human-in-the-Loop" in content:
            return SyncCheck("Immutable rules", "pass", "Present and readable")
        return SyncCheck("Immutable rules", "warn", "File exists but expected authority clauses not detected")
    except OSError as exc:
        return SyncCheck("Immutable rules", "fail", f"Cannot read: {exc}")


# ---------------------------------------------------------------------------
# Check: state file
# ---------------------------------------------------------------------------

def _check_state_file() -> list[SyncCheck]:
    results: list[SyncCheck] = []

    if not STATE_FILE.exists():
        _write_state(dict(REQUIRED_STATE_KEYS))
        results.append(SyncCheck(
            "State file (.system_state.json)", "warn",
            "Missing — created with required keys",
            remediation="Created .system_state.json",
        ))
        return results

    try:
        data: dict = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        data = {}
        results.append(SyncCheck(
            "State file (.system_state.json)", "fail",
            f"Corrupted JSON ({exc}) — rebuilt",
            remediation="Overwrote with safe defaults",
        ))

    missing_keys = [k for k in REQUIRED_STATE_KEYS if k not in data]
    if missing_keys:
        for k in missing_keys:
            data[k] = REQUIRED_STATE_KEYS[k]
        _write_state(data)
        results.append(SyncCheck(
            "State file (.system_state.json)", "warn",
            f"Added missing keys: {', '.join(missing_keys)}",
            remediation=f"Injected {missing_keys}",
        ))
    else:
        results.append(SyncCheck(
            "State file (.system_state.json)", "pass",
            f"All required keys present — KILLSWITCH={data['KILLSWITCH_ACTIVE']}",
        ))

    # Validate types
    for k, expected in REQUIRED_STATE_KEYS.items():
        if k not in data:
            continue
        val = data[k]
        if k.endswith("_ACTIVE") or k.endswith("_ENABLED"):
            if not isinstance(val, bool):
                data[k] = bool(val)
                results.append(SyncCheck(
                    f"State key: {k}", "warn",
                    f"Wrong type — corrected to bool",
                    remediation=f"Coerced {k} to bool",
                ))
            else:
                results.append(SyncCheck(f"State key: {k}", "pass", f"= {val}"))
        else:
            results.append(SyncCheck(f"State key: {k}", "pass", f"= {val!r}"))

    _write_state(data)
    return results


def _write_state(data: dict) -> None:
    STATE_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _stamp_sync_timestamp() -> None:
    """Update LAST_SYNC_TIMESTAMP in .system_state.json."""
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    except json.JSONDecodeError:
        raw = {}
    raw["LAST_SYNC_TIMESTAMP"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_state(raw)


# ---------------------------------------------------------------------------
# Check: pipeline imports (circular dependency detection)
# ---------------------------------------------------------------------------

def _check_pipeline_imports() -> list[SyncCheck]:
    results: list[SyncCheck] = []

    # Isolate each import in a subprocess-like way using importlib in a fresh
    # namespace; we clear any previously cached version first to catch errors.
    for mod_name in PIPELINE_MODULES:
        # Remove from cache so we get a fresh import attempt
        cached = sys.modules.pop(mod_name, None)
        try:
            importlib.import_module(mod_name)
            results.append(SyncCheck(f"Import: {mod_name}", "pass", "OK"))
        except ImportError as exc:
            msg = str(exc)
            # Missing third-party dep is a warning, not a failure
            status: Status = "warn" if "No module named" in msg else "fail"
            results.append(SyncCheck(f"Import: {mod_name}", status, msg))
        except Exception as exc:
            results.append(SyncCheck(f"Import: {mod_name}", "fail", str(exc)))
        finally:
            # Restore original cache entry so we don't break a running process
            if cached is not None and mod_name not in sys.modules:
                sys.modules[mod_name] = cached

    return results


# ---------------------------------------------------------------------------
# Receipt persistence
# ---------------------------------------------------------------------------

def _save_receipt(report: SyncReport) -> Path:
    INTELLIGENCE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = report.timestamp.replace(" ", "_").replace(":", "")
    path = INTELLIGENCE_DIR / f"sync_report_{safe_ts}.md"
    path.write_text(report.receipt_text(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class SyncManager:
    def run(self) -> SyncReport:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = SyncReport(timestamp=timestamp)

        report.checks.extend(_check_directories())
        report.checks.extend(_check_files())
        report.checks.extend(_check_policy_mirror())
        report.checks.append(_check_immutable_rules())
        report.checks.extend(_check_state_file())
        report.checks.extend(_check_pipeline_imports())

        _stamp_sync_timestamp()

        try:
            report.receipt_path = _save_receipt(report)
        except Exception as exc:
            report.checks.append(SyncCheck("Receipt save", "warn", f"Could not write: {exc}"))

        return report


# ---------------------------------------------------------------------------
# Control panel adapter
# ---------------------------------------------------------------------------

def run_sync_ui() -> tuple[str, str]:
    """Return (summary_md, full_receipt_text) for the Gradio UI."""
    try:
        report = SyncManager().run()
        return report.summary_md(), report.receipt_text()
    except Exception as exc:
        import traceback
        return "❌ Sync crashed.", traceback.format_exc()


def latest_sync_report_text() -> str:
    if not INTELLIGENCE_DIR.exists():
        return "No sync reports yet. Click **Run Full System Sync** to generate one."
    reports = sorted(INTELLIGENCE_DIR.glob("sync_report_*.md"), reverse=True)
    if not reports:
        return "No sync reports yet. Click **Run Full System Sync** to generate one."
    return reports[0].read_text(encoding="utf-8", errors="replace")


def readiness_badge_md() -> str:
    """One-line badge for the control panel header — cheap, no full sync run."""
    reports = sorted(INTELLIGENCE_DIR.glob("sync_report_*.md"), reverse=True) if INTELLIGENCE_DIR.exists() else []
    if not reports:
        return "🔲 **System Sync:** Not yet run — click **Run Full System Sync**"
    txt = reports[0].read_text(encoding="utf-8", errors="replace")
    if "100% READY" in txt:
        return "✅ **System Sync:** 100% READY FOR LIVE TESTING"
    if "READY WITH WARNINGS" in txt:
        return "⚠️ **System Sync:** Ready with warnings"
    return "❌ **System Sync:** Not ready — failures detected"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        prog="sync_manager",
        description="Pantheon Studios system synchronization and readiness check",
    )
    parser.add_argument("--verify", action="store_true", help="Run full sync and report readiness")
    args = parser.parse_args()

    if not args.verify:
        parser.print_help()
        sys.exit(0)

    report = SyncManager().run()

    print(f"\nPantheon Studios — System Sync  {report.timestamp}")
    print("=" * 55)
    for c in report.checks:
        icon = _ICON[c.status]
        rem = f"  → {c.remediation}" if c.remediation else ""
        print(f"  {icon}  {c.name}: {c.message}{rem}")

    print()
    print(f"  {report.readiness_label}")
    print(f"  ({report.passed} passed, {report.warned} warned, {report.failed} failed)")
    if report.receipt_path:
        print(f"  Receipt: {report.receipt_path.as_posix()}")

    sys.exit(0 if report.overall != "fail" else 1)


if __name__ == "__main__":
    _cli()
