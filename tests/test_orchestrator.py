import unittest

from modules.orchestrator import OrchestratorEngine


class OrchestratorEngineTests(unittest.TestCase):
    def test_context_is_ready_when_lore_is_comprehensive(self) -> None:
        engine = OrchestratorEngine()
        entries = [
            {"title": "First lore", "content": "The city of Aster spans rivers and ancient gates. Its people fear the moonlit eclipse and guard the sacred archive."},
            {"title": "Second lore", "content": "A faction called the Lantern Keepers preserves relics and bargains with spirits beneath the ruined bridge."},
            {"title": "Third lore", "content": "Characters carry weathered journals, each explaining a different truth about the red star that watches the capital."},
        ]

        decision = engine.evaluate_context(entries)

        self.assertTrue(decision["ready"])
        self.assertGreaterEqual(decision["score"], 70)


if __name__ == "__main__":
    unittest.main()
