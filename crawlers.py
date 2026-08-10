#!/usr/bin/env python3
"""Pantheon Studios autonomous intelligence crawler.

Fetches a URL using a custom User-Agent, analyzes text density, and writes
structured intelligence logs in Markdown format.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import argparse
import re

import requests
from bs4 import BeautifulSoup
from modules.crawler_engine import CrawlerEngine


TIMEOUT_SECONDS = 20


@dataclass
class CrawlReport:
    url: str
    title: str
    fetched_at: str
    status_code: int
    word_count: int
    character_count: int
    paragraph_count: int
    avg_words_per_paragraph: float
    content_density: float
    top_keywords: list[tuple[str, int]]
    snippet: str


def slugify(value: str, max_length: int = 80) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", value).strip().lower()
    cleaned = re.sub(r"[\s_-]+", "-", cleaned)
    slug = cleaned.strip("-") or "untitled"
    return slug[:max_length].rstrip("-")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fetch_page(url: str) -> tuple[requests.Response, dict[str, str], float]:
    engine = CrawlerEngine(timeout_seconds=TIMEOUT_SECONDS)
    crawl_response = engine.fetch(url)
    return crawl_response.response, crawl_response.used_headers, crawl_response.delay_seconds


def analyze_html(url: str, response: requests.Response) -> CrawlReport:
    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "meta", "link"]):
        tag.extract()

    title = normalize_whitespace(soup.title.string) if soup.title and soup.title.string else "Untitled Page"
    paragraphs = [normalize_whitespace(p.get_text(" ")) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if p]

    text = normalize_whitespace(soup.get_text(" "))
    words = re.findall(r"\b[a-zA-Z][a-zA-Z-]{1,}\b", text.lower())
    word_count = len(words)

    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "have", "are", "was",
        "you", "your", "they", "their", "will", "would", "about", "there", "which",
        "when", "what", "where", "while", "into", "been", "more", "than", "also",
    }
    filtered_words = [w for w in words if w not in stop_words and len(w) > 3]
    top_keywords = Counter(filtered_words).most_common(10)

    char_count = len(text)
    paragraph_count = len(paragraphs)
    avg_words_per_paragraph = (word_count / paragraph_count) if paragraph_count else 0.0
    density = (char_count / len(response.text)) if response.text else 0.0
    snippet = text[:900] + ("..." if len(text) > 900 else "")

    return CrawlReport(
        url=url,
        title=title,
        fetched_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status_code=response.status_code,
        word_count=word_count,
        character_count=char_count,
        paragraph_count=paragraph_count,
        avg_words_per_paragraph=avg_words_per_paragraph,
        content_density=density,
        top_keywords=top_keywords,
        snippet=snippet,
    )


def render_report(report: CrawlReport, used_headers: dict[str, str], delay_seconds: float) -> str:
    keyword_lines = "\n".join(
        f"- {word}: {count}" for word, count in report.top_keywords
    ) or "- No strong keywords detected"

    return f"""# Intelligence Log: {report.title}

## Source
- URL: {report.url}
- Fetched At: {report.fetched_at}
- HTTP Status: {report.status_code}
- User-Agent: {used_headers.get('User-Agent', 'unknown')}
- Request Delay (seconds): {delay_seconds:.2f}

## Metrics
- Word Count: {report.word_count}
- Character Count: {report.character_count}
- Paragraph Count: {report.paragraph_count}
- Avg Words / Paragraph: {report.avg_words_per_paragraph:.2f}
- Content Density (visible chars / raw HTML chars): {report.content_density:.4f}

## Top Keywords
{keyword_lines}

## Content Snippet
{report.snippet}
"""


def save_report(
    report: CrawlReport,
    workspace: Path,
    used_headers: dict[str, str],
    delay_seconds: float,
) -> Path:
    filename = f"intelligence_log_{slugify(report.title)}.md"
    path = workspace / filename

    suffix = 1
    while path.exists():
        path = workspace / f"intelligence_log_{slugify(report.title)}_{suffix}.md"
        suffix += 1

    path.write_text(render_report(report, used_headers, delay_seconds), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pantheon Studios intelligence crawler")
    parser.add_argument("url", nargs="?", help="Target URL to crawl")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_url = args.url or input("Enter target URL: ").strip()

    if not target_url:
        print("No URL provided. Exiting.")
        return

    try:
        response, used_headers, delay_seconds = fetch_page(target_url)
        report = analyze_html(target_url, response)
    except requests.RequestException as exc:
        print(f"Fetch failed: {exc}")
        return
    except Exception as exc:
        print(f"Unexpected crawler error: {exc}")
        return

    output_path = save_report(report, Path.cwd(), used_headers, delay_seconds)
    print(f"Intelligence report created: {output_path.name}")


if __name__ == "__main__":
    main()
