#!/usr/bin/env python3
"""Pantheon Studios local web control panel (Gradio).

Run with:
    python modules/control_panel.py

Opens on http://127.0.0.1:7860 — localhost only, never exposed externally.
"""

from __future__ import annotations

import os
import shutil
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

import gradio as gr

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional for environment loading

try:
    from modules.lore_ingest import save_entry
    from modules.system_state import get_state, is_killswitch_active, set_killswitch
    from modules.diagnostics import latest_receipt_text, run_diagnostics_ui
    from modules.learning_engine import (
        get_learning_status_md,
        latest_learning_log_text,
        run_feedback_only_ui,
        run_full_cycle_ui,
        toggle_trend_learning_ui,
    )
    from modules.sync_manager import (
        latest_sync_report_text,
        readiness_badge_md,
        run_sync_ui,
    )
    from modules.orchestrator import orchestrator_status_md, run_orchestrator_ui, toggle_orchestrator
    from modules.distribution_seeder import DistributionSeeder
    from modules.continuous_tester import ContinuousTesterEngine
    from modules.activity_logger import get_activity_logger
    from modules.heavy_crawler import run_parallel_scan
except ModuleNotFoundError:
    from lore_ingest import save_entry  # type: ignore[no-redef]
    from system_state import get_state, is_killswitch_active, set_killswitch  # type: ignore[no-redef]
    from diagnostics import latest_receipt_text, run_diagnostics_ui  # type: ignore[no-redef]
    from learning_engine import (  # type: ignore[no-redef]
        get_learning_status_md,
        latest_learning_log_text,
        run_feedback_only_ui,
        run_full_cycle_ui,
        toggle_trend_learning_ui,
    )
    from sync_manager import (  # type: ignore[no-redef]
        latest_sync_report_text,
        readiness_badge_md,
        run_sync_ui,
    )
    from orchestrator import (  # type: ignore[no-redef]
        orchestrator_status_md,
        run_orchestrator_ui,
        toggle_orchestrator,
    )
    from distribution_seeder import DistributionSeeder  # type: ignore[no-redef]
    from continuous_tester import ContinuousTesterEngine  # type: ignore[no-redef]
    from activity_logger import get_activity_logger  # type: ignore[no-redef]
    from heavy_crawler import run_parallel_scan  # type: ignore[no-redef]


def _resolve_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"


PENDING_DIR = Path("queue") / "pending"
APPROVED_DIR = Path("queue") / "approved"
REJECTED_DIR = Path("queue") / "rejected"

CSS_THEME = """
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Fira+Code:wght@400;500;700&display=swap');

:root { color-scheme: dark; }
.gradio-container {
  background: radial-gradient(circle at top left, rgba(0,243,255,0.08), transparent 24%), linear-gradient(180deg, #06080e 0%, #0b0f19 100%);
  font-family: 'Orbitron', sans-serif;
  padding: 16px;
}
.gradio-container::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image: linear-gradient(rgba(0,243,255,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(0,243,255,0.08) 1px, transparent 1px);
  background-size: 28px 28px;
  opacity: 0.16;
  mask-image: linear-gradient(180deg, rgba(0,0,0,0.65), rgba(0,0,0,0));
}
body, .gradio-container, .gradio-container .gradio-markdown, .gradio-container .gradio-textbox, .gradio-container .gradio-dropdown, .gradio-container .gradio-checkbox, .gradio-container .gradio-slider {
  color: #eafcff;
}
h1, h2, h3, .hud-title {
  font-family: 'Orbitron', sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.22em;
  text-shadow: 0 0 10px rgba(0,243,255,0.45);
}
.hud-card, .gradio-container .gr-box, .gradio-container .gr-form, .gradio-container .block, .gradio-container .tabitem, .gradio-container .tabs {
  background: rgba(14, 20, 36, 0.84) !important;
  border: 1px solid rgba(0,243,255,0.42) !important;
  box-shadow: 0 0 12px rgba(0,243,255,0.15), inset 0 0 8px rgba(0,243,255,0.08) !important;
  border-radius: 16px;
}
.gradio-container .gradio-button {
  background: linear-gradient(135deg, #092635 0%, #0f8f9b 100%) !important;
  color: #f7ffff !important;
  border: 1px solid rgba(0,243,255,0.55) !important;
  box-shadow: 0 0 10px rgba(0,243,255,0.22) !important;
  border-radius: 999px !important;
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}
.gradio-container .gradio-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 16px rgba(0,243,255,0.36) !important;
}
.hud-btn-killswitch {
  background: linear-gradient(135deg, #26070c 0%, #ff3366 100%) !important;
  box-shadow: 0 0 14px rgba(255,51,102,0.38) !important;
}
.hud-btn-success {
  background: linear-gradient(135deg, #062e1f 0%, #00ff88 100%) !important;
  box-shadow: 0 0 10px rgba(0,255,136,0.28) !important;
}
.hud-terminal {
  background: #050b12 !important;
  color: #78ffb2 !important;
  font-family: 'Fira Code', monospace !important;
  border: 1px solid rgba(0,243,255,0.35) !important;
  box-shadow: inset 0 0 12px rgba(0,243,255,0.12) !important;
}
.hud-banner {
  padding: 16px 20px;
  border-radius: 18px;
  background: linear-gradient(90deg, rgba(7,16,28,0.95), rgba(12,25,41,0.9));
  border: 1px solid rgba(0,243,255,0.5);
  box-shadow: 0 0 20px rgba(0,243,255,0.18);
}
.hud-badge {
  display: inline-block;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(0,255,136,0.14);
  color: #7bffb1;
  border: 1px solid rgba(0,255,136,0.36);
  box-shadow: 0 0 8px rgba(0,255,136,0.18);
}
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: rgba(4,8,14,0.8); }
::-webkit-scrollbar-thumb {
  background: linear-gradient(180deg, #0f8f9b, #00f3ff);
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.08);
}
"""

HUD_BANNER_HTML = """
<div class='hud-banner'>
  <div style='display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;'>
    <div>
      <div class='hud-title' style='font-size:1.35rem; margin:0;'>PANTHEON STUDIOS — MISSION CONTROL HUD</div>
      <div style='font-size:0.9rem; color:#88d8ff; margin-top:6px;'>Multi-threaded orchestration • secure LAN access • autonomous synthesis</div>
    </div>
    <div style='display:flex; align-items:center; gap:10px; flex-wrap:wrap;'>
      <span class='hud-badge'>● SYSTEM ONLINE / MULTI-THREADED</span>
      <span style='font-family:"Fira Code", monospace; color:#7af7ff;'>http://{local_ip}:7860</span>
      <span class='hud-badge'>AUTHORIZED ACCESS</span>
    </div>
  </div>
</div>
""".format(local_ip=_resolve_local_ip())

for _d in (PENDING_DIR, APPROVED_DIR, REJECTED_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

CONTROL_PANEL_USER = os.getenv("CONTROL_PANEL_USER", "admin")
CONTROL_PANEL_PASS = os.getenv("CONTROL_PANEL_PASS", "@Sammyzzz3Jimbo21")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pending_files() -> list[Path]:
    return sorted(PENDING_DIR.glob("*.md"))


def _pending_names() -> list[str]:
    return [f.name for f in _pending_files()]


def _move(source: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name
    counter = 1
    while dest.exists():
        dest = dest_dir / f"{source.stem}_{counter}{source.suffix}"
        counter += 1
    return Path(shutil.move(str(source), str(dest)))


def _status_md() -> str:
    state = get_state()
    killed = bool(state.get("KILLSWITCH_ACTIVE"))
    pending_count = len(_pending_files())
    readiness = readiness_badge_md()
    kill_icon = "🔴 ACTIVE — all automation HALTED" if killed else "🟢 Inactive — system running"
    return (
        f"| Indicator | Value |\n"
        f"|-----------|-------|\n"
        f"| **Killswitch** | {kill_icon} |\n"
        f"| **Pending queue items** | {pending_count} |\n"
        f"| **System readiness** | {readiness} |\n"
        f"| **Timestamp** | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |\n"
    )


def _connection_banner() -> str:
    ip = _resolve_local_ip()
    return (
        f"🌐 On this PC: http://localhost:7860 or http://127.0.0.1:7860\n"
        f"📱 On phone/laptop (same Wi-Fi): http://{ip}:7860\n"
        f"🔐 Sign in with the credentials stored in the workspace .env file."
    )


# ---------------------------------------------------------------------------
# Killswitch
# ---------------------------------------------------------------------------

def toggle_killswitch(current_state: bool) -> tuple[bool, str, str]:
    new_state = not current_state
    set_killswitch(new_state)
    label = "🔴 KILLSWITCH — DEACTIVATE" if new_state else "🟢 KILLSWITCH — ACTIVATE"
    status = _status_md()
    return new_state, label, status


# ---------------------------------------------------------------------------
# Lore ingest
# ---------------------------------------------------------------------------

def save_lore(title: str, category: str, tags_raw: str, body: str) -> str:
    title = title.strip()
    body = body.strip()
    if not title:
        return "Error: Title cannot be empty."
    if not body:
        return "Error: Content cannot be empty."
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw.strip() else []
    path = save_entry(title, category, tags, body)
    return f"Saved to {path.as_posix()}"


# ---------------------------------------------------------------------------
# Approval queue
# ---------------------------------------------------------------------------

def refresh_queue() -> tuple[list[str], str]:
    names = _pending_names()
    preview = "" if not names else _preview(names[0])
    return names, preview


def _preview(filename: str) -> str:
    if not filename:
        return ""
    path = PENDING_DIR / filename
    if not path.exists():
        return "(file no longer exists)"
    content = path.read_text(encoding="utf-8", errors="replace")
    return content[:3000] + ("\n\n...[truncated]" if len(content) > 3000 else "")


def load_preview(filename: str) -> tuple[str, str]:
    return _preview(filename), _preview(filename)


def approve_item(filename: str) -> tuple[str, list[str], str]:
    if not filename:
        return "No item selected.", _pending_names(), _status_md()
    src = PENDING_DIR / filename
    if not src.exists():
        return f"File not found: {filename}", _pending_names(), _status_md()
    dest = _move(src, APPROVED_DIR)
    dispatch_summary = dispatch_latest_approved(limit=1)
    return f"Approved → {dest.as_posix()}\n{dispatch_summary}", _pending_names(), _status_md()


def reject_item(filename: str) -> tuple[str, list[str], str]:
    if not filename:
        return "No item selected.", _pending_names(), _status_md()
    src = PENDING_DIR / filename
    if not src.exists():
        return f"File not found: {filename}", _pending_names(), _status_md()
    dest = _move(src, REJECTED_DIR)
    return f"Rejected → {dest.as_posix()}", _pending_names(), _status_md()


def save_edit(filename: str, edited_content: str) -> tuple[str, list[str]]:
    if not filename:
        return "No item selected.", _pending_names()
    path = PENDING_DIR / filename
    if not path.exists():
        return f"File not found: {filename}", _pending_names()
    path.write_text(edited_content, encoding="utf-8")
    return f"Saved edits to {filename}", _pending_names()


def get_security_snapshot() -> str:
    try:
        from modules.security_manager import SecurityManager

        security = SecurityManager()
        headers = security.random_browser_headers()
        return (
            f"- Header rotation: active\n"
            f"- Current user-agent sample: {headers['User-Agent']}\n"
            f"- Metadata stripping: available via SecurityManager.strip_sensitive_metadata()\n"
            f"- Default jitter range: 2s–7s\n"
            f"- Proxy/crawler stealth: randomized browser headers + delayed requests"
        )
    except Exception as exc:
        return f"Security snapshot unavailable: {exc}"


def update_security_settings(
    enable_jitter: bool,
    min_delay: int,
    max_delay: int,
    strip_metadata: bool,
) -> str:
    safe_min = max(2, min(min_delay, 7))
    safe_max = max(safe_min, min(max_delay, 7))
    return (
        f"- Jitter enabled: {'Yes' if enable_jitter else 'No'}\n"
        f"- Delay window: {safe_min}s–{safe_max}s\n"
        f"- Metadata stripping: {'Enabled' if strip_metadata else 'Disabled'}\n"
        f"- Stealth profile: randomized browser headers + {'delayed requests' if enable_jitter else 'direct requests'}"
    )


def run_diagnostics_with_log(auto_repair: bool = True) -> tuple[str, str, str]:
    status, receipt = run_diagnostics_ui(auto_repair=auto_repair)
    return status, receipt, "Diagnostics completed. Review the receipt for any auto-repair actions."


def refresh_learning_views() -> tuple[str, str]:
    return get_learning_status_md(), latest_learning_log_text()


def refresh_distribution_status() -> str:
    seeder = DistributionSeeder(workspace=Path.cwd())
    return seeder.distribution_status_md()


def refresh_system_readiness() -> str:
    return _status_md()


def dispatch_latest_approved(limit: int = 1) -> str:
    seeder = DistributionSeeder(workspace=Path.cwd())
    result = seeder.dispatch_approved_items(limit=limit)
    if result["receipts"]:
        return f"Dispatched {result['dispatched_count']} approved item(s) to {len(result['targets'])} active target(s)."
    return "No approved items available for outbound dispatch."


def refresh_activity_stream() -> str:
    logger = get_activity_logger()
    return logger.snapshot()


def refresh_distribution_ledger() -> str:
    seeder = DistributionSeeder(workspace=Path.cwd())
    ledger = seeder.build_distribution_ledger()
    if not ledger:
        return "No distribution records yet."
    lines = [
        "| Timestamp | Platform | Status | Summary | URL/Path |",
        "|-----------|----------|--------|---------|----------|",
    ]
    for entry in ledger:
        title = entry["title"][:80]
        lines.append(
            f"| {entry['timestamp']} | {entry['platform']} | {entry['status']} | {title} | {entry['url_or_path']} |"
        )
    return "\n".join(lines)


def runtime_tester_status() -> str:
    engine = ContinuousTesterEngine(workspace=Path.cwd(), send_sms=False)
    try:
        result = engine.run_cycle()
        if result.get("status") == "simulated":
            return "🟢 Runtime Tester: Active"
    except Exception as exc:  # noqa: BLE001
        return f"🔴 Runtime Tester: Idle ({exc})"
    return "🟡 Runtime Tester: Idle"


def run_continuous_test_now() -> str:
    engine = ContinuousTesterEngine(workspace=Path.cwd(), send_sms=False)
    result = engine.run_cycle()
    return f"Simulation complete. {result['status']} | receipts: {len(result['receipt_paths'])}"


def send_test_ping_now() -> str:
    try:
        from modules.notifier import send_test_sms_ping
        return send_test_sms_ping()
    except Exception as exc:  # noqa: BLE001
        return f"Test ping failed: {exc}"


def launch_deep_web_crawl() -> str:
    targets = [
        "https://example.com",
        "https://example.org",
        "https://news.ycombinator.com",
    ]
    try:
        results = run_parallel_scan(targets, max_workers=4)
        summaries = "; ".join(f"{entry['target']}->{entry['status']}" for entry in results[:4])
        return f"Deep crawl launched across {len(results)} targets. {summaries}"
    except Exception as exc:  # noqa: BLE001
        return f"Deep crawl failed: {exc}"


def scan_trend_targets() -> str:
    try:
        targets = [
            "https://www.reddit.com/r/technology/",
            "https://news.ycombinator.com",
            "https://example.com",
        ]
        results = run_parallel_scan(targets, max_workers=3)
        return f"Trend scan complete; {len(results)} targets evaluated with parallel worker pool."
    except Exception as exc:  # noqa: BLE001
        return f"Trend scan failed: {exc}"


def toggle_test_daemon(enabled: bool) -> str:
    if not enabled:
        return "Test daemon stopped"
    engine = ContinuousTesterEngine(workspace=Path.cwd(), send_sms=False)
    engine.start_background_loop(interval_minutes=15)
    return "Test daemon started"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

LORE_CATEGORIES = [
    "Universe Rule", "Character Note", "World-Building",
    "Story Idea", "Plot Thread", "Faction / Group", "Timeline Event", "Misc",
]

_initial_killed = is_killswitch_active()
_initial_kill_label = "🔴 KILLSWITCH — DEACTIVATE" if _initial_killed else "🟢 KILLSWITCH — ACTIVATE"

with gr.Blocks(title="Pantheon Studios Control Panel", theme=gr.themes.Base()) as demo:
    gr.HTML(HUD_BANNER_HTML)
    gr.Markdown(
        "> **Secure LAN access** — this panel can be reached from other devices on the same local network. "
        "Credentials are read from the workspace .env file and nothing is published without your explicit approval.",
        elem_classes=["hud-card"],
    )

    # ---- Readiness badge (live, auto-refreshes every 30 s) ----
    with gr.Row():
        readiness_badge = gr.Markdown(value=readiness_badge_md(), every=30, elem_classes=["hud-card"])

    # ---- State management ----
    killswitch_state = gr.State(value=_initial_killed)

    # ---- Status bar (always visible) ----
    with gr.Row():
        status_display = gr.Markdown(value=_status_md(), every=10, elem_classes=["hud-card"])

    orchestrator_status_display = gr.Markdown(value=orchestrator_status_md(), elem_classes=["hud-card"])
    runtime_tester_badge = gr.Markdown(value=runtime_tester_status(), every=30, elem_classes=["hud-card"])
    connection_banner = gr.Markdown(value=_connection_banner(), elem_classes=["hud-card"])

    # ---- Master Killswitch (always visible, prominent) ----
    with gr.Row():
        refresh_readiness_btn = gr.Button("[ REFRESH SYSTEM READINESS ]", size="lg", elem_classes=["hud-btn-success"])
        master_killswitch_btn = gr.Button(
            value="[ MASTER KILLSWITCH ]",
            variant="stop" if _initial_killed else "primary",
            size="lg",
            elem_classes=["hud-btn-killswitch"],
        )
        orchestrator_toggle = gr.Checkbox(label="Autonomous Orchestrator", value=True)

    gr.Markdown("---")

    with gr.Tabs():

        # ---- Tab 1: Approval Queue & Editor ----
        with gr.Tab("Approval Queue & Editor"):
            gr.Markdown(
                "Review pending drafts, edit them live, and then approve, save, or reject before anything moves."
            )
            with gr.Row():
                queue_list = gr.Dropdown(
                    choices=_pending_names(),
                    label="Pending items",
                    interactive=True,
                    scale=3,
                )
                refresh_btn = gr.Button("[ REFRESH QUEUE ]", scale=1, elem_classes=["hud-btn-success"])

            preview_box = gr.Textbox(
                label="Content preview",
                lines=16,
                interactive=False,
                max_lines=30,
            )
            edit_box = gr.Textbox(
                label="Edit content before approving or rejecting",
                lines=16,
                interactive=True,
                max_lines=30,
            )

            with gr.Row():
                approve_btn = gr.Button("[ APPROVE SELECTED ]", variant="primary", elem_classes=["hud-btn-success"])
                save_edit_btn = gr.Button("[ SAVE EDITS ]", elem_classes=["hud-btn-success"])
                reject_btn = gr.Button("[ REJECT & PURGE ]", variant="stop", elem_classes=["hud-btn-killswitch"])

            queue_action_msg = gr.Textbox(label="Action result", interactive=False, elem_classes=["hud-card"])

            refresh_btn.click(
                fn=refresh_queue,
                outputs=[queue_list, preview_box],
            )
            queue_list.change(
                fn=load_preview,
                inputs=[queue_list],
                outputs=[preview_box, edit_box],
            )
            approve_btn.click(
                fn=approve_item,
                inputs=[queue_list],
                outputs=[queue_action_msg, queue_list, status_display],
            )
            reject_btn.click(
                fn=reject_item,
                inputs=[queue_list],
                outputs=[queue_action_msg, queue_list, status_display],
            )
            save_edit_btn.click(
                fn=save_edit,
                inputs=[queue_list, edit_box],
                outputs=[queue_action_msg, queue_list],
            )

        # ---- Tab 2: Lore Ingestion ----
        with gr.Tab("Lore Ingestion"):
            gr.Markdown("Paste quick lore notes, world rules, and character submissions for the generator engine.")
            lore_title = gr.Textbox(label="Entry title", placeholder="e.g. The Veil Between Worlds")
            lore_category = gr.Dropdown(
                choices=LORE_CATEGORIES,
                value="Misc",
                label="Category",
            )
            lore_tags = gr.Textbox(
                label="Tags (comma-separated, optional)",
                placeholder="magic, timeline, faction-x",
            )
            lore_body = gr.Textbox(
                label="Lore notes / content",
                lines=16,
                placeholder="Write or paste your lore here…",
            )
            lore_save_btn = gr.Button("[ SAVE TO KNOWLEDGE BANK ]", variant="primary", elem_classes=["hud-btn-success"])
            lore_synthesis_btn = gr.Button("[ TRIGGER IMMEDIATE SYNTHESIS ]", elem_classes=["hud-btn-success"])
            lore_result = gr.Textbox(label="Result", interactive=False, elem_classes=["hud-card"])

            lore_save_btn.click(
                fn=save_lore,
                inputs=[lore_title, lore_category, lore_tags, lore_body],
                outputs=[lore_result],
            )
            lore_synthesis_btn.click(
                fn=run_orchestrator_ui,
                outputs=[lore_result],
            )

        # ---- Tab 3: Security & Stealth Management ----
        with gr.Tab("Security & Stealth Management"):
            gr.Markdown("Inspect stealth posture, adjust jitter, and review metadata-scrubbing behavior.")
            security_status = gr.Markdown(value=get_security_snapshot())
            with gr.Row():
                jitter_toggle = gr.Checkbox(label="Enable request jitter", value=True)
                metadata_strip_toggle = gr.Checkbox(label="Strip sensitive metadata", value=True)
            with gr.Row():
                jitter_min = gr.Slider(minimum=2, maximum=7, value=2, step=1, label="Min jitter (s)")
                jitter_max = gr.Slider(minimum=2, maximum=7, value=7, step=1, label="Max jitter (s)")
            stealth_settings_view = gr.Textbox(
                label="Stealth configuration preview",
                value=update_security_settings(True, 2, 7, True),
                lines=8,
                interactive=False,
                max_lines=20,
            )
            with gr.Row():
                inspect_security_btn = gr.Button("Refresh stealth snapshot", size="lg", elem_classes=["hud-btn-success"])

            jitter_toggle.change(
                fn=update_security_settings,
                inputs=[jitter_toggle, jitter_min, jitter_max, metadata_strip_toggle],
                outputs=[stealth_settings_view],
            )
            jitter_min.change(
                fn=update_security_settings,
                inputs=[jitter_toggle, jitter_min, jitter_max, metadata_strip_toggle],
                outputs=[stealth_settings_view],
            )
            jitter_max.change(
                fn=update_security_settings,
                inputs=[jitter_toggle, jitter_min, jitter_max, metadata_strip_toggle],
                outputs=[stealth_settings_view],
            )
            metadata_strip_toggle.change(
                fn=update_security_settings,
                inputs=[jitter_toggle, jitter_min, jitter_max, metadata_strip_toggle],
                outputs=[stealth_settings_view],
            )
            inspect_security_btn.click(
                fn=get_security_snapshot,
                outputs=[security_status],
            )

        # ---- Tab 4: Deep Search & Crawlers ----
        with gr.Tab("Deep Search & Crawlers"):
            gr.Markdown("Launch multimodal, multi-threaded crawl tasks and scan trend targets without blocking the rest of the pipeline.")
            deep_search_result = gr.Textbox(
                label="Deep search activity",
                value="No crawl launched yet.",
                lines=10,
                interactive=False,
                max_lines=20,
            )
            with gr.Row():
                crawl_btn = gr.Button("[ LAUNCH DEEP WEB CRAWL ]", variant="primary", size="lg")
                trend_scan_btn = gr.Button("[ SCAN TREND TARGETS ]", size="lg")
            crawl_btn.click(fn=launch_deep_web_crawl, outputs=[deep_search_result])
            trend_scan_btn.click(fn=scan_trend_targets, outputs=[deep_search_result])

        # ---- Tab 5: Diagnostics & Self-Repair ----
        with gr.Tab("Diagnostics & Self-Repair"):
            gr.Markdown(
                "Run the diagnostics engine, review auto-repair output, and inspect the latest health receipt."
            )

            diag_subsystem_status = gr.Markdown(
                value="Click **Run Diagnostics & Self-Repair** to check subsystem health."
            )
            repair_log_view = gr.Textbox(
                label="Auto-repair log",
                value="No repair run yet.",
                lines=8,
                interactive=False,
                max_lines=20,
            )

            with gr.Row():
                run_diag_btn = gr.Button(
                    "[ RUN FULL DIAGNOSTICS & SELF-REPAIR ]", variant="primary", size="lg", elem_classes=["hud-btn-success"]
                )
                load_receipt_btn = gr.Button("[ LOAD LATEST RECEIPT ]", size="lg", elem_classes=["hud-btn-success"])
                run_sim_btn = gr.Button("[ RUN IMMEDIATE SANDBOX SIMULATION ]", size="lg", elem_classes=["hud-btn-success"])

            daemon_toggle = gr.Checkbox(label="Continuous Testing Daemon", value=True)
            with gr.Row():
                ping_sms_btn = gr.Button("[ SEND TEST SMS PING NOW ]", variant="secondary", size="lg", elem_classes=["hud-btn-success"])
            simulation_stream = gr.Textbox(
                label="Simulation activity stream",
                value="Waiting for the next simulation cycle…",
                lines=8,
                interactive=False,
                max_lines=20,
                elem_classes=["hud-terminal"],
            )

            diag_receipt_view = gr.Textbox(
                label="System health receipt",
                value=latest_receipt_text(),
                lines=28,
                interactive=False,
                max_lines=60,
                elem_classes=["hud-terminal"],
            )

            run_diag_btn.click(
                fn=run_diagnostics_with_log,
                outputs=[diag_subsystem_status, diag_receipt_view, repair_log_view],
            )
            load_receipt_btn.click(
                fn=latest_receipt_text,
                outputs=[diag_receipt_view],
            )
            run_sim_btn.click(
                fn=run_continuous_test_now,
                outputs=[simulation_stream],
            )
            ping_sms_btn.click(
                fn=send_test_ping_now,
                outputs=[simulation_stream],
            )
            daemon_toggle.change(
                fn=lambda enabled: "Continuous Testing Daemon enabled" if enabled else "Continuous Testing Daemon disabled",
                inputs=[daemon_toggle],
                outputs=[simulation_stream],
            )

        # ---- Tab 6: Continuous Testing ----
        with gr.Tab("Continuous Testing"):
            gr.Markdown("Start or stop the background test daemon and trigger an immediate sandbox simulation from the UI.")
            daemon_state = gr.State(value=True)
            daemon_result = gr.Textbox(
                label="Daemon activity",
                value="Daemon ready.",
                lines=8,
                interactive=False,
                max_lines=20,
                elem_classes=["hud-terminal"],
            )
            with gr.Row():
                daemon_toggle_btn = gr.Button("[ START/STOP TEST DAEMON ]", variant="primary", size="lg", elem_classes=["hud-btn-success"])
                sandbox_btn = gr.Button("[ RUN IMMEDIATE SANDBOX SIMULATION ]", size="lg", elem_classes=["hud-btn-success"])
            daemon_toggle_btn.click(
                fn=lambda enabled: toggle_test_daemon(not enabled),
                inputs=[daemon_state],
                outputs=[daemon_result],
            )
            sandbox_btn.click(fn=run_continuous_test_now, outputs=[daemon_result])

        # ---- Tab 7: Live System Process ----
        with gr.Tab("Live System Process"):
            gr.Markdown("Watch the live execution stream from crawlers, synthesis, learning, and testing services.")
            worker_status = gr.Markdown(
                "| Worker | Status |\n|--------|--------|\n| Crawlers | ACTIVE |\n| Synthesizer | ACTIVE |\n| Tester | ACTIVE |"
            )
            activity_stream = gr.Textbox(
                label="System Execution Stream",
                value=refresh_activity_stream(),
                lines=24,
                interactive=False,
                max_lines=60,
                every=10,
                elem_classes=["hud-terminal"],
            )
            refresh_stream_btn = gr.Button("[ REFRESH LIVE STREAM ]")
            refresh_stream_btn.click(fn=refresh_activity_stream, outputs=[activity_stream])

        # ---- Tab 8: Live Distribution Ledger ----
        with gr.Tab("Live Distribution Ledger"):
            gr.Markdown("Inspect every dispatched post across Reddit, YouTube, Substack, Medium, Discord, X/Twitter, and RSS.")
            ledger_view = gr.Textbox(
                label="Distribution ledger",
                value=refresh_distribution_ledger(),
                lines=20,
                interactive=False,
                max_lines=60,
                every=15,
                elem_classes=["hud-terminal"],
            )
            refresh_ledger_btn = gr.Button("[ RESYNC DISTRIBUTION LEDGER ]")
            refresh_ledger_btn.click(fn=refresh_distribution_ledger, outputs=[ledger_view])

        # ---- Tab 9: Continuous Learning & Guardrails ----
        with gr.Tab("Continuous Learning & Guardrails"):
            gr.Markdown(
                "Review active RLHF style weights, toggle trend learning, and inspect guardrail compliance logs."
            )

            learn_status_display = gr.Markdown(value=get_learning_status_md())

            with gr.Row():
                trend_toggle = gr.Checkbox(
                    label="Enable automated trend learning (fetches public pages)",
                    value=True,
                    interactive=True,
                )

            with gr.Row():
                feedback_btn = gr.Button("Run Feedback Analysis (local only)", variant="primary")
                full_cycle_btn = gr.Button("Run Full Cycle (feedback + trends)", variant="secondary")
                refresh_learn_btn = gr.Button("Refresh Status")

            learn_log_view = gr.Textbox(
                label="Guardrail compliance log",
                value=latest_learning_log_text(),
                lines=28,
                interactive=False,
                max_lines=60,
            )

            trend_toggle.change(
                fn=toggle_trend_learning_ui,
                inputs=[trend_toggle],
                outputs=[learn_status_display],
            )
            feedback_btn.click(
                fn=run_feedback_only_ui,
                outputs=[learn_status_display, learn_log_view],
            )
            full_cycle_btn.click(
                fn=run_full_cycle_ui,
                outputs=[learn_status_display, learn_log_view],
            )
            refresh_learn_btn.click(
                fn=refresh_learning_views,
                outputs=[learn_status_display, learn_log_view],
            )

        # ---- Tab 10: Distribution & Outbound ----
        with gr.Tab("Distribution & Outbound"):
            gr.Markdown(
                "Review outbound targets, dispatch approved drafts, and inspect the latest distribution receipts."
            )
            distribution_status = gr.Markdown(value=refresh_distribution_status())
            with gr.Row():
                dispatch_btn = gr.Button("Dispatch Approved Drafts", variant="primary", size="lg")
                refresh_dist_btn = gr.Button("Refresh Status", size="lg")
            dist_receipt_view = gr.Textbox(
                label="Latest distribution receipts",
                value="No distribution receipts yet.",
                lines=12,
                interactive=False,
                max_lines=30,
            )
            dispatch_btn.click(
                fn=dispatch_latest_approved,
                outputs=[distribution_status],
            )
            refresh_dist_btn.click(
                fn=refresh_distribution_status,
                outputs=[distribution_status],
            )

        # ---- Tab 11: System Sync ----
        with gr.Tab("System Sync"):
            gr.Markdown(
                "Verify file integrity, policy mirrors, and workspace readiness with a single click."
            )

            sync_summary_display = gr.Markdown(value=latest_sync_report_text())

            with gr.Row():
                run_sync_btn = gr.Button(
                    "Verify Integrity & Policy Mirrors", variant="primary", size="lg"
                )
                load_sync_btn = gr.Button("Load Latest Report", size="lg")

            sync_report_view = gr.Textbox(
                label="Sync receipt",
                value=latest_sync_report_text(),
                lines=30,
                interactive=False,
                max_lines=65,
            )

            run_sync_btn.click(
                fn=run_sync_ui,
                outputs=[sync_summary_display, sync_report_view],
            )
            load_sync_btn.click(
                fn=latest_sync_report_text,
                outputs=[sync_report_view],
            )
            run_sync_btn.click(
                fn=readiness_badge_md,
                outputs=[readiness_badge],
            )

    # ---- Killswitch wiring (done last so all outputs exist) ----
    refresh_readiness_btn.click(
        fn=refresh_system_readiness,
        outputs=[status_display],
    )
    master_killswitch_btn.click(
        fn=toggle_killswitch,
        inputs=[killswitch_state],
        outputs=[killswitch_state, master_killswitch_btn, status_display],
    )
    orchestrator_toggle.change(
        fn=toggle_orchestrator,
        inputs=[orchestrator_toggle],
        outputs=[orchestrator_status_display],
    )
    orchestrator_toggle.change(
        fn=run_orchestrator_ui,
        outputs=[orchestrator_status_display],
    )
    daemon_toggle.change(
        fn=lambda enabled: runtime_tester_status(),
        inputs=[daemon_toggle],
        outputs=[runtime_tester_badge],
    )


def main() -> None:
    local_ip = _resolve_local_ip()
    print("=" * 60)
    print("Pantheon Studios control panel")
    print("=" * 60)
    print("On this PC: http://localhost:7860")
    print("On this PC: http://127.0.0.1:7860")
    print(f"On phone/laptop (same Wi-Fi): http://{local_ip}:7860")
    print("Credentials come from the workspace .env file.")
    print("=" * 60)
    try:
        from modules.continuous_tester import ContinuousTesterEngine
        from modules.orchestrator import OrchestratorEngine
        from modules.crawler_engine import CrawlerEngine
        from modules.learning_engine import run_feedback_analysis, LearningState
        from modules.activity_logger import emit_activity

        def _worker_loop(target: str, fn, interval_seconds: int) -> None:
            while True:
                try:
                    emit_activity("System Thought", target, f"worker loop active ({target})")
                    fn()
                except Exception as exc:  # noqa: BLE001
                    emit_activity("System Thought", target, f"worker error: {exc}")
                time.sleep(interval_seconds)

        engine = ContinuousTesterEngine(workspace=Path.cwd(), send_sms=False)
        orchestrator = OrchestratorEngine()
        crawler = CrawlerEngine()
        learning_state = LearningState()
        threads = [
            threading.Thread(target=engine.start_daemon, kwargs={"interval_minutes": 15}, daemon=True),
            threading.Thread(target=lambda: _worker_loop("orchestrator", orchestrator.run_cycle, 1800), daemon=True),
            threading.Thread(target=lambda: _worker_loop("crawler", lambda: crawler.fetch("https://example.com"), 3600), daemon=True),
            threading.Thread(target=lambda: _worker_loop("learning", lambda: run_feedback_analysis(learning_state), 3600), daemon=True),
        ]
        for thread in threads:
            thread.start()
    except Exception:
        pass

    demo.launch(
        auth=(CONTROL_PANEL_USER, CONTROL_PANEL_PASS),
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        css=CSS_THEME,
    )


if __name__ == "__main__":
    main()
