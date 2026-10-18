import json
import tempfile
import unittest
from pathlib import Path

from modules import edit_safety


class EditSafetyTests(unittest.TestCase):
    def test_write_snapshots_existing_file_and_records_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "dossier.html"
            target.write_text("before", encoding="utf-8")

            edit_safety.write_text(
                target,
                "after",
                "update dossier",
                root,
            )

            events = [
                json.loads(line)
                for line in (root / edit_safety.EDIT_LOG_NAME)
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["action"], "update dossier")
            self.assertEqual(events[0]["target"], "dossier.html")
            self.assertTrue(events[0]["timestamp"])
            backup = root / events[0]["backup"]
            self.assertEqual(backup.read_text(encoding="utf-8"), "before")
            self.assertEqual(target.read_text(encoding="utf-8"), "after")

    def test_rollback_restores_previous_content_and_is_audited(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "builder.html"
            target.write_text("known good", encoding="utf-8")
            edit_safety.write_text(target, "changed", "site edit", root)

            restored = edit_safety.rollback_latest(root)

            self.assertEqual(restored, target)
            self.assertEqual(target.read_text(encoding="utf-8"), "known good")
            events = [
                json.loads(line)
                for line in (root / edit_safety.EDIT_LOG_NAME)
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(events[-1]["action"], "rollback builder.html")

    def test_rollback_removes_a_file_created_by_the_latest_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "news.html"
            edit_safety.write_text(target, "new content", "create news", root)

            edit_safety.rollback_latest(root)

            self.assertFalse(target.exists())
            events = [
                json.loads(line)
                for line in (root / edit_safety.EDIT_LOG_NAME)
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual(events[-1]["action"], "rollback news.html")

    def test_write_rejects_targets_outside_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / "outside.html"

            with self.assertRaises(ValueError):
                edit_safety.write_text(outside, "content", "invalid", root)


if __name__ == "__main__":
    unittest.main()
