from __future__ import annotations

import re
from typing import Any

import pandas as pd

from app.llm.prompt_builder import build_llm_prompt
from app.llm.tool_registry import list_tools, run_tool


DEFAULT_TOOLS = [
    "strength_analysis",
    "compare_strength_windows",
    "get_weekly_training_summary",
    "get_fatigue_snapshot",
    "get_recovery_trend",
    "get_cardio_load_trend",
    "get_highest_intensity_workouts",
    "suggest_next_workout",
]

EXERCISE_KEYWORDS = {
    "bench": "Bench Press (Barbell)",
    "bench press": "Bench Press (Barbell)",
    "squat": "Squat (Barbell)",
    "deadlift": "Deadlift (Barbell)",
    "row": "Bent Over Row (Barbell)",
    "rowing": "Bent Over Row (Barbell)",
    "ohp": "Overhead Press (Barbell)",
    "overhead press": "Overhead Press (Barbell)",
}

MUSCLE_KEYWORDS = {
    "chest": "chest",
    "back": "back",
    "legs": "legs",
    "shoulders": "shoulders",
    "arms": "arms",
    "glutes": "glutes",
    "core": "core",
}

MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def _today() -> pd.Timestamp:
    return pd.Timestamp.now().normalize()


def _select_tools(user_query: str) -> list[str]:
    q = user_query.lower()

    if any(k in q for k in ["muscle group", "muscle-group", "groupwise", "each muscle"]):
        return ["strength_analysis"]

    if any(k in q for k in ["highest intensity", "hardest workout", "hardest workouts", "highest heart rate", "avg heart rate", "average heart rate", "peak heart rate", "peak hr", "workout heart rate"]):
        return ["get_highest_intensity_workouts"]

    if any(k in q for k in ["what should i train next", "plan my next workout", "what workout tomorrow", "what should i do today"]):
        return ["suggest_next_workout"]

    if any(k in q for k in ["cardio load", "training load", "cardio", "zone 2", "running load", "cycling load"]):
        return ["get_cardio_load_trend"]

    if any(k in q for k in ["bench", "squat", "deadlift", "progress", "pr", "1rm", "stronger"]):
        return ["strength_analysis"]

    if any(k in q for k in ["fatigue", "overtrain", "tired", "readiness", "burnout"]):
        return ["get_fatigue_snapshot", "get_recovery_trend"]

    if any(k in q for k in ["recovery", "hrv", "sleep", "resting hr", "resting heart"]):
        return ["get_recovery_trend"]

    if any(k in q for k in ["weekly", "last week", "this week", "summary", "overview"]):
        return ["get_weekly_training_summary"]

    return ["get_weekly_training_summary"]


def _last_user_message(conversation_history: list[dict[str, Any]] | None) -> str | None:
    if not conversation_history:
        return None

    for message in reversed(conversation_history):
        if str(message.get("role", "")).lower() != "user":
            continue
        text = str(message.get("message_text", "")).strip()
        if text:
            return text
    return None


def _is_followup_query(user_query: str) -> bool:
    q = user_query.lower().strip()
    followup_starts = (
        "what data",
        "why",
        "what about",
        "how about",
        "and what",
        "was that",
        "is that",
        "does that",
        "can you explain",
    )
    if q.startswith(followup_starts):
        return True

    return "compared to before" in q


def _previous_adjacent_window(start: str, end: str) -> tuple[str, str]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    span = end_ts - start_ts
    prev_end = start_ts - pd.Timedelta(days=1)
    prev_start = prev_end - span
    return str(prev_start.date()), str(prev_end.date())


def _followup_tool_params(user_query: str, last_user: str | None) -> dict[str, Any]:
    q = user_query.lower().strip()

    start, end = _infer_window(user_query)
    if start and end:
        return {"date_start": start, "date_end": end}

    if not last_user:
        return {}

    last_start, last_end = _infer_window(last_user)
    if not (last_start and last_end):
        return {}

    # Resolve explicit adjacent-window follow-ups against the last inferred range.
    if "month before that" in q or "week before that" in q:
        start, end = _previous_adjacent_window(last_start, last_end)
        return {"date_start": start, "date_end": end}

    # Let compare-style strength questions reuse the last explicit window.
    if "compared to before" in q:
        return {"date_start": last_start, "date_end": last_end}

    return {}


def _routing_query(user_query: str, conversation_history: list[dict[str, Any]] | None) -> str:
    if not _is_followup_query(user_query):
        return user_query

    last_user = _last_user_message(conversation_history)
    if not last_user:
        return user_query

    return f"{last_user} {user_query}"


def _infer_exercise(user_query: str) -> str | None:
    q = user_query.lower()
    for key, exercise in EXERCISE_KEYWORDS.items():
        if key in q:
            return exercise
    return None


def _infer_muscle(user_query: str) -> str | None:
    q = user_query.lower()
    for key, muscle in MUSCLE_KEYWORDS.items():
        if key in q:
            return muscle
    return None


def _month_bounds(year: int, month: int) -> tuple[str, str]:
    start = pd.Timestamp(year=year, month=month, day=1)
    end = start + pd.offsets.MonthEnd(1)
    return str(start.date()), str(end.date())


def _most_recent_past_month_bounds(today: pd.Timestamp, month: int) -> tuple[str, str]:
    year = today.year
    if month >= today.month:
        year -= 1
    return _month_bounds(year, month)


def _infer_window(user_query: str) -> tuple[str | None, str | None]:
    q = user_query.lower().strip()
    today = _today()

    month_compare = re.search(
        r"\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b\s+vs\s+\b"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b"
        r"(?:\s+(\d{4}))?",
        q,
    )
    if month_compare:
        current_month = MONTH_NAMES[month_compare.group(2)]
        year = int(month_compare.group(3)) if month_compare.group(3) else today.year
        if month_compare.group(3) is None and current_month >= today.month:
            year -= 1
        return _month_bounds(year, current_month)

    between_months = re.search(
        r"\bbetween\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)"
        r"\s+and\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
        q,
    )
    if between_months:
        current_month = MONTH_NAMES[between_months.group(2)]
        return _most_recent_past_month_bounds(today, current_month)

    in_month = re.search(
        r"\bin\s+"
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b",
        q,
    )
    if in_month:
        month = MONTH_NAMES[in_month.group(1)]
        return _most_recent_past_month_bounds(today, month)

    bare_month = re.fullmatch(
        r"(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)",
        q,
    )
    if bare_month:
        month = MONTH_NAMES[bare_month.group(1)]
        return _most_recent_past_month_bounds(today, month)

    relative_months = re.search(r"\b(?:past|last)\s+(\d+)\s+(?:months?|mos?)\b", q)
    if relative_months:
        months = int(relative_months.group(1))
        end = today
        start = end - pd.DateOffset(months=months) + pd.Timedelta(days=1)
        return str(start.date()), str(end.date())

    relative_weeks = re.search(r"\b(?:past|last)\s+(\d+)\s+weeks?\b", q)
    if relative_weeks:
        weeks = int(relative_weeks.group(1))
        end = today
        start = end - pd.Timedelta(weeks=weeks) + pd.Timedelta(days=1)
        return str(start.date()), str(end.date())

    if "last month" in q or "past month" in q:
        end = today
        start = end - pd.DateOffset(months=1) + pd.Timedelta(days=1)
        return str(start.date()), str(end.date())

    return None, None


def _default_tool_params(user_query: str, selected_tools: list[str]) -> dict[str, dict[str, Any]]:
    start, end = _infer_window(user_query)
    exercise = _infer_exercise(user_query)
    muscle = _infer_muscle(user_query)
    q = user_query.lower()

    defaults: dict[str, dict[str, Any]] = {}
    for tool_name in selected_tools:
        params: dict[str, Any] = {}
        if start and end:
            params["date_start"] = start
            params["date_end"] = end
        if tool_name == "strength_analysis":
            params["mode"] = "compare"
            if any(k in q for k in ["muscle group", "muscle-group", "groupwise", "each muscle"]):
                params["mode"] = "muscle_group"
            elif any(k in q for k in ["trend", "over time"]):
                params["mode"] = "trend"
            if exercise:
                params["exercise"] = exercise
            if muscle:
                params["muscle"] = muscle
        if tool_name == "compare_strength_windows" and exercise:
            params["exercise"] = exercise
        defaults[tool_name] = params
    return defaults


def answer_question(
    user_query: str,
    tool_params: dict[str, dict[str, Any]] | None = None,
    metrics_context: str = "",
    research_context: str = "",
    preferences: dict[str, Any] | None = None,
    conversation_history: list[dict[str, Any]] | None = None,
    call_llm: bool = True,
) -> dict[str, Any]:
    last_user = _last_user_message(conversation_history)
    routing_query = _routing_query(user_query, conversation_history)
    followup_params = _followup_tool_params(user_query, last_user)
    selected_tools = _select_tools(routing_query)
    params_by_tool = _default_tool_params(routing_query, selected_tools)
    for tool_name in selected_tools:
        if not followup_params:
            continue
        params_by_tool.setdefault(tool_name, {})
        for key, value in followup_params.items():
            params_by_tool[tool_name].setdefault(key, value)
    for tool_name, params in (tool_params or {}).items():
        params_by_tool.setdefault(tool_name, {})
        params_by_tool[tool_name].update(params)

    tool_outputs: list[dict[str, Any]] = []
    for tool_name in selected_tools:
        params = params_by_tool.get(tool_name, {})
        result = run_tool(tool_name, params)
        tool_outputs.append(result)

    no_data_low_confidence = bool(tool_outputs) and all(
        str(output.get("confidence", "")).lower() == "low"
        and "no_data" in output.get("quality_flags", [])
        for output in tool_outputs
    )

    llm_input = {
        "selected_tools": selected_tools,
        "tool_outputs": tool_outputs,
    }

    prompt = build_llm_prompt(
        user_query=user_query,
        tool_results=llm_input,
        metrics_context=metrics_context,
        research_context=research_context,
        preferences=preferences,
        conversation_history=conversation_history,
    )

    response_text = None
    if no_data_low_confidence:
        response_text = "I don’t have enough recent data to answer that yet."
    elif call_llm:
        from app.llm.llm_client import run_llm

        response_text = run_llm(prompt)

    return {
        "user_query": user_query,
        "available_tools": list_tools(),
        "selected_tools": selected_tools,
        "tool_outputs": tool_outputs,
        "prompt": prompt,
        "answer": response_text,
        "preferences": preferences or {},
        "conversation_history": conversation_history or [],
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
