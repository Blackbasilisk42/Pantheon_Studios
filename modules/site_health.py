from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup


PRIVATE_DIRECTORIES = {
    ".git",
    ".venv",
    "backups",
    "dist",
    "lore",
    "modules",
    "node_modules",
    "policies",
    "staged_updates",
}
REFERENCE_ATTRIBUTES = ("href", "src")
MAX_FINDINGS = 100


def inspect_site(root: Path) -> dict[str, object]:
    resolved_root = Path(root).resolve()
    checked_files = 0
    missing_references = []

    for html_file in sorted(resolved_root.rglob("*.html")):
        relative_file = html_file.relative_to(resolved_root)
        if any(
            part.startswith(".") or part.lower() in PRIVATE_DIRECTORIES
            for part in relative_file.parts
        ):
            continue
        checked_files += 1
        soup = BeautifulSoup(
            html_file.read_text(encoding="utf-8"),
            "html.parser",
        )
        for element in soup.find_all(True):
            for attribute in REFERENCE_ATTRIBUTES:
                reference = element.get(attribute)
                if not isinstance(reference, str) or not reference.strip():
                    continue
                parsed = urlparse(reference.strip())
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                local_path = unquote(parsed.path)
                if local_path.startswith("/"):
                    target = resolved_root / local_path.lstrip("/")
                else:
                    target = html_file.parent / local_path
                try:
                    target.resolve().relative_to(resolved_root)
                    exists = target.exists()
                except ValueError:
                    exists = False
                if not exists and len(missing_references) < MAX_FINDINGS:
                    missing_references.append(
                        {
                            "file": relative_file.as_posix(),
                            "reference": reference,
                        }
                    )

    return {
        "status": "healthy" if not missing_references else "issues_found",
        "checked_files": checked_files,
        "missing_references": missing_references,
    }
