import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

import ai_webmaster


class AIWebmasterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.staged = self.root / "staged_updates"
        self.dossier = self.root / "dossier.html"
        self.dossier.write_text(
            (ai_webmaster.ROOT / "dossier.html").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        self.patches = (
            patch.object(ai_webmaster, "ROOT", self.root),
            patch.object(ai_webmaster, "DOSSIER_FILE", self.dossier),
            patch.object(ai_webmaster, "STAGED_DIRECTORY", self.staged),
            patch.object(
                ai_webmaster, "DOSSIER_OUTPUT", self.staged / "kaige_dossier.html"
            ),
            patch.object(
                ai_webmaster, "DOSSIER_RECEIPT", self.staged / "kaige_receipt.txt"
            ),
            patch.object(
                ai_webmaster, "NEWS_OUTPUT", self.staged / "news_bulletin.html"
            ),
            patch.object(
                ai_webmaster, "NEWS_RECEIPT", self.staged / "crawler_receipt.txt"
            ),
        )
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self):
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temporary.cleanup()

    def test_dossier_clones_reference_structure_and_injects_payload(self):
        html_path, receipt_path = ai_webmaster.generate_character_dossier()
        output = html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(output, "html.parser")

        card = soup.select_one(".bento-card.dossier-main-panel")
        self.assertIsNotNone(card)
        self.assertIsNone(card.get("id"))
        self.assertEqual(card.select_one(".hero-title-group h1").get_text(), "KAIGE")
        self.assertEqual(
            card.select_one(".spec-tag").get_text(),
            "Frieza-Race // Elite Patroller",
        )
        self.assertEqual(
            card.select_one(".power-rank-value").get_text(),
            "LEVEL 199 MAX",
        )
        metric_values = {
            row.select_one(".stat-name").get_text(strip=True):
            row.select_one(".stat-val-num").get_text(strip=True)
            for row in card.select(".stat-line")
        }
        self.assertEqual(metric_values, ai_webmaster.KAIGE["metrics"])
        self.assertEqual(
            [chip.get_text() for chip in card.select(".skill-chip")],
            ["KI BLAST SPECIALIST", "SHADOW CRUSHER", "BACKFLIP"],
        )
        lore_text = card.select_one(".lore-box").get_text(" ", strip=True)
        for lore in ai_webmaster.KAIGE["lore"].values():
            self.assertIn(lore, lore_text)
        self.assertIn(".dossier-header-grid", soup.style.get_text())
        receipt = receipt_path.read_text(encoding="utf-8")
        self.assertIn("cloned dossier.html template", receipt)
        self.assertIn('"name": "KAIGE"', receipt)
        self.assertNotIn("ollama", output.lower())

    def test_dossier_uses_native_fallback_when_reference_missing(self):
        self.dossier.unlink()

        html_path, receipt_path = ai_webmaster.generate_character_dossier()

        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        self.assertIsNotNone(soup.select_one(".bento-card"))
        self.assertIn("LEVEL 199 MAX", soup.get_text(" ", strip=True))
        self.assertIn("fallback template", receipt_path.read_text(encoding="utf-8"))

    def test_news_crawler_writes_structured_bulletin_and_appends_receipt(self):
        pages = [
            (
                "https://dbxv2.bn-ent.net/update/",
                "Maintenance Update",
                "Server maintenance begins Friday.",
            )
        ]
        with patch.object(ai_webmaster, "_scrape_update_sources", return_value=pages):
            result = ai_webmaster.run_news_crawler()

        self.assertIsNotNone(result)
        html_path, receipt_path = result
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        self.assertIsNotNone(soup.select_one(".bento-card.news-card"))
        self.assertEqual(
            soup.select_one(".card-header").get_text(),
            "Maintenance Update",
        )
        self.assertIn(
            "Server maintenance begins Friday.",
            soup.select_one(".metrics-section").get_text(),
        )
        self.assertIn(
            "https://dbxv2.bn-ent.net/update/",
            soup.select_one(".lore-section").get_text(),
        )
        self.assertIn("news_bulletin.html", receipt_path.read_text(encoding="utf-8"))
        with patch.object(ai_webmaster, "_scrape_update_sources", return_value=pages):
            ai_webmaster.run_news_crawler()
        self.assertEqual(
            receipt_path.read_text(encoding="utf-8").count("Timestamp (UTC):"),
            2,
        )

    def test_news_crawler_logs_network_failure_without_raising(self):
        with patch.object(
            ai_webmaster,
            "_scrape_update_sources",
            side_effect=OSError("connection unavailable"),
        ):
            self.assertIsNone(ai_webmaster.run_news_crawler())


if __name__ == "__main__":
    unittest.main()
