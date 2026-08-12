#!/usr/bin/env python3
"""Python-friendly launcher for Pantheon multi-site startup.

Use this when you prefer `python modules/run.py` instead of running `run.bat` directly.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], *, cwd: Path) -> None:
    result = subprocess.run(cmd, cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    python_bin = str(venv_python if venv_python.exists() else Path(sys.executable))

    # Keep behavior consistent with run.bat: preflight first, then start all enabled sites.
    _run([python_bin, "modules/preflight.py"], cwd=ROOT)
    _run([python_bin, "scripts/site_launcher.py", "start-all"], cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
