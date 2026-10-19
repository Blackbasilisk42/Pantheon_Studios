import math
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
MAX_FILE_BYTES = 500_000
MAX_SNIPPET_CHARACTERS = 1_200
TOKEN_PATTERN = re.compile(r"[\w'-]+", re.UNICODE)
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "backups",
    "dist",
    "node_modules",
    "policies",
    "__pycache__",
}
NAVIGATION_TARGETS = {
    "hub": {
        "description": "Show hub and character roster",
        "target": "index.html#dossier-container",
        "terms": {"hub", "home", "roster", "characters", "show"},
    },
    "stats": {
        "description": "Character statistics and dossier",
        "target": "dossier.html#dossier-display",
        "terms": {"stat", "stats", "attribute", "attributes", "dossier"},
    },
    "lore": {
        "description": "Character lore and dossier",
        "target": "dossier.html#dossier-display",
        "terms": {"lore", "story", "background", "tactics", "skills"},
    },
    "builder": {
        "description": "Character builder",
        "target": "builder.html#hero-builder-form",
        "terms": {"builder", "build", "create", "creation", "character"},
    },
    "command_center": {
        "description": "Command Center",
        "target": "command-center.html#webmaster-form",
        "terms": {"command", "center", "console", "webmaster"},
    },
}
ALLOWED_NAVIGATION_TARGETS = {
    entry["target"] for entry in NAVIGATION_TARGETS.values()
}


def _source_files(root: Path) -> list[Path]:
    candidates = [
        root / "staged_updates" / "kaige_dossier.html",
        root / "dossier.html",
        root / "builder.html",
        root / "index.html",
        root / "command-center.html",
        root / "edit_log.json",
        root / "edit_log.jsonl",
    ]
    candidates.extend(root.glob("*.md"))
    candidates.extend((root / "lore").glob("*.md"))
    candidates.extend((root / "staged_updates").glob("*receipt*.txt"))
    candidates.extend((root / "logs").glob("*.log"))

    files = []
    seen = set()
    for candidate in candidates:
        if not candidate.is_file():
            continue
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue
        if any(part.casefold() in EXCLUDED_PARTS for part in relative.parts):
            continue
        if resolved not in seen and resolved.stat().st_size <= MAX_FILE_BYTES:
            seen.add(resolved)
            files.append(resolved)
    return files


def _plain_text(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".html", ".htm"}:
        soup = BeautifulSoup(content, "html.parser")
        content_root = soup.find(["main", "article"]) or soup.body or soup
        blocks = content_root.find_all(
            ["h1", "h2", "h3", "h4", "p", "li", "label", "button"]
        )
        if blocks:
            paragraphs = []
            headings = []
            for block in blocks:
                text = block.get_text(" ", strip=True)
                if not text:
                    continue
                if block.name in {"h1", "h2", "h3", "h4"}:
                    headings.append(text)
                    continue
                paragraphs.append(" ".join([*headings, text]))
                headings.clear()
            paragraphs.extend(headings)
            return "\n\n".join(paragraphs)
        return content_root.get_text(" ", strip=True)
    return content


def _chunks(path: Path, root: Path) -> list[tuple[str, str]]:
    text = _plain_text(path)
    relative_path = path.relative_to(root).as_posix()
    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", text)
        if paragraph.strip()
    ]
    chunks = []
    for paragraph in paragraphs:
        while len(paragraph) > MAX_SNIPPET_CHARACTERS:
            boundary = paragraph.rfind(" ", 0, MAX_SNIPPET_CHARACTERS)
            if boundary < MAX_SNIPPET_CHARACTERS // 2:
                boundary = MAX_SNIPPET_CHARACTERS
            chunks.append((relative_path, paragraph[:boundary].strip()))
            paragraph = paragraph[boundary:].strip()
        if paragraph:
            chunks.append((relative_path, paragraph))
    if not chunks and text.strip():
        chunks.append((relative_path, text.strip()[:MAX_SNIPPET_CHARACTERS]))
    return chunks


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_PATTERN.findall(text)]


def _rank_chunks(query: str, chunks: list[tuple[str, str]], limit: int) -> list[dict[str, object]]:
    query_counts = Counter(_tokens(query))
    if not query_counts or not chunks:
        return []

    document_counts = [Counter(_tokens(text)) for _, text in chunks]
    document_frequency = Counter(
        token
        for counts in document_counts
        for token in counts
    )
    document_total = len(document_counts)
    inverse_frequency = {
        token: math.log((document_total + 1) / (frequency + 1)) + 1
        for token, frequency in document_frequency.items()
    }
    query_vector = {
        token: (1 + math.log(count)) * inverse_frequency.get(token, 1)
        for token, count in query_counts.items()
    }
    query_norm = math.sqrt(sum(value * value for value in query_vector.values()))
    ranked = []

    for (source, text), counts in zip(chunks, document_counts):
        document_vector = {
            token: (1 + math.log(count)) * inverse_frequency[token]
            for token, count in counts.items()
            if token in inverse_frequency
        }
        document_norm = math.sqrt(
            sum(value * value for value in document_vector.values())
        )
        if not document_norm:
            continue
        score = sum(
            value * document_vector.get(token, 0)
            for token, value in query_vector.items()
        ) / (query_norm * document_norm)
        if score:
            ranked.append(
                {
                    "source": source,
                    "text": text,
                    "score": round(score, 4),
                }
            )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:max(0, limit)]


def build_context(
    query: str,
    root: Path = ROOT,
    limit: int = 6,
) -> dict[str, object]:
    resolved_root = Path(root).resolve()
    chunks = [
        chunk
        for path in _source_files(resolved_root)
        for chunk in _chunks(path, resolved_root)
    ]
    return {
        "snippets": _rank_chunks(query, chunks, limit),
        "navigation": {
            key: {
                "description": entry["description"],
                "target": entry["target"],
            }
            for key, entry in NAVIGATION_TARGETS.items()
        },
    }
