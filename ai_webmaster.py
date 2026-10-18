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
DOSSIER_REFERENCE_FILE = ROOT / "dossier.html"
STAGED_DIRECTORY = ROOT / "staged_updates"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5-coder:7b"
UPDATE_SOURCE_URL = "https://dbxv2.bn-ent.net/"
ALLOWED_SOURCE_HOSTS = {"dbxv2.bn-ent.net"}
REQUEST_TIMEOUT_SECONDS = 30
OLLAMA_TIMEOUT_SECONDS = 300
MAX_PAGE_BYTES = 2_000_000
MAX_SOURCE_CHARACTERS = 20_000
MAX_DOSSIER_CHARACTERS = 12_000
UPDATE_LINK_PATTERN = re.compile(
    r"patch|update|maintenance|version|news|information|"
    r"アップデート|お知らせ|メンテナンス|更新",
    re.IGNORECASE,
)
DOSSIER_SYSTEM_PROMPT = (
    "Mirror the layout, metric categories, and lore styling of dossier.html. "
    "Output only a clean HTML block wrapped in a container with the "
    "`.bento-card` class. Include the dossier's structural sections for the "
    "character heading, subtitle, power level, combat metrics, equipped combat "
    "skills, and tactical dossier and lore notes.\n\n"
    "Hardcoded Kaige character payload:\n"
    "- Name: KAIGE\n"
    "- Subtitle: Frieza-Race // Elite Patroller\n"
    "- Power Level: LEVEL 199 MAX\n"
    "- Specs: Health 85/100, Ki Specs 100/100, Stamina 88/100, Strike Super "
    "75/100, Ki Blast Super 98/100\n"
    "- Visual Details: Tall, original solid black body design, green eyes, "
    "dark emerald green aura.\n"
    "- Lore/Tactics: Pure Ki-blast primary build utilizing the Center of "
    "Gravity (COG) technique for orbital positioning relative to locked-on "
    "targets. Employs secondary Strike counters including Shadow Crusher and "
    "Backflip to punish gap-closers and reset distance."
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
            "model": OLLAMA_MODEL,
            "system": system,
            "prompt": prompt,
            "stream": False,
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
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
    dossier_html = DOSSIER_REFERENCE_FILE.read_text(encoding="utf-8")
    if not dossier_html.strip():
        raise ValueError(f"{DOSSIER_REFERENCE_FILE.name} is empty.")
    dossier_reference = _extract_dossier_reference(dossier_html)
    dossier = _ollama_generate(dossier_reference, DOSSIER_SYSTEM_PROMPT)
    STAGED_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc)
    html_path = STAGED_DIRECTORY / "kaige_dossier.html"
    receipt_path = STAGED_DIRECTORY / "kaige_receipt.txt"
    html_path.write_text(_render_dossier_html(dossier), encoding="utf-8")
    _write_receipt(
        receipt_path,
        [html_path, receipt_path],
        DOSSIER_REFERENCE_FILE.name,
        timestamp,
    )
    logging.info("Staged character dossier: %s", html_path)
    logging.info("Generated receipt: %s", receipt_path)
    return html_path, receipt_path


def _extract_dossier_reference(dossier_html: str) -> str:
    soup = BeautifulSoup(dossier_html, "html.parser")
    style = soup.find("style")
    scripts = "\n".join(script.get_text() for script in soup.find_all("script"))
    template_match = re.search(
        r"display\.innerHTML\s*=\s*`(.*?)`;", scripts, re.DOTALL
    )
    selectors = {
        ".dossier-main-panel",
        ".dossier-header-grid",
        ".hero-title-group",
        ".power-rank-badge",
        ".spec-grid",
        ".spec-box",
        ".spec-box-title",
        ".stat-line",
        ".stat-name",
        ".stat-val-num",
        ".skill-chip-list",
        ".skill-chip",
        ".lore-box",
        ".lore-title",
    }
    style_rules = []
    if style:
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", style.get_text()):
            if any(
                selector in rule.group(1)
                for selector in selectors
            ):
                style_rules.append(rule.group(0).strip())
    template = template_match.group(1).strip() if template_match else ""
    if not template or not style_rules:
        raise ValueError(
            "Could not extract dossier structure and styles from dossier.html."
        )
    return (
        "Dossier HTML structural reference:\n"
        f"{template}\n\n"
        "Relevant dossier CSS rules:\n"
        + "\n".join(style_rules)
    )


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
