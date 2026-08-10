from pathlib import Path

from modules.activity_logger import ActivityLogger


def test_activity_logger_persists_tail_and_file(tmp_path: Path) -> None:
    log_path = tmp_path / "system_activity.log"
    logger = ActivityLogger(log_path=log_path)

    logger.log("System Thought", "test", "Probe event")

    assert log_path.exists()
    tail = logger.tail(5)
    assert any("Probe event" in item for item in tail)
