from __future__ import annotations

from pprint import pprint
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm.agent_orchestrator import answer_question


EVAL_CASES = [
    {
        "id": "E-001",
        "user_query": "How did my bench press progress over the last month?",
        "tool_params": {
            "compare_strength_windows": {
                "exercise": "Bench Press (Barbell)",
                "date_start": "2025-12-01",
                "date_end": "2026-01-15",
            }
        },
        "expect_tools": ["compare_strength_windows"],
    },
    {
        "id": "E-002",
        "user_query": "Was I more fatigued in the last 2 weeks?",
        "tool_params": {
            "get_fatigue_snapshot": {
                "date_start": "2026-01-01",
                "date_end": "2026-01-31",
            },
            "get_recovery_trend": {
                "date_start": "2026-01-01",
                "date_end": "2026-01-31",
            },
        },
        "expect_tools": ["get_fatigue_snapshot", "get_recovery_trend"],
    },
    {
        "id": "E-003",
        "user_query": "How was my training last week?",
        "tool_params": {
            "get_weekly_training_summary": {
                "date_start": "2026-01-19",
                "date_end": "2026-01-25",
            }
        },
        "expect_tools": ["get_weekly_training_summary"],
    },
]


def main() -> None:
    for case in EVAL_CASES:
        result = answer_question(
            user_query=case["user_query"],
            tool_params=case["tool_params"],
            call_llm=False,
        )
        pprint(
            {
                "id": case["id"],
                "selected_tools": result["selected_tools"],
                "expected_tools": case["expect_tools"],
                "confidence": [x["confidence"] for x in result["tool_outputs"]],
                "quality_flags": [x["quality_flags"] for x in result["tool_outputs"]],
            }
        )


if __name__ == "__main__":
    main()
