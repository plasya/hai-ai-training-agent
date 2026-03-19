import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from pathlib import Path

DB_DSN = "postgresql://app:app@localhost:5432/health"
BASE_DIR = Path(__file__).resolve().parents[2]
EXERCISE_REF_PATH = BASE_DIR / "data" / "exercise_reference_final.csv"


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


def load_daily_features() -> pd.DataFrame:
    query = """
    SELECT *
    FROM daily_features
    ORDER BY date;
    """
    with psycopg2.connect(DB_DSN) as conn:
        daily = pd.read_sql(query, conn) # type: ignore

    daily["date"] = pd.to_datetime(daily["date"])
    return daily


def build_weekly_strength_features():
    exercise_summary = load_exercise_progress()
    exercise_ref = pd.read_csv(EXERCISE_REF_PATH)

    exercise_summary = exercise_summary.merge(
        exercise_ref[[
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

    exercise_summary["week_start"] = (
        pd.to_datetime(exercise_summary["date"]).dt.to_period("W").dt.start_time
    )

    weekly_muscle = (
        exercise_summary
        .groupby(["week_start", "primary_muscle"], as_index=False)
        .agg(
            weekly_volume=("volume", "sum"),
            weekly_sets=("sets", "sum"),
            weekly_best_1rm=("est_1rm", "max"),
            exercise_count=("exercise_title", "nunique"),
            pr_count=("is_pr", "sum")
        )
    )

    weekly_strength = (
        exercise_summary
        .groupby("week_start", as_index=False)
        .agg(
            weekly_strength_volume=("volume", "sum"),
            weekly_prs=("is_pr", "sum")
        )
    )

    daily = load_daily_features()

    daily["week_start"] = pd.to_datetime(daily["date"]).dt.to_period("W").dt.start_time

    weekly_recovery = (
        daily
            .groupby("week_start", as_index=False)
            .agg(
                weekly_trimp=("trimp_total", "sum"),
                weekly_hrv=("hrv_sdnn", "mean"),
                weekly_rhr=("resting_hr", "mean"),
                weekly_acwr=("acwr", "mean"),
                fatigue_days=("fatigue_risk", "sum")
            )
    )

    weekly_training = weekly_strength.merge(
        weekly_recovery,
        on="week_start",
        how="left"
    )

    weekly_training["strength_readiness"] = (
        (weekly_training["weekly_hrv"] / weekly_training["weekly_hrv"].mean()) * 0.4
        +
        (weekly_training["weekly_strength_volume"] / weekly_training["weekly_strength_volume"].mean()) * 0.4
        -
        (weekly_training["weekly_acwr"].fillna(1)) * 0.2
    )

    return weekly_muscle, weekly_training


def save_weekly_muscle_features(weekly_muscle: pd.DataFrame) -> None:
    create_table_query = """
    CREATE TABLE IF NOT EXISTS weekly_muscle_features (
        week_start DATE,
        primary_muscle TEXT,
        weekly_volume DOUBLE PRECISION,
        weekly_sets INT,
        weekly_best_1rm DOUBLE PRECISION,
        exercise_count INT,
        pr_count INT
    );
    """

    insert_query = """
    INSERT INTO weekly_muscle_features (
        week_start,
        primary_muscle,
        weekly_volume,
        weekly_sets,
        weekly_best_1rm,
        exercise_count,
        pr_count
    ) VALUES %s
    """

    cols = [
        "week_start",
        "primary_muscle",
        "weekly_volume",
        "weekly_sets",
        "weekly_best_1rm",
        "exercise_count",
        "pr_count",
    ]

    rows = list(weekly_muscle[cols].itertuples(index=False, name=None))

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(create_table_query)
            cur.execute("TRUNCATE TABLE weekly_muscle_features;")
            execute_values(cur, insert_query, rows)
        conn.commit()


def save_weekly_training_features(weekly_training: pd.DataFrame) -> None:
    create_table_query = """
    CREATE TABLE IF NOT EXISTS weekly_training_features (
        week_start DATE,
        weekly_strength_volume DOUBLE PRECISION,
        weekly_prs INT,
        weekly_hrv DOUBLE PRECISION,
        weekly_rhr DOUBLE PRECISION,
        weekly_trimp DOUBLE PRECISION,
        weekly_acwr DOUBLE PRECISION,
        fatigue_days INT,
        strength_readiness DOUBLE PRECISION
    );
    """

    insert_query = """
    INSERT INTO weekly_training_features (
        week_start,
        weekly_strength_volume,
        weekly_prs,
        weekly_hrv,
        weekly_rhr,
        weekly_trimp,
        weekly_acwr,
        fatigue_days,
        strength_readiness
    ) VALUES %s
    """

    cols = [
        "week_start",
        "weekly_strength_volume",
        "weekly_prs",
        "weekly_hrv",
        "weekly_rhr",
        "weekly_trimp",
        "weekly_acwr",
        "fatigue_days",
        "strength_readiness",
    ]

    rows = list(weekly_training[cols].itertuples(index=False, name=None))

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(create_table_query)
            cur.execute("TRUNCATE TABLE weekly_training_features;")
            execute_values(cur, insert_query, rows)
        conn.commit()


def main():
    weekly_muscle, weekly_training = build_weekly_strength_features()
    save_weekly_muscle_features(weekly_muscle)
    save_weekly_training_features(weekly_training)
    print(f"saved {len(weekly_muscle)} rows to weekly_muscle_features")
    print(f"saved {len(weekly_training)} rows to weekly_training_features")


if __name__ == "__main__":
    main()
