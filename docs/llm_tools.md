# LLM Tools Spec

This document defines the structured analytics tools that the LLM layer can call.

## Shared Contracts

### Standard Input
All tools should accept:
- `user_id: str`
- `date_start: date | null`
- `date_end: date | null`
- `timezone: str` (default `America/Los_Angeles`)

### Standard Output Envelope
All tools must return:
```json
{
  "tool_name": "string",
  "window": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
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

### Quality Rules
- Coverage values are fractions in `[0, 1]`.
- Missing metrics must be `null`, not `0`.
- `quality_flags` must be deterministic and enumerable.

## Tool Catalog

## `compare_strength_windows`
Compares a current window to a previous same-length window.

`payload`:
```json
{
  "current": { "volume": 0, "sets": 0, "best_1rm": 0, "prs": 0 },
  "previous": { "volume": 0, "sets": 0, "best_1rm": 0, "prs": 0 },
  "trend": "improving|flat|declining"
}
```

## `get_fatigue_snapshot`
Summarizes short-term load and recovery mismatch.

`payload`:
```json
{
  "acute_7d": 0,
  "chronic_28d_avg": 0,
  "acwr": 0,
  "fatigue_risk": "low|moderate|high",
  "supporting": {
    "rhr_delta": 0,
    "hrv_delta": 0,
    "sleep_delta": 0
  }
}
```

## `get_recovery_trend`
Returns trend over the selected date range.

`payload`:
```json
{
  "resting_hr_trend": "up|flat|down",
  "hrv_trend": "up|flat|down",
  "sleep_trend": "up|flat|down",
  "consistency_score": 0.0
}
```

## `get_muscle_group_progress`
Summarizes weekly progress by primary muscle group.

`payload`:
```json
{
  "muscle_group": "string",
  "weekly_volume": 0,
  "weekly_sets": 0,
  "weekly_best_1rm": 0,
  "exercise_count": 0,
  "pr_count": 0,
  "trend": "improving|flat|declining"
}
```

## `get_weekly_training_summary`
High-level weekly performance and readiness summary.

`payload`:
```json
{
  "weekly_strength_volume": 0,
  "weekly_prs": 0,
  "weekly_trimp": 0,
  "weekly_acwr": 0,
  "fatigue_days": 0,
  "strength_readiness": "low|medium|high"
}
```

## Prompt Builder Mapping

- Strength change question -> `compare_strength_windows`
- Fatigue/recovery question -> `get_fatigue_snapshot` + `get_recovery_trend`
- Muscle-specific progress question -> `get_muscle_group_progress`
- Weekly overview question -> `get_weekly_training_summary`

## Validation Checklist

Before any tool output is passed to the LLM:
- Schema validation passes.
- Coverage fields are present.
- Missing vs zero is preserved.
- Confidence is derived from explicit rules.
- `quality_flags` are non-empty when coverage is low.
