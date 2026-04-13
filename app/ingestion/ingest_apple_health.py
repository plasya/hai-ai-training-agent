from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values


DB_DSN = "postgresql://app:app@localhost:5432/health"
BASE_DIR = Path(__file__).resolve().parents[2]
LOOKBACK_DAYS = 14


def parse_dt(value: str | None) -> pd.Timestamp | pd.NaT:
    return pd.to_datetime(value, utc=True, errors="coerce")


def to_utc_timestamp(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def resolve_xml_path() -> Path:
    candidates = [
        BASE_DIR / "data" / "raw" / "export_2_unzipped" / "apple_health_export" / "export.xml",
        BASE_DIR / "data" / "raw" / "apple_health_export" / "export.xml",
        Path.home() / "Downloads" / "apple_health_export" / "export.xml",
    ]
    existing = [p for p in candidates if p.exists()]
    if not existing:
        raise FileNotFoundError("No Apple export.xml found in data/raw/apple_health_export or Downloads/apple_health_export")
    selected = max(existing, key=lambda p: p.stat().st_mtime)
    print(f"Using Apple export: {selected}")
    return selected


def get_last_heart_rate_time() -> pd.Timestamp | None:
    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(recorded_at) FROM heart_rate_raw;")
            row = cur.fetchone()

    if row is None or row[0] is None:
        return None
    return to_utc_timestamp(row[0])


def get_last_apple_workout_time() -> pd.Timestamp | None:
    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MAX(start_time) FROM apple_workouts;")
            row = cur.fetchone()

    if row is None or row[0] is None:
        return None
    return to_utc_timestamp(row[0])


def ensure_tables() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS heart_rate_raw (
        id BIGSERIAL PRIMARY KEY,
        recorded_at TIMESTAMPTZ NOT NULL,
        bpm INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_hr_time ON heart_rate_raw(recorded_at);

    CREATE TABLE IF NOT EXISTS apple_workouts (
      apple_workout_id BIGSERIAL PRIMARY KEY,
      activity_type TEXT NOT NULL,
      start_time TIMESTAMPTZ NOT NULL,
      end_time TIMESTAMPTZ NOT NULL,
      duration_min DOUBLE PRECISION,
      source_name TEXT,
      source_version TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_apple_workouts_time
      ON apple_workouts (start_time, end_time);

    CREATE INDEX IF NOT EXISTS idx_apple_workouts_type
      ON apple_workouts (activity_type);
    """

    dedupe_sql = """
    DELETE FROM heart_rate_raw a
    USING heart_rate_raw b
    WHERE a.id < b.id
      AND a.recorded_at = b.recorded_at
      AND a.bpm = b.bpm;

    DELETE FROM apple_workouts a
    USING apple_workouts b
    WHERE a.apple_workout_id < b.apple_workout_id
      AND a.activity_type = b.activity_type
      AND a.start_time = b.start_time
      AND a.end_time = b.end_time;
    """

    unique_index_sql = """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_hr_recorded_at_bpm
      ON heart_rate_raw (recorded_at, bpm);

    CREATE UNIQUE INDEX IF NOT EXISTS uq_apple_workout_identity
      ON apple_workouts (activity_type, start_time, end_time);
    """

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
            cur.execute(dedupe_sql)
            cur.execute(unique_index_sql)
        conn.commit()


def extract_heart_rate(root: ET.Element, full_refresh: bool = False) -> pd.DataFrame:
    cutoff = None
    if not full_refresh:
        last_time = get_last_heart_rate_time()
        if last_time is not None:
            cutoff = last_time - pd.Timedelta(days=LOOKBACK_DAYS)
            print(f"Incremental Apple HR import: keeping records from {cutoff.date()} onward")

    rows: list[dict[str, object]] = []
    for record in root.findall("Record"):
        if record.attrib.get("type") != "HKQuantityTypeIdentifierHeartRate":
            continue

        recorded_at = parse_dt(record.attrib.get("startDate"))
        if pd.isna(recorded_at):
            continue
        if cutoff is not None and recorded_at < cutoff:
            continue

        try:
            bpm = int(float(record.attrib.get("value", "")))
        except (TypeError, ValueError):
            continue

        rows.append({"recorded_at": recorded_at, "bpm": bpm})

    if not rows:
        return pd.DataFrame(columns=["recorded_at", "bpm"])

    hr_df = pd.DataFrame(rows)
    hr_df = hr_df.drop_duplicates(subset=["recorded_at", "bpm"]).sort_values("recorded_at")
    return hr_df


def extract_apple_workouts(root: ET.Element, full_refresh: bool = False) -> pd.DataFrame:
    cutoff = None
    if not full_refresh:
        last_time = get_last_apple_workout_time()
        if last_time is not None:
            cutoff = last_time - pd.Timedelta(days=LOOKBACK_DAYS)
            print(f"Incremental Apple workout import: keeping workouts from {cutoff.date()} onward")

    rows: list[dict[str, object]] = []
    for workout in root.findall("Workout"):
        attrs = workout.attrib
        start = parse_dt(attrs.get("startDate"))
        end = parse_dt(attrs.get("endDate"))

        if pd.isna(start) or pd.isna(end):
            continue
        if cutoff is not None and start < cutoff:
            continue

        duration_value = attrs.get("duration")
        duration_min = None
        if duration_value not in {None, ""}:
            try:
                duration_min = float(duration_value)
            except ValueError:
                duration_min = None

        rows.append(
            {
                "activity_type": attrs.get("workoutActivityType"),
                "start_time": start,
                "end_time": end,
                "duration_min": duration_min,
                "source_name": attrs.get("sourceName"),
                "source_version": attrs.get("sourceVersion"),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "activity_type",
                "start_time",
                "end_time",
                "duration_min",
                "source_name",
                "source_version",
            ]
        )

    workouts_df = pd.DataFrame(rows)
    workouts_df = workouts_df.drop_duplicates(
        subset=["activity_type", "start_time", "end_time"]
    ).sort_values("start_time")
    return workouts_df


def upsert_heart_rate(df: pd.DataFrame) -> None:
    if df.empty:
        print("No new Apple heart rate rows to ingest.")
        return

    rows = [
        (row.recorded_at.to_pydatetime(), int(row.bpm))
        for row in df.itertuples(index=False)
    ]

    sql = """
    INSERT INTO heart_rate_raw (recorded_at, bpm)
    VALUES %s
    ON CONFLICT (recorded_at, bpm) DO NOTHING;
    """

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=5000)
        conn.commit()

    print(f"Upserted {len(rows)} Apple heart rate rows.")


def upsert_apple_workouts(df: pd.DataFrame) -> None:
    if df.empty:
        print("No new Apple workout rows to ingest.")
        return

    rows = [
        (
            row.activity_type,
            row.start_time.to_pydatetime(),
            row.end_time.to_pydatetime(),
            row.duration_min,
            row.source_name,
            row.source_version,
        )
        for row in df.itertuples(index=False)
    ]

    sql = """
    INSERT INTO apple_workouts
      (activity_type, start_time, end_time, duration_min, source_name, source_version)
    VALUES %s
    ON CONFLICT (activity_type, start_time, end_time) DO UPDATE SET
      duration_min = EXCLUDED.duration_min,
      source_name = EXCLUDED.source_name,
      source_version = EXCLUDED.source_version;
    """

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=2000)
        conn.commit()

    print(f"Upserted {len(rows)} Apple workout rows.")


def main(full_refresh: bool = False) -> None:
    ensure_tables()
    tree = ET.parse(resolve_xml_path())
    root = tree.getroot()

    hr_df = extract_heart_rate(root, full_refresh=full_refresh)
    workouts_df = extract_apple_workouts(root, full_refresh=full_refresh)

    upsert_heart_rate(hr_df)
    upsert_apple_workouts(workouts_df)


if __name__ == "__main__":
    main()
