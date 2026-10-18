import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import webmaster


class WebmasterTests(unittest.TestCase):
    def test_source_must_be_the_official_https_host(self):
        self.assertEqual(
            webmaster.validate_source_url(webmaster.DEFAULT_SOURCE_URL),
            webmaster.DEFAULT_SOURCE_URL,
        )
        with self.assertRaises(ValueError):
            webmaster.validate_source_url("http://dbxv2.bn-ent.net/")
        with self.assertRaises(ValueError):
            webmaster.validate_source_url("https://example.com/")
        with self.assertRaises(ValueError):
            webmaster.validate_source_url(
                "https://dbxv2.bn-ent.net/?access_token=not-allowed"
            )

    @patch("webmaster.requests.get")
    def test_scraper_extracts_text_from_the_allowlisted_source(self, request_get):
        response = Mock()
        response.text = (
            "<html><body><main><h1>Update</h1>"
            "<p>Official patch notes</p></main></body></html>"
        )
        request_get.return_value = response

        source_url, text = webmaster.scrape_source(webmaster.DEFAULT_SOURCE_URL)

        self.assertEqual(source_url, webmaster.DEFAULT_SOURCE_URL)
        self.assertIn("Official patch notes", text)
        self.assertFalse(request_get.call_args.kwargs["allow_redirects"])

    @patch("webmaster.requests.get")
    def test_scraper_follows_official_update_links(self, request_get):
        landing_page = Mock()
        landing_page.text = (
            '<a href="/update/patch-notes.html">Update notes</a>'
        )
        update_page = Mock()
        update_page.text = "<main><h1>Patch notes</h1><p>Balance changes</p></main>"
        request_get.side_effect = [landing_page, update_page]

        source_url, text = webmaster.scrape_source(webmaster.DEFAULT_SOURCE_URL)

        self.assertEqual(
            source_url,
            "https://dbxv2.bn-ent.net/update/patch-notes.html",
        )
        self.assertIn("Balance changes", text)
        self.assertEqual(request_get.call_count, 2)

    def test_update_formatter_uses_source_text_without_inventing_content(self):
        update = webmaster.generate_update(
            "Official Patch Notes\nBalance changes\nServer maintenance"
        )
        self.assertEqual(
            update,
            {
                "title": "Official Patch Notes",
                "summary": "Balance changes Server maintenance",
            },
        )

    def test_generated_html_escapes_source_content(self):
        block = webmaster.render_html_block(
            {
                "title": '<script>alert("x")</script>',
                "summary": "Update summary",
            }
        )

        self.assertNotIn("<script>", block)
        self.assertIn("&lt;script&gt;", block)

    def test_stage_writes_html_and_receipt_without_touching_live_index(self):
        index_path = webmaster.ROOT / "index.html"
        original_index = index_path.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            with (
                patch.object(webmaster, "ROOT", temporary_root),
                patch.object(
                    webmaster,
                    "STAGED_DIRECTORY",
                    temporary_root / "staged_updates",
                ),
            ):
                html_path, receipt_path = webmaster.stage_update(
                    webmaster.DEFAULT_SOURCE_URL,
                    {"title": "Patch Update", "summary": "Summary"},
                )

            self.assertTrue(html_path.is_file())
            self.assertTrue(receipt_path.is_file())
            receipt = receipt_path.read_text(encoding="utf-8")
            self.assertIn(webmaster.DEFAULT_SOURCE_URL, receipt)
            self.assertIn("formatted deterministically", receipt)
            self.assertIn(html_path.name, receipt)
            self.assertIn(receipt_path.name, receipt)
            self.assertIn("not added to index.html", receipt)
        self.assertEqual(index_path.read_bytes(), original_index)


if __name__ == "__main__":
    unittest.main()
