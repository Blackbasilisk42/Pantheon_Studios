import argparse
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from modules import edit_safety

ROOT = Path(__file__).resolve().parent
STAGED_DIRECTORY = ROOT / "staged_updates"
DEFAULT_SOURCE_URL = "https://dbxv2.bn-ent.net/"
ALLOWED_SOURCE_HOSTS = {"dbxv2.bn-ent.net"}
REQUEST_TIMEOUT_SECONDS = 30
MAX_SOURCE_CHARACTERS = 20_000
UPDATE_LINK_PATTERN = re.compile(
    r"patch|update|maintenance|version|news|information|"
    r"アップデート|お知らせ|メンテナンス|更新",
    re.IGNORECASE,
)

def validate_source_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_SOURCE_HOSTS
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise ValueError(
            "Source URL must use HTTPS on the official Xenoverse host "
            "dbxv2.bn-ent.net."
        )
    return source_url


def scrape_source(source_url: str) -> tuple[str, str]:
    source_url = validate_source_url(source_url)
    response = requests.get(
        source_url,
        headers={"User-Agent": "PantheonStudios-Webmaster/1.0"},
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text[:2_000_000], "html.parser")
    for anchor in soup.find_all("a", href=True):
        candidate = urljoin(source_url, anchor["href"])
        link_text = anchor.get_text(" ", strip=True)
        if not UPDATE_LINK_PATTERN.search(f"{link_text} {candidate}"):
            continue
        try:
            candidate = validate_source_url(candidate)
        except ValueError:
            continue
        if candidate != source_url:
            update_response = requests.get(
                candidate,
                headers={"User-Agent": "PantheonStudios-Webmaster/1.0"},
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,
            )
            update_response.raise_for_status()
            source_url = candidate
            soup = BeautifulSoup(
                update_response.text[:2_000_000], "html.parser"
            )
            break

    content = soup.find(["main", "article"]) or soup.body or soup
    lines = [
        element.get_text(" ", strip=True)
        for element in content.find_all(["h1", "h2", "h3", "p", "li"])
    ]
    source_text = "\n".join(line for line in lines if line)
    if not source_text:
        raise ValueError("No readable update text was found at the source URL.")
    return source_url, source_text[:MAX_SOURCE_CHARACTERS]


def generate_update(source_text: str) -> dict[str, str]:
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Official source text is empty.")
    title = lines[0][:200]
    summary = " ".join(lines[1:]) or lines[0]
    return {"title": title, "summary": summary[:2_000]}


def render_html_block(update: dict[str, str]) -> str:
    title = html.escape(update["title"], quote=True)
    summary = html.escape(update["summary"], quote=True)
    return (
        '<article class="hud-card lore-update">\n'
        f'  <h2 class="card-header">{title}</h2>\n'
        f'  <p class="lattice-logs">{summary}</p>\n'
        "</article>\n"
    )


def stage_update(
    source_url: str, update: dict[str, str]
) -> tuple[Path, Path]:
    STAGED_DIRECTORY.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    stamp = timestamp.strftime("%Y%m%d_%H%M%S_%fZ")
    title_slug = re.sub(
        r"[^a-z0-9]+", "-", update["title"].lower()
    ).strip("-")[:48] or "update"
    html_path = STAGED_DIRECTORY / f"{stamp}_{title_slug}.html"
    receipt_path = STAGED_DIRECTORY / f"{stamp}_{title_slug}.txt"
    receipt = (
        "Pantheon Studios Webmaster - Staged Update Receipt\n"
        f"Scraped at (UTC): {timestamp.isoformat()}\n"
        f"Source URL: {source_url}\n"
        "Content formatted deterministically from the official source.\n"
        "Files generated:\n"
        f"- {html_path.relative_to(ROOT)}\n"
        f"- {receipt_path.relative_to(ROOT)}\n"
        "Review required: this staged HTML was not added to index.html.\n"
    )
    edit_safety.write_text(
        html_path,
        render_html_block(update),
        "stage generated official update",
        ROOT,
    )
    edit_safety.write_text(
        receipt_path,
        receipt,
        "write official update receipt",
        ROOT,
    )
    return html_path, receipt_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scrape official Xenoverse updates and stage a deterministic "
            "HTML block for manual review."
        )
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="Official Xenoverse source on dbxv2.bn-ent.net",
    )
    args = parser.parse_args()

    try:
        source_url, source_text = scrape_source(args.source_url)
        update = generate_update(source_text)
        html_file, receipt_file = stage_update(source_url, update)
    except (requests.RequestException, ValueError) as error:
        print(f"Webmaster run failed: {error}", file=sys.stderr)
        return 1

    print(f"Staged HTML: {html_file.relative_to(ROOT)}")
    print(f"Receipt: {receipt_file.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
