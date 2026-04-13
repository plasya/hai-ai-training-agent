from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
from sqlalchemy import text

from app.analytics.db import engine
from app.analytics.strength_queries import (
    compare_strength_windows,
    get_strength_progress,
    load_exercise_summary,
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]


def _to_date(x: Any) -> str | None:
    if x is None:
        return None
    ts = pd.to_datetime(x, errors="coerce")
    if pd.isna(ts):
        return None
    return str(ts.date())


def _window_dates(params: dict[str, Any]) -> tuple[str, str]:
    end = _to_date(params.get("date_end"))
    start = _to_date(params.get("date_start"))

    if end is None:
        end = str(pd.Timestamp.now().date())
    if start is None:
        start = str((pd.Timestamp(end) - pd.Timedelta(days=27)).date())

    return start, end


def _load_daily_slice(start: str, end: str) -> pd.DataFrame:
    query = text("""
    SELECT date, trimp_total, resting_hr, hrv_sdnn, sleep_minutes
    FROM daily_features
    WHERE date BETWEEN :start AND :end
    ORDER BY date;
    """)
    return pd.read_sql(query, engine, params={"start": start, "end": end})


def _load_weekly_training(start: str, end: str) -> pd.DataFrame:
    query = text("""
    SELECT
      week_start,
      weekly_strength_volume,
      weekly_prs,
      weekly_hrv,
      weekly_rhr,
      weekly_trimp,
      weekly_acwr,
      fatigue_days,
      strength_readiness
    FROM weekly_training_features
    WHERE week_start BETWEEN :start AND :end
    ORDER BY week_start;
    """)
    return pd.read_sql(query, engine, params={"start": start, "end": end})


def _load_weekly_muscle(start: str, end: str) -> pd.DataFrame:
    query = text("""
    SELECT
      week_start,
      primary_muscle,
      weekly_volume,
      weekly_sets,
      weekly_best_1rm,
      exercise_count,
      pr_count
    FROM weekly_muscle_features
    WHERE week_start BETWEEN :start AND :end
    ORDER BY week_start, primary_muscle;
    """)
    return pd.read_sql(query, engine, params={"start": start, "end": end})


def _load_workout_hr_summary(start: str, end: str) -> pd.DataFrame:
    query = text("""
    SELECT
      aw.apple_workout_id,
      aw.activity_type,
      aw.start_time,
      aw.end_time,
      aw.duration_min,
      COUNT(hr.bpm) AS hr_points,
      ROUND(AVG(hr.bpm))::int AS avg_bpm,
      MAX(hr.bpm) AS max_bpm
    FROM apple_workouts aw
    LEFT JOIN heart_rate_raw hr
      ON hr.recorded_at BETWEEN aw.start_time AND aw.end_time
    WHERE DATE(aw.start_time) BETWEEN :start AND :end
    GROUP BY
      aw.apple_workout_id,
      aw.activity_type,
      aw.start_time,
      aw.end_time,
      aw.duration_min
    ORDER BY aw.start_time;
    """)
    return pd.read_sql(query, engine, params={"start": start, "end": end})


def _coverage(daily: pd.DataFrame) -> dict[str, float]:
    if daily.empty:
        return {
            "hrv_coverage": 0.0,
            "resting_hr_coverage": 0.0,
            "sleep_coverage": 0.0,
            "trimp_coverage": 0.0,
        }
    return {
        "hrv_coverage": float(daily["hrv_sdnn"].notna().mean()),
        "resting_hr_coverage": float(daily["resting_hr"].notna().mean()),
        "sleep_coverage": float(daily["sleep_minutes"].notna().mean()),
        "trimp_coverage": float(daily["trimp_total"].notna().mean()),
    }


def _quality_flags(cov: dict[str, float], has_payload: bool) -> list[str]:
    flags: list[str] = []
    metric_map = {
        "hrv_coverage": "hrv",
        "resting_hr_coverage": "resting_hr",
        "sleep_coverage": "sleep",
        "trimp_coverage": "trimp",
    }

    for key, alias in metric_map.items():
        c = cov.get(key, 0.0)
        if c == 0.0:
            flags.append(f"missing_{alias}")
        elif c < 0.5:
            flags.append(f"low_{alias}_coverage")

    if not has_payload:
        flags.append("no_data")

    return flags


def _strength_quality_flags(payload: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    mode = payload.get("mode")

    if mode == "muscle_group":
        if payload.get("subject", {}).get("muscle"):
            points = payload.get("points", [])
            if not points:
                return ["no_data"]
            if len(points) < 2:
                flags.append("limited_muscle_group_history")
            return flags

        muscles = payload.get("muscles", [])
        if not muscles:
            return ["no_data"]
        if len(muscles) < 2:
            flags.append("limited_muscle_group_history")
        return flags

    if mode == "trend":
        points = payload.get("points", [])
        if not points:
            return ["no_data"]
        if len(points) < 2:
            flags.append("low_current_strength_history")
        return flags

    current = payload.get("current")
    previous = payload.get("previous")

    if not current:
        return ["no_data"]

    if (current.get("sets") or 0) == 0:
        flags.append("no_current_strength_data")
    elif (current.get("sets") or 0) < 5:
        flags.append("low_current_strength_history")

    if not previous or (previous.get("sets") or 0) == 0:
        flags.append("limited_previous_window")

    return flags


def _weekly_quality_flags(payload: dict[str, Any], cov: dict[str, float]) -> list[str]:
    flags: list[str] = []
    weeks = payload.get("weeks", [])

    if not weeks:
        return ["no_data"]

    if cov.get("trimp_coverage", 0.0) == 0.0:
        flags.append("missing_trimp")
    elif cov.get("trimp_coverage", 0.0) < 0.5:
        flags.append("low_trimp_coverage")

    if cov.get("hrv_coverage", 0.0) == 0.0:
        flags.append("missing_hrv")
    elif cov.get("hrv_coverage", 0.0) < 0.5:
        flags.append("low_hrv_coverage")

    return flags


def _recovery_quality_flags(cov: dict[str, float], has_payload: bool) -> list[str]:
    return _quality_flags(cov, has_payload)


def _cardio_quality_flags(payload: dict[str, Any], cov: dict[str, float]) -> list[str]:
    flags: list[str] = []
    if not payload:
        return ["no_data"]

    if cov.get("trimp_coverage", 0.0) == 0.0:
        flags.append("missing_trimp")
    elif cov.get("trimp_coverage", 0.0) < 0.5:
        flags.append("low_trimp_coverage")

    return flags


def _workout_hr_quality_flags(payload: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    workouts = payload.get("workouts", [])
    if not workouts:
        return ["no_data"]

    hr_coverage = payload.get("hr_workout_coverage", 0.0)
    if hr_coverage == 0.0:
        flags.append("missing_workout_hr")
    elif hr_coverage < 0.5:
        flags.append("low_workout_hr_coverage")

    return flags


def _confidence_for_strength(payload: dict[str, Any]) -> str:
    mode = payload.get("mode")
    if mode == "muscle_group":
        if payload.get("subject", {}).get("muscle"):
            points = payload.get("points", [])
            if len(points) >= 3:
                return "high"
            if len(points) >= 1:
                return "medium"
            return "low"

        muscles = payload.get("muscles", [])
        if len(muscles) >= 3:
            return "high"
        if muscles:
            return "medium"
        return "low"

    if mode == "trend":
        points = payload.get("points", [])
        if len(points) >= 3:
            return "high"
        if points:
            return "medium"
        return "low"

    current = payload.get("current")
    previous = payload.get("previous")
    if not current:
        return "low"

    current_sets = current.get("sets") or 0
    previous_sets = (previous or {}).get("sets") or 0

    if current_sets >= 8 and previous_sets >= 8:
        return "high"
    if current_sets >= 1:
        return "medium"
    return "low"


def _confidence_for_weekly_summary(payload: dict[str, Any], cov: dict[str, float]) -> str:
    weeks = payload.get("weeks", [])
    if not weeks:
        return "low"

    trimp_cov = cov.get("trimp_coverage", 0.0)
    if len(weeks) >= 1 and trimp_cov >= 0.5:
        return "high"
    if len(weeks) >= 1:
        return "medium"
    return "low"


def _confidence_for_recovery(flags: list[str]) -> str:
    if any(f.startswith("missing_") for f in flags) or "no_data" in flags:
        return "low"
    if any(f.startswith("low_") for f in flags):
        return "medium"
    return "high"


def _confidence_for_cardio(payload: dict[str, Any], flags: list[str]) -> str:
    if not payload or "no_data" in flags:
        return "low"
    if any(f.startswith("missing_") for f in flags):
        return "low"
    if any(f.startswith("low_") for f in flags):
        return "medium"
    return "high"


def _confidence_for_workout_hr(payload: dict[str, Any], flags: list[str]) -> str:
    workouts = payload.get("workouts", []) if payload else []
    if not workouts or "no_data" in flags:
        return "low"
    if any(f.startswith("missing_") for f in flags):
        return "low"
    if any(f.startswith("low_") for f in flags):
        return "medium"
    if len(workouts) >= 3:
        return "high"
    return "medium"


def _confidence_for_next_workout(payload: dict[str, Any]) -> str:
    muscles = payload.get("target_muscles", []) if payload else []
    exercises = payload.get("suggested_exercises", []) if payload else []
    if not muscles or not exercises:
        return "low"
    if len(muscles) >= 2:
        return "high"
    return "medium"


def _confidence(tool_name: str, payload: dict[str, Any], cov: dict[str, float], flags: list[str]) -> str:
    if "no_data" in flags:
        return "low"

    if tool_name == "compare_strength_windows":
        return _confidence_for_strength(payload)

    if tool_name == "strength_analysis":
        return _confidence_for_strength(payload)

    if tool_name == "get_weekly_training_summary":
        return _confidence_for_weekly_summary(payload, cov)

    if tool_name in {"get_fatigue_snapshot", "get_recovery_trend"}:
        return _confidence_for_recovery(flags)

    if tool_name == "get_cardio_load_trend":
        return _confidence_for_cardio(payload, flags)

    if tool_name == "get_highest_intensity_workouts":
        return _confidence_for_workout_hr(payload, flags)

    if tool_name == "suggest_next_workout":
        return _confidence_for_next_workout(payload)

    return _confidence_for_recovery(flags)


def _tool_quality_flags(tool_name: str, payload: dict[str, Any], cov: dict[str, float], has_payload: bool) -> list[str]:
    if tool_name == "compare_strength_windows":
        return _strength_quality_flags(payload)

    if tool_name == "strength_analysis":
        return _strength_quality_flags(payload)

    if tool_name == "get_weekly_training_summary":
        return _weekly_quality_flags(payload, cov)

    if tool_name in {"get_fatigue_snapshot", "get_recovery_trend"}:
        return _recovery_quality_flags(cov, has_payload)

    if tool_name == "get_cardio_load_trend":
        return _cardio_quality_flags(payload, cov)

    if tool_name == "get_highest_intensity_workouts":
        return _workout_hr_quality_flags(payload)

    if tool_name == "suggest_next_workout":
        return [] if payload else ["no_data"]

    return _quality_flags(cov, has_payload)


def _envelope(
    tool_name: str,
    start: str,
    end: str,
    payload: dict[str, Any],
    daily: pd.DataFrame,
) -> dict[str, Any]:
    cov = _coverage(daily)
    has_payload = bool(payload)
    flags = _tool_quality_flags(tool_name, payload, cov, has_payload=has_payload)
    return {
        "tool_name": tool_name,
        "window": {"start": start, "end": end},
        "payload": payload,
        "data_quality": cov,
        "quality_flags": flags,
        "confidence": _confidence(tool_name, payload, cov, flags),
    }


def tool_compare_strength_windows(params: dict[str, Any]) -> dict[str, Any]:
    start, end = _window_dates(params)
    exercise_summary = load_exercise_summary()
    result = compare_strength_windows(
        exercise_summary,
        from_date=start,
        to_date=end,
        exercise=params.get("exercise"),
        muscle=params.get("muscle"),
        weekly=bool(params.get("weekly", True)),
        compounds_only=bool(params.get("compounds_only", False)),
    )
    daily = _load_daily_slice(start, end)
    return _envelope("compare_strength_windows", start, end, result, daily)


def _strength_points_payload(points: pd.DataFrame) -> list[dict[str, Any]]:
    if points.empty:
        return []

    formatted = points.copy()
    formatted["period_start"] = pd.to_datetime(formatted["period_start"]).dt.strftime("%Y-%m-%d")
    return [
        {
            "period_start": row["period_start"],
            "volume": float(row["total_volume"]),
            "sets": int(row["total_sets"]),
            "best_estimated_max": None if pd.isna(row["best_1rm"]) else float(row["best_1rm"]),
            "prs": int(row["pr_count"]),
            "exercise_count": int(row["exercise_count"]),
        }
        for _, row in formatted.iterrows()
    ]


def _strength_trend_from_points(points: list[dict[str, Any]]) -> str:
    if len(points) < 2:
        return "flat"

    first = points[0]["volume"] or 0.0
    last = points[-1]["volume"] or 0.0
    if first == 0 and last > 0:
        return "improving"
    if first > 0:
        ratio = last / first
        if ratio > 1.1:
            return "improving"
        if ratio < 0.9:
            return "declining"
    return "flat"


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return ((current - previous) / previous) * 100.0


def tool_strength_analysis(params: dict[str, Any]) -> dict[str, Any]:
    start, end = _window_dates(params)
    mode = str(params.get("mode", "compare"))
    exercise = params.get("exercise")
    muscle = params.get("muscle")
    weekly = bool(params.get("weekly", True))
    compounds_only = bool(params.get("compounds_only", False))

    # Keep the compare mode aligned with the existing narrow tool while we migrate.
    if mode == "compare":
        exercise_summary = load_exercise_summary()
        result = compare_strength_windows(
            exercise_summary,
            from_date=start,
            to_date=end,
            exercise=exercise,
            muscle=muscle,
            weekly=weekly,
            compounds_only=compounds_only,
        )
        current = result["current"]
        previous = result["previous"]
        payload = {
            "mode": "compare",
            "subject": {
                "exercise": exercise,
                "muscle": muscle,
            },
            "current": {
                "volume": None if current is None else current["volume"],
                "sets": None if current is None else current["sets"],
                "best_estimated_max": None if current is None else current["best_1rm"],
                "prs": None if current is None else current["prs"],
            },
            "previous": {
                "volume": None if previous is None else previous["volume"],
                "sets": None if previous is None else previous["sets"],
                "best_estimated_max": None if previous is None else previous["best_1rm"],
                "prs": None if previous is None else previous["prs"],
            },
            "volume_change": None if current is None or previous is None else current["volume"] - previous["volume"],
            "volume_change_pct": None if current is None or previous is None else _pct_change(current["volume"], previous["volume"]),
            "set_change": None if current is None or previous is None else current["sets"] - previous["sets"],
            "best_estimated_max_change": (
                None
                if current is None or previous is None or current["best_1rm"] is None or previous["best_1rm"] is None
                else current["best_1rm"] - previous["best_1rm"]
            ),
            "best_estimated_max_change_pct": (
                None
                if current is None or previous is None
                else _pct_change(current["best_1rm"], previous["best_1rm"])
            ),
            "pr_change": None if current is None or previous is None else current["prs"] - previous["prs"],
            "had_recent_pr": None if current is None else bool((current["prs"] or 0) > 0),
            "trend": result["trend"],
        }
    elif mode == "trend":
        exercise_summary = load_exercise_summary()
        progress = get_strength_progress(
            exercise_summary,
            exercise=exercise,
            muscle=muscle,
            from_date=start,
            to_date=end,
            weekly=weekly,
            compounds_only=compounds_only,
        )
        points = _strength_points_payload(progress)
        payload = {
            "mode": "trend",
            "subject": {
                "exercise": exercise,
                "muscle": muscle,
            },
            "points": points,
            "trend": _strength_trend_from_points(points),
        }
    elif mode == "muscle_group":
        weekly_muscle = _load_weekly_muscle(start, end)
        if muscle:
            filtered = weekly_muscle[weekly_muscle["primary_muscle"] == muscle].copy()
            filtered["week_start"] = pd.to_datetime(filtered["week_start"]).dt.strftime("%Y-%m-%d")
            points = [
                {
                    "period_start": row["week_start"],
                    "weekly_volume": float(row["weekly_volume"]),
                    "weekly_sets": int(row["weekly_sets"]),
                    "weekly_best_estimated_max": None if pd.isna(row["weekly_best_1rm"]) else float(row["weekly_best_1rm"]),
                    "exercise_count": int(row["exercise_count"]),
                    "pr_count": int(row["pr_count"]),
                }
                for _, row in filtered.iterrows()
            ]
            payload = {
                "mode": "muscle_group",
                "subject": {
                    "exercise": None,
                    "muscle": muscle,
                },
                "points": points,
                "trend": _strength_trend_from_points(
                    [
                        {
                            "period_start": p["period_start"],
                            "volume": p["weekly_volume"],
                        }
                        for p in points
                    ]
                ),
            }
        else:
            summary = (
                weekly_muscle.groupby("primary_muscle", as_index=False)
                .agg(
                    total_volume=("weekly_volume", "sum"),
                    total_sets=("weekly_sets", "sum"),
                    best_estimated_max=("weekly_best_1rm", "max"),
                    exercise_count=("exercise_count", "max"),
                    pr_count=("pr_count", "sum"),
                )
                .sort_values("total_volume", ascending=False)
            )
            payload = {
                "mode": "muscle_group",
                "subject": {
                    "exercise": None,
                    "muscle": None,
                },
                "muscles": [
                    {
                        "muscle": row["primary_muscle"],
                        "total_volume": float(row["total_volume"]),
                        "total_sets": int(row["total_sets"]),
                        "best_estimated_max": None if pd.isna(row["best_estimated_max"]) else float(row["best_estimated_max"]),
                        "exercise_count": int(row["exercise_count"]),
                        "pr_count": int(row["pr_count"]),
                    }
                    for _, row in summary.iterrows()
                ],
            }
    else:
        payload = {
            "mode": mode,
            "subject": {
                "exercise": exercise,
                "muscle": muscle,
            },
            "points": [],
        }

    daily = _load_daily_slice(start, end)
    return _envelope("strength_analysis", start, end, payload, daily)


def tool_get_weekly_training_summary(params: dict[str, Any]) -> dict[str, Any]:
    start, end = _window_dates(params)
    weekly = _load_weekly_training(start, end)

    if weekly.empty:
        payload: dict[str, Any] = {"weeks": []}
    else:
        w = weekly.copy()
        w["week_start"] = pd.to_datetime(w["week_start"]).dt.strftime("%Y-%m-%d")
        payload = {
            "weeks": w.to_dict("records"),
            "summary": {
                "weeks": int(len(w)),
                "weekly_strength_volume_total": float(w["weekly_strength_volume"].fillna(0).sum()),
                "weekly_prs_total": int(w["weekly_prs"].fillna(0).sum()),
                "weekly_trimp_total": float(w["weekly_trimp"].fillna(0).sum()),
            },
        }

    daily = _load_daily_slice(start, end)
    return _envelope("get_weekly_training_summary", start, end, payload, daily)


def tool_get_fatigue_snapshot(params: dict[str, Any]) -> dict[str, Any]:
    start, end = _window_dates(params)
    query = text("""
    SELECT date, acute_7d, chronic_28d_avg, acwr, fatigue_risk, rhr_delta, hrv_delta, sleep_delta
    FROM daily_features
    WHERE date BETWEEN :start AND :end
    ORDER BY date DESC
    LIMIT 1;
    """)
    snap = pd.read_sql(query, engine, params={"start": start, "end": end})

    if snap.empty:
        payload = {}
    else:
        row = snap.iloc[0]
        risk = "moderate"
        if bool(row["fatigue_risk"]):
            risk = "high"
        elif pd.notna(row["acwr"]) and float(row["acwr"]) < 0.8:
            risk = "low"

        payload = {
            "date": str(pd.to_datetime(row["date"]).date()),
            "acute_7d": None if pd.isna(row["acute_7d"]) else float(row["acute_7d"]),
            "chronic_28d_avg": None if pd.isna(row["chronic_28d_avg"]) else float(row["chronic_28d_avg"]),
            "acwr": None if pd.isna(row["acwr"]) else float(row["acwr"]),
            "fatigue_risk": risk,
            "supporting": {
                "rhr_delta": None if pd.isna(row["rhr_delta"]) else float(row["rhr_delta"]),
                "hrv_delta": None if pd.isna(row["hrv_delta"]) else float(row["hrv_delta"]),
                "sleep_delta": None if pd.isna(row["sleep_delta"]) else float(row["sleep_delta"]),
            },
        }

    daily = _load_daily_slice(start, end)
    return _envelope("get_fatigue_snapshot", start, end, payload, daily)


def _trend_from_series(series: pd.Series, up_thresh: float, down_thresh: float) -> str:
    clean = series.dropna()
    if clean.empty:
        return "flat"
    delta = float(clean.iloc[-1] - clean.iloc[0])
    if delta >= up_thresh:
        return "up"
    if delta <= down_thresh:
        return "down"
    return "flat"


def tool_get_recovery_trend(params: dict[str, Any]) -> dict[str, Any]:
    start, end = _window_dates(params)
    query = text("""
    SELECT date, resting_hr, hrv_sdnn, sleep_minutes
    FROM daily_features
    WHERE date BETWEEN :start AND :end
    ORDER BY date;
    """)
    daily = pd.read_sql(query, engine, params={"start": start, "end": end})

    if daily.empty:
        payload = {}
    else:
        payload = {
            "resting_hr_trend": _trend_from_series(daily["resting_hr"], up_thresh=2.0, down_thresh=-2.0),
            "hrv_trend": _trend_from_series(daily["hrv_sdnn"], up_thresh=5.0, down_thresh=-5.0),
            "sleep_trend": _trend_from_series(daily["sleep_minutes"], up_thresh=30.0, down_thresh=-30.0),
            "consistency_score": float(
                (
                    daily["resting_hr"].notna().mean()
                    + daily["hrv_sdnn"].notna().mean()
                    + daily["sleep_minutes"].notna().mean()
                )
                / 3
            ),
        }

    daily_cov = _load_daily_slice(start, end)
    return _envelope("get_recovery_trend", start, end, payload, daily_cov)


def tool_get_cardio_load_trend(params: dict[str, Any]) -> dict[str, Any]:
    start, end = _window_dates(params)
    query = text("""
    SELECT date, trimp_total, acute_7d, chronic_28d_avg, acwr
    FROM daily_features
    WHERE date BETWEEN :start AND :end
    ORDER BY date;
    """)
    daily = pd.read_sql(query, engine, params={"start": start, "end": end})

    if daily.empty:
        payload = {}
    else:
        clean = daily.copy()
        midpoint = max(len(clean) // 2, 1)
        early = clean.iloc[:midpoint]
        late = clean.iloc[midpoint:]

        early_load = float(early["trimp_total"].fillna(0).sum())
        late_load = float(late["trimp_total"].fillna(0).sum())

        trend = "flat"
        if early_load == 0 and late_load > 0:
            trend = "up"
        elif early_load > 0:
            ratio = late_load / early_load
            if ratio > 1.1:
                trend = "up"
            elif ratio < 0.9:
                trend = "down"

        latest = clean.iloc[-1]
        payload = {
            "trend": trend,
            "total_training_load": float(clean["trimp_total"].fillna(0).sum()),
            "average_daily_load": float(clean["trimp_total"].dropna().mean()) if clean["trimp_total"].notna().any() else None,
            "latest_acute_load": None if pd.isna(latest["acute_7d"]) else float(latest["acute_7d"]),
            "latest_chronic_load": None if pd.isna(latest["chronic_28d_avg"]) else float(latest["chronic_28d_avg"]),
            "latest_load_balance": None if pd.isna(latest["acwr"]) else float(latest["acwr"]),
        }

    daily_cov = _load_daily_slice(start, end)
    return _envelope("get_cardio_load_trend", start, end, payload, daily_cov)


def tool_get_highest_intensity_workouts(params: dict[str, Any]) -> dict[str, Any]:
    start, end = _window_dates(params)
    workout_type = params.get("activity_type")
    workouts = _load_workout_hr_summary(start, end)

    if workout_type:
        workouts = workouts[workouts["activity_type"].str.lower() == str(workout_type).lower()]

    if workouts.empty:
        payload = {}
    else:
        ranked = workouts.copy()
        ranked["hr_points"] = ranked["hr_points"].fillna(0)
        ranked["avg_bpm"] = ranked["avg_bpm"].fillna(0)
        ranked["max_bpm"] = ranked["max_bpm"].fillna(0)
        ranked["duration_min"] = ranked["duration_min"].fillna(0)
        ranked["intensity_score"] = ranked["avg_bpm"] * ranked["duration_min"]
        ranked = ranked.sort_values(["intensity_score", "max_bpm", "duration_min"], ascending=False)

        top_n = int(params.get("limit", 3))
        top = ranked.head(top_n).copy()
        top["start_time"] = pd.to_datetime(top["start_time"]).dt.strftime("%Y-%m-%d %H:%M")

        hr_coverage = float((ranked["hr_points"] > 0).mean()) if not ranked.empty else 0.0
        payload = {
            "hr_workout_coverage": hr_coverage,
            "workouts": [
                {
                    "date": row["start_time"],
                    "activity_type": row["activity_type"],
                    "duration_min": float(row["duration_min"]),
                    "avg_bpm": int(row["avg_bpm"]) if row["avg_bpm"] else None,
                    "max_bpm": int(row["max_bpm"]) if row["max_bpm"] else None,
                }
                for _, row in top.iterrows()
            ],
        }

    daily_cov = _load_daily_slice(start, end)
    return _envelope("get_highest_intensity_workouts", start, end, payload, daily_cov)


def tool_suggest_next_workout(params: dict[str, Any]) -> dict[str, Any]:
    start, end = _window_dates(params)
    recent = _load_weekly_muscle(start, end)
    used_fallback = False

    muscle_exercises = {
        "chest": ["Bench Press (Barbell)", "Incline Dumbbell Press"],
        "back": ["Bent Over Row (Barbell)", "Lat Pulldown (Cable)"],
        "legs": ["Squat (Barbell)", "Romanian Deadlift"],
        "shoulders": ["Overhead Press (Barbell)", "Lateral Raise (Dumbbell)"],
        "arms": ["Barbell Curl", "Cable Triceps Pushdown"],
        "glutes": ["Hip Thrust (Barbell)", "Belt Squat (Machine)"],
        "core": ["Cable Crunch", "Hanging Leg Raise"],
    }

    if recent.empty:
        used_fallback = True
        # Fallback to raw strength exposure in the same window when weekly rollups are unavailable.
        exercise_summary = load_exercise_summary()
        exercise_summary["date"] = pd.to_datetime(exercise_summary["date"])
        fallback_recent = exercise_summary[
            (exercise_summary["date"] >= pd.to_datetime(start))
            & (exercise_summary["date"] <= pd.to_datetime(end))
        ].copy()

        if fallback_recent.empty:
            target_muscles = ["chest", "back"]
            recent_volume = 0.0
        else:
            exposure = (
                fallback_recent.dropna(subset=["primary_muscle"])
                .groupby("primary_muscle", as_index=False)["volume"]
                .sum()
                .sort_values(["volume", "primary_muscle"])
            )
            target_muscles = [
                str(muscle)
                for muscle in exposure["primary_muscle"].tolist()
                if muscle in muscle_exercises
            ][:2]
            if not target_muscles:
                target_muscles = ["chest", "back"]
            recent_volume = float(exposure["volume"].sum()) if not exposure.empty else 0.0
    else:
        exposure = (
            recent.groupby("primary_muscle", as_index=False)["weekly_volume"]
            .sum()
            .sort_values(["weekly_volume", "primary_muscle"])
        )
        target_muscles = [
            str(muscle)
            for muscle in exposure["primary_muscle"].tolist()
            if muscle in muscle_exercises
        ][:2]
        if not target_muscles:
            target_muscles = ["chest", "back"]
        recent_volume = float(exposure["weekly_volume"].sum())

    suggested_exercises: list[str] = []
    for muscle in target_muscles:
        suggested_exercises.extend(muscle_exercises.get(muscle, []))

    intensity_guidance = "moderate"
    if recent_volume > 12000:
        intensity_guidance = "keep it lighter and submaximal"
    elif recent_volume < 4000:
        intensity_guidance = "moderate to hard if you feel fresh"

    rationale = (
        "This is based on your recent exercise frequency and strength exposure in the latest window, "
        "since weekly muscle load features were not available."
        if used_fallback
        else "This is based on your recent strength exposure, aiming at muscle groups that looked least trained in the latest window."
    )
    payload = {
        "recommendation_type": "low_recent_strength_exposure",
        "target_muscles": target_muscles,
        "suggested_exercises": suggested_exercises[:4],
        "intensity_guidance": intensity_guidance,
        "rationale": rationale,
        "confidence": "high" if len(target_muscles) >= 2 else "medium",
    }

    daily_cov = _load_daily_slice(start, end)
    return _envelope("suggest_next_workout", start, end, payload, daily_cov)


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "strength_analysis": ToolSpec(
        name="strength_analysis",
        description="Broad strength analytics for lift, trend, and muscle-group questions.",
        handler=tool_strength_analysis,
    ),
    "compare_strength_windows": ToolSpec(
        name="compare_strength_windows",
        description="Compare current vs previous strength window.",
        handler=tool_compare_strength_windows,
    ),
    "get_weekly_training_summary": ToolSpec(
        name="get_weekly_training_summary",
        description="Summarize weekly training/recovery metrics.",
        handler=tool_get_weekly_training_summary,
    ),
    "get_fatigue_snapshot": ToolSpec(
        name="get_fatigue_snapshot",
        description="Return most recent fatigue snapshot in window.",
        handler=tool_get_fatigue_snapshot,
    ),
    "get_recovery_trend": ToolSpec(
        name="get_recovery_trend",
        description="Return resting HR, HRV, and sleep trends in window.",
        handler=tool_get_recovery_trend,
    ),
    "get_cardio_load_trend": ToolSpec(
        name="get_cardio_load_trend",
        description="Summarize cardio training load trends from workout heart-rate derived load.",
        handler=tool_get_cardio_load_trend,
    ),
    "get_highest_intensity_workouts": ToolSpec(
        name="get_highest_intensity_workouts",
        description="Return the highest-intensity Apple workouts by heart-rate and duration.",
        handler=tool_get_highest_intensity_workouts,
    ),
    "suggest_next_workout": ToolSpec(
        name="suggest_next_workout",
        description="Suggest the next workout using recent strength exposure heuristics.",
        handler=tool_suggest_next_workout,
    ),
}


def list_tools() -> list[dict[str, str]]:
    return [
        {"name": t.name, "description": t.description}
        for t in TOOL_REGISTRY.values()
    ]


def run_tool(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' is not allowlisted")
    return TOOL_REGISTRY[tool_name].handler(params)
