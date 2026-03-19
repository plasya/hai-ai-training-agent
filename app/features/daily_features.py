import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DB_DSN = "postgresql://app:app@localhost:5432/health"
DOB = pd.Timestamp("1999-11-21", tz="UTC")


def load_apple_workout_hr() -> pd.DataFrame:
    query_aw_hr = """
    SELECT
      aw.apple_workout_id,
      aw.activity_type,
      aw.start_time,
      aw.end_time,
      aw.duration_min,
      aw.source_name,
      aw.source_version,
      COUNT(hr.bpm) AS hr_points,
      ROUND(AVG(hr.bpm))::int AS avg_bpm,
      MAX(hr.bpm) AS max_bpm,
      MIN(hr.bpm) AS min_bpm
    FROM apple_workouts aw
    LEFT JOIN heart_rate_raw hr
      ON hr.recorded_at BETWEEN aw.start_time AND aw.end_time
    GROUP BY
      aw.apple_workout_id,
      aw.activity_type,
      aw.start_time,
      aw.end_time,
      aw.duration_min,
      aw.source_name,
      aw.source_version
    ORDER BY aw.start_time;
    """
    with psycopg2.connect(DB_DSN) as conn:
        aw = pd.read_sql(query_aw_hr, conn) # type: ignore

    aw["start_time"] = pd.to_datetime(aw["start_time"], utc=True)
    aw["end_time"] = pd.to_datetime(aw["end_time"], utc=True)
    aw["date"] = aw["start_time"].dt.tz_convert(None).dt.normalize()    

    return aw


def build_apple_workout_features() -> pd.DataFrame:
    aw = load_apple_workout_hr()

    today = pd.Timestamp.now("UTC")
    age = (today - DOB).days / 365.25
    hr_max = 208 - 0.7 * age

    aw["duration_flag"] = "ok"
    aw.loc[aw["duration_min"] < 5, "duration_flag"] = "short"
    aw.loc[aw["duration_min"] > 200, "duration_flag"] = "long"

    aw["hr_density"] = aw["hr_points"] / aw["duration_min"]
    aw.loc[
        (aw["duration_flag"] == "ok") & (aw["hr_density"] < 0.3),
        "duration_flag"
    ] = "low_hr_density"

    aw["hr_intensity"] = aw["avg_bpm"] / hr_max
    aw["trimp"] = aw["duration_min"] * aw["hr_intensity"]

    aw["valid_workout"] = aw["duration_flag"] == "ok"
    aw.loc[~aw["valid_workout"], "trimp"] = pd.NA

    return aw


def load_recovery() -> pd.DataFrame:
    query_rec = """
    SELECT
      date,
      resting_hr,
      hrv_sdnn,
      sleep_minutes
    FROM apple_daily_recovery
    ORDER BY date;
    """
    with psycopg2.connect(DB_DSN) as conn:
        rec = pd.read_sql(query_rec, conn) # type: ignore

    rec["date"] = pd.to_datetime(rec["date"]).dt.tz_localize(None).dt.normalize()
    rec = rec.sort_values("date")

    rec["rhr_7d"] = rec["resting_hr"].rolling(7, min_periods=3).mean()
    rec["hrv_7d"] = rec["hrv_sdnn"].rolling(7, min_periods=3).mean()
    rec["sleep_7d"] = rec["sleep_minutes"].rolling(7, min_periods=3).mean()

    rec["rhr_delta"] = rec["resting_hr"] - rec["rhr_7d"]
    rec["hrv_delta"] = rec["hrv_sdnn"] - rec["hrv_7d"]
    rec["sleep_delta"] = rec["sleep_minutes"] - rec["sleep_7d"]

    return rec


def load_strength_daily() -> pd.DataFrame:
    query_strength = """
    SELECT
        DATE(w.start_time) AS date,
        SUM(COALESCE(s.weight_lbs, 0) * COALESCE(s.reps, 0)) AS strength_volume
    FROM workouts w
    JOIN sets s
      ON w.workout_id = s.workout_id
    GROUP BY DATE(w.start_time)
    ORDER BY date;
    """
    with psycopg2.connect(DB_DSN) as conn: 
        strength = pd.read_sql(query_strength, conn) # type: ignore

    strength["date"] = pd.to_datetime(strength["date"]).dt.tz_localize(None).dt.normalize()
    return strength


def build_daily_features() -> pd.DataFrame:
    aw = build_apple_workout_features()
    rec = load_recovery()
    strength = load_strength_daily()

    daily_load = (
        aw.groupby("date", as_index=False)["trimp"]
        .sum(min_count=1)
        .rename({"trimp": "trimp_total"}, axis=1)
    )

    daily = daily_load.merge(
        rec[[
            "date",
            "resting_hr",
            "hrv_sdnn",
            "sleep_minutes",
            "rhr_delta",
            "hrv_delta",
            "sleep_delta"
        ]],
        on="date",
        how="outer"
    ).sort_values("date")

    all_days = pd.DataFrame({
        "date": pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    })

    daily = all_days.merge(daily, on="date", how="left")

    trimp_for_roll = daily["trimp_total"].fillna(0)

    daily["acute_7d"] = trimp_for_roll.rolling(7, min_periods=7).sum()
    daily["chronic_28d_avg"] = trimp_for_roll.rolling(28, min_periods=14).mean()
    daily["acwr"] = daily["acute_7d"] / (daily["chronic_28d_avg"] * 7)
    daily["acwr"] = daily["acwr"].clip(0, 4)

    daily = daily.merge(strength, on="date", how="left")
    daily["strength_volume"] = daily["strength_volume"].fillna(0)

    daily["fatigue_risk"] = (
        (daily["acwr"] > 1.5) &
        (daily["rhr_delta"] > 5) &
        (daily["hrv_delta"] < -10)
    )

    daily["trimp_confidence"] = 0.0
    daily.loc[daily["trimp_total"].notna(), "trimp_confidence"] += 0.5
    daily.loc[daily["acwr"].notna(), "trimp_confidence"] += 0.2
    daily.loc[daily["rhr_delta"].notna(), "trimp_confidence"] += 0.15
    daily.loc[daily["hrv_delta"].notna(), "trimp_confidence"] += 0.15

    return daily


def save_daily_features(daily: pd.DataFrame) -> None:
    cols = [
        "date",
        "trimp_total",
        "resting_hr",
        "hrv_sdnn",
        "sleep_minutes",
        "rhr_delta",
        "hrv_delta",
        "sleep_delta",
        "acute_7d",
        "chronic_28d_avg",
        "acwr",
        "fatigue_risk",
        "strength_volume",
        "trimp_confidence"
    ]

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_features (
                date DATE PRIMARY KEY,
                trimp_total DOUBLE PRECISION,
                resting_hr DOUBLE PRECISION,
                hrv_sdnn DOUBLE PRECISION,
                sleep_minutes DOUBLE PRECISION,
                rhr_delta DOUBLE PRECISION,
                hrv_delta DOUBLE PRECISION,
                sleep_delta DOUBLE PRECISION,
                acute_7d DOUBLE PRECISION,
                chronic_28d_avg DOUBLE PRECISION,
                acwr DOUBLE PRECISION,
                fatigue_risk BOOLEAN,
                strength_volume DOUBLE PRECISION,
                trimp_confidence DOUBLE PRECISION
            );
            """)

            cur.execute("TRUNCATE TABLE daily_features;")

            records = list(daily[cols].itertuples(index=False, name=None))

            execute_values(
                cur,
                """
                INSERT INTO daily_features (
                    date, trimp_total, resting_hr, hrv_sdnn, sleep_minutes,
                    rhr_delta, hrv_delta, sleep_delta,
                    acute_7d, chronic_28d_avg, acwr,
                    fatigue_risk, strength_volume, trimp_confidence
                ) VALUES %s
                """,
                records
            )

        conn.commit()


def main():
    daily = build_daily_features()
    save_daily_features(daily)
    print(f"saved {len(daily)} rows to daily_features")


if __name__ == "__main__":
    main()