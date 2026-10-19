import json
import os
from typing import Any

from openai import OpenAI, OpenAIError

from context_builder import ALLOWED_NAVIGATION_TARGETS


DEFAULT_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_API_MODEL = "gemini-2.0-flash"
SYSTEM_PROMPT = (
    "You are the Pantheon Studios site guide. Answer only from the supplied "
    "local site context. If the context does not contain the answer, say so "
    "clearly and do not invent facts. Return only a JSON object with the "
    "shape {\"reply\": \"answer text\", \"redirect\": null}. If the user "
    "explicitly asks to open or view a site page, set redirect to exactly "
    "one target from the supplied navigation table; otherwise use null. "
    "Never return any other redirect target."
)


class APIHandlerError(RuntimeError):
    pass


class APIConfigurationError(APIHandlerError):
    pass


class APIRequestError(APIHandlerError):
    pass


class APIResponseError(APIHandlerError):
    pass


def _client() -> tuple[OpenAI, str]:
    api_key = os.getenv("API_KEY", "").strip()
    if not api_key:
        raise APIConfigurationError(
            "Cloud answers are unavailable because API_KEY is not configured."
        )
    base_url = os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL).strip()
    model = os.getenv("API_MODEL", DEFAULT_API_MODEL).strip()
    if not base_url or not model:
        raise APIConfigurationError(
            "API_BASE_URL and API_MODEL must not be empty."
        )
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=30,
        max_retries=1,
    ), model


def _parse_response(content: Any) -> dict[str, str | None]:
    if not isinstance(content, str):
        raise APIResponseError("The cloud API returned an empty response.")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise APIResponseError(
            "The cloud API returned an invalid JSON response."
        ) from error
    if not isinstance(payload, dict):
        raise APIResponseError("The cloud API response must be a JSON object.")
    reply = payload.get("reply")
    redirect = payload.get("redirect")
    if not isinstance(reply, str) or not reply.strip():
        raise APIResponseError("The cloud API response omitted its reply.")
    if redirect is not None and (
        not isinstance(redirect, str)
        or redirect not in ALLOWED_NAVIGATION_TARGETS
    ):
        raise APIResponseError(
            "The cloud API returned an unsupported navigation target."
        )
    return {"reply": reply.strip(), "redirect": redirect}


def answer_query(query: str, context: dict[str, object]) -> dict[str, str | None]:
    snippets = context.get("snippets")
    navigation = context.get("navigation")
    if not isinstance(snippets, list) or not isinstance(navigation, dict):
        raise ValueError("The query context is incomplete.")
    context_payload = json.dumps(
        {
            "snippets": snippets,
            "navigation": navigation,
        },
        ensure_ascii=False,
    )
    client, model = _client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Local site context:\n{context_payload}\n\n"
                        f"User question:\n{query}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
    except OpenAIError as error:
        raise APIRequestError(
            f"The cloud API request failed ({type(error).__name__})."
        ) from error
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as error:
        raise APIResponseError(
            "The cloud API returned an unexpected response."
        ) from error
    return _parse_response(content)
