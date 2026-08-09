"""Exact topological branch-and-bound scheduler for bounded requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from planforge.canonical import canonical_bytes, sha256_hex
from planforge.model import PlanningRequest, Task

PLAN_SCHEMA = "planforge.plan.v1"
ALGORITHM = "exact-topological-branch-and-bound-v1"
PLANNER_VERSION = "0.2.0"


@dataclass(frozen=True, slots=True)
class _Block:
    task: Task
    start_minute: int
    end_minute: int

    @property
    def tardiness_minutes(self) -> int:
        return max(0, self.end_minute - self.task.due_minute)

    def to_document(self, sequence: int) -> dict[str, Any]:
        return {
            "dependencies": list(self.task.dependencies),
            "due_minute": self.task.due_minute,
            "end_minute": self.end_minute,
            "priority": self.task.priority,
            "sequence": sequence,
            "start_minute": self.start_minute,
            "tardiness_minutes": self.tardiness_minutes,
            "task_id": self.task.id,
            "title": self.task.title,
        }


def _quality(blocks: tuple[_Block, ...], start_minute: int) -> tuple[int, int, int, int, int]:
    total_priority = sum(block.task.priority for block in blocks)
    on_time_priority = sum(
        block.task.priority for block in blocks if block.tardiness_minutes == 0
    )
    tardiness = sum(block.tardiness_minutes for block in blocks)
    completion = blocks[-1].end_minute if blocks else start_minute
    return (total_priority, on_time_priority, -tardiness, len(blocks), -completion)


def _objective(blocks: tuple[_Block, ...], start_minute: int) -> dict[str, int]:
    completion = blocks[-1].end_minute if blocks else start_minute
    return {
        "completion_minute": completion,
        "on_time_priority": sum(
            block.task.priority for block in blocks if block.tardiness_minutes == 0
        ),
        "scheduled_count": len(blocks),
        "total_priority": sum(block.task.priority for block in blocks),
        "total_tardiness_minutes": sum(block.tardiness_minutes for block in blocks),
    }


def _is_better(
    candidate: tuple[_Block, ...],
    incumbent: tuple[_Block, ...],
    start_minute: int,
) -> bool:
    candidate_quality = _quality(candidate, start_minute)
    incumbent_quality = _quality(incumbent, start_minute)
    if candidate_quality != incumbent_quality:
        return candidate_quality > incumbent_quality
    return tuple(block.task.id for block in candidate) < tuple(
        block.task.id for block in incumbent
    )


def _unscheduled(
    request: PlanningRequest, blocks: tuple[_Block, ...]
) -> list[dict[str, Any]]:
    selected = {block.task.id for block in blocks}
    result: list[dict[str, Any]] = []
    for task in request.tasks:
        if task.id in selected:
            continue
        missing = sorted(set(task.dependencies) - selected)
        result.append(
            {
                "missing_dependencies": missing,
                "priority": task.priority,
                "reason": (
                    "dependency_not_selected" if missing else "capacity_tradeoff"
                ),
                "task_id": task.id,
                "title": task.title,
            }
        )
    return result


def solve(request: PlanningRequest) -> dict[str, Any]:
    """Return the deterministic globally optimal plan for one bounded request."""
    best: tuple[_Block, ...] = ()
    expanded_states = 0
    candidate_schedules = 0
    pruned_horizon = 0
    pruned_priority_bound = 0

    def search(
        blocks: tuple[_Block, ...],
        selected: frozenset[str],
        cursor: int,
        priority: int,
    ) -> None:
        nonlocal best
        nonlocal expanded_states, candidate_schedules
        nonlocal pruned_horizon, pruned_priority_bound
        expanded_states += 1
        candidate_schedules += 1
        if _is_better(blocks, best, request.start_minute):
            best = blocks

        remaining = [task for task in request.tasks if task.id not in selected]
        optimistic_priority = priority + sum(task.priority for task in remaining)
        incumbent_priority = sum(block.task.priority for block in best)
        if optimistic_priority < incumbent_priority:
            pruned_priority_bound += 1
            return

        for task in remaining:
            if not set(task.dependencies).issubset(selected):
                continue
            start = max(cursor, task.earliest_start_minute)
            end = start + task.duration_minutes
            if end > request.end_minute:
                pruned_horizon += 1
                continue
            search(
                blocks + (_Block(task=task, start_minute=start, end_minute=end),),
                selected | {task.id},
                end,
                priority + task.priority,
            )

    search((), frozenset(), request.start_minute, 0)
    request_sha = sha256_hex(canonical_bytes(request.to_document()))
    document = {
        "algorithm": ALGORITHM,
        "objective": _objective(best, request.start_minute),
        "planner_version": PLANNER_VERSION,
        "proof": {
            "candidate_schedules": candidate_schedules,
            "expanded_states": expanded_states,
            "optimal": True,
            "pruned_horizon": pruned_horizon,
            "pruned_priority_bound": pruned_priority_bound,
            "search_complete": True,
        },
        "request_sha256": request_sha,
        "scheduled": [
            block.to_document(index)
            for index, block in enumerate(best, start=1)
        ],
        "schema": PLAN_SCHEMA,
        "unscheduled": _unscheduled(request, best),
    }
    canonical_bytes(document)
    return document
