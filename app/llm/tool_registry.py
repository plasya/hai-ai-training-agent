from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
from sqlalchemy import text

from app.analytics.db import engine
from app.analytics.strength_queries import compare_strength_windows, load_exercise_summary


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


def _confidence(flags: list[str]) -> str:
    if any(f.startswith("missing_") for f in flags) or "no_data" in flags:
        return "low"
    if any(f.startswith("low_") for f in flags):
        return "medium"
    return "high"


def _envelope(
    tool_name: str,
    start: str,
    end: str,
    payload: dict[str, Any],
    daily: pd.DataFrame,
) -> dict[str, Any]:
    cov = _coverage(daily)
    has_payload = bool(payload)
    flags = _quality_flags(cov, has_payload=has_payload)
    return {
        "tool_name": tool_name,
        "window": {"start": start, "end": end},
        "payload": payload,
        "data_quality": cov,
        "quality_flags": flags,
        "confidence": _confidence(flags),
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


TOOL_REGISTRY: dict[str, ToolSpec] = {
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
