import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DB_DSN = "postgresql://app:app@localhost:5432/health"
CSV_PATH = "data/workout_data.csv"
MAX_BIGINT = 9223372036854775807  # Postgres BIGINT max

def to_ts(x):
    if pd.isna(x) or x == "":
        return None
    return pd.to_datetime(x, utc=True, errors="coerce")

def py(x):
    if pd.isna(x):
        return None
    # Convert numpy/pandas scalars to native Python types
    if hasattr(x, "item"):
        return x.item()
    return x

def main():
    df = pd.read_csv(CSV_PATH)
    #1 Normalize column names
    df.columns = [c.strip() for c in df.columns]

    #2 Normalize timestamps 
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True, errors="coerce")
    df["end_time"] = pd.to_datetime(df["end_time"], utc=True, errors="coerce")

    key_df = df[["title", "start_time", "end_time"]].astype(str)
    h = pd.util.hash_pandas_object(key_df, index=False).astype("uint64")
    df["workout_id"] = (h % MAX_BIGINT).astype("int64")

    #3 Preserve CSV order and assign a stable row number within each workout
    df["_row"] = range(len(df))
    df["row_in_workout"] = df.sort_values("_row").groupby("workout_id").cumcount()


    #4 Coerce numerics safely (turn junk into NaN/None)
    for col in ["set_index", "reps"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    for col in ["weight_lbs", "distance_miles", "duration_seconds", "rpe"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ---- build workouts (dedupe by workout_id) ----
    workouts = (
        df[["workout_id", "title", "start_time", "end_time", "description"]]
        .dropna(subset=["workout_id", "title", "start_time"])
        .drop_duplicates(subset=["workout_id"])
    )

    # ---- build sets ----
    sets = df[
        [
            "workout_id","row_in_workout",
            "exercise_title",
            "set_index",
            "set_type",
            "weight_lbs",
            "reps",
            "distance_miles",
            "duration_seconds",
            "rpe",
            "superset_id",
            "exercise_notes",
        ]
    ].dropna(subset=["workout_id", "exercise_title", "set_index"])

    # Convert pandas NA to Python None for psycopg2
    workouts_rows = [tuple(py(x) for x in row) for row in workouts.itertuples(index=False, name=None)]
    sets_rows = [tuple(py(x) for x in row) for row in sets.itertuples(index=False, name=None)]
    dups = sets.duplicated(subset=["workout_id","exercise_title","set_index"], keep=False)
    sets = sets.sort_values(["workout_id","exercise_title","set_index"]).drop_duplicates(
    subset=["workout_id","exercise_title","set_index"], keep="last"
)

    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO workouts (workout_id, title, start_time, end_time, description)
                VALUES %s
                ON CONFLICT (workout_id) DO UPDATE
                SET title = EXCLUDED.title,
                    start_time = EXCLUDED.start_time,
                    end_time = EXCLUDED.end_time,
                    description = EXCLUDED.description
                """,
                workouts_rows,
                page_size=1000,
            )

            execute_values(
                cur,
                """
                INSERT INTO sets (
                workout_id, row_in_workout, exercise_title, set_index, set_type,
                weight_lbs, reps, distance_miles, duration_seconds, rpe,
                superset_id, exercise_notes
                )
                VALUES %s
                ON CONFLICT (workout_id, row_in_workout) DO UPDATE
                SET exercise_title = EXCLUDED.exercise_title,
                    set_index = EXCLUDED.set_index,
                    set_type = EXCLUDED.set_type,
                    weight_lbs = EXCLUDED.weight_lbs,
                    reps = EXCLUDED.reps,
                    distance_miles = EXCLUDED.distance_miles,
                    duration_seconds = EXCLUDED.duration_seconds,
                    rpe = EXCLUDED.rpe,
                    superset_id = EXCLUDED.superset_id,
                    exercise_notes = EXCLUDED.exercise_notes;

                """,
                sets_rows,
                page_size=5000,
            )

        conn.commit()
        print(f"✅ Ingested: workouts={len(workouts)}, sets={len(sets)}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()