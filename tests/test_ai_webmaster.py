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

    def test_dossier_generation_reads_html_and_stages_fixed_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "dossier.html"
            reference.write_text(
                "<style>.spec-box { display: grid; }"
                ".lore-box { color: gold; }</style>"
                "<script>display.innerHTML = `"
                '<div class="spec-box">COMBAT METRICS &amp; SPECS</div>'
                '<div class="lore-box"><div class="lore-title">'
                "TACTICAL DOSSIER &amp; LORE NOTES</div></div>`;</script>"
                "<p>private unrelated content</p>",
                encoding="utf-8",
            )
            staged = root / "staged_updates"
            with (
                patch.object(ai_webmaster, "ROOT", root),
                patch.object(ai_webmaster, "DOSSIER_REFERENCE_FILE", reference),
                patch.object(ai_webmaster, "STAGED_DIRECTORY", staged),
                patch.object(
                    ai_webmaster,
                    "_ollama_generate",
                    return_value="```html\n"
                    + (
                        '<article class="bento-card"><h2>Kaige</h2>'
                        "<p>Kaige dossier</p><script>bad()</script></article>"
                    )
                    + "\n```",
                ) as generate,
            ):
                html_path, receipt_path = ai_webmaster.generate_character_dossier()

            self.assertEqual(html_path.name, "kaige_dossier.html")
            self.assertEqual(receipt_path.name, "kaige_receipt.txt")
            self.assertTrue(receipt_path.is_file())
            dossier_reference, system_prompt = generate.call_args.args
            self.assertIn("COMBAT METRICS", dossier_reference)
            self.assertIn("TACTICAL DOSSIER", dossier_reference)
            self.assertIn(".spec-box", dossier_reference)
            self.assertNotIn("private unrelated content", dossier_reference)
            self.assertIn("Name: KAIGE", system_prompt)
            self.assertIn("Frieza-Race // Elite Patroller", system_prompt)
            self.assertIn("Health 85/100", system_prompt)
            self.assertIn("Ki Blast Super 98/100", system_prompt)
            self.assertIn("Center of Gravity (COG)", system_prompt)
            self.assertIn("dossier.html", system_prompt)
            self.assertIn("`.bento-card`", system_prompt)
            generated_html = html_path.read_text(encoding="utf-8")
            self.assertIn('class="bento-card"', generated_html)
            self.assertIn("Kaige dossier", generated_html)
            self.assertNotIn("<script>", generated_html)
            self.assertNotIn("```", generated_html)
            self.assertIn("Generated at (UTC):", receipt_path.read_text(encoding="utf-8"))

    def test_news_crawler_stages_text_only_bulletin_and_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "staged_updates"
            pages = [
                ("https://dbxv2.bn-ent.net/update/", "Official update text")
            ]
            with (
                patch.object(ai_webmaster, "ROOT", root),
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
