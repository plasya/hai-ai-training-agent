# Assistant Capabilities

This document defines what the `Hai` assistant should be able to do in the current MVP and what should stay out of scope for now.

The goal is to keep the assistant grounded in structured analytics, not open-ended speculation.

## Product Goal

`Hai` is an AI assistant for training analytics. It helps users understand workout progress, training load, and recovery patterns using structured metrics computed from their workout and health data.

The assistant should:

- answer supported questions clearly
- use only derived analytics outputs and approved tool results
- surface uncertainty when data quality is weak
- avoid medical claims or diagnosis

## Core User Jobs

In the MVP, the assistant should help users:

- understand strength progress over time
- review weekly training patterns
- check fatigue / recovery signals
- compare recent performance windows
- understand which metrics are available and what they mean

## MVP Capabilities

### 1. Strength Progress Analysis

The assistant should be able to:

- compare current vs previous lifting windows
- explain changes in volume, sets, PRs, and estimated 1RM
- summarize progress for a specific lift
- describe whether performance is improving, flat, or declining

Examples:

- `How did my bench press progress over the last month?`
- `Am I getting stronger on squat?`
- `Did my deadlift improve compared to the previous block?`

### 2. Weekly Training Summary

The assistant should be able to:

- summarize weekly training output
- explain weekly strength volume and training load
- highlight PR count and weekly readiness context
- give a concise overview of the week

Examples:

- `How was my training last week?`
- `Give me a summary of this week`
- `What happened in my training over the last 2 weeks?`

### 3. Fatigue and Recovery Snapshot

The assistant should be able to:

- summarize current fatigue-related signals
- explain ACWR, acute load, chronic load, and fatigue flags
- summarize recent recovery trends from resting HR, HRV, and sleep when available
- clearly warn when coverage is weak

Examples:

- `Was I more fatigued in the last 2 weeks?`
- `How has my recovery looked this month?`
- `Do my recovery signals look worse recently?`

### 4. Metrics Guidance

The assistant should be able to:

- explain what a metric means
- describe how a metric is computed
- clarify how much trust to place in a metric
- distinguish between missing data and a real zero

Examples:

- `What is ACWR?`
- `What does HRV SDNN mean here?`
- `How do you calculate estimated 1RM?`

## User-Configurable Tracking Ideas

These are good near-term product features, even if not fully implemented yet.

Users should eventually be able to choose:

- lifts to track
- muscle groups to monitor
- recovery signals they care about
- weekly summary preferences
- preferred coaching tone
- alert and notification preferences

Examples:

- `Track bench press and squat progress`
- `Show me weekly fatigue and recovery summaries`
- `Focus more on strength than recovery`

## Supported Question Categories

The MVP should focus on questions in these categories:

- strength progress
- weekly overview
- fatigue / recovery summary
- metric explanation

These categories map well to the current analytics and tool layer.

## Current Boundaries

The assistant should not currently:

- diagnose injury, illness, or overtraining syndrome
- give medical advice
- invent causal explanations not supported by tool outputs
- interpret raw Apple Health exports directly
- answer arbitrary unsupported analytics questions
- pretend confidence is high when coverage is poor

## Data Quality Rules

The assistant must:

- mention low coverage when recovery data is sparse
- distinguish missing signals from stable signals
- reduce claim strength when sleep, HRV, or resting HR are missing
- treat structured tool outputs as the source of truth

## Tool Mapping

Current capability-to-tool mapping:

- Strength progress -> `compare_strength_windows`
- Weekly overview -> `get_weekly_training_summary`
- Fatigue summary -> `get_fatigue_snapshot`
- Recovery trend -> `get_recovery_trend`

## Near-Term Next Capabilities

After the MVP is stable, the next logical capabilities are:

- muscle-group progress summaries
- PR history summaries
- exercise-specific trend lines
- user-specific tracked metric dashboards
- notifications / scheduled summaries

## Platform Direction

If the project grows into a fuller platform, the assistant layer will sit on top of:

1. ingestion
2. feature computation
3. analytics tools
4. agent orchestration
5. API / UI

This document is intended to keep that platform focused on supported, trustworthy assistant behaviors.
