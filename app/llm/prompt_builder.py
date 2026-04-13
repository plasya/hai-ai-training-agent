import json


SYSTEM_PROMPT = """
You are a health and training insights assistant.

Rules:
- Do NOT invent metrics.
- Use only tool results.
- Answer directly first.
- If confidence is low, be cautious.
- Sound natural.
- Mention only the 1-2 main reasons that support the answer.
"""


def _preferences_context(preferences: dict | None) -> str:
    if not preferences:
        return ""

    tone = preferences.get("tone", "standard")
    focus_area = preferences.get("focus_area", "balanced")
    tracked_lifts = preferences.get("tracked_lifts", [])
    tracked_metrics = preferences.get("tracked_metrics", [])
    summary_frequency = preferences.get("summary_frequency", "weekly")

    return (
        f"User tone preference: {tone}\n"
        f"User focus area: {focus_area}\n"
        f"User preferred summary frequency: {summary_frequency}\n"
        f"Tracked lifts: {', '.join(tracked_lifts) if tracked_lifts else 'none specified'}\n"
        f"Tracked metrics: {', '.join(tracked_metrics) if tracked_metrics else 'none specified'}"
    )


def _history_context(conversation_history: list[dict] | None) -> str:
    if not conversation_history:
        return "No prior conversation context."

    recent = conversation_history[-8:]
    lines = []
    for message in recent:
        role = str(message.get("role", "unknown")).strip().lower()
        text = str(message.get("message_text", "")).strip()
        if not text:
            continue
        lines.append(f"{role}: {text}")

    return "\n".join(lines) if lines else "No prior conversation context."


def build_llm_prompt(user_query, tool_results, metrics_context="", research_context="", preferences=None, conversation_history=None):
    prompt = f"""
{SYSTEM_PROMPT}

Metric docs:
{metrics_context}

Research context:
{research_context}

User preferences:
{_preferences_context(preferences)}

Recent conversation:
{_history_context(conversation_history)}

User question:
{user_query}

Tool results:
{json.dumps(tool_results, indent=2)}

Write a concise user-facing response.

If a strength comparison payload includes derived compare fields such as `volume_change`, `volume_change_pct`, `best_estimated_max_change`, `best_estimated_max_change_pct`, `set_change`, `pr_change`, or `had_recent_pr`, prefer those fields over manually comparing raw current and previous values.
For strength comparison answers, explain the result first and use only the 1-2 main drivers.
"""

    return prompt
