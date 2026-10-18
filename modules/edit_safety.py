import json
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path


BACKUP_DIRECTORY_NAME = "backups"
EDIT_LOG_NAME = "edit_log.jsonl"
_EDIT_LOCK = threading.Lock()


def _resolve_target(target: Path, root: Path) -> tuple[Path, Path]:
    resolved_root = Path(root).resolve()
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = resolved_root / candidate
    resolved_target = candidate.resolve()
    try:
        relative_target = resolved_target.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("Write target must be inside the workspace.") from error
    if (
        relative_target.parts
        and relative_target.parts[0].casefold()
        == BACKUP_DIRECTORY_NAME.casefold()
    ) or resolved_target == resolved_root / EDIT_LOG_NAME:
        raise ValueError("Backup and edit-log files cannot be write targets.")
    return resolved_target, relative_target


def _backup_existing(
    target: Path,
    relative_target: Path,
    root: Path,
) -> Path | None:
    if not target.is_file():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / BACKUP_DIRECTORY_NAME / timestamp / relative_target
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, backup)
    return backup


def _record_edit(
    root: Path,
    target: Path,
    relative_target: Path,
    action: str,
    backup: Path | None,
) -> None:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "target": relative_target.as_posix(),
        "backup": backup.relative_to(root).as_posix() if backup else None,
    }
    log_path = root / EDIT_LOG_NAME
    with log_path.open("a", encoding="utf-8") as edit_log:
        edit_log.write(json.dumps(event, ensure_ascii=True) + "\n")


def write_text(
    target: Path,
    content: str,
    action: str,
    root: Path,
) -> Path:
    resolved_root = Path(root).resolve()
    resolved_target, relative_target = _resolve_target(target, resolved_root)
    with _EDIT_LOCK:
        backup = _backup_existing(
            resolved_target,
            relative_target,
            resolved_root,
        )
        _record_edit(
            resolved_root,
            resolved_target,
            relative_target,
            action,
            backup,
        )
        resolved_target.parent.mkdir(parents=True, exist_ok=True)
        resolved_target.write_text(content, encoding="utf-8")
    return resolved_target


def append_text(
    target: Path,
    content: str,
    action: str,
    root: Path,
) -> Path:
    resolved_root = Path(root).resolve()
    resolved_target, relative_target = _resolve_target(target, resolved_root)
    with _EDIT_LOCK:
        backup = _backup_existing(
            resolved_target,
            relative_target,
            resolved_root,
        )
        _record_edit(
            resolved_root,
            resolved_target,
            relative_target,
            action,
            backup,
        )
        resolved_target.parent.mkdir(parents=True, exist_ok=True)
        with resolved_target.open("a", encoding="utf-8") as output:
            output.write(content)
    return resolved_target


def rollback_latest(root: Path) -> Path:
    resolved_root = Path(root).resolve()
    log_path = resolved_root / EDIT_LOG_NAME
    if not log_path.is_file():
        raise FileNotFoundError("No edit history is available to roll back.")

    events = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for event in reversed(events):
        backup_name = event.get("backup")
        target_name = event.get("target")
        if not isinstance(target_name, str):
            continue
        if not isinstance(backup_name, str):
            raise FileNotFoundError(
                f"No prior snapshot is available for {target_name}."
            )
        backup = (resolved_root / backup_name).resolve()
        target = (resolved_root / target_name).resolve()
        try:
            backup.relative_to(resolved_root / BACKUP_DIRECTORY_NAME)
            target.relative_to(resolved_root)
        except ValueError:
            continue
        if backup.is_file():
            return write_text(
                target,
                backup.read_text(encoding="utf-8"),
                f"rollback {target_name}",
                resolved_root,
            )
        raise FileNotFoundError(
            f"The latest snapshot for {target_name} is unavailable."
        )
    raise FileNotFoundError("No prior file snapshot is available to roll back.")
