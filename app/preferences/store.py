from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
PREFERENCES_PATH = BASE_DIR / "data" / "user_preferences.json"

DEFAULT_PREFERENCES: dict[str, Any] = {
    "tracked_lifts": ["Bench Press (Barbell)"],
    "tracked_metrics": ["estimated_1rm", "prs", "trimp", "fatigue_risk"],
    "summary_frequency": "weekly",
    "tone": "standard",
    "focus_area": "balanced",
    "debug_default": False,
}


def load_preferences() -> dict[str, Any]:
    if not PREFERENCES_PATH.exists():
        return dict(DEFAULT_PREFERENCES)

    with PREFERENCES_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    prefs = dict(DEFAULT_PREFERENCES)
    if isinstance(data, dict):
        prefs.update(data)
    return prefs


def save_preferences(new_values: dict[str, Any]) -> dict[str, Any]:
    prefs = dict(DEFAULT_PREFERENCES)
    prefs.update(load_preferences())
    prefs.update(new_values)

    PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PREFERENCES_PATH.open("w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2)

    return prefs
