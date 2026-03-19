from app.features.daily_features import main as build_daily
from app.features.strength_exercise_progress import main as build_strength
from app.features.weekly_strength_features import main as build_weekly


def main():

    print("Building daily features...")
    build_daily()

    print("Building exercise progress...")
    build_strength()

    print("Building weekly strength features...")
    build_weekly()

    print("All features updated successfully")


if __name__ == "__main__":
    main()
