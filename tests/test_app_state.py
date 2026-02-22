import tempfile
import unittest
from pathlib import Path

from app_state import AppState, load_state, save_state


class AppStateTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            state = AppState(qa_draft="hello", selected_tab="qa", docs_page=3, onboarding_dismissed=True)
            save_state(path, state)

            loaded = load_state(path)

            self.assertEqual(loaded.qa_draft, "hello")
            self.assertEqual(loaded.selected_tab, "qa")
            self.assertEqual(loaded.docs_page, 3)
            self.assertTrue(loaded.onboarding_dismissed)


if __name__ == "__main__":
    unittest.main()
