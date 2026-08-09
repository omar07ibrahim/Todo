# PlanForge exact-planning contract

PlanForge is a bounded classical-AI / operations-research planner for one person and one day. It turns a small dependency graph of non-preemptive tasks into an independently verifiable schedule. This document defines claims before implementation.

## Input boundary

A request is exact `planforge.request.v1` JSON with a 15-minute-aligned start, a 60–720 minute horizon contained in one civil day, and 1–9 tasks. Every task has a canonical slug, trimmed control-free title, 15–240 minute duration, priority 1–100, due minute, earliest start, and an acyclic list of in-request dependencies.

Unknown fields, booleans in integer fields, duplicate identifiers/dependencies, cycles, unknown references, control characters, non-slot durations, and oversized requests fail closed. Canonical serialization is sorted-key ASCII JSON with one trailing newline; task order is normalized by identifier.

## Feasible schedule

A schedule is a serial, non-preemptive sequence. A task starts no earlier than the current cursor, its own earliest start, and completion of all dependencies. It must finish by the hard horizon. Selecting a task requires selecting every dependency before it.

## Optimization order

The exact solver compares feasible schedules lexicographically:

1. maximize total scheduled priority;
2. maximize priority completed by each task's due minute;
3. minimize total tardiness in minutes;
4. maximize scheduled task count;
5. minimize final completion minute;
6. choose the lexicographically smallest task-id sequence.

The first five components are the public objective vector. The final sequence rule removes nondeterministic ties.

## Proof claim

For at most nine tasks, the exact engine will enumerate every feasible topological sequence, with only an admissible optimistic-priority bound allowed to prune branches. A result may claim `optimal: true` only after the search closes and an implementation-independent verifier reproduces the optimum from the original request.

## Non-claims

This is not calendar synchronization, multi-user resource allocation, continuous-time optimization, a stochastic forecast, an LLM, or a medical/employment decision system. Priority and duration are caller-provided assumptions. A mathematically optimal result can still be a poor real-world plan if those assumptions are wrong.
