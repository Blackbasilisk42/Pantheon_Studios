import tempfile
import unittest
from pathlib import Path

from modules.site_health import inspect_site


class SiteHealthTests(unittest.TestCase):
    def test_reports_missing_local_references_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "about.html").write_text(
                "<html><body>About</body></html>",
                encoding="utf-8",
            )
            (root / "index.html").write_text(
                '<a href="about.html">About</a>'
                '<img src="/missing.png">'
                '<a href="https://example.com">External</a>',
                encoding="utf-8",
            )

            report = inspect_site(root)

            self.assertEqual(report["status"], "issues_found")
            self.assertEqual(report["checked_files"], 2)
            self.assertEqual(
                report["missing_references"],
                [{"file": "index.html", "reference": "/missing.png"}],
            )


if __name__ == "__main__":
    unittest.main()
