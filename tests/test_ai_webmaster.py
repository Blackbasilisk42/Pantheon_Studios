import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_webmaster


class AIWebmasterTests(unittest.TestCase):
    def test_bento_card_escapes_model_output(self):
        card = ai_webmaster._render_bento_card(
            "<Kaige>", '<img src="bad">', "dossier-content"
        )

        self.assertIn('class="bento-card"', card)
        self.assertIn("&lt;Kaige&gt;", card)
        self.assertIn("&lt;img", card)
        self.assertNotIn("<img", card)

    def test_dossier_generation_reads_reference_and_stages_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "aj_profile_reference.txt"
            reference.write_text("Reference layout", encoding="utf-8")
            staged = root / "staged_updates"
            with (
                patch.object(ai_webmaster, "REFERENCE_FILE", reference),
                patch.object(ai_webmaster, "STAGED_DIRECTORY", staged),
                patch.object(
                    ai_webmaster,
                    "_ollama_generate",
                    return_value="Kaige dossier",
                ) as generate,
            ):
                html_path, receipt_path = ai_webmaster.generate_character_dossier()

            self.assertEqual(html_path.name, "kaige_dossier.html")
            self.assertTrue(receipt_path.is_file())
            self.assertIn(
                "Reference layout", generate.call_args.args[0]
            )
            self.assertIn("Level 199 Elite Patroller", generate.call_args.args[1])
            self.assertIn("Kaige dossier", html_path.read_text(encoding="utf-8"))

    def test_news_crawler_stages_text_only_bulletin_and_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            staged = Path(temporary)
            pages = [
                ("https://dbxv2.bn-ent.net/update/", "Official update text")
            ]
            with (
                patch.object(ai_webmaster, "STAGED_DIRECTORY", staged),
                patch.object(
                    ai_webmaster, "_scrape_update_sources", return_value=pages
                ),
                patch.object(
                    ai_webmaster, "_ollama_generate", return_value="<img>"
                ) as generate,
            ):
                result = ai_webmaster.run_news_crawler()

            self.assertIsNotNone(result)
            html_path, receipt_path = result
            content = html_path.read_text(encoding="utf-8")
            receipt = receipt_path.read_text(encoding="utf-8")
            self.assertNotIn("<img", content)
            self.assertIn("Official update text", generate.call_args.args[0])
            self.assertIn("dbxv2.bn-ent.net/update/", receipt)
            self.assertIn(html_path.name, receipt)
            self.assertIn(receipt_path.name, receipt)


if __name__ == "__main__":
    unittest.main()
