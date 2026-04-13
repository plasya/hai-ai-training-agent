from __future__ import annotations

from pathlib import Path
import unittest
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm.agent_orchestrator import _followup_tool_params, _infer_window, _routing_query


class FollowupResolutionTests(unittest.TestCase):
    @patch("app.llm.agent_orchestrator._today")
    def test_month_before_that_uses_previous_adjacent_window(self, mock_today) -> None:
        mock_today.return_value = __import__("pandas").Timestamp("2026-04-12")
        history = [
            {"role": "user", "message_text": "How did my bench press progress over the last month?"},
        ]

        routing_query = _routing_query("what about the month before that?", history)
        params = _followup_tool_params("what about the month before that?", history[0]["message_text"])

        self.assertIn("bench press", routing_query.lower())
        self.assertEqual(params["date_start"], "2026-02-10")
        self.assertEqual(params["date_end"], "2026-03-12")

    @patch("app.llm.agent_orchestrator._today")
    def test_week_before_that_uses_previous_adjacent_window(self, mock_today) -> None:
        mock_today.return_value = __import__("pandas").Timestamp("2026-04-12")
        history = [
            {"role": "user", "message_text": "How was my training in the last 2 weeks?"},
        ]

        params = _followup_tool_params("what about the week before that?", history[0]["message_text"])

        self.assertEqual(params["date_start"], "2026-03-16")
        self.assertEqual(params["date_end"], "2026-03-29")

    @patch("app.llm.agent_orchestrator._today")
    def test_mos_alias_is_supported_in_window_inference(self, mock_today) -> None:
        mock_today.return_value = __import__("pandas").Timestamp("2026-04-12")
        start, end = _infer_window("how did my performance affect past 3 mos")

        self.assertEqual(start, "2026-01-13")
        self.assertEqual(end, "2026-04-12")

    @patch("app.llm.agent_orchestrator._today")
    def test_named_month_resolves_to_most_recent_past_occurrence(self, mock_today) -> None:
        mock_today.return_value = __import__("pandas").Timestamp("2026-04-12")
        start, end = _infer_window("november")

        self.assertEqual(start, "2025-11-01")
        self.assertEqual(end, "2025-11-30")

    @patch("app.llm.agent_orchestrator._today")
    def test_between_named_months_uses_second_month_window(self, mock_today) -> None:
        mock_today.return_value = __import__("pandas").Timestamp("2026-04-12")
        start, end = _infer_window("between november and december")

        self.assertEqual(start, "2025-12-01")
        self.assertEqual(end, "2025-12-31")

    @patch("app.llm.agent_orchestrator._today")
    def test_compared_to_before_reuses_previous_window_and_subject(self, mock_today) -> None:
        mock_today.return_value = __import__("pandas").Timestamp("2026-04-12")
        history = [
            {"role": "user", "message_text": "How did my bench press progress over the last month?"},
        ]

        routing_query = _routing_query("compared to before", history)
        params = _followup_tool_params("compared to before", history[0]["message_text"])

        self.assertIn("bench press", routing_query.lower())
        self.assertEqual(params["date_start"], "2026-03-13")
        self.assertEqual(params["date_end"], "2026-04-12")


if __name__ == "__main__":
    unittest.main()
