import json
import unittest
from unittest.mock import patch

import api_handler
import context_builder


class APIHandlerTests(unittest.TestCase):
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
    @patch("api_handler.OpenAI")
    def test_answer_query_sends_context_and_uses_configured_client(self, client_type):
        message = type("Message", (), {"content": '{"reply":"Kaige has high Ki blast stats.","redirect":null}'})
        choice = type("Choice", (), {"message": message})
        response = type("Response", (), {"choices": [choice]})
        client = client_type.return_value
        client.chat.completions.create.return_value = response
        context = {
            "snippets": [{"source": "dossier.html", "text": "KI BLAST: 98 / 100"}],
            "navigation": context_builder.build_context("stats")["navigation"],
        }

        result = api_handler.answer_query("What is Kaige's Ki blast stat?", context)

        self.assertEqual(
            result,
            {"reply": "Kaige has high Ki blast stats.", "redirect": None},
        )
        client_type.assert_called_once()
        self.assertIn(
            "KI BLAST: 98 / 100",
            client.chat.completions.create.call_args.kwargs["messages"][1]["content"],
        )

    @patch.dict("os.environ", {}, clear=True)
    def test_answer_query_requires_api_key(self):
        with self.assertRaises(api_handler.APIConfigurationError):
            api_handler.answer_query("What is on the site?", {"snippets": [], "navigation": {}})


if __name__ == "__main__":
    unittest.main()
