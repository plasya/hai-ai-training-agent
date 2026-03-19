import pandas as pd
import psycopg2
from pathlib import Path

DB_DSN = "postgresql://app:app@localhost:5432/health"

BASE_DIR = Path(__file__).resolve().parents[2]
EXERCISE_REF_PATH = BASE_DIR / "data" / "exercise_reference_final.csv"

COMPOUND_LIFTS = {
    "Squat (Barbell)",
    "Bench Press (Barbell)",
    "Deadlift (Barbell)",
    "Bent Over Row (Barbell)",
    "Overhead Press (Barbell)",
    "Rack Pull",
    "Pull Up (Assisted)",
    "Lat Pulldown (Cable)",
    "Leg Press (Machine)",
    "Belt Squat (Machine)"
}


def load_exercise_progress() -> pd.DataFrame:
    query = """
    SELECT *
    FROM exercise_progress
    ORDER BY date, exercise_title;
    """
    with psycopg2.connect(DB_DSN) as conn:
        df = pd.read_sql(query, conn) # type: ignore

    df["date"] = pd.to_datetime(df["date"])
    return df


def load_exercise_reference() -> pd.DataFrame:
    return pd.read_csv(EXERCISE_REF_PATH)


def load_exercise_summary() -> pd.DataFrame:
    df = load_exercise_progress()
    ref = load_exercise_reference()

    df = df.merge(
        ref[[
            "exercise_title",
            "movement_pattern",
            "primary_muscle",
            "secondary_muscles",
            "equipment",
            "is_compound",
            "is_bodyweight",
            "needs_review"
        ]],
        on="exercise_title",
        how="left"
    )
    return df


def get_strength_progress(
    exercise_summary: pd.DataFrame,
    exercise: str | None = None,
    muscle: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    weekly: bool = True,
    compounds_only: bool = False,
):
    df = exercise_summary.copy()
    df["date"] = pd.to_datetime(df["date"])

    if compounds_only:
        df = df[df["exercise_title"].isin(COMPOUND_LIFTS)]

    if exercise is not None:
        df = df[df["exercise_title"] == exercise]

    if muscle is not None:
        df = df[df["primary_muscle"] == muscle]

    if from_date is not None:
        df = df[df["date"] >= pd.to_datetime(from_date)]

    if to_date is not None:
        df = df[df["date"] <= pd.to_datetime(to_date)]

    if weekly:
        df["period_start"] = df["date"].dt.to_period("W").dt.start_time # type: ignore
    else:
        df["period_start"] = df["date"]

    out = (
        df.groupby(["period_start"], as_index=False)
        .agg(
            total_volume=("volume", "sum"),
            total_sets=("sets", "sum"),
            best_1rm=("est_1rm", "max"),
            pr_count=("is_pr", "sum"),
            exercise_count=("exercise_title", "nunique"),
        )
        .sort_values("period_start")
    )

    return out


def compare_strength_windows(
    exercise_summary: pd.DataFrame,
    from_date: str,
    to_date: str,
    exercise: str | None = None,
    muscle: str | None = None,
    weekly: bool = True,
    compounds_only: bool = False,
):
    current = get_strength_progress(
        exercise_summary,
        exercise=exercise,
        muscle=muscle,
        from_date=from_date,
        to_date=to_date,
        weekly=weekly,
        compounds_only=compounds_only,
    )

    if current.empty:
        return {"current": None, "previous": None, "trend": "no_data"}

    start = pd.to_datetime(from_date)
    end = pd.to_datetime(to_date)

    span = end - start

    prev_end = start - pd.Timedelta(days=1)
    prev_start = prev_end - span

    previous = get_strength_progress(
        exercise_summary,
        exercise=exercise,
        muscle=muscle,
        from_date=str(prev_start.date()),
        to_date=str(prev_end.date()),
        weekly=weekly,
        compounds_only=compounds_only,
    )

    cur = {
        "volume": float(current["total_volume"].sum()),
        "sets": int(current["total_sets"].sum()),
        "best_1rm": float(current["best_1rm"].max()) if not current["best_1rm"].isna().all() else None,
        "prs": int(current["pr_count"].sum()),
    }

    prev = {
        "volume": float(previous["total_volume"].sum()) if not previous.empty else 0.0,
        "sets": int(previous["total_sets"].sum()) if not previous.empty else 0,
        "best_1rm": float(previous["best_1rm"].max()) if (not previous.empty and not previous["best_1rm"].isna().all()) else None,
        "prs": int(previous["pr_count"].sum()) if not previous.empty else 0,
    }

    trend = "flat"
    if prev["volume"] == 0 and cur["volume"] > 0:
        trend = "improving"
    elif prev["volume"] > 0:
        ratio = cur["volume"] / prev["volume"]
        if ratio > 1.1:
            trend = "improving"
        elif ratio < 0.9:
            trend = "declining"

    return {
        "current": cur,
        "previous": prev,
        "trend": trend
    }


if __name__ == "__main__":
    exercise_summary = load_exercise_summary()
    print(
        compare_strength_windows(
            exercise_summary,
            exercise="Bench Press (Barbell)",
            from_date="2025-12-01",
            to_date="2026-01-15",
            weekly=True
        )
    )