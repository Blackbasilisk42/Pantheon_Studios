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

    @patch.dict("os.environ", {"API_KEY": "test-key"}, clear=True)
    @patch("api_handler._local_answer_query")
    @patch("api_handler._request_answer")
    @patch("api_handler._client", return_value=(object(), "gemini-test"))
    def test_cloud_rate_limit_falls_back_to_ollama(
        self,
        get_client,
        request_answer,
        local_answer,
    ):
        quota_error = OpenAIError("Quota exceeded for this project.")
        quota_error.body = {
            "error": {
                "code": "insufficient_quota",
                "message": "Quota exceeded for this project.",
            }
        }
        request_answer.side_effect = quota_error
        local_answer.return_value = {
            "reply": "Local fallback response.",
            "redirect": None,
        }
        context = {"snippets": [], "navigation": {}}

        result = api_handler.answer_query("What is on the site?", context)

        self.assertEqual(
            result,
            {"reply": "Local fallback response.", "redirect": None},
        )
        request_answer.assert_called_once()
        local_answer.assert_called_once()
        self.assertEqual(local_answer.call_args.args[0], "What is on the site?")

    @patch.dict("os.environ", {"API_KEY": "test-key"}, clear=True)
    @patch("api_handler._local_answer_query")
    @patch(
        "api_handler._request_answer",
        side_effect=OpenAIError("The cloud API is temporarily unavailable."),
    )
    @patch("api_handler._client", return_value=(object(), "missing-model"))
    def test_non_quota_cloud_failure_does_not_fall_back_to_ollama(
        self,
        get_client,
        request_answer,
        local_answer,
    ):
        request_answer.side_effect.status_code = 503
        with self.assertRaisesRegex(
            api_handler.APIRequestError,
            "HTTP 503 OpenAIError.*Ollama fallback is reserved for exhausted cloud quota",
        ):
            api_handler.answer_query(
                "Question?",
                {"snippets": [], "navigation": {}},
            )

        request_answer.assert_called_once()
        local_answer.assert_not_called()

    @patch.dict("os.environ", {}, clear=True)
    @patch("api_handler._local_answer_query")
    def test_missing_cloud_key_does_not_use_ollama(self, local_answer):
        with self.assertRaises(api_handler.APIConfigurationError):
            api_handler.answer_query(
                "Show me the roster",
                {"snippets": [], "navigation": {}},
            )

        local_answer.assert_not_called()

    @patch.dict(
        "os.environ",
        {
            "API_KEY": "test-key",
            "OLLAMA_BASE_URL": "http://localhost:11434/v1",
            "OLLAMA_MODEL": "phi3",
        },
        clear=True,
    )
    @patch("api_handler.OpenAI")
    def test_local_fallback_uses_configured_ollama_endpoint(self, openai_client):
        result_message = type(
            "Message",
            (),
            {"content": '{"reply":"Offline answer.","redirect":null}'},
        )
        choice = type("Choice", (), {"message": result_message})
        response = type("Response", (), {"choices": [choice]})
        client = openai_client.return_value
        client.chat.completions.create.return_value = response

        result = api_handler._local_answer_query(
            "Question?",
            '{"snippets":[],"navigation":{}}',
        )

        self.assertEqual(result["reply"], "Offline answer.")
        openai_client.assert_called_once_with(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
            timeout=60,
            max_retries=0,
        )
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["model"],
            "phi3",
        )

    @patch.dict("os.environ", {"API_KEY": "test-key"}, clear=True)
    @patch(
        "api_handler._local_answer_query",
        side_effect=api_handler.APIRequestError("Ollama is offline."),
    )
    @patch("api_handler._request_answer")
    @patch("api_handler._client", return_value=(object(), "gemini-test"))
    def test_reports_cloud_and_local_errors_if_both_providers_fail(
        self,
        get_client,
        request_answer,
        local_answer,
    ):
        quota_error = OpenAIError("Insufficient quota.")
        quota_error.body = {
            "error": {
                "code": "insufficient_quota",
                "message": "Insufficient quota.",
            }
        }
        request_answer.side_effect = quota_error
        with self.assertRaisesRegex(
            api_handler.APIRequestError,
            "Cloud quota exhausted .* local fallback failed: Ollama is offline",
        ):
            api_handler.answer_query(
                "Question?",
                {"snippets": [], "navigation": {}},
            )


if __name__ == "__main__":
    unittest.main()
