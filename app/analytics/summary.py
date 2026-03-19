from .db import query

def training_summary(start, end):

    workouts = query(f"""
        SELECT COUNT(*) as workouts
        FROM workouts
        WHERE start_time BETWEEN '{start}' AND '{end}'
    """)

    volume = query(f"""
        SELECT SUM(weight_lbs * reps) as volume
        FROM sets s
        JOIN workouts w
        ON s.workout_id = w.workout_id
        WHERE w.start_time BETWEEN '{start}' AND '{end}'
    """)

    top_exercises = query(f"""
    SELECT
        s.exercise_title,
        SUM(COALESCE(s.weight_lbs, 0) * COALESCE(s.reps, 0)) AS volume
    FROM sets s
    JOIN workouts w
      ON s.workout_id = w.workout_id
    WHERE w.start_time BETWEEN '{start}' AND '{end}'
    GROUP BY s.exercise_title
    HAVING SUM(COALESCE(s.weight_lbs, 0) * COALESCE(s.reps, 0)) > 0
    ORDER BY volume DESC
    LIMIT 5
    """)
    workout_volumes = query(f"""
    SELECT
        w.workout_id,
        w.title,
        w.start_time,
        SUM(COALESCE(s.weight_lbs, 0) * COALESCE(s.reps, 0)) AS volume
    FROM workouts w
    JOIN sets s
      ON w.workout_id = s.workout_id
    WHERE w.start_time BETWEEN '{start}' AND '{end}'
    GROUP BY w.workout_id, w.title, w.start_time
    ORDER BY w.start_time DESC
    """)

    return {
        "workouts": int(workouts.iloc[0]["workouts"]),
        "volume": float(volume.iloc[0]["volume"] or 0),
        "top_exercises": top_exercises.to_dict("records"),
        "workout_volumes": workout_volumes.to_dict("records")
    }