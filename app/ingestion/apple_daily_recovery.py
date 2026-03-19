import xml.etree.ElementTree as ET
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DB_DSN = "postgresql://app:app@localhost:5432/health"
XML_PATH = "../../data/raw/apple_health_export/export.xml"


def parse_dt(x):
    return pd.to_datetime(x, utc=True, errors="coerce")


def extract_recovery_data():
    tree = ET.parse(XML_PATH)
    root = tree.getroot()

    resting_rows = []
    hrv_rows = []
    sleep_rows = []

    for record in root.findall("Record"):
        rtype = record.attrib.get("type")
        start = parse_dt(record.attrib.get("startDate"))
        end = parse_dt(record.attrib.get("endDate"))
        value = record.attrib.get("value")

        if pd.isna(start):
            continue

        # Resting heart rate
        if rtype == "HKQuantityTypeIdentifierRestingHeartRate":
            try:
                resting_rows.append({
                    "date": start.date(),
                    "resting_hr": float(value)
                })
            except (TypeError, ValueError):
                continue

        # HRV SDNN
        elif rtype == "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
            try:
                hrv_rows.append({
                    "date": start.date(),
                    "hrv_sdnn": float(value)
                })
            except (TypeError, ValueError):
                continue

        # Sleep
        elif rtype == "HKCategoryTypeIdentifierSleepAnalysis":
            if pd.isna(end):
                continue

            # Only count actual sleep states, not "in bed" if you want cleaner sleep time
            sleep_value = value or ""
            if "Asleep" in sleep_value or sleep_value in {
                "HKCategoryValueSleepAnalysisAsleep",
                "HKCategoryValueSleepAnalysisAsleepCore",
                "HKCategoryValueSleepAnalysisAsleepDeep",
                "HKCategoryValueSleepAnalysisAsleepREM",
                "HKCategoryValueSleepAnalysisAsleepUnspecified",
            }:
                minutes = (end - start).total_seconds() / 60.0
                if minutes > 0:
                    sleep_rows.append({
                        "date": start.date(),
                        "sleep_minutes": minutes
                    })

    resting_df = pd.DataFrame(resting_rows)
    hrv_df = pd.DataFrame(hrv_rows)
    sleep_df = pd.DataFrame(sleep_rows)

    # Aggregate by day
    if not resting_df.empty:
        resting_daily = (
            resting_df.groupby("date", as_index=False)["resting_hr"]
            .mean()
        )
    else:
        resting_daily = pd.DataFrame(columns=["date", "resting_hr"])

    if not hrv_df.empty:
        hrv_daily = (
            hrv_df.groupby("date", as_index=False)["hrv_sdnn"]
            .mean()
        )
    else:
        hrv_daily = pd.DataFrame(columns=["date", "hrv_sdnn"])

    if not sleep_df.empty:
        sleep_daily = (
            sleep_df.groupby("date", as_index=False)["sleep_minutes"]
            .sum()
        )
    else:
        sleep_daily = pd.DataFrame(columns=["date", "sleep_minutes"])

    # Outer join so missing signals don't get dropped
    recovery = resting_daily.merge(hrv_daily, on="date", how="outer")
    recovery = recovery.merge(sleep_daily, on="date", how="outer")
    recovery = recovery.sort_values("date").reset_index(drop=True)

    return recovery


def upsert_recovery(df: pd.DataFrame):
    if df.empty:
        print("No recovery data found.")
        return

    create_sql = """
    CREATE TABLE IF NOT EXISTS apple_daily_recovery (
        date DATE PRIMARY KEY,
        resting_hr DOUBLE PRECISION,
        hrv_sdnn DOUBLE PRECISION,
        sleep_minutes DOUBLE PRECISION
    );
    """

    rows = [
        (
            row.date,
            None if pd.isna(row.resting_hr) else float(row.resting_hr),
            None if pd.isna(row.hrv_sdnn) else float(row.hrv_sdnn),
            None if pd.isna(row.sleep_minutes) else float(row.sleep_minutes),
        )
        for row in df.itertuples(index=False)
    ]

    upsert_sql = """
    INSERT INTO apple_daily_recovery (date, resting_hr, hrv_sdnn, sleep_minutes)
    VALUES %s
    ON CONFLICT (date) DO UPDATE SET
        resting_hr = EXCLUDED.resting_hr,
        hrv_sdnn = EXCLUDED.hrv_sdnn,
        sleep_minutes = EXCLUDED.sleep_minutes;
    """

    with psycopg2.connect(DB_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(create_sql)
            execute_values(cur, upsert_sql, rows, page_size=1000)
        conn.commit()

    print(f"Upserted {len(df)} daily recovery rows.")


def main():
    df = extract_recovery_data()
    print(df.head())
    upsert_recovery(df)


if __name__ == "__main__":
    main()