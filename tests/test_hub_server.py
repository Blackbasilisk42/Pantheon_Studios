import os
import threading
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
        self.assertEqual(self.client.get("/backups/latest.html").status_code, 404)
        response = self.client.get("/command-center.html")
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_assistant_assets_are_loaded_on_site_pages(self):
        for page in (
            "command-center.html",
            "index.html",
            "dossier.html",
            "builder.html",
            "dossier-builder.html",
        ):
            with self.subTest(page=page):
                response = self.client.get(f"/{page}")
                self.assertEqual(response.status_code, 200)
                self.assertIn(b"webmaster-assistant.js", response.data)
                self.assertIn(b"webmaster-assistant.css", response.data)
                response.close()

        for asset in (
            "/js/webmaster-assistant.js",
            "/css/webmaster-assistant.css",
        ):
            response = self.client.get(asset)
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_execute_endpoint_routes_character_requests(self):
        dossier = hub_server.ROOT / "staged_updates" / "kaige_dossier.html"
        receipt = hub_server.ROOT / "staged_updates" / "kaige_receipt.txt"
        with patch(
            "hub_server.ai_webmaster.generate_character_dossier",
            return_value=(dossier, receipt),
        ) as generate:
            response = self.client.post(
                "/api/execute",
                json={"command": "Update Kaige's stats"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {
                "action": "generate_character_dossier",
                "result": [
                    "staged_updates/kaige_dossier.html",
                    "staged_updates/kaige_receipt.txt",
                ],
            },
        )
        generate.assert_called_once()

    def test_exact_news_command_bypasses_context_and_cloud_api(self):
        bulletin = hub_server.ROOT / "staged_updates" / "news_bulletin.html"
        receipt = hub_server.ROOT / "staged_updates" / "crawler_receipt.txt"
        with (
            patch(
                "hub_server.ai_webmaster.run_news_crawler",
                return_value=(bulletin, receipt),
            ) as run_news,
            patch("hub_server.context_builder.build_context") as build_context,
            patch("hub_server.api_handler.answer_query") as answer_query,
        ):
            response = self.client.post(
                "/api/execute",
                json={"command": "NEWS UPDATE"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["action"], "run_news_crawler")
        run_news.assert_called_once()
        build_context.assert_not_called()
        answer_query.assert_not_called()

    def test_open_ended_question_returns_reply_and_navigation_event(self):
        context = {"snippets": [], "navigation": {}}
        answer = {
            "reply": "The character builder is available.",
            "redirect": "builder.html#hero-builder-form",
        }
        with (
            patch(
                "hub_server.context_builder.build_context",
                return_value=context,
            ) as build_context,
            patch(
                "hub_server.api_handler.answer_query",
                return_value=answer,
            ) as answer_query,
        ):
            response = self.client.post(
                "/api/execute",
                json={"command": "Where can I build a character?"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["message"],
            "The character builder is available.",
        )
        self.assertEqual(
            response.get_json()["navigation"],
            {
                "type": "navigate",
                "target": "builder.html#hero-builder-form",
            },
        )
        build_context.assert_called_once_with(
            "Where can I build a character?",
            hub_server.ROOT,
        )
        answer_query.assert_called_once_with(
            "Where can I build a character?",
            context,
        )

    def test_navigation_request_is_sent_to_context_api(self):
        with (
            patch(
                "hub_server.context_builder.build_context",
                return_value={"snippets": [], "navigation": {}},
            ) as build_context,
            patch(
                "hub_server.api_handler.answer_query",
                return_value={"reply": "Opening the hub.", "redirect": None},
            ) as answer_query,
        ):
            response = self.client.post(
                "/api/execute",
                json={"command": "Go to the hub"},
            )

        self.assertEqual(response.status_code, 200)
        build_context.assert_called_once()
        answer_query.assert_called_once()

    def test_execute_endpoint_routes_health_requests(self):
        with patch(
            "hub_server.site_health.inspect_site",
            return_value={
                "status": "healthy",
                "checked_files": 1,
                "missing_references": [],
            },
        ):
            response = self.client.post(
                "/api/execute",
                json={"command": "Check for broken elements"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["action"],
            "site_health_check",
        )

    def test_execute_endpoint_routes_official_source_staging(self):
        html_path = hub_server.ROOT / "staged_updates" / "update.html"
        receipt_path = hub_server.ROOT / "staged_updates" / "update.txt"
        with (
            patch(
                "hub_server.webmaster.scrape_source",
                return_value=(
                    "https://dbxv2.bn-ent.net/update/",
                    "Patch notes\nBalance changes",
                ),
            ) as scrape,
            patch(
                "hub_server.webmaster.generate_update",
                return_value={
                    "title": "Patch notes",
                    "summary": "Balance changes",
                },
            ) as format_update,
            patch(
                "hub_server.webmaster.stage_update",
                return_value=(html_path, receipt_path),
            ) as stage,
        ):
            response = self.client.post(
                "/api/execute",
                json={"command": "Stage official source update"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["action"],
            "stage_official_update",
        )
        scrape.assert_called_once()
        format_update.assert_called_once_with("Patch notes\nBalance changes")
        stage.assert_called_once_with(
            "https://dbxv2.bn-ent.net/update/",
            {"title": "Patch notes", "summary": "Balance changes"},
        )

    def test_execute_endpoint_rejects_invalid_and_unrecognized_requests(self):
        missing_command = self.client.post("/api/execute", json={})
        unsupported = self.client.post(
            "/api/execute",
            json={"command": "run arbitrary Python"},
        )

        self.assertEqual(missing_command.status_code, 400)
        self.assertEqual(unsupported.status_code, 400)
        self.assertEqual(unsupported.mimetype, "application/json")
        self.assertEqual(
            unsupported.get_json(),
            {
                "error": (
                    "Command is not supported. Use a maintenance command or "
                    "ask a site question."
                )
            },
        )

    def test_greeting_returns_local_result_without_calling_answer_provider(self):
        with patch("hub_server.api_handler.answer_query") as answer_query:
            response = self.client.post(
                "/api/execute",
                json={"command": "hello"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(response.get_json()["action"], "greeting")
        self.assertIn("Hello!", response.get_json()["message"])
        answer_query.assert_not_called()

    def test_execute_endpoint_returns_json_for_unexpected_backend_errors(self):
        with patch(
            "hub_server._dispatch_command",
            side_effect=TypeError("unexpected backend failure"),
        ):
            response = self.client.post(
                "/api/execute",
                json={"command": "Check for broken elements"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(
            response.get_json(),
            {"error": "Webmaster command failed."},
        )

    def test_execute_endpoint_returns_json_for_result_serialization_errors(self):
        with patch(
            "hub_server._dispatch_command",
            return_value=("test_action", object()),
        ):
            response = self.client.post(
                "/api/execute",
                json={"command": "Check for broken elements"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(
            response.get_json(),
            {"error": "Webmaster command failed."},
        )

    def test_scheduler_runs_background_jobs_and_stays_active(self):
        dossier_ran = threading.Event()
        news_ran = threading.Event()
        with (
            patch(
                "hub_server.ai_webmaster.generate_character_dossier",
                side_effect=dossier_ran.set,
            ),
            patch(
                "hub_server.ai_webmaster.run_news_crawler",
                side_effect=news_ran.set,
            ),
        ):
            hub_server.start_scheduler()
            try:
                self.assertTrue(dossier_ran.wait(timeout=1))
                self.assertTrue(news_ran.wait(timeout=1))
                self.assertTrue(hub_server._scheduler_thread.is_alive())
                self.assertEqual(len(hub_server.webmaster_scheduler.jobs), 2)
            finally:
                hub_server.stop_scheduler()


if __name__ == "__main__":
    unittest.main()
