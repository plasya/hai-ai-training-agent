from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm.agent_orchestrator import _select_tools


class NextWorkoutRoutingTests(unittest.TestCase):
    def test_next_workout_triggers_tool(self) -> None:
        self.assertEqual(_select_tools("what should I train next"), ["suggest_next_workout"])
        self.assertEqual(_select_tools("plan my next workout"), ["suggest_next_workout"])
        self.assertEqual(_select_tools("what workout tomorrow"), ["suggest_next_workout"])


if __name__ == "__main__":
    unittest.main()
