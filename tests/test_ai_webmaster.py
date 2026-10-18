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
                patch.object(ai_webmaster, "ROOT", root),
                patch.object(ai_webmaster, "REFERENCE_FILE", reference),
                patch.object(ai_webmaster, "STAGED_DIRECTORY", staged),
                patch.object(
                    ai_webmaster,
                    "_ollama_generate",
                    return_value=(
                        '<article class="bento-card"><h2>Kaige</h2>'
                        "<p>Kaige dossier</p><script>bad()</script></article>"
                    ),
                ) as generate,
            ):
                html_path, receipt_path = ai_webmaster.generate_character_dossier()

            self.assertEqual(html_path.name, "kaige_dossier.html")
            self.assertTrue(receipt_path.is_file())
            self.assertIn(
                "Reference layout", generate.call_args.args[0]
            )
            self.assertEqual(
                generate.call_args.args[1],
                (
                    "You are an expert lore writer for the Pantheon Studios "
                    "Lega-Z-y project. Analyze the provided reference profile "
                    "(`aj_profile_reference.txt`) for structural layout, "
                    "category headings, and analytical tone. Using that exact "
                    "same framework, write a complete character dossier for "
                    "Kaige.\n\n"
                    "Integrate these specific details into his Tactical Dossier "
                    "and Lore Notes:\n\n"
                    "- Subtitle: Frieza-race // Elite Patroller.\n"
                    "- Visuals: A tall, original solid black body design with "
                    "green eyes (a legacy design predating Black Frieza by 6 "
                    "years) and a dark emerald green aura.\n"
                    "- Combat Style: A pure Ki-blast primary build.\n"
                    "- Key Attributes: He utilizes the 'Center of Gravity' "
                    "(COG) technique, focusing heavily on precise orbital "
                    "positioning relative to locked-on targets.\n"
                    "- Evasive/Counter Tactics: While predominantly a distant "
                    "zoner and Ki-blast specialist, he employs secondary Strike "
                    "counters like Shadow Crusher and Backflip to punish "
                    "opponents who attempt to close the gap, immediately "
                    "repositioning to maintain his spatial advantage.\n"
                    "- Output the final result formatted as clean HTML matching "
                    "the `.bento-card` CSS structure, utilizing the exact same "
                    "metric categories and lore sub-headings as the reference "
                    "file."
                ),
            )
            generated_html = html_path.read_text(encoding="utf-8")
            self.assertIn('class="bento-card"', generated_html)
            self.assertIn("Kaige dossier", generated_html)
            self.assertNotIn("<script>", generated_html)

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
