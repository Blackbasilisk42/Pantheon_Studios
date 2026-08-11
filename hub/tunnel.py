from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
PUBLIC_URL_FILE = STATIC_DIR / "PUBLIC_URL.txt"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_URL_FILE.write_text("Awaiting public tunnel...\n", encoding="utf-8")


def _color(text: str, color_code: str) -> str:
    if sys.stdout.isatty():
        return f"{color_code}{text}\033[0m"
    return text


def _get_local_ips() -> list[str]:
    ips: set[str] = set()
    try:
        hostname = socket.gethostname()
        for entry in socket.gethostbyname_ex(hostname)[2]:
            if entry and not entry.startswith("127."):
                ips.add(entry)
    except Exception:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
            if local_ip and not local_ip.startswith("127."):
                ips.add(local_ip)
    except Exception:
        pass
    return sorted(ips)


def _print_banner(public_url: Optional[str]) -> None:
    print("\n" + "=" * 80)
    print(_color("PANTHEON STUDIOS PUBLIC TUNNEL", "\033[96m"))
    print("=" * 80)
    print(_color("Local target: http://localhost:7861", "\033[96m"))
    for ip in _get_local_ips():
        print(_color(f"LAN: http://{ip}:7861", "\033[96m"))
    if public_url:
        print(_color(f"PUBLIC: {public_url}", "\033[96m"))
    else:
        print(_color("PUBLIC: waiting for cloudflared output...", "\033[93m"))
    print("=" * 80 + "\n")


def _ensure_cloudflared() -> Path:
    candidates = ["cloudflared", "cloudflared.exe"]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return Path(found)

    bin_dir = ROOT / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        archive_name = "cloudflared-windows-amd64.exe"
        download_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/{archive_name}"
        destination = bin_dir / "cloudflared.exe"
    else:
        archive_name = "cloudflared-linux-amd64"
        download_url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/{archive_name}"
        destination = bin_dir / "cloudflared"

    if not destination.exists():
        print(_color(f"Downloading cloudflared from {download_url}", "\033[93m"))
        try:
            urllib.request.urlretrieve(download_url, destination)
            if os.name != "nt":
                os.chmod(destination, 0o755)
        except Exception as exc:
            raise RuntimeError(f"Unable to download cloudflared: {exc}") from exc

    return destination


def _write_public_url(url: str) -> None:
    PUBLIC_URL_FILE.write_text(url + "\n", encoding="utf-8")


def main() -> None:
    try:
        cloudflared = _ensure_cloudflared()
    except Exception as exc:
        print(_color(f"cloudflared unavailable: {exc}", "\033[91m"))
        return

    _print_banner(None)
    command = [str(cloudflared), "tunnel", "--url", "http://localhost:7861", "--no-autoupdate"]
    print(_color(f"Launching: {' '.join(command)}", "\033[93m"))

    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    public_url: Optional[str] = None
    try:
        while True:
            line = process.stdout.readline() if process.stdout else ""
            if not line:
                if process.poll() is not None:
                    break
                time.sleep(0.25)
                continue

            line = line.rstrip()
            if not line:
                continue

            print(line)
            match = re.search(r"https://[A-Za-z0-9.-]+\.trycloudflare\.com", line)
            if match:
                public_url = match.group(0)
                _write_public_url(public_url)
                _print_banner(public_url)
                break
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
