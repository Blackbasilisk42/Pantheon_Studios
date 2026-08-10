#!/usr/bin/env python3
"""Pantheon Studios local web control panel (Gradio).

Run with:
    python modules/control_panel.py

Opens on http://127.0.0.1:7860 — localhost only, never exposed externally.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import gradio as gr

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

PENDING_DIR = Path("queue") / "pending"
APPROVED_DIR = Path("queue") / "approved"
REJECTED_DIR = Path("queue") / "rejected"

for _d in (PENDING_DIR, APPROVED_DIR, REJECTED_DIR):
    _d.mkdir(parents=True, exist_ok=True)


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
    kill_icon = "🔴 ACTIVE — all automation HALTED" if killed else "🟢 Inactive — system running"
    return (
        f"| Indicator | Value |\n"
        f"|-----------|-------|\n"
        f"| **Killswitch** | {kill_icon} |\n"
        f"| **Pending queue items** | {pending_count} |\n"
        f"| **Timestamp** | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |\n"
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
    return f"Approved → {dest.as_posix()}", _pending_names(), _status_md()


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
    gr.Markdown("# Pantheon Studios — Control Panel")
    gr.Markdown(
        "> **Local only** — this interface is never accessible outside your machine. "
        "Nothing is sent or published without your explicit approval."
    )

    # ---- Readiness badge wiring ----
    # ---- Readiness badge (live, auto-refreshes every 30 s) ----
    with gr.Row():
        readiness_badge = gr.Markdown(value=readiness_badge_md, every=30)

    # ---- Status bar (always visible) ----
    with gr.Row():
        status_display = gr.Markdown(value=_status_md, every=10)

    # ---- Master Killswitch (always visible, prominent) ----
    with gr.Row():
        kill_btn = gr.Button(
            value=_initial_kill_label,
            variant="stop" if _initial_killed else "primary",
            size="lg",
        )

    gr.Markdown("---")

    with gr.Tabs():

        # ---- Tab 1: Approval Queue ----
        with gr.Tab("Approval Queue"):
            gr.Markdown(
                "Review pending drafts. Nothing moves to `queue/approved/` unless you click **Approve**."
            )
            with gr.Row():
                queue_list = gr.Dropdown(
                    choices=_pending_names(),
                    label="Pending items",
                    interactive=True,
                    scale=3,
                )
                refresh_btn = gr.Button("Refresh", scale=1)

            preview_box = gr.Textbox(
                label="Content preview (read-only)",
                lines=18,
                interactive=False,
                max_lines=30,
            )
            edit_box = gr.Textbox(
                label="Edit content (optional — edits saved to pending before approving)",
                lines=18,
                interactive=True,
                max_lines=30,
            )

            with gr.Row():
                approve_btn = gr.Button("✅ Approve", variant="primary")
                save_edit_btn = gr.Button("💾 Save Edits")
                reject_btn = gr.Button("❌ Reject", variant="stop")

            queue_action_msg = gr.Textbox(label="Action result", interactive=False)

            # Wire up
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
            gr.Markdown("Paste or type lore notes. Saved directly to `lore/` for the generator engine.")
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
                lines=14,
                placeholder="Write or paste your lore here…",
            )
            lore_save_btn = gr.Button("Save to Lore", variant="primary")
            lore_result = gr.Textbox(label="Result", interactive=False)

            lore_save_btn.click(
                fn=save_lore,
                inputs=[lore_title, lore_category, lore_tags, lore_body],
                outputs=[lore_result],
            )

        # ---- Tab 3: System Diagnostics & Health ----
        with gr.Tab("System Diagnostics & Health"):
            gr.Markdown(
                "Automated environment audit, pipeline dry-run, and self-repair. "
                "No content is published and no real network calls are made to external targets."
            )

            diag_subsystem_status = gr.Markdown(
                value="Click **Run Diagnostics** to check subsystem health."
            )

            with gr.Row():
                run_diag_btn = gr.Button(
                    "Run System Diagnostics & Self-Repair", variant="primary", size="lg"
                )
                load_receipt_btn = gr.Button("Load Latest Receipt", size="lg")

            diag_receipt_view = gr.Textbox(
                label="Diagnostic receipt",
                value=latest_receipt_text,
                lines=28,
                interactive=False,
                max_lines=60,
            )

            run_diag_btn.click(
                fn=run_diagnostics_ui,
                outputs=[diag_subsystem_status, diag_receipt_view],
            )
            load_receipt_btn.click(
                fn=latest_receipt_text,
                outputs=[diag_receipt_view],
            )

        # ---- Tab 4: Continuous Learning & Guardrails ----
        with gr.Tab("Continuous Learning & Guardrails"):
            gr.Markdown(
                "Local RLHF from your approved/rejected queue items, plus optional structural "
                "trend analysis from public pages. Every adjustment is validated against "
                "`lore/immutable_rules.md` — nothing touches security, the killswitch, or the "
                "approval workflow."
            )

            learn_status_display = gr.Markdown(value=get_learning_status_md)

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
                label="Latest learning log",
                value=latest_learning_log_text,
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
                fn=get_learning_status_md,
                outputs=[learn_status_display],
            )

        # ---- Tab 5: Sync & System Readiness ----
        with gr.Tab("Sync & System Readiness"):
            gr.Markdown(
                "Full workspace integrity check, policy mirror sync, state file validation, "
                "and pipeline import audit. Runs auto-repair on every click."
            )

            sync_summary_display = gr.Markdown(value=latest_sync_report_text)

            with gr.Row():
                run_sync_btn = gr.Button(
                    "Run Full System Sync", variant="primary", size="lg"
                )
                load_sync_btn = gr.Button("Load Latest Report", size="lg")

            sync_report_view = gr.Textbox(
                label="Sync receipt",
                value=latest_sync_report_text,
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

            # Sync run also refreshes the header badge
            run_sync_btn.click(
                fn=readiness_badge_md,
                outputs=[readiness_badge],
            )

    # ---- Killswitch wiring (done last so all outputs exist) ----
    kill_btn.click(
        fn=toggle_killswitch,
        inputs=[killswitch_state],
        outputs=[killswitch_state, kill_btn, status_display],
    )


def main() -> None:
    demo.launch(
        server_name="127.0.0.1",  # localhost only — never bind to 0.0.0.0
        server_port=7860,
        share=False,
        show_error=True,
    )


if __name__ == "__main__":
    main()
