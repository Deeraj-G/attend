import unittest

from backend.app.agents.transcription import transcription_contract
from backend.app.agents.web_search import research_contract


class StandInContractTests(unittest.TestCase):
    """The routes build these directly until the Manager emits them; they must still validate."""

    def test_subtasks_match_manager_keys(self):
        self.assertEqual(transcription_contract().subtask, "transcribe")
        self.assertEqual(research_contract().subtask, "research")


if __name__ == "__main__":
    unittest.main()
