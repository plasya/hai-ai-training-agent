import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DB_DSN = "postgresql://app:app@localhost:5432/health"


def load_strength_base() -> pd.DataFrame:
    query = """
    SELECT
        w.workout_id,
        w.title,
        w.start_time,
        w.end_time,
        s.id AS set_row_id,
        s.row_in_workout,
        s.exercise_title,
        s.set_index,
        s.set_type,
        s.weight_lbs,
        s.reps,
        s.distance_miles,
        s.duration_seconds,
        s.rpe,
        s.superset_id,
        s.exercise_notes
    FROM workouts w
    JOIN sets s
      ON w.workout_id = s.workout_id
    ORDER BY w.start_time, s.row_in_workout;
    """
    with psycopg2.connect(DB_DSN) as conn:
        df = pd.read_sql(query, conn) # type: ignore

    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
    df["date"] = pd.to_datetime(df["start_time"]).dt.date
    df["end_time"] = pd.to_datetime(df["end_time"], utc=True)

    return df


def build_exercise_progress() -> pd.DataFrame:
    strength_base = load_strength_base()

    strength_base["volume"] = strength_base["weight_lbs"] * strength_base["reps"]
    strength_base["est_1rm"] = strength_base["weight_lbs"] * (1 + strength_base["reps"] / 30)

    exercise_summary = (
        strength_base
        .groupby(["workout_id", "exercise_title"], as_index=False)
        .agg(
            sets=("set_index", "count"),
            volume=("volume", "sum"),
            top_weight=("weight_lbs", "max"),
            top_est_1rm=("est_1rm", "max"),
        )
    )

    workout_dates = strength_base[["workout_id", "start_time", "date"]].drop_duplicates()
    exercise_summary = exercise_summary.merge(workout_dates, on="workout_id", how="left")
    exercise_summary = exercise_summary.sort_values(["exercise_title", "date", "start_time"])

    exercise_summary["prev_best_1rm"] = (
        exercise_summary.groupby("exercise_title")["top_est_1rm"].cummax().shift(1)
    )

    exercise_summary["is_pr"] = (
        exercise_summary["top_est_1rm"] > exercise_summary["prev_best_1rm"]
    ).fillna(False)

    return exercise_summary


def save_exercise_progress(exercise_summary: pd.DataFrame) -> None:
    create_table_query = """
    CREATE TABLE IF NOT EXISTS exercise_progress (
        workout_id BIGINT,
        date DATE,
        exercise_title TEXT,
        sets INT,
        volume DOUBLE PRECISION,
        top_weight DOUBLE PRECISION,
        est_1rm DOUBLE PRECISION,
        prev_best_1rm DOUBLE PRECISION,
        is_pr BOOLEAN
    );
    """

    insert_query = """
    INSERT INTO exercise_progress (
        workout_id,
        date,
        exercise_title,
        sets,
        volume,
        top_weight,
        est_1rm,
        prev_best_1rm,
        is_pr
    ) VALUES %s
    """

    cols = [
        "workout_id",
        "date",
        "exercise_title",
        "sets",
        "volume",
        "top_weight",
        "top_est_1rm",
        "prev_best_1rm",
        "is_pr",
    ]

    rows = list(exercise_summary[cols].itertuples(index=False, name=None))

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(create_table_query)
            cur.execute("TRUNCATE TABLE exercise_progress;")
            execute_values(cur, insert_query, rows)
        conn.commit()


def main():
    exercise_summary = build_exercise_progress()
    save_exercise_progress(exercise_summary)
    print(f"saved {len(exercise_summary)} rows to exercise_progress")


if __name__ == "__main__":
    main()