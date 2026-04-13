# LLM Tools Spec

This document defines the target analytics tool layer for the Hai agent.

The current repo started with narrow tools such as `compare_strength_windows` and
`get_fatigue_snapshot`. The next step is to move toward a smaller set of broader,
parameterized tool families. That gives us:

- fewer tools to maintain
- simpler routing from user prompt to analytics
- better coverage of real user questions without exposing raw DB access
- cleaner frontend and prompt-builder integration

## Design Goal

The LLM should not query raw tables directly.

Instead, it should call a small analytics layer with:
- explicit inputs
- explicit modes
- deterministic payloads
- tool-specific quality checks

## Shared Contracts

### Standard Input

All tool families should support this base input shape:

```json
{
  "user_id": "string",
  "date_start": "YYYY-MM-DD|null",
  "date_end": "YYYY-MM-DD|null",
  "timezone": "America/Los_Angeles",
  "mode": "string"
}
```

Additional tool-specific fields are allowed.

### Standard Output Envelope

All tools must return:

```json
{
  "tool_name": "string",
  "window": {
    "start": "YYYY-MM-DD",
    "end": "YYYY-MM-DD"
  },
  "payload": {},
  "data_quality": {
    "hrv_coverage": 0.0,
    "resting_hr_coverage": 0.0,
    "sleep_coverage": 0.0,
    "trimp_coverage": 0.0
  },
  "quality_flags": [],
  "confidence": "high|medium|low"
}
```

### Output Rules

- Missing values must be `null`, not `0`.
- `quality_flags` must be deterministic and enumerable.
- Confidence must be tool-specific, not globally tied to recovery coverage.
- Tools should return only the metrics needed for the requested mode.

## Tool Families

## `strength_analysis`

Broad strength analytics entry point for lift, muscle-group, and progress questions.

### Intended Questions

- How did my bench press change this month?
- Did my squat improve from November to December?
- How are my legs doing?
- Which lifts are progressing fastest?

### Input

```json
{
  "user_id": "string",
  "date_start": "YYYY-MM-DD|null",
  "date_end": "YYYY-MM-DD|null",
  "timezone": "America/Los_Angeles",
  "mode": "summary|compare|trend|prs|muscle_group",
  "exercise": "string|null",
  "muscle": "string|null",
  "granularity": "weekly|daily",
  "compounds_only": false
}
```

### Payload by Mode

#### `mode = "compare"`

```json
{
  "subject": {
    "exercise": "Bench Press (Barbell)",
    "muscle": null
  },
  "current": {
    "volume": 0,
    "sets": 0,
    "best_estimated_max": 0,
    "prs": 0
  },
  "previous": {
    "volume": 0,
    "sets": 0,
    "best_estimated_max": 0,
    "prs": 0
  },
  "trend": "improving|flat|declining"
}
```

#### `mode = "trend"`

```json
{
  "subject": {
    "exercise": "Squat (Barbell)",
    "muscle": null
  },
  "points": [
    {
      "period_start": "YYYY-MM-DD",
      "volume": 0,
      "sets": 0,
      "best_estimated_max": 0,
      "prs": 0
    }
  ]
}
```

#### `mode = "muscle_group"`

```json
{
  "subject": {
    "exercise": null,
    "muscle": "legs"
  },
  "points": [
    {
      "period_start": "YYYY-MM-DD",
      "weekly_volume": 0,
      "weekly_sets": 0,
      "weekly_best_estimated_max": 0,
      "exercise_count": 0,
      "pr_count": 0
    }
  ],
  "trend": "improving|flat|declining"
}
```

### Quality Flags

Possible flags:
- `no_data`
- `no_current_strength_data`
- `limited_previous_window`
- `low_current_strength_history`
- `limited_muscle_group_history`

## `recovery_analysis`

Broad recovery and fatigue entry point for snapshot and trend questions.

### Intended Questions

- How has my fatigue trended recently?
- Am I recovering well?
- What does my recovery look like this month?
- Did my recovery get worse over the last 2 weeks?

### Input

```json
{
  "user_id": "string",
  "date_start": "YYYY-MM-DD|null",
  "date_end": "YYYY-MM-DD|null",
  "timezone": "America/Los_Angeles",
  "mode": "snapshot|trend|summary",
  "metrics": ["resting_hr", "hrv", "sleep", "fatigue"]
}
```

### Payload by Mode

#### `mode = "snapshot"`

```json
{
  "date": "YYYY-MM-DD",
  "fatigue_risk": "low|moderate|high",
  "acute_load": 0,
  "chronic_load": 0,
  "load_balance": 0,
  "supporting": {
    "resting_hr_delta": 0,
    "hrv_delta": 0,
    "sleep_delta": 0
  }
}
```

#### `mode = "trend"`

```json
{
  "resting_hr_trend": "up|flat|down",
  "hrv_trend": "up|flat|down",
  "sleep_trend": "up|flat|down",
  "fatigue_risk_trend": "up|flat|down",
  "consistency_score": 0.0
}
```

#### `mode = "summary"`

```json
{
  "average_resting_hr": 0,
  "average_hrv": 0,
  "average_sleep_minutes": 0,
  "high_fatigue_days": 0,
  "overall_recovery_direction": "improving|flat|declining|mixed"
}
```

### Quality Flags

Possible flags:
- `no_data`
- `missing_hrv`
- `missing_resting_hr`
- `missing_sleep`
- `missing_trimp`
- `low_hrv_coverage`
- `low_resting_hr_coverage`
- `low_sleep_coverage`
- `low_trimp_coverage`

## `cardio_load_analysis`

Broad cardio and load-analysis entry point built from workout HR-derived load.

### Intended Questions

- How has my cardio load changed over the past month?
- Is my training load going up or down?
- What has my recent cardio workload looked like?
- How does recent load compare to my baseline?

### Input

```json
{
  "user_id": "string",
  "date_start": "YYYY-MM-DD|null",
  "date_end": "YYYY-MM-DD|null",
  "timezone": "America/Los_Angeles",
  "mode": "summary|trend|load_balance"
}
```

### Payload by Mode

#### `mode = "summary"`

```json
{
  "total_training_load": 0,
  "average_daily_load": 0,
  "active_load_days": 0
}
```

#### `mode = "trend"`

```json
{
  "trend": "up|flat|down",
  "total_training_load": 0,
  "average_daily_load": 0
}
```

#### `mode = "load_balance"`

```json
{
  "latest_acute_load": 0,
  "latest_chronic_load": 0,
  "latest_load_balance": 0,
  "balance_band": "low|moderate|high"
}
```

### Quality Flags

Possible flags:
- `no_data`
- `missing_trimp`
- `low_trimp_coverage`

## `workout_session_analysis`

Broad workout-session analytics entry point for individual workout inspection.

### Intended Questions

- What were my hardest workouts this month?
- Which sessions had the highest heart rate?
- What were my longest sessions?
- Which cardio sessions were most intense?

### Input

```json
{
  "user_id": "string",
  "date_start": "YYYY-MM-DD|null",
  "date_end": "YYYY-MM-DD|null",
  "timezone": "America/Los_Angeles",
  "mode": "hardest|longest|highest_hr",
  "activity_type": "string|null",
  "sort_by": "intensity|duration|avg_hr|max_hr",
  "limit": 3
}
```

### Payload by Mode

#### `mode = "hardest"`

```json
{
  "workouts": [
    {
      "date": "YYYY-MM-DD HH:MM",
      "activity_type": "string",
      "duration_min": 0,
      "avg_bpm": 0,
      "max_bpm": 0
    }
  ],
  "hr_workout_coverage": 0.0
}
```

#### `mode = "longest"`

```json
{
  "workouts": [
    {
      "date": "YYYY-MM-DD HH:MM",
      "activity_type": "string",
      "duration_min": 0,
      "avg_bpm": 0,
      "max_bpm": 0
    }
  ],
  "hr_workout_coverage": 0.0
}
```

#### `mode = "highest_hr"`

```json
{
  "workouts": [
    {
      "date": "YYYY-MM-DD HH:MM",
      "activity_type": "string",
      "duration_min": 0,
      "avg_bpm": 0,
      "max_bpm": 0
    }
  ],
  "hr_workout_coverage": 0.0
}
```

### Quality Flags

Possible flags:
- `no_data`
- `missing_workout_hr`
- `low_workout_hr_coverage`

## Current-to-Target Mapping

These are the current narrow tools and where they belong in the broader design:

- `compare_strength_windows` -> `strength_analysis(mode="compare")`
- `get_weekly_training_summary` -> partly `strength_analysis(mode="summary")` and partly `cardio_load_analysis(mode="summary")`
- `get_fatigue_snapshot` -> `recovery_analysis(mode="snapshot")`
- `get_recovery_trend` -> `recovery_analysis(mode="trend")`
- `get_cardio_load_trend` -> `cardio_load_analysis(mode="trend")`
- `get_highest_intensity_workouts` -> `workout_session_analysis(mode="hardest")`

## Prompt Builder Mapping

- Lift-specific progress question -> `strength_analysis`
- Muscle-group question -> `strength_analysis(mode="muscle_group")`
- Fatigue or recovery question -> `recovery_analysis`
- Cardio/training-load question -> `cardio_load_analysis`
- Hardest / longest / highest-HR workout question -> `workout_session_analysis`

## Validation Checklist

Before any tool output is passed to the LLM:

- Schema validation passes.
- Window is explicit.
- Missing vs zero is preserved.
- Tool mode is explicit.
- Confidence is derived from tool-specific rules.
- `quality_flags` reflect only the data relevant to that tool family.
- Payload includes only the metrics needed to answer the specific question.
