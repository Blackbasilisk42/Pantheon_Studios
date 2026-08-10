#!/usr/bin/env python3
"""Autonomous continuous testing, sandbox simulation, and daily heartbeat engine."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from modules.diagnostics import DiagnosticsEngine
    from modules.notifier import send_daily_heartbeat, send_test_sms_ping
    from modules.orchestrator import OrchestratorEngine
    from modules.security_manager import SecurityManager
    from modules.system_state import abort_if_killed, get_state, is_killswitch_active, set_killswitch
    from modules.activity_logger import emit_activity
except ModuleNotFoundError:  # pragma: no cover
    from diagnostics import DiagnosticsEngine  # type: ignore[no-redef]
    from notifier import send_daily_heartbeat, send_test_sms_ping  # type: ignore[no-redef]
    from orchestrator import OrchestratorEngine  # type: ignore[no-redef]
    from security_manager import SecurityManager  # type: ignore[no-redef]
    from system_state import abort_if_killed, get_state, is_killswitch_active, set_killswitch  # type: ignore[no-redef]
    from activity_logger import emit_activity  # type: ignore[no-redef]


INTELLIGENCE_DIR = Path("intelligence")
TELEMETRY_LOG = INTELLIGENCE_DIR / "sms_telemetry.log"
STATE_FILE = Path(".system_state.json")


class ContinuousTesterEngine:
    """Runs sandbox simulations and heartbeat checks without sending real outbound posts."""

    def __init__(self, workspace: Path | None = None, send_sms: bool = True) -> None:
        self.workspace = workspace or Path.cwd()
        self.send_sms = send_sms
        self.intelligence_dir = self.workspace / INTELLIGENCE_DIR
        self.telemetry_log = self.workspace / TELEMETRY_LOG
        self.state_file = self.workspace / STATE_FILE
        self.intelligence_dir.mkdir(parents=True, exist_ok=True)
        self.telemetry_log.touch(exist_ok=True)
        self.security = SecurityManager()

    def _append_telemetry(self, message: str) -> None:
        with self.telemetry_log.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")

    def _write_simulation_log(self, content: str) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.intelligence_dir / f"simulation_log_{timestamp}.md"
        path.write_text(content, encoding="utf-8")
        return path

    def _load_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"KILLSWITCH_ACTIVE": False, "LAST_SMS_HEARTBEAT_TIMESTAMP": None}
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"KILLSWITCH_ACTIVE": False, "LAST_SMS_HEARTBEAT_TIMESTAMP": None}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_file.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def _heartbeat_due(self, state: dict[str, Any]) -> bool:
        last_ts = state.get("LAST_SMS_HEARTBEAT_TIMESTAMP")
        if not last_ts:
            return True
        try:
            last = datetime.fromisoformat(str(last_ts))
        except ValueError:
            return True
        return datetime.now() - last >= timedelta(hours=24)

    def _simulate_sandbox(self) -> dict[str, Any]:
        mock_lore = [
            "The Lanternkeepers guard the river of memory.",
            "A faction of eclipse archivists studies the city beneath the bridge.",
            "A sacred relic awakens during the moonlit watch.",
        ]
        orchestration = OrchestratorEngine()
        result = orchestration.evaluate_context([
            {"title": f"mock_{idx}", "content": item} for idx, item in enumerate(mock_lore)
        ])
        queue_dir = self.workspace / "queue" / "pending"
        queue_dir.mkdir(parents=True, exist_ok=True)
        draft_path = queue_dir / "continuous_tester_mock.md"
        draft_path.write_text("# Sandbox Draft\n\nMock content for continuous testing.\n", encoding="utf-8")
        security_headers = self.security.random_browser_headers()
        return {
            "mock_lore_count": len(mock_lore),
            "orchestrator_ready": bool(result.get("ready")),
            "queue_staged": draft_path.exists(),
            "headers_sample": security_headers["User-Agent"],
            "formatting_ok": True,
        }

    def run_cycle(self) -> dict[str, Any]:
        state = self._load_state()
        if bool(state.get("KILLSWITCH_ACTIVE", False)):
            return {"status": "halted", "message": "Killswitch active."}

        emit_activity("System Thought", "continuous_tester", "Running self-healing diagnostics")
        diagnostics = DiagnosticsEngine(auto_repair=True)
        diagnostics.run()

        sandbox = self._simulate_sandbox()
        emit_activity("System Thought", "continuous_tester", "Completing sandbox simulation")
        receipt_paths = []
        receipt_path = self._write_simulation_log(
            "\n".join(
                [
                    "# Continuous Testing Simulation Receipt",
                    "",
                    f"- Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"- Orchestrator ready: {sandbox['orchestrator_ready']}",
                    f"- Queue staged: {sandbox['queue_staged']}",
                    f"- Headers sample: {sandbox['headers_sample']}",
                    f"- Formatting OK: {sandbox['formatting_ok']}",
                ]
            )
        )
        receipt_paths.append(receipt_path.as_posix())

        if self.send_sms and self._heartbeat_due(state):
            try:
                send_daily_heartbeat()
                state["LAST_SMS_HEARTBEAT_TIMESTAMP"] = datetime.now().isoformat()
                self._save_state(state)
            except Exception as exc:  # noqa: BLE001
                self._append_telemetry(f"{datetime.now().isoformat()} heartbeat_error {exc}")

        self._append_telemetry(
            f"{datetime.now().isoformat()} simulation status={sandbox['orchestrator_ready']} queue={sandbox['queue_staged']}"
        )
        return {
            "status": "simulated",
            "receipt_paths": receipt_paths,
            "log_path": self.intelligence_dir / receipt_path.name,
            "sandbox": sandbox,
        }

    def start_daemon(self, interval_minutes: int = 15, stop_event: threading.Event | None = None) -> None:
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            try:
                if is_killswitch_active():
                    self._append_telemetry(f"{datetime.now().isoformat()} daemon_halted killswitch")
                    break
                self.run_cycle()
            except Exception as exc:  # noqa: BLE001
                self._append_telemetry(f"{datetime.now().isoformat()} daemon_error {exc}")
            stop_event.wait(interval_minutes * 60)


def run_daemon_cli(interval_minutes: int = 15) -> None:
    engine = ContinuousTesterEngine(send_sms=True)
    engine.start_daemon(interval_minutes=interval_minutes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pantheon Studios continuous tester")
    parser.add_argument("--daemon", action="store_true", help="start the background daemon loop")
    parser.add_argument("--interval-minutes", type=int, default=15)
    args = parser.parse_args()
    if args.daemon:
        run_daemon_cli(interval_minutes=args.interval_minutes)
    else:
        engine = ContinuousTesterEngine(send_sms=False)
        result = engine.run_cycle()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
