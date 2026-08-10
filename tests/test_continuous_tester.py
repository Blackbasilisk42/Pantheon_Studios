from pathlib import Path

from modules.continuous_tester import ContinuousTesterEngine


def test_continuous_tester_run_cycle_creates_receipts_and_logs(tmp_path: Path) -> None:
    workspace = tmp_path
    (workspace / "queue" / "pending").mkdir(parents=True, exist_ok=True)
    (workspace / "queue" / "approved").mkdir(parents=True, exist_ok=True)
    (workspace / "intelligence").mkdir(parents=True, exist_ok=True)
    (workspace / "config").mkdir(parents=True, exist_ok=True)
    (workspace / "config" / "distribution_targets.json").write_text(
        '[{"name":"local_dry_run","channel":"local","kind":"dry_run","active":true}]',
        encoding="utf-8",
    )

    engine = ContinuousTesterEngine(workspace=workspace, send_sms=False)
    result = engine.run_cycle()

    assert result["status"] == "simulated"
    assert result["receipt_paths"]
    assert Path(result["receipt_paths"][0]).exists()
    assert result["log_path"].exists()
