from __future__ import annotations

from typing import Any

from app.llm.prompt_builder import build_llm_prompt
from app.llm.tool_registry import list_tools, run_tool


DEFAULT_TOOLS = [
    "compare_strength_windows",
    "get_weekly_training_summary",
    "get_fatigue_snapshot",
    "get_recovery_trend",
]


def _select_tools(user_query: str) -> list[str]:
    q = user_query.lower()

    if any(k in q for k in ["bench", "squat", "deadlift", "progress", "pr", "1rm", "stronger"]):
        return ["compare_strength_windows"]

    if any(k in q for k in ["fatigue", "overtrain", "tired", "readiness", "burnout"]):
        return ["get_fatigue_snapshot", "get_recovery_trend"]

    if any(k in q for k in ["recovery", "hrv", "sleep", "resting hr", "resting heart"]):
        return ["get_recovery_trend"]

    if any(k in q for k in ["weekly", "last week", "this week", "summary", "overview"]):
        return ["get_weekly_training_summary"]

    return ["get_weekly_training_summary"]


def answer_question(
    user_query: str,
    tool_params: dict[str, dict[str, Any]] | None = None,
    metrics_context: str = "",
    research_context: str = "",
    call_llm: bool = True,
) -> dict[str, Any]:
    selected_tools = _select_tools(user_query)
    params_by_tool = tool_params or {}

    tool_outputs: list[dict[str, Any]] = []
    for tool_name in selected_tools:
        params = params_by_tool.get(tool_name, {})
        result = run_tool(tool_name, params)
        tool_outputs.append(result)

    llm_input = {
        "selected_tools": selected_tools,
        "tool_outputs": tool_outputs,
    }

    prompt = build_llm_prompt(
        user_query=user_query,
        tool_results=llm_input,
        metrics_context=metrics_context,
        research_context=research_context,
    )

    response_text = None
    if call_llm:
        from app.llm.llm_client import run_llm

        response_text = run_llm(prompt)

    return {
        "user_query": user_query,
        "available_tools": list_tools(),
        "selected_tools": selected_tools,
        "tool_outputs": tool_outputs,
        "prompt": prompt,
        "answer": response_text,
    }


if __name__ == "__main__":
    out = answer_question(
        user_query="How did my bench press progress over the last month?",
        tool_params={
            "compare_strength_windows": {
                "exercise": "Bench Press (Barbell)",
            }
        },
        call_llm=False,
    )
    print(out["selected_tools"])
    print(out["tool_outputs"][0]["tool_name"])
