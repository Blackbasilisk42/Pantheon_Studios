#!/usr/bin/env python3
"""Pre-flight auto-healing launcher for Pantheon Studios."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_FILE = ROOT / "requirements.txt"
ENV_FILE = ROOT / ".env"
CONTROL_PANEL_FILE = ROOT / "modules" / "control_panel.py"


def _print(title: str, message: str) -> None:
    print(f"[preflight] {title}: {message}")


def _iter_core_scripts() -> list[Path]:
    scripts = [
        ROOT / "agent_hub.py",
        ROOT / "crawlers.py",
        ROOT / "creator.py",
        ROOT / "synthesizer.py",
    ]
    for directory in (ROOT / "modules", ROOT / "publishers"):
        if directory.exists():
            scripts.extend(sorted(directory.glob("*.py")))
    return [path for path in scripts if path.exists()]


def _normalize_requirement_name(requirement: str) -> str:
    cleaned = requirement.split("#", 1)[0].strip()
    if not cleaned:
        return ""
    cleaned = cleaned.split(";", 1)[0].strip()
    cleaned = cleaned.split("[", 1)[0]
    cleaned = re.split(r"[<>=!~]+", cleaned, maxsplit=1)[0].strip()
    cleaned = cleaned.replace("_", "-").lower()
    return cleaned


def _load_requirements() -> list[str]:
    if not REQUIREMENTS_FILE.exists():
        return []
    requirements: list[str] = []
    for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        requirements.append(candidate)
    return requirements


def _check_requirement_installed(requirement: str) -> bool:
    name = _normalize_requirement_name(requirement)
    if not name:
        return True
    try:
        metadata.version(name)
        return True
    except metadata.PackageNotFoundError:
        return False


def _install_missing_requirements(requirements: list[str]) -> bool:
    missing = [req for req in requirements if not _check_requirement_installed(req)]
    if not missing:
        _print("requirements", "all dependencies are already satisfied")
        return True

    _print("requirements", f"installing {len(missing)} missing package(s)")
    for requirement in missing:
        _print("install", requirement)
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", requirement],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0:
            _print("error", f"failed to install {requirement}")
            return False
    return True


def _run_py_compile() -> bool:
    scripts = _iter_core_scripts()
    if not scripts:
        _print("compile", "no core scripts discovered")
        return True

    _print("compile", f"checking {len(scripts)} core script(s)")
    for script in scripts:
        completed = subprocess.run(
            [sys.executable, "-m", "py_compile", str(script)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stdout)
            _print("error", f"syntax check failed for {script.relative_to(ROOT)}")
            return False
    return True


def _ensure_env_file() -> bool:
    defaults = {
        "CONTROL_PANEL_USER": "admin",
        "CONTROL_PANEL_PASS": "@Sammyzzz3Jimbo21",
        "TWILIO_ACCOUNT_SID": "",
        "TWILIO_AUTH_TOKEN": "",
        "TWILIO_FROM_NUMBER": "",
        "TWILIO_TO_NUMBER": "",
    }

    if not ENV_FILE.exists():
        content = "\n".join(f"{key}={value}" for key, value in defaults.items()) + "\n"
        ENV_FILE.write_text(content, encoding="utf-8")
        _print("env", f"created default environment file at {ENV_FILE.name}")
        return True

    existing = ENV_FILE.read_text(encoding="utf-8")
    missing = []
    for key, value in defaults.items():
        if re.search(rf"^\s*{re.escape(key)}\s*=", existing, flags=re.MULTILINE) is None:
            missing.append(f"{key}={value}")

    if missing:
        with ENV_FILE.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            for line in missing:
                handle.write(line + "\n")
        _print("env", "appended missing environment defaults")
    else:
        _print("env", "environment file already contains the required keys")
    return True


def _patch_control_panel_gradio_api() -> bool:
    if not CONTROL_PANEL_FILE.exists():
        _print("gradio", "control panel file not found")
        return False

    original = CONTROL_PANEL_FILE.read_text(encoding="utf-8")
    updated = original

    updated = updated.replace(
        'with gr.Blocks(title="Pantheon Studios Control Panel", css=CSS_THEME) as demo:',
        'with gr.Blocks(title="Pantheon Studios Control Panel", theme=gr.themes.Base()) as demo:',
    )
    updated = updated.replace(
        'with gr.Blocks(title="Pantheon Studios Control Panel") as demo:',
        'with gr.Blocks(title="Pantheon Studios Control Panel", theme=gr.themes.Base()) as demo:',
    )
    updated = updated.replace(
        '        theme=gr.themes.Base(),\n',
        '',
    )
    updated = updated.replace(
        '        show_error=True,\n        theme=gr.themes.Base(),\n',
        '        show_error=True,\n        css=CSS_THEME,\n',
    )
    updated = updated.replace(
        '        show_error=True,\n        theme=gr.themes.Base(),\n    )',
        '        show_error=True,\n        css=CSS_THEME,\n    )',
    )

    if updated != original:
        CONTROL_PANEL_FILE.write_text(updated, encoding="utf-8")
        _print("gradio", "patched Gradio Blocks/launch arguments")
    else:
        _print("gradio", "Gradio launch arguments already compatible")
    return True


def main() -> int:
    print("\n=== Pantheon Studios Pre-Flight Auto-Healer ===")
    print("This pass verifies syntax, dependency health, environment config, and Gradio launch compatibility.\n")

    try:
        _patch_control_panel_gradio_api()
        if not _ensure_env_file():
            return 1
        if not _run_py_compile():
            return 1
        if not _install_missing_requirements(_load_requirements()):
            return 1
        _print("success", "pre-flight checks passed")
        return 0
    except Exception as exc:  # pragma: no cover - defensive wrapper
        _print("error", f"pre-flight interrupted: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
