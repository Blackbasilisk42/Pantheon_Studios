import os
import unittest
from unittest.mock import patch

import hub_server


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class HubServerTests(unittest.TestCase):
    def setUp(self):
        self.client = hub_server.app.test_client()

    @patch.dict(os.environ, {}, clear=True)
    def test_metrics_without_credentials_are_null_values(self):
        response = self.client.get("/api/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "youtube_subscribers": None,
                "discord_online": None,
                "meta_followers": None,
            },
        )

    @patch.dict(
        os.environ,
        {
            "YOUTUBE_API_KEY": "test-youtube-secret",
            "YOUTUBE_CHANNEL_ID": "channel-id",
            "DISCORD_BOT_TOKEN": "test-discord-secret",
            "DISCORD_GUILD_ID": "guild-id",
            "META_ACCESS_TOKEN": "test-meta-secret",
            "META_PAGE_ID": "page-id",
        },
        clear=True,
    )
    @patch("hub_server.requests.get")
    def test_metrics_return_only_sanitized_numeric_fields(self, request_get):
        def response_for_provider(url, **kwargs):
            if "googleapis" in url:
                return FakeResponse(
                    {"items": [{"statistics": {"subscriberCount": "123"}}]}
                )
            if "discord.com" in url:
                return FakeResponse({"approximate_presence_count": 7})
            return FakeResponse({"followers_count": 45, "id": "page-id"})

        request_get.side_effect = response_for_provider
        response = self.client.get("/api/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "youtube_subscribers": 123,
                "discord_online": 7,
                "meta_followers": 45,
            },
        )
        self.assertNotIn(b"test-", response.data)
        calls_by_host = {
            call.args[0].split("/")[2]: call.kwargs
            for call in request_get.call_args_list
        }
        self.assertEqual(
            calls_by_host["discord.com"]["headers"]["Authorization"],
            "Bot test-discord-secret",
        )
        self.assertEqual(
            calls_by_host["graph.facebook.com"]["headers"]["Authorization"],
            "Bearer test-meta-secret",
        )
        self.assertEqual(
            calls_by_host["www.googleapis.com"]["params"]["key"],
            "test-youtube-secret",
        )

    def test_static_server_does_not_expose_private_files(self):
        self.assertEqual(self.client.get("/.env").status_code, 404)
        self.assertEqual(self.client.get("/hub_server.py").status_code, 404)
        response = self.client.get("/command-center.html")
        self.assertEqual(response.status_code, 200)
        response.close()


if __name__ == "__main__":
    unittest.main()
