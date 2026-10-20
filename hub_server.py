import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
from typing import Callable

import requests
from dotenv import load_dotenv
import schedule
from flask_cors import CORS
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

import ai_webmaster
import webmaster
import api_handler
import context_builder
from modules import edit_safety, site_health


ROOT = Path(__file__).resolve().parent
REQUEST_TIMEOUT_SECONDS = 6
SCHEDULER_POLL_SECONDS = 1
MAX_COMMAND_LENGTH = 1000
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
    "backups",
    "dist",
    "lore",
    "modules",
    "node_modules",
    "policies",
    "staged_updates",
}

load_dotenv(ROOT / ".env")

app = Flask(__name__, static_folder=None)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ["https://pantheoncore.studios"],
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type"],
        }
    },
)
app.logger.setLevel(logging.INFO)
webmaster_scheduler = schedule.Scheduler()
_scheduler_stop = threading.Event()
_scheduler_lock = threading.Lock()
_scheduler_thread: threading.Thread | None = None


def _json_error(message: str, status_code: int):
    return jsonify({
        "status": "error",
        "message": message,
        "error": message,
    }), status_code


@app.errorhandler(HTTPException)
def handle_http_exception(error: HTTPException):
    if request.path.startswith("/api/"):
        message = error.description
        return _json_error(message, error.code or 500)
    return error


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


def _run_scheduled(action: str, operation: Callable[[], object]) -> None:
    try:
        operation()
    except Exception:
        app.logger.exception("Scheduled Webmaster action failed: %s", action)


def _scheduler_loop() -> None:
    _run_scheduled("startup dossier generation", ai_webmaster.generate_character_dossier)
    _run_scheduled("startup news crawl", ai_webmaster.run_news_crawler)
    while not _scheduler_stop.wait(SCHEDULER_POLL_SECONDS):
        webmaster_scheduler.run_pending()


def start_scheduler() -> None:
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread and _scheduler_thread.is_alive():
            return
        _scheduler_stop.clear()
        webmaster_scheduler.clear()
        webmaster_scheduler.every(1).day.do(
            _run_scheduled,
            "daily dossier generation",
            ai_webmaster.generate_character_dossier,
        )
        webmaster_scheduler.every(3).hours.do(
            _run_scheduled,
            "news crawler",
            ai_webmaster.run_news_crawler,
        )
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            name="webmaster-scheduler",
            daemon=True,
        )
        _scheduler_thread.start()
        app.logger.info("Webmaster scheduler started.")


def stop_scheduler() -> None:
    _scheduler_stop.set()
    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=SCHEDULER_POLL_SECONDS + 1)


def _dispatch_command(command: str) -> tuple[str, object]:
    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        command.strip().lower(),
    ).strip()
    if normalized in {"hello", "hi", "hey", "hello there"}:
        return (
            "greeting",
            "Hello! Try SITE CHECK, DOSSIER, NEWS UPDATE, or ask a site question.",
        )
    if normalized in {
        "rollback",
        "rollback latest edit",
        "revert",
        "restore",
        "restore latest edit",
    }:
        return "rollback", edit_safety.rollback_latest(ROOT)
    if normalized in {
        "health",
        "diagnostic",
        "diagnostics",
        "site check",
        "check site",
        "run site check",
        "check for broken elements",
    }:
        return "site_health_check", site_health.inspect_site(ROOT)
    if normalized in {
        "dossier",
        "kaige dossier",
        "update kaige dossier",
        "update kaige s dossier",
        "update kaige stats",
        "update kaige s stats",
        "generate character dossier",
    }:
        return "generate_character_dossier", ai_webmaster.generate_character_dossier()
    if normalized in {
        "news update",
        "run news update",
        "update news",
        "news",
        "run news crawler",
        "maintenance",
        "run maintenance",
    }:
        result = ai_webmaster.run_news_crawler()
        if result is None:
            raise RuntimeError("News crawler could not write its results.")
        return "run_news_crawler", result
    if normalized in {
        "stage official source update",
        "stage official update",
        "scrape official update",
    }:
        source_url, source_text = webmaster.scrape_source(
            webmaster.DEFAULT_SOURCE_URL
        )
        update = webmaster.generate_update(source_text)
        return "stage_official_update", webmaster.stage_update(
            source_url,
            update,
        )
    if command.strip().endswith("?") or re.match(
        r"^(what|who|where|when|why|how|which|can|could|would|should|"
        r"is|are|do|does|did|tell me|explain|go to|open|view|"
        r"show me|take me to|navigate to)\b",
        command.strip(),
        re.IGNORECASE,
    ):
        context = context_builder.build_context(command, ROOT)
        return "site_knowledge_answer", api_handler.answer_query(
            command,
            context,
        )
    raise ValueError(
        "Command is not supported. Use a maintenance command or ask a site "
        "question."
    )


@app.get("/api/health")
def site_health_status():
    try:
        return jsonify(site_health.inspect_site(ROOT))
    except (OSError, UnicodeError, ValueError):
        app.logger.exception("Site health check failed.")
        return jsonify({"error": "Site health check failed."}), 500


@app.post("/api/execute")
def execute_command():
    try:
        return _execute_command()
    except Exception:
        app.logger.exception("Unexpected Webmaster request failure.")
        return _json_error("Webmaster command failed.", 500)


def _execute_command():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _json_error("A JSON object with a command is required.", 400)
    command = payload.get("command")
    if not isinstance(command, str) or not command.strip():
        return _json_error("Command must be a non-empty string.", 400)
    if len(command) > MAX_COMMAND_LENGTH:
        return _json_error("Command exceeds the maximum length.", 413)

    try:
        action, result = _dispatch_command(command)
    except api_handler.APIConfigurationError as error:
        return _json_error(str(error), 503)
    except api_handler.APIHandlerError as error:
        app.logger.warning("Site question failed: %s", str(error))
        return _json_error(str(error), 502)
    except ValueError as error:
        return _json_error(str(error), 400)
    except (OSError, requests.RequestException, RuntimeError, UnicodeError):
        app.logger.exception("Webmaster command failed.")
        return _json_error("Webmaster command failed.", 500)
    except Exception:
        app.logger.exception("Unexpected Webmaster command failure.")
        return _json_error("Webmaster command failed.", 500)

    try:
        if isinstance(result, tuple) and all(
            isinstance(path, Path) for path in result
        ):
            serialized_result = [
                path.relative_to(ROOT).as_posix() for path in result
            ]
        elif isinstance(result, Path):
            serialized_result = result.relative_to(ROOT).as_posix()
        else:
            serialized_result = result
        response_payload: dict[str, object] = {
            "action": action,
            "result": serialized_result,
        }
        if action == "greeting" and isinstance(result, str):
            response_payload["message"] = result
        if action == "site_knowledge_answer" and isinstance(result, dict):
            message = result.get("reply")
            redirect = result.get("redirect")
            if isinstance(message, str):
                response_payload["message"] = message
            if isinstance(redirect, str):
                response_payload["redirect"] = redirect
                response_payload["navigation"] = {
                    "type": "navigate",
                    "target": redirect,
                }
        return jsonify(response_payload)
    except Exception:
        app.logger.exception("Unable to serialize Webmaster command result.")
        return _json_error("Webmaster command failed.", 500)


@app.get("/")
def home():
    return send_from_directory(ROOT, "command-center.html")


@app.get("/<path:filename>")
def public_file(filename: str):
    path = PurePosixPath(filename)
    if path.parts and path.parts[0].lower() == "api":
        return _json_error("Not found", 404)
    if (
        path.suffix.lower() not in PUBLIC_SUFFIXES
        or any(part.startswith(".") or part.lower() in PRIVATE_DIRECTORIES
               for part in path.parts)
    ):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(ROOT, filename)


if __name__ == "__main__":
    start_scheduler()
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
        use_reloader=False,
    )
