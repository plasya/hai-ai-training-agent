from __future__ import annotations

from pprint import pprint

from app.llm.prompt_builder import build_llm_prompt


def build_tool_output(
    tool_name: str,
    start: str,
    end: str,
    payload: dict,
    confidence: str,
    quality_flags: list[str],
    data_quality: dict,
) -> dict:
    return {
        "tool_name": tool_name,
        "window": {"start": start, "end": end},
        "payload": payload,
        "data_quality": data_quality,
        "quality_flags": quality_flags,
        "confidence": confidence,
    }


COMMON_LOW_COVERAGE = {
    "hrv_coverage": 0.34,
    "resting_hr_coverage": 0.07,
    "sleep_coverage": 0.0,
    "trimp_coverage": 0.52,
}

COMMON_GOOD_COVERAGE = {
    "hrv_coverage": 0.82,
    "resting_hr_coverage": 0.88,
    "sleep_coverage": 0.79,
    "trimp_coverage": 0.93,
}

EXAMPLES = [
    {
        "name": "bench_progress",
        "user_query": "How did my bench press improve from December 1, 2025 to January 15, 2026?",
        "selected_tools": ["compare_strength_windows"],
        "tool_outputs": [
            build_tool_output(
                tool_name="compare_strength_windows",
                start="2025-12-01",
                end="2026-01-15",
                payload={
                    "current": {
                        "volume": 19435.0,
                        "sets": 30,
                        "best_1rm": 114.0,
                        "prs": 2,
                    },
                    "previous": {
                        "volume": 7270.0,
                        "sets": 16,
                        "best_1rm": 97.5,
                        "prs": 1,
                    },
                    "trend": "improving",
                },
                confidence="medium",
                quality_flags=["low_hrv_coverage", "low_resting_hr_coverage", "low_sleep_coverage"],
                data_quality=COMMON_LOW_COVERAGE,
            )
        ],
    },
    {
        "name": "fatigue_last_2_weeks",
        "user_query": "Was I more fatigued in the last 2 weeks?",
        "selected_tools": ["get_fatigue_snapshot", "get_recovery_trend"],
        "tool_outputs": [
            build_tool_output(
                tool_name="get_fatigue_snapshot",
                start="2026-01-01",
                end="2026-01-31",
                payload={
                    "date": "2026-01-29",
                    "acute_7d": 229.81,
                    "chronic_28d_avg": 59.31,
                    "acwr": 0.55,
                    "fatigue_risk": "low",
                    "supporting": {
                        "rhr_delta": None,
                        "hrv_delta": None,
                        "sleep_delta": None,
                    },
                },
                confidence="low",
                quality_flags=["low_hrv_coverage", "low_resting_hr_coverage", "missing_sleep"],
                data_quality=COMMON_LOW_COVERAGE,
            ),
            build_tool_output(
                tool_name="get_recovery_trend",
                start="2026-01-01",
                end="2026-01-31",
                payload={
                    "resting_hr_trend": "up",
                    "hrv_trend": "up",
                    "sleep_trend": "flat",
                    "consistency_score": 0.14,
                },
                confidence="low",
                quality_flags=["low_hrv_coverage", "low_resting_hr_coverage", "missing_sleep"],
                data_quality=COMMON_LOW_COVERAGE,
            ),
        ],
    },
    {
        "name": "weekly_summary",
        "user_query": "How was my training last week?",
        "selected_tools": ["get_weekly_training_summary"],
        "tool_outputs": [
            build_tool_output(
                tool_name="get_weekly_training_summary",
                start="2026-01-19",
                end="2026-01-25",
                payload={
                    "weeks": [
                        {
                            "week_start": "2026-01-19",
                            "weekly_strength_volume": 23130.0,
                            "weekly_prs": 2,
                            "weekly_hrv": 58.4,
                            "weekly_rhr": 69.5,
                            "weekly_trimp": 170.1,
                            "weekly_acwr": 0.88,
                            "fatigue_days": 0,
                            "strength_readiness": 1.11,
                        }
                    ],
                    "summary": {
                        "weeks": 1,
                        "weekly_strength_volume_total": 23130.0,
                        "weekly_prs_total": 2,
                        "weekly_trimp_total": 170.1,
                    },
                },
                confidence="high",
                quality_flags=[],
                data_quality=COMMON_GOOD_COVERAGE,
            )
        ],
    },
    {
        "name": "metric_explanation_seed",
        "user_query": "What does HRV SDNN mean here?",
        "selected_tools": [],
        "tool_outputs": [],
    },
]

example = EXAMPLES[0]
prompt = build_llm_prompt(
    example["user_query"],
    {
        "selected_tools": example["selected_tools"],
        "tool_outputs": example["tool_outputs"],
    },
)

pprint(example)
pprint(prompt)
