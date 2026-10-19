import copy
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import schedule
from bs4 import BeautifulSoup
from bs4.element import Tag

from modules import edit_safety

ROOT = Path(__file__).parent.resolve()
DOSSIER_FILE = ROOT / "dossier.html"
STAGED_DIRECTORY = ROOT / "staged_updates"
DOSSIER_OUTPUT = STAGED_DIRECTORY / "kaige_dossier.html"
DOSSIER_RECEIPT = STAGED_DIRECTORY / "kaige_receipt.txt"
NEWS_OUTPUT = STAGED_DIRECTORY / "news_bulletin.html"
NEWS_RECEIPT = STAGED_DIRECTORY / "crawler_receipt.txt"
UPDATE_SOURCE_URL = "https://dbxv2.bn-ent.net/"
ALLOWED_SOURCE_HOSTS = {"dbxv2.bn-ent.net"}
REQUEST_TIMEOUT_SECONDS = 20
MAX_PAGE_BYTES = 2_000_000
MAX_SOURCE_CHARACTERS = 20_000
UPDATE_LINK_PATTERN = re.compile(
    r"patch|update|maintenance|version|news|information|"
    r"アップデート|お知らせ|メンテナンス|更新",
    re.IGNORECASE,
)
KAIGE = {
    "name": "KAIGE",
    "subtitle": "Frieza-Race // Elite Patroller",
    "power_level": "LEVEL 199 MAX",
    "metrics": {
        "MAX HEALTH": "85 / 100",
        "MAX KI SPECS": "100 / 100",
        "MAX STAMINA": "88 / 100",
        "STRIKE SUPER POWER": "75 / 100",
        "KI BLAST SUPER POWER": "98 / 100",
    },
    "skills": [
        {"name": "KI BLAST SPECIALIST", "type": "ki"},
        {"name": "SHADOW CRUSHER", "type": "strike"},
        {"name": "BACKFLIP", "type": "strike"},
    ],
    "lore": {
        "title": "Ki-Blast Specialist and Orbital Zoner",
        "attributes": (
            "Features a tall, original solid black body design with green "
            "eyes—a legacy design predating the Black Frieza form by over "
            "half a decade—wreathed in a dark emerald green aura. Operates on "
            "a pure Ki-blast primary combat build, utilizing the 'Center of "
            "Gravity' (COG) technique to maintain precise orbital positioning "
            "relative to locked-on targets."
        ),
        "evasive": (
            "Relies heavily on maintaining spatial advantage. Instead of "
            "engaging in close-quarters brawling, utilizes skills like Backflip "
            "to instantly create distance, forcing opponents into optimal "
            "zoning range where overwhelming Ki-blast damage dictates the pace."
        ),
        "counters": (
            "Proficient in punishing adversaries who attempt to close the gap. "
            "Employs secondary Strike counters like Shadow Crusher to break "
            "incoming momentum, allowing immediate repositioning to resume "
            "high-damage energy assaults."
        ),
    },
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)


def _timestamp() -> datetime:
    return datetime.now(timezone.utc)


def _require_tag(element: Tag | None, description: str) -> Tag:
    if element is None:
        raise ValueError(f"Required HTML element was not found: {description}")
    return element


def _replace_contents(element: Tag, text: str) -> None:
    element.clear()
    element.append(text)


def _template_markup(source: BeautifulSoup) -> str:
    scripts = "\n".join(
        script.get_text() for script in source.find_all("script")
    )
    match = re.search(
        r"display\.innerHTML\s*=\s*`(.*?)`;", scripts, re.DOTALL
    )
    if not match:
        raise ValueError("Dossier render template was not found.")
    markup = re.sub(
        r'<img src="\$\{avatarSrc\}".*?>',
        "",
        match.group(1),
        flags=re.DOTALL,
    )
    replacements = {
        "${hero.name || 'UNKNOWN OPERATIVE'}": "KAIGE",
        "${hero.spec || 'Unclassified Data'}": KAIGE["subtitle"],
        "${hero.power || 'CLASSIFIED'}": KAIGE["power_level"],
        "${hero.health || '0 / 100'}": KAIGE["metrics"]["MAX HEALTH"],
        "${hero.ki || '0 / 100'}": KAIGE["metrics"]["MAX KI SPECS"],
        "${hero.stamina || '0 / 100'}": KAIGE["metrics"]["MAX STAMINA"],
        "${hero.strikeSuper || '0 / 100'}": KAIGE["metrics"][
            "STRIKE SUPER POWER"
        ],
        "${hero.kiSuper || '0 / 100'}": KAIGE["metrics"][
            "KI BLAST SUPER POWER"
        ],
        "${skillsHTML}": "",
        "${hero.lore || 'No tactical lore logged for this operative.'}": "",
    }
    for placeholder, value in replacements.items():
        markup = markup.replace(placeholder, value)
    if "${" in markup:
        raise ValueError("Dossier render template has unsupported placeholders.")
    return markup


def _append_lore_sections(lore_box: Tag) -> None:
    title = lore_box.select_one(".lore-title")
    lore_box.clear()
    if title:
        lore_box.append(title)
    for heading, content in (
        (KAIGE["lore"]["title"], None),
        ("ATTRIBUTES", KAIGE["lore"]["attributes"]),
        ("EVASIVE TACTICS", KAIGE["lore"]["evasive"]),
        ("COUNTER TACTICS", KAIGE["lore"]["counters"]),
    ):
        if content is None:
            section_title = _require_tag(
                BeautifulSoup(
                    '<div class="lore-title"></div>', "html.parser"
                ).div,
                "lore section heading",
            )
            section_title.string = heading
            lore_box.append(section_title)
            continue
        section = _require_tag(
            BeautifulSoup(
                '<p class="lore-section"></p>', "html.parser"
            ).p,
            "lore section",
        )
        section.append(heading + ": ")
        section.append(content)
        lore_box.append(section)


def _relevant_styles(source: BeautifulSoup, card: Tag) -> str:
    style = source.find("style")
    if not style:
        return ""
    classes = {
        class_name
        for element in card.find_all(True)
        for class_name in element.get("class", [])
    }
    classes.update(card.get("class", []))
    ids = {
        element.get("id")
        for element in card.find_all(True)
        if element.get("id")
    }
    rules = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", style.get_text()):
        selector_group = match.group(1).strip()
        selectors = [selector.strip() for selector in selector_group.split(",")]
        relevant = any(
            selector in {":root", "*"}
            or any(f".{class_name}" in selector for class_name in classes)
            or any(f"#{element_id}" in selector for element_id in ids)
            for selector in selectors
        )
        if relevant:
            rules.append(f"{selector_group} {{{match.group(2)}}}")
    return "\n".join(rules)


def _fallback_dossier_card() -> str:
    soup = BeautifulSoup(
        '<article class="bento-card dossier-main-panel">'
        '<div class="dossier-header-grid">'
        '<div class="big-avatar"></div>'
        '<div class="hero-title-group"><h1 class="card-header"></h1>'
        '<div class="spec-tag"></div></div>'
        '<div class="power-rank-badge">'
        '<div class="power-rank-label">RECORDED POWER LEVEL</div>'
        '<div class="power-rank-value"></div></div></div>'
        '<div class="spec-grid">'
        '<div class="spec-box metrics-section"><div class="spec-box-title">'
        'COMBAT METRICS &amp; SPECS</div></div>'
        '<div class="spec-box"><div class="spec-box-title">'
        'EQUIPPED COMBAT SKILLS</div><div class="skill-chip-list"></div></div>'
        '</div><div class="lore-box lore-section"><div class="lore-title">'
        'TACTICAL DOSSIER &amp; LORE NOTES</div></div></article>',
        "html.parser",
    )
    card = soup.article
    _inject_kaige(card)
    return str(card)


def _inject_kaige(card: Tag) -> None:
    card["class"] = list(dict.fromkeys([*card.get("class", []), "bento-card"]))
    card.attrs.pop("id", None)
    avatar = card.select_one(".big-avatar")
    if avatar:
        _replace_contents(avatar, "K")
    _replace_contents(
        _require_tag(card.select_one(".hero-title-group h1"), "dossier name"),
        KAIGE["name"],
    )
    _replace_contents(
        _require_tag(card.select_one(".spec-tag"), "dossier subtitle"),
        KAIGE["subtitle"],
    )
    _replace_contents(
        _require_tag(card.select_one(".power-rank-value"), "power level"),
        KAIGE["power_level"],
    )
    metric_values: dict[str, Tag] = {}
    for metric in card.select(".stat-line"):
        name = metric.select_one(".stat-name")
        value = metric.select_one(".stat-val-num")
        if name is not None and value is not None:
            metric_values[name.get_text(" ", strip=True)] = value
    for label, value in KAIGE["metrics"].items():
        value_element = metric_values.get(label)
        if value_element is None:
            metric = _require_tag(
                BeautifulSoup(
                    '<div class="stat-line"><span class="stat-name"></span>'
                    '<span class="stat-val-num"></span></div>',
                    "html.parser",
                ).div,
                "new stat row",
            )
            _replace_contents(
                _require_tag(metric.select_one(".stat-name"), "stat name"),
                label,
            )
            _replace_contents(
                _require_tag(metric.select_one(".stat-val-num"), "stat value"),
                value,
            )
            _require_tag(card.select_one(".spec-box"), "stats section").append(
                metric
            )
        else:
            _replace_contents(value_element, value)
    skills = card.select_one(".skill-chip-list")
    if skills:
        skills.clear()
        for skill in KAIGE["skills"]:
            chip = _require_tag(
                BeautifulSoup(
                    '<span class="skill-chip"></span>', "html.parser"
                ).span,
                "skill chip",
            )
            chip["class"] = ["skill-chip", skill["type"]]
            chip.string = skill["name"]
            skills.append(chip)
    lore_box = card.select_one(".lore-box")
    if lore_box:
        _append_lore_sections(lore_box)


def _write_dossier_receipt(status: str) -> None:
    receipt = (
        "Pantheon Studios deterministic dossier receipt\n"
        f"Timestamp (UTC): {_timestamp().isoformat()}\n"
        f"Status: {status}\n"
        f"Output: {DOSSIER_OUTPUT.relative_to(ROOT)}\n"
        "Character payload injected:\n"
        f"{json.dumps(KAIGE, ensure_ascii=False, indent=2)}\n"
    )
    edit_safety.write_text(
        DOSSIER_RECEIPT,
        receipt,
        "write dossier generation receipt",
        ROOT,
    )


def generate_character_dossier() -> tuple[Path, Path]:
    STAGED_DIRECTORY.mkdir(parents=True, exist_ok=True)
    status = "fallback template"
    card_html = _fallback_dossier_card()
    try:
        source_html = DOSSIER_FILE.read_text(encoding="utf-8")
        source = BeautifulSoup(source_html, "html.parser")
        source_card = source.select_one(".dossier-main-panel")
        if source_card is not None:
            template = BeautifulSoup(_template_markup(source), "html.parser")
            cloned_card = copy.deepcopy(source_card)
            cloned_card.clear()
            for child in list(template.contents):
                cloned_card.append(copy.deepcopy(child))
            _inject_kaige(cloned_card)
            styles = _relevant_styles(source, cloned_card)
            card_html = f"<style>\n{styles}\n</style>\n{cloned_card}"
            status = "cloned dossier.html template"
        else:
            logging.warning("Dossier card not found; using fallback template.")
    except (OSError, UnicodeError, ValueError) as error:
        logging.warning("Unable to clone dossier.html (%s); using fallback.", error)
    edit_safety.write_text(
        DOSSIER_OUTPUT,
        card_html + "\n",
        "generate character dossier",
        ROOT,
    )
    _write_dossier_receipt(status)
    logging.info("Staged Kaige dossier: %s", DOSSIER_OUTPUT)
    logging.info("Wrote dossier receipt: %s", DOSSIER_RECEIPT)
    return DOSSIER_OUTPUT, DOSSIER_RECEIPT


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
        headers={
            "User-Agent": os.getenv(
                "PANTHEON_CRAWLER_USER_AGENT",
                "PantheonStudios-AI-Webmaster/1.0",
            )
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=False,
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "html" not in content_type:
        raise ValueError("Update source did not return HTML.")
    return BeautifulSoup(response.content[:MAX_PAGE_BYTES], "html.parser")


def _extract_source_text(soup: BeautifulSoup) -> tuple[str, str]:
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    heading = soup.find(["h1", "h2", "h3"])
    title_element = heading or soup.find("title")
    title = (
        title_element.get_text(" ", strip=True)
        if title_element is not None
        else "Dragon Ball / Xenoverse Update"
    )
    content = soup.find(["main", "article"]) or soup.body or soup
    lines = [
        element.get_text(" ", strip=True)
        for element in content.find_all(["p", "li"])
    ]
    text = "\n".join(line for line in lines if line)[:MAX_SOURCE_CHARACTERS]
    return title, text


def _scrape_update_sources() -> list[tuple[str, str, str]]:
    homepage = _fetch_page(UPDATE_SOURCE_URL)
    candidates = []
    for anchor in homepage.find_all("a", href=True):
        href = anchor.get("href")
        if not isinstance(href, str):
            continue
        destination = urljoin(UPDATE_SOURCE_URL, href)
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
        try:
            title, text = _extract_source_text(_fetch_page(source_url))
        except (requests.RequestException, ValueError) as error:
            logging.warning("Unable to scrape %s (%s).", source_url, error)
            continue
        if text:
            pages.append((source_url, title, text))
    if not pages:
        title, text = _extract_source_text(homepage)
        if text:
            pages.append((UPDATE_SOURCE_URL, title, text))
    if not pages:
        raise ValueError("No readable update text was found on official sources.")
    return pages


def _news_bulletin_html(pages: list[tuple[str, str, str]]) -> str:
    soup = BeautifulSoup(
        '<article class="bento-card news-card">'
        '<div class="card-topline"><span class="card-index">'
        'OFFICIAL TRANSMISSION</span></div>'
        '<h2 class="card-header"></h2>'
        '<section class="metrics-section"><h3>UPDATE DETAILS</h3><ul></ul></section>'
        '<section class="lore-section"><h3>SOURCE</h3><ul></ul></section>'
        "</article>",
        "html.parser",
    )
    card = _require_tag(soup.article, "news bulletin")
    first_title = pages[0][1]
    _require_tag(card.select_one(".card-header"), "news title").string = first_title
    details = _require_tag(
        card.select_one(".metrics-section ul"),
        "news details list",
    )
    sources = _require_tag(
        card.select_one(".lore-section ul"),
        "news sources list",
    )
    for source_url, title, text in pages:
        if title and title != first_title:
            heading = soup.new_tag("li")
            heading.string = title
            details.append(heading)
        for line in text.splitlines():
            if line.strip():
                item = soup.new_tag("li")
                item.string = line.strip()
                details.append(item)
        source_item = soup.new_tag("li")
        source_link = soup.new_tag("a", href=source_url, rel="noopener noreferrer")
        source_link.string = source_url
        source_item.append(source_link)
        sources.append(source_item)
    return str(card)


def _append_crawler_receipt(
    status: str,
    pages: list[tuple[str, str, str]],
    error: str | None = None,
) -> None:
    receipt = (
        f"Timestamp (UTC): {_timestamp().isoformat()}\n"
        f"Status: {status}\n"
        f"Output: {NEWS_OUTPUT.relative_to(ROOT)}\n"
        "Sources:\n"
        + (
            "\n".join(f"- {url}: {title}" for url, title, _ in pages)
            if pages
            else f"- {UPDATE_SOURCE_URL}\n"
        )
        + (f"Error: {error}\n" if error else "")
        + "\n"
    )
    edit_safety.append_text(
        NEWS_RECEIPT,
        receipt,
        "append news crawler receipt",
        ROOT,
    )


def _news_unavailable_html(error: str) -> str:
    soup = BeautifulSoup(
        '<article class="bento-card news-card">'
        '<div class="card-topline"><span class="card-index">'
        'CRAWLER STATUS</span></div>'
        '<h2 class="card-header">SOURCE UNAVAILABLE</h2>'
        '<section class="metrics-section"><h3>UPDATE DETAILS</h3><p></p></section>'
        '<section class="lore-section"><h3>SOURCE</h3><p></p></section>'
        "</article>",
        "html.parser",
    )
    _require_tag(
        soup.select_one(".metrics-section p"),
        "crawler status details",
    ).string = (
        "No update content was staged because the official source could not "
        "be reached."
    )
    _require_tag(
        soup.select_one(".lore-section p"),
        "crawler status source",
    ).string = (
        f"{UPDATE_SOURCE_URL} — {error}"
    )
    return str(_require_tag(soup.article, "crawler status"))


def run_news_crawler() -> tuple[Path, Path] | None:
    try:
        pages = _scrape_update_sources()
        STAGED_DIRECTORY.mkdir(parents=True, exist_ok=True)
        edit_safety.write_text(
            NEWS_OUTPUT,
            _news_bulletin_html(pages) + "\n",
            "stage news bulletin",
            ROOT,
        )
        _append_crawler_receipt("news bulletin staged", pages)
        logging.info("Staged news bulletin: %s", NEWS_OUTPUT)
        logging.info("Appended crawler receipt: %s", NEWS_RECEIPT)
        return NEWS_OUTPUT, NEWS_RECEIPT
    except (
        OSError,
        requests.RequestException,
        UnicodeError,
        ValueError,
    ) as error:
        logging.warning(
            "News crawler source unavailable; staging status (%s).",
            error,
        )
        try:
            STAGED_DIRECTORY.mkdir(parents=True, exist_ok=True)
            edit_safety.write_text(
                NEWS_OUTPUT,
                _news_unavailable_html(str(error)) + "\n",
                "stage crawler unavailable status",
                ROOT,
            )
            _append_crawler_receipt(
                "source unavailable; no news staged",
                [],
                str(error),
            )
            return NEWS_OUTPUT, NEWS_RECEIPT
        except OSError:
            logging.exception("Unable to write crawler failure status.")
            return None


def main() -> None:
    STAGED_DIRECTORY.mkdir(parents=True, exist_ok=True)
    try:
        generate_character_dossier()
    except (OSError, UnicodeError, ValueError):
        logging.exception("Character dossier generation failed.")
    run_news_crawler()
    schedule.every(3).hours.do(run_news_crawler)
    logging.info("News crawler scheduled to run every three hours.")
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    main()
