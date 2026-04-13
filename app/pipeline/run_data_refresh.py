from app.ingestion.ingest_apple_health import main as ingest_apple_health
from app.ingestion.apple_daily_recovery import main as ingest_apple_recovery
from app.ingestion.ingest_hevy import main as ingest_hevy
from app.pipeline.build_all_features import main as build_features


def main() -> None:
    print("Ingesting Apple workouts and heart rate...")
    ingest_apple_health()

    print("Ingesting Apple daily recovery...")
    ingest_apple_recovery()

    print("Ingesting Hevy workouts...")
    ingest_hevy()

    print("Rebuilding derived features...")
    build_features()

    print("Data refresh completed successfully.")


if __name__ == "__main__":
    main()
