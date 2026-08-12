#!/usr/bin/env python3
"""Unified site launcher and per-site kill switch controller for Pantheon Studios."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HUB_ROOT = ROOT / "hub"
RUNTIME_DIR = ROOT / "logs" / "runtime"
PROCESS_FILE = RUNTIME_DIR / "site_processes.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.system_state import get_site_switches, set_killswitch, set_site_enabled  # noqa: E402

HUB_REQUIREMENTS = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
    "python-jose",
    "passlib",
    "bcrypt",
    "python-multipart",
    "jinja2",
    "requests",
]

SERVICES: dict[str, dict[str, object]] = {
    "control_panel": {
        "title": "Pantheon Control Panel",
        "cwd": ROOT,
        "cmd": 'title Pantheon Control Panel && call ".venv\\Scripts\\activate.bat" && python modules\\control_panel.py',
    },
    "team_hub": {
        "title": "Pantheon Team Hub",
        "cwd": HUB_ROOT,
        "cmd": 'title Pantheon Team Hub && call ".venv\\Scripts\\activate.bat" && python -m uvicorn server:app --host 0.0.0.0 --port 7861',
    },
    "hub_tunnel": {
        "title": "Pantheon Hub Tunnel",
        "cwd": HUB_ROOT,
        "cmd": 'title Pantheon Hub Tunnel && call ".venv\\Scripts\\activate.bat" && python tunnel.py',
    },
}


def _ensure_runtime_files() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not PROCESS_FILE.exists():
        PROCESS_FILE.write_text(json.dumps({}, indent=2) + "\n", encoding="utf-8")


def _read_registry() -> dict[str, dict[str, object]]:
    _ensure_runtime_files()
    try:
        raw = json.loads(PROCESS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _write_registry(registry: dict[str, dict[str, object]]) -> None:
    _ensure_runtime_files()
    PROCESS_FILE.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout or "").strip().lower()
    return bool(output) and "no tasks" not in output


def _ensure_hub_venv() -> None:
    activate_script = HUB_ROOT / ".venv" / "Scripts" / "activate.bat"
    if activate_script.exists():
        return

    print("[site-launcher] creating hub virtual environment...")
    subprocess.run([sys.executable, "-m", "venv", ".venv"], cwd=HUB_ROOT, check=True)

    hub_python = HUB_ROOT / ".venv" / "Scripts" / "python.exe"
    print("[site-launcher] installing hub dependencies...")
    subprocess.run(
        [str(hub_python), "-m", "pip", "install", "-q", *HUB_REQUIREMENTS],
        cwd=HUB_ROOT,
        check=True,
    )


def _start_service(name: str, force: bool = False) -> int:
    if name not in SERVICES:
        print(f"[site-launcher] unknown service: {name}")
        return 1

    switches = get_site_switches()
    if not force and not bool(switches.get(name, False)):
        print(f"[site-launcher] {name} is disabled by switch; skipping.")
        return 0

    if name in {"team_hub", "hub_tunnel"}:
        _ensure_hub_venv()

    registry = _read_registry()
    existing = registry.get(name, {})
    existing_pid = int(existing.get("pid", 0)) if isinstance(existing, dict) else 0
    if existing_pid and _is_pid_running(existing_pid):
        print(f"[site-launcher] {name} already running (PID {existing_pid}).")
        return 0

    service = SERVICES[name]
    cmd = str(service["cmd"])
    cwd = Path(service["cwd"])
    process = subprocess.Popen(
        ["cmd", "/k", cmd],
        cwd=cwd,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    registry[name] = {
        "pid": process.pid,
        "running": True,
        "cwd": str(cwd),
    }
    _write_registry(registry)
    print(f"[site-launcher] started {name} (PID {process.pid}).")
    return 0


def _stop_service(name: str) -> int:
    registry = _read_registry()
    entry = registry.get(name)
    if not isinstance(entry, dict):
        print(f"[site-launcher] {name} is not tracked as running.")
        return 0

    pid = int(entry.get("pid", 0))
    if pid <= 0 or not _is_pid_running(pid):
        print(f"[site-launcher] {name} is already offline.")
        registry[name] = {"pid": 0, "running": False}
        _write_registry(registry)
        return 0

    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    registry[name] = {"pid": 0, "running": False}
    _write_registry(registry)
    print(f"[site-launcher] stopped {name} (PID {pid}).")
    return 0


def _status() -> int:
    registry = _read_registry()
    switches = get_site_switches()
    print("Pantheon Site Status")
    print("=" * 44)
    for name in SERVICES:
        entry = registry.get(name, {})
        pid = int(entry.get("pid", 0)) if isinstance(entry, dict) else 0
        running = _is_pid_running(pid)
        enabled = bool(switches.get(name, False))
        print(f"- {name:14} enabled={enabled:<5} running={running:<5} pid={pid if running else 0}")
    return 0


def _set_site_switch(name: str, enabled: bool) -> int:
    set_site_enabled(name, enabled)
    state = "enabled" if enabled else "disabled"
    print(f"[site-launcher] {name} switch {state}.")
    return 0


def _master_killswitch(active: bool) -> int:
    set_killswitch(active)
    state = "ACTIVE" if active else "INACTIVE"
    print(f"[site-launcher] master killswitch is now {state}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pantheon multi-site launcher")
    sub = parser.add_subparsers(dest="command", required=True)

    start_all = sub.add_parser("start-all", help="Start all enabled services")
    start_all.add_argument("--force", action="store_true", help="Ignore service switches")

    start_one = sub.add_parser("start", help="Start one service")
    start_one.add_argument("service", choices=tuple(SERVICES.keys()))
    start_one.add_argument("--force", action="store_true", help="Ignore service switch")

    stop = sub.add_parser("stop", help="Stop one service or all")
    stop.add_argument("service", choices=("all", *SERVICES.keys()))

    enable = sub.add_parser("enable", help="Enable a service switch")
    enable.add_argument("service", choices=tuple(SERVICES.keys()))

    disable = sub.add_parser("disable", help="Disable a service switch")
    disable.add_argument("service", choices=tuple(SERVICES.keys()))

    mkill = sub.add_parser("master-killswitch", help="Toggle global killswitch")
    mkill.add_argument("state", choices=("on", "off"))

    sub.add_parser("status", help="Show tracked runtime status")

    args = parser.parse_args()

    if args.command == "start-all":
        rc = 0
        for name in SERVICES:
            rc = max(rc, _start_service(name, force=args.force))
        return rc
    if args.command == "start":
        return _start_service(args.service, force=args.force)
    if args.command == "stop":
        if args.service == "all":
            rc = 0
            for name in SERVICES:
                rc = max(rc, _stop_service(name))
            return rc
        return _stop_service(args.service)
    if args.command == "enable":
        return _set_site_switch(args.service, True)
    if args.command == "disable":
        return _set_site_switch(args.service, False)
    if args.command == "master-killswitch":
        return _master_killswitch(args.state == "on")
    if args.command == "status":
        return _status()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
