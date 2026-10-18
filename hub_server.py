import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Callable

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory


ROOT = Path(__file__).resolve().parent
REQUEST_TIMEOUT_SECONDS = 6
PUBLIC_SUFFIXES = {
    ".avif",
    ".css",
    ".gif",
    ".html",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".png",
    ".svg",
    ".ttf",
    ".webp",
    ".woff",
    ".woff2",
}
PRIVATE_DIRECTORIES = {
    ".git",
    ".venv",
    "dist",
    "lore",
    "modules",
    "node_modules",
    "policies",
    "staged_updates",
}

load_dotenv(ROOT / ".env")

app = Flask(__name__, static_folder=None)
app.logger.setLevel(logging.INFO)


class MetricProviderError(RuntimeError):
    pass


def _configured_values(*names: str) -> tuple[str, ...] | None:
    values = tuple(os.getenv(name, "").strip() for name in names)
    if not any(values):
        return None
    if not all(values):
        raise MetricProviderError("incomplete provider configuration")
    return values


def _request_json(url: str, **kwargs: object) -> dict[str, object]:
    try:
        response = requests.get(
            url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise MetricProviderError(type(error).__name__) from None
    if not isinstance(payload, dict):
        raise MetricProviderError("unexpected provider response")
    return payload


def _numeric_field(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, str) and value.isdecimal():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MetricProviderError("provider omitted numeric metric")
    if value < 0 or not float(value).is_integer():
        raise MetricProviderError("provider returned invalid metric")
    return int(value)


def _youtube_subscribers() -> int | None:
    configured = _configured_values("YOUTUBE_API_KEY", "YOUTUBE_CHANNEL_ID")
    if configured is None:
        return None
    api_key, channel_id = configured
    payload = _request_json(
        "https://www.googleapis.com/youtube/v3/channels",
        params={
            "part": "statistics",
            "id": channel_id,
            "key": api_key,
        },
    )
    items = payload.get("items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise MetricProviderError("provider omitted channel")
    statistics = items[0].get("statistics")
    if not isinstance(statistics, dict):
        raise MetricProviderError("provider omitted statistics")
    return _numeric_field(statistics, "subscriberCount")


def _discord_online() -> int | None:
    configured = _configured_values("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID")
    if configured is None:
        return None
    bot_token, guild_id = configured
    payload = _request_json(
        f"https://discord.com/api/v10/guilds/{guild_id}/preview",
        headers={"Authorization": f"Bot {bot_token}"},
    )
    return _numeric_field(payload, "approximate_presence_count")


def _meta_followers() -> int | None:
    configured = _configured_values("META_ACCESS_TOKEN", "META_PAGE_ID")
    if configured is None:
        return None
    access_token, page_id = configured
    version = os.getenv("META_GRAPH_API_VERSION", "v23.0").strip()
    if not version.startswith("v") or not version[1:].replace(".", "").isdigit():
        raise MetricProviderError("invalid Graph API version")
    payload = _request_json(
        f"https://graph.facebook.com/{version}/{page_id}",
        params={"fields": "followers_count"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return _numeric_field(payload, "followers_count")


METRIC_PROVIDERS: dict[str, tuple[str, Callable[[], int | None]]] = {
    "youtube_subscribers": ("YouTube", _youtube_subscribers),
    "discord_online": ("Discord", _discord_online),
    "meta_followers": ("Meta", _meta_followers),
}


@app.get("/api/metrics")
def metrics():
    values: dict[str, int | None] = {
        metric_name: None for metric_name in METRIC_PROVIDERS
    }
    provider_errors = 0
    with ThreadPoolExecutor(max_workers=len(METRIC_PROVIDERS)) as executor:
        futures = {
            executor.submit(provider): (metric_name, provider_name)
            for metric_name, (provider_name, provider) in METRIC_PROVIDERS.items()
        }
        for future in as_completed(futures):
            metric_name, provider_name = futures[future]
            try:
                values[metric_name] = future.result()
            except MetricProviderError as error:
                provider_errors += 1
                app.logger.warning(
                    "%s metric request failed (%s)",
                    provider_name,
                    str(error),
                )
    return jsonify(values), (502 if provider_errors else 200)


@app.get("/")
def home():
    return send_from_directory(ROOT, "command-center.html")


@app.get("/<path:filename>")
def public_file(filename: str):
    path = PurePosixPath(filename)
    if (
        path.suffix.lower() not in PUBLIC_SUFFIXES
        or any(part.startswith(".") or part.lower() in PRIVATE_DIRECTORIES
               for part in path.parts)
    ):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(ROOT, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
