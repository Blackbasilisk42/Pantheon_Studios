#!/usr/bin/env python3
"""Shared system-state reader/writer for Pantheon Studios.

All background scripts must call abort_if_killed() before any network or
queue action so the Master Killswitch in control_panel.py takes immediate
effect across every process.
"""

from __future__ import annotations

import json
from pathlib import Path

STATE_FILE = Path(".system_state.json")

_DEFAULTS: dict[str, object] = {
    "KILLSWITCH_ACTIVE": False,
    "LEARNING_ENABLED": True,
    "LAST_SYNC_TIMESTAMP": None,
    "SITE_SWITCHES": {
        "control_panel": True,
        "team_hub": True,
        "hub_tunnel": True,
    },
}


_KNOWN_SITES = ("control_panel", "team_hub", "hub_tunnel")


def _read() -> dict[str, object]:
    if not STATE_FILE.exists():
        return dict(_DEFAULTS)
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return {**_DEFAULTS, **data}
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)


def _write(state: dict[str, object]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def is_killswitch_active() -> bool:
    return bool(_read().get("KILLSWITCH_ACTIVE", False))


def set_killswitch(active: bool) -> None:
    state = _read()
    state["KILLSWITCH_ACTIVE"] = active
    _write(state)


def get_site_switches() -> dict[str, bool]:
    state = _read()
    raw = state.get("SITE_SWITCHES")
    switches = dict(_DEFAULTS["SITE_SWITCHES"])
    if isinstance(raw, dict):
        for site in _KNOWN_SITES:
            if site in raw:
                switches[site] = bool(raw.get(site))
    return switches


def is_site_enabled(site_name: str) -> bool:
    return bool(get_site_switches().get(site_name, False))


def set_site_enabled(site_name: str, enabled: bool) -> dict[str, bool]:
    if site_name not in _KNOWN_SITES:
        raise ValueError(f"Unknown site switch: {site_name}")
    state = _read()
    switches = get_site_switches()
    switches[site_name] = bool(enabled)
    state["SITE_SWITCHES"] = switches
    _write(state)
    return switches


def abort_if_killed() -> None:
    """Raise RuntimeError immediately if the killswitch is active."""
    if is_killswitch_active():
        raise RuntimeError(
            "KILLSWITCH_ACTIVE — all automated actions are halted. "
            "Disable the Master Killswitch in the control panel to resume."
        )


def get_state() -> dict[str, object]:
    return _read()
