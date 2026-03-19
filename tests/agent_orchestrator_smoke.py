from pprint import pprint
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm.agent_orchestrator import answer_question


if __name__ == "__main__":
    result = answer_question(
        user_query="Was I more fatigued in the last 2 weeks?",
        tool_params={
            "get_fatigue_snapshot": {"date_start": "2026-01-01", "date_end": "2026-01-31"},
            "get_recovery_trend": {"date_start": "2026-01-01", "date_end": "2026-01-31"},
        },
        call_llm=False,
    )

    pprint({
        "selected_tools": result["selected_tools"],
        "tool_names": [t["tool_name"] for t in result["tool_outputs"]],
        "quality_flags": [t["quality_flags"] for t in result["tool_outputs"]],
    })
