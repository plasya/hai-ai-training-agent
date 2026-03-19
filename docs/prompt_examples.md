# Prompt Examples

This file collects representative user prompts and the intended agent/tool behavior for the `Hai` MVP.

Use this document for:

- prompt design iteration
- regression testing
- demo preparation
- resume / portfolio examples

The matching code-based examples live in [`tests/llm_prompt_examples.py`](/Users/lasya/hai/tests/llm_prompt_examples.py).

## Example 1: Strength Progress

### User prompt

`How did my bench press improve from December 1, 2025 to January 15, 2026?`

### Expected tools

- `compare_strength_windows`

### What the answer should do

- answer directly whether progress improved, stayed flat, or declined
- cite volume, sets, estimated 1RM, and PR count
- mention uncertainty if coverage or strength history is sparse

## Example 2: Fatigue Trend

### User prompt

`Was I more fatigued in the last 2 weeks?`

### Expected tools

- `get_fatigue_snapshot`
- `get_recovery_trend`

### What the answer should do

- summarize whether fatigue appears elevated or not
- reference ACWR and recent recovery signals
- reduce confidence if HRV / resting HR / sleep coverage is low

## Example 3: Weekly Overview

### User prompt

`How was my training last week?`

### Expected tools

- `get_weekly_training_summary`

### What the answer should do

- summarize weekly load and performance in plain language
- mention strength volume, TRIMP, PRs, and readiness where available
- include a short next-best action

## Example 4: Recovery Check

### User prompt

`How has my recovery looked this month?`

### Expected tools

- `get_recovery_trend`

### What the answer should do

- summarize resting HR, HRV, and sleep trends
- clearly distinguish missing data from stable trends
- avoid overstating conclusions from low coverage

## Response Shape

For MVP, a good final answer should follow this structure:

1. direct answer
2. evidence from metrics
3. confidence / caveats
4. next action

## Notes

- keep prompts realistic and user-like
- include both strong-data and weak-data cases
- keep at least one example per major tool
- expand this file as new tools are added
