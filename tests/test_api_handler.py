import json
import unittest
from unittest.mock import Mock, patch

import api_handler
import context_builder
from openai import OpenAIError


class APIHandlerTests(unittest.TestCase):
    @patch.dict("os.environ", {"API_KEY": "test-key"}, clear=True)
    @patch("api_handler.OpenAI")
    def test_default_client_uses_current_gemini_flash_model(self, openai_client):
        client, model = api_handler._client()

        self.assertIs(client, openai_client.return_value)
        self.assertEqual(model, "gemini-3.8-flash")
        openai_client.assert_called_once_with(
            api_key="test-key",
            base_url=api_handler.DEFAULT_API_BASE_URL,
            timeout=api_handler.API_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def test_parse_response_accepts_only_known_navigation_targets(self):
        payload = api_handler._parse_response(
            json.dumps(
                {
                    "reply": "Opening the builder.",
                    "redirect": "builder.html#hero-builder-form",
                }
            )
        )

        self.assertEqual(
            payload,
            {
                "reply": "Opening the builder.",
                "redirect": "builder.html#hero-builder-form",
            },
        )

    def test_parse_response_rejects_external_navigation(self):
        with self.assertRaises(api_handler.APIResponseError):
            api_handler._parse_response(
                '{"reply":"Opening it.","redirect":"https://example.com"}'
            )

    @patch.dict("os.environ", {"API_KEY": "test-key"}, clear=True)
    @patch("api_handler._client")
    def test_answer_query_sends_context_and_uses_cloud_first(self, get_client):
        message = type("Message", (), {"content": '{"reply":"Kaige has high Ki blast stats.","redirect":null}'})
        choice = type("Choice", (), {"message": message})
        response = type("Response", (), {"choices": [choice]})
        client = Mock()
        client.chat.completions.create.return_value = response
        get_client.return_value = (client, "gemini-test")
        context = {
            "snippets": [{"source": "dossier.html", "text": "KI BLAST: 98 / 100"}],
            "navigation": context_builder.build_context("stats")["navigation"],
        }

        result = api_handler.answer_query("What is Kaige's Ki blast stat?", context)

        self.assertEqual(
            result,
            {"reply": "Kaige has high Ki blast stats.", "redirect": None},
        )
        get_client.assert_called_once()
        self.assertIn(
            "KI BLAST: 98 / 100",
            client.chat.completions.create.call_args.kwargs["messages"][1]["content"],
        )
        self.assertIn(
            "current_datetime_utc",
            client.chat.completions.create.call_args.kwargs["messages"][1]["content"],
        )
        self.assertIn(
            "general questions using your general knowledge",
            client.chat.completions.create.call_args.kwargs["messages"][0]["content"],
        )

    @patch.dict("os.environ", {"API_KEY": "test-key"}, clear=True)
    @patch("api_handler._request_answer")
    @patch("api_handler._client", return_value=(object(), "gemini-test"))
    def test_quota_exhaustion_returns_cloud_error_without_fallback(
        self,
        get_client,
        request_answer,
    ):
        quota_error = OpenAIError("Quota exceeded for this project.")
        quota_error.body = {
            "error": {
                "code": "insufficient_quota",
                "message": "Quota exceeded for this project.",
            }
        }
        request_answer.side_effect = quota_error

        with self.assertRaisesRegex(
            api_handler.APIRequestError,
            "cloud API request failed",
        ):
            api_handler.answer_query(
                "Question?",
                {"snippets": [], "navigation": {}},
            )

        get_client.assert_called_once()
        request_answer.assert_called_once()

    @patch.dict("os.environ", {"API_KEY": "test-key"}, clear=True)
    @patch("api_handler._request_answer")
    @patch("api_handler._client", return_value=(object(), "gemini-test"))
    def test_cloud_provider_failure_returns_error_after_single_request(
        self,
        get_client,
        request_answer,
    ):
        timeout_error = OpenAIError("The cloud API timed out.")
        timeout_error.status_code = 503
        request_answer.side_effect = timeout_error

        with self.assertRaisesRegex(
            api_handler.APIRequestError,
            "HTTP 503 OpenAIError",
        ):
            api_handler.answer_query(
                "Question?",
                {"snippets": [], "navigation": {}},
            )

        get_client.assert_called_once()
        request_answer.assert_called_once()

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_cloud_key_raises_configuration_error(self):
        with self.assertRaises(api_handler.APIConfigurationError):
            api_handler.answer_query(
                "Show me the roster",
                {"snippets": [], "navigation": {}},
            )


if __name__ == "__main__":
    unittest.main()
