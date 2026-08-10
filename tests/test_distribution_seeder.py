from pathlib import Path

from modules.distribution_seeder import DistributionSeeder


def test_dispatch_builds_receipt_and_targets(tmp_path: Path) -> None:
    workspace = tmp_path
    (workspace / "queue" / "approved").mkdir(parents=True, exist_ok=True)
    (workspace / "queue" / "pending").mkdir(parents=True, exist_ok=True)
    (workspace / "intelligence").mkdir(parents=True, exist_ok=True)

    approved_path = workspace / "queue" / "approved" / "approved_sample.md"
    approved_path.write_text(
        "# Sample Approved Draft\n\nThis is a sample approved draft for distribution.\n",
        encoding="utf-8",
    )

    seeder = DistributionSeeder(workspace=workspace)
    result = seeder.dispatch_approved_items(limit=1)

    assert result["dispatched_count"] == 1
    assert result["receipts"]
    receipt_path = Path(result["receipts"][0])
    assert receipt_path.exists()

    payload = receipt_path.read_text(encoding="utf-8")
    assert "Sample Approved Draft" in payload
    assert "public-policy disclaimer" in payload.lower()
