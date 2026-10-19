import tempfile
import unittest
from pathlib import Path

import context_builder


class ContextBuilderTests(unittest.TestCase):
    def test_build_context_ranks_relevant_local_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "dossier.html").write_text(
                "<main><h1>Kaige</h1>"
                "<p>Ki blast power is 98 / 100.</p>"
                "<p>His tactical lore describes orbital zoning.</p></main>",
                encoding="utf-8",
            )
            (root / "builder.html").write_text(
                "<main><h1>Show Builder</h1>"
                "<p>Configure a character roster.</p></main>",
                encoding="utf-8",
            )
            (root / "backups").mkdir()
            (root / "backups" / "private.md").write_text(
                "Kaige secret archive content",
                encoding="utf-8",
            )

            context = context_builder.build_context("Kaige Ki blast stats", root)

            self.assertEqual(context["snippets"][0]["source"], "dossier.html")
            self.assertIn("98 / 100", context["snippets"][0]["text"])
            self.assertTrue(
                all(
                    snippet["source"] != "backups/private.md"
                    for snippet in context["snippets"]
                )
            )

    def test_navigation_targets_point_to_existing_site_sections(self):
        for entry in context_builder.NAVIGATION_TARGETS.values():
            page, fragment = entry["target"].split("#", maxsplit=1)
            page_text = (context_builder.ROOT / page).read_text(
                encoding="utf-8"
            )
            self.assertIn(f'id="{fragment}"', page_text)


if __name__ == "__main__":
    unittest.main()
