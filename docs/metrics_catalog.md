# Metrics Catalog

This document defines the main metrics currently used or planned in the `Hai` MVP.

For each metric, the goal is to capture:

- what it means
- where it comes from
- how it is computed
- how to interpret it
- when to be cautious

## Principles

Metrics in `Hai` should be:

- grounded in the database and feature pipeline
- explainable to end users
- cautious in interpretation
- explicit about missing data

The assistant should never present a metric confidently if the supporting coverage is weak.

## Strength Metrics

### Volume

Definition:
- Total lifted work, typically `weight_lbs * reps` summed across sets.

Source:
- `sets`
- derived into `exercise_progress`
- aggregated in analytics functions

Used for:
- exercise progress
- weekly strength summaries
- workload comparison

Interpretation:
- higher volume usually means more total strength work
- useful for comparing training blocks

Caution:
- does not capture effort quality by itself
- bodyweight movements may need separate handling

## Sets

Definition:
- Number of sets performed for a lift or time window.

Source:
- `sets`
- aggregated into `exercise_progress`

Used for:
- exercise comparisons
- workload summaries

Interpretation:
- more sets generally means more training exposure

Caution:
- more sets does not automatically mean better progress

## Estimated 1RM

Definition:
- An estimated one-rep max derived from submaximal sets.

Current formula:
- `weight_lbs * (1 + reps / 30)`

Source:
- computed in `strength_exercise_progress.py`

Used for:
- lift progress comparisons
- PR detection

Interpretation:
- rising estimated 1RM often suggests improving strength output

Caution:
- it is a model-based estimate, not a tested true max
- can vary with exercise selection and rep ranges

## PR Count

Definition:
- Count of new personal records based on estimated 1RM exceeding prior best values.

Source:
- `exercise_progress.is_pr`

Used for:
- strength momentum summaries
- weekly summaries

Interpretation:
- more PRs generally indicate performance progression

Caution:
- depends on the estimated 1RM logic
- can be affected by sparse history

## Recovery Metrics

### Resting Heart Rate

Definition:
- Average resting heart rate for a given day.

Source:
- Apple Health export
- stored in `apple_daily_recovery`
- rolled into `daily_features`

Used for:
- recovery trend checks
- fatigue context

Interpretation:
- elevated resting HR relative to baseline can sometimes indicate stress or poorer recovery

Caution:
- interpret against baseline, not as an isolated absolute value
- sparse coverage lowers confidence

### HRV SDNN

Definition:
- Heart Rate Variability measured as the standard deviation of NN intervals.

Source:
- Apple Health export
- stored in `apple_daily_recovery`

Used for:
- recovery trend checks
- fatigue context

Interpretation:
- HRV is commonly used as a recovery-related signal
- changes are more useful relative to a personal baseline than as a raw number alone

Caution:
- highly context-dependent
- low coverage should reduce confidence sharply
- the assistant should avoid over-interpreting HRV direction by itself

### Sleep Minutes

Definition:
- Total minutes of sleep counted from Apple sleep states considered asleep.

Source:
- Apple Health export
- stored in `apple_daily_recovery`

Used for:
- recovery summaries
- fatigue context

Interpretation:
- lower sleep relative to baseline may contribute to poorer recovery

Caution:
- missing sleep data must be described as missing, not as stable or unchanged

## Load / Fatigue Metrics

### TRIMP

Definition:
- A training load proxy derived from workout duration and heart-rate intensity.

Current implementation:
- `duration_min * hr_intensity`

Source:
- computed in `daily_features.py` from Apple workout + heart rate data

Used for:
- daily training load
- weekly training load
- fatigue context

Interpretation:
- higher TRIMP generally indicates higher cardiovascular training load

Caution:
- depends on workout validity and heart-rate density
- confidence should drop when underlying HR coverage is weak

### Acute 7-Day Load

Definition:
- Rolling 7-day sum of TRIMP.

Source:
- `daily_features.acute_7d`

Used for:
- short-term load monitoring
- fatigue context

Interpretation:
- reflects recent training demand

Caution:
- not meaningful without enough recent training records

### Chronic 28-Day Average

Definition:
- Rolling average training load across the longer baseline window.

Source:
- `daily_features.chronic_28d_avg`

Used for:
- comparing current load against longer baseline

Interpretation:
- higher chronic load can indicate accumulated training base

Caution:
- should not be interpreted on its own without context

### ACWR

Definition:
- Acute-to-Chronic Workload Ratio.

Current implementation:
- `acute_7d / (chronic_28d_avg * 7)`

Source:
- `daily_features.acwr`

Used for:
- fatigue / load-risk summaries

Interpretation:
- helps compare recent load against longer-term baseline

Caution:
- should be treated as a workload heuristic, not a diagnosis
- the assistant should avoid presenting it as a medical risk score

### Fatigue Risk

Definition:
- A rule-based fatigue flag derived from combined load and recovery signals.

Current logic:
- `acwr > 1.5`
- `rhr_delta > 5`
- `hrv_delta < -10`

Source:
- `daily_features.fatigue_risk`

Used for:
- fatigue snapshots
- weekly fatigue day counts

Interpretation:
- helps flag higher-stress periods when multiple signals align

Caution:
- rule-based heuristic only
- should be described as a training signal, not a medical conclusion

## Delta / Baseline Metrics

### RHR Delta

Definition:
- Daily resting HR minus rolling resting HR baseline.

Source:
- `daily_features.rhr_delta`

Interpretation:
- positive delta can suggest higher-than-usual resting HR

Caution:
- only meaningful with enough baseline history

### HRV Delta

Definition:
- Daily HRV minus rolling HRV baseline.

Source:
- `daily_features.hrv_delta`

Interpretation:
- negative delta may suggest below-baseline HRV

Caution:
- should not be over-interpreted in isolation

### Sleep Delta

Definition:
- Daily sleep minutes minus rolling sleep baseline.

Source:
- `daily_features.sleep_delta`

Interpretation:
- negative delta can suggest below-baseline sleep

Caution:
- missing sleep data must remain missing

## Weekly Metrics

### Weekly Strength Volume

Definition:
- Total strength-training volume aggregated by week.

Source:
- `weekly_training_features.weekly_strength_volume`

### Weekly PRs

Definition:
- Number of PRs achieved within the week.

Source:
- `weekly_training_features.weekly_prs`

### Weekly TRIMP

Definition:
- Total weekly cardiovascular load.

Source:
- `weekly_training_features.weekly_trimp`

### Weekly ACWR

Definition:
- Average ACWR over the week.

Source:
- `weekly_training_features.weekly_acwr`

### Fatigue Days

Definition:
- Count of days in the week where fatigue risk was flagged.

Source:
- `weekly_training_features.fatigue_days`

### Strength Readiness

Definition:
- A composite score combining weekly HRV, strength volume, and ACWR.

Source:
- `weekly_training_features.strength_readiness`

Interpretation:
- intended as a rough readiness indicator

Caution:
- composite heuristic
- should be explained carefully or kept secondary in user-facing answers until better calibrated

## Data Quality Metrics

These are especially important for the assistant layer.

### HRV Coverage

Definition:
- Fraction of days in the selected window with HRV values present.

### Resting HR Coverage

Definition:
- Fraction of days in the selected window with resting HR values present.

### Sleep Coverage

Definition:
- Fraction of days in the selected window with sleep values present.

### TRIMP Coverage

Definition:
- Fraction of days in the selected window with training load values present.

Used for:
- tool confidence
- quality flags
- assistant caveats

Interpretation:
- higher coverage means higher confidence in time-window insights

Caution:
- low coverage should directly lower answer confidence
- missing coverage should be mentioned explicitly

## Future Catalog Additions

As the project grows, this catalog can expand to include:

- muscle-group balance metrics
- consistency scores with clearer definitions
- bodyweight / conditioning metrics
- notification thresholds
- user-selected tracked metrics

This file should stay aligned with the code and the tool layer rather than becoming a purely theoretical list.
