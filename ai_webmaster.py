import html
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import schedule
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
REFERENCE_FILE = ROOT / "aj_profile_reference.txt"
STAGED_DIRECTORY = ROOT / "staged_updates"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
UPDATE_SOURCE_URL = "https://dbxv2.bn-ent.net/"
ALLOWED_SOURCE_HOSTS = {"dbxv2.bn-ent.net"}
REQUEST_TIMEOUT_SECONDS = 30
MAX_PAGE_BYTES = 2_000_000
MAX_SOURCE_CHARACTERS = 20_000
MAX_DOSSIER_CHARACTERS = 12_000
UPDATE_LINK_PATTERN = re.compile(
    r"patch|update|maintenance|version|news|information|"
    r"アップデート|お知らせ|メンテナンス|更新",
    re.IGNORECASE,
)
DOSSIER_SYSTEM_PROMPT = (
    "You are an expert lore writer for the Pantheon Studios Lega-Z-y project. "
    "Analyze the provided reference profile (`aj_profile_reference.txt`) for "
    "structural layout, category headings, and analytical tone. Using that "
    "exact same framework, write a complete character dossier for Kaige.\n\n"
    "Integrate these specific details into his Tactical Dossier and Lore Notes:\n\n"
    "- Subtitle: Frieza-race // Elite Patroller.\n"
    "- Visuals: A tall, original solid black body design with green eyes (a "
    "legacy design predating Black Frieza by 6 years) and a dark emerald green "
    "aura.\n"
    "- Combat Style: A pure Ki-blast primary build.\n"
    "- Key Attributes: He utilizes the 'Center of Gravity' (COG) technique, "
    "focusing heavily on precise orbital positioning relative to locked-on "
    "targets.\n"
    "- Evasive/Counter Tactics: While predominantly a distant zoner and "
    "Ki-blast specialist, he employs secondary Strike counters like Shadow "
    "Crusher and Backflip to punish opponents who attempt to close the gap, "
    "immediately repositioning to maintain his spatial advantage.\n"
    "- Output the final result formatted as clean HTML matching the "
    "`.bento-card` CSS structure, utilizing the exact same metric categories "
    "and lore sub-headings as the reference file."
)
NEWS_PROMPT = (
    "Summarize this DBZ/Xenoverse update into a short, lore-friendly news "
    "bulletin for the Lega-Z-y project. Do not include or output any <img> tags."
)
NEWS_SYSTEM_PROMPT = (
    "Write a concise and accurate news bulletin using only facts in the source "
    "text. Do not invent update details. Return plain text only, with no HTML "
    "tags, including no image tags."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def _ollama_generate(prompt: str, system: str) -> str:
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "llama3.1",
            "system": system,
            "prompt": prompt,
            "stream": False,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    result = payload.get("response")
    if not isinstance(result, str) or not result.strip():
        raise ValueError("Ollama returned an empty or invalid response.")
    return result.strip()[:MAX_DOSSIER_CHARACTERS]


def _render_bento_card(title: str, content: str, content_class: str) -> str:
    escaped_title = html.escape(title, quote=True)
    escaped_content = html.escape(content, quote=True)
    return (
        '<article class="bento-card">\n'
        '  <div class="card-topline">\n'
        '    <span class="card-kicker">LEGA-Z-Y HUB</span>\n'
        '    <span class="card-index">STAGED UPDATE</span>\n'
        "  </div>\n"
        f"  <h2>{escaped_title}</h2>\n"
        f'  <div class="{content_class}">{escaped_content}</div>\n'
        "</article>\n"
    )


def _sanitize_dossier_html(generated_html: str) -> str:
    allowed_tags = {
        "article",
        "b",
        "blockquote",
        "br",
        "div",
        "em",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "li",
        "ol",
        "p",
        "section",
        "span",
        "strong",
        "ul",
    }
    soup = BeautifulSoup(generated_html, "html.parser")
    for element in soup.find_all(["script", "style", "iframe", "object", "svg"]):
        element.decompose()
    for element in soup.find_all(True):
        if element.name not in allowed_tags:
            element.unwrap()
            continue
        classes = element.get("class", [])
        safe_classes = [
            name for name in classes
            if re.fullmatch(r"[A-Za-z0-9_-]+", name)
        ]
        element.attrs = {"class": safe_classes} if safe_classes else {}
    return str(soup).strip()


def _render_dossier_html(generated_html: str) -> str:
    sanitized = _sanitize_dossier_html(generated_html)
    soup = BeautifulSoup(sanitized, "html.parser")
    if soup.find("article", class_="bento-card"):
        return sanitized + "\n"
    return (
        '<article class="bento-card">\n'
        '  <div class="card-topline">\n'
        '    <span class="card-kicker">LEGA-Z-Y HUB</span>\n'
        '    <span class="card-index">STAGED UPDATE</span>\n'
        "  </div>\n"
        f'  <h2>Kaige</h2>\n  <div class="dossier-content">\n{sanitized}\n'
        "  </div>\n</article>\n"
    )


def _write_receipt(
    receipt_path: Path,
    generated_files: list[Path],
    source: str,
    timestamp: datetime,
) -> None:
    files = "\n".join(
        f"- {path.relative_to(ROOT)}" for path in generated_files
    )
    receipt = (
        "Pantheon Studios AI Webmaster Receipt\n"
        f"Generated at (UTC): {timestamp.isoformat()}\n"
        f"Source: {source}\n"
        f"Files generated:\n{files}\n"
        "Review required: staged content was not added to the live site.\n"
    )
    receipt_path.write_text(receipt, encoding="utf-8")


def generate_character_dossier() -> tuple[Path, Path]:
    reference = REFERENCE_FILE.read_text(encoding="utf-8").strip()
    if not reference:
        raise ValueError(f"{REFERENCE_FILE.name} is empty.")
    dossier = _ollama_generate(
        f"Reference profile (`aj_profile_reference.txt`):\n\n{reference}",
        DOSSIER_SYSTEM_PROMPT,
    )
    STAGED_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    html_path = STAGED_DIRECTORY / "kaige_dossier.html"
    receipt_path = STAGED_DIRECTORY / (
        f"kaige_dossier_{timestamp.strftime('%Y%m%d_%H%M%S_%fZ')}.txt"
    )
    html_path.write_text(_render_dossier_html(dossier), encoding="utf-8")
    _write_receipt(
        receipt_path,
        [html_path, receipt_path],
        REFERENCE_FILE.name,
        timestamp,
    )
    logging.info("Staged character dossier: %s", html_path)
    logging.info("Generated receipt: %s", receipt_path)
    return html_path, receipt_path


def _validate_source_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    try:
        valid_port = parsed.port in (None, 443)
    except ValueError:
        valid_port = False
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_SOURCE_HOSTS
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not valid_port
    ):
        raise ValueError("Update source URL is not an approved official URL.")
    return source_url


def _fetch_page(source_url: str) -> BeautifulSoup:
    response = requests.get(
        _validate_source_url(source_url),
        headers={"User-Agent": "PantheonStudios-AI-Webmaster/1.0"},
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    return BeautifulSoup(response.content[:MAX_PAGE_BYTES], "html.parser")


def _extract_source_text(soup: BeautifulSoup) -> str:
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    content = soup.find(["main", "article"]) or soup.body or soup
    lines = [
        element.get_text(" ", strip=True)
        for element in content.find_all(["h1", "h2", "h3", "p", "li"])
    ]
    return "\n".join(line for line in lines if line)[:MAX_SOURCE_CHARACTERS]


def _scrape_update_sources() -> list[tuple[str, str]]:
    homepage = _fetch_page(UPDATE_SOURCE_URL)
    candidates = []
    for anchor in homepage.find_all("a", href=True):
        destination = urljoin(UPDATE_SOURCE_URL, anchor["href"])
        label = anchor.get_text(" ", strip=True)
        if not UPDATE_LINK_PATTERN.search(f"{label} {destination}"):
            continue
        try:
            destination = _validate_source_url(destination)
        except ValueError:
            continue
        if destination != UPDATE_SOURCE_URL and destination not in candidates:
            candidates.append(destination)

    pages = []
    for source_url in candidates[:3]:
        soup = _fetch_page(source_url)
        text = _extract_source_text(soup)
        if text:
            pages.append((source_url, text))
    if not pages:
        text = _extract_source_text(homepage)
        if text:
            pages.append((UPDATE_SOURCE_URL, text))
    if not pages:
        raise ValueError("No readable update text was found on official sources.")
    return pages


def run_news_crawler() -> tuple[Path, Path] | None:
    try:
        pages = _scrape_update_sources()
        source_text = "\n\n".join(
            f"Source URL: {source_url}\n{text}"
            for source_url, text in pages
        )[:MAX_SOURCE_CHARACTERS]
        bulletin = _ollama_generate(
            f"{NEWS_PROMPT}\n\nSource text:\n{source_text}",
            NEWS_SYSTEM_PROMPT,
        )
        timestamp = datetime.now(timezone.utc)
        stamp = timestamp.strftime("%Y%m%d_%H%M%S_%fZ")
        STAGED_DIRECTORY.mkdir(parents=True, exist_ok=True)
        html_path = STAGED_DIRECTORY / f"news_update_{stamp}.html"
        receipt_path = STAGED_DIRECTORY / f"news_update_{stamp}.txt"
        html_path.write_text(
            _render_bento_card("Lega-Z-y News Update", bulletin, "news-content"),
            encoding="utf-8",
        )
        _write_receipt(
            receipt_path,
            [html_path, receipt_path],
            ", ".join(source_url for source_url, _ in pages),
            timestamp,
        )
        logging.info("Staged news bulletin: %s", html_path)
        logging.info("Generated receipt: %s", receipt_path)
        return html_path, receipt_path
    except (
        OSError,
        requests.RequestException,
        json.JSONDecodeError,
        ValueError,
    ):
        logging.exception("News crawler run failed.")
        return None


def main() -> None:
    try:
        generate_character_dossier()
    except (
        OSError,
        requests.RequestException,
        json.JSONDecodeError,
        ValueError,
    ):
        logging.exception("Character dossier generation failed.")
    schedule.every(3).hours.do(run_news_crawler)
    logging.info("News crawler scheduled to run every three hours.")
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
