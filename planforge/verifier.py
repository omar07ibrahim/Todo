"""Implementation-independent exhaustive verifier for PlanForge plans."""

from __future__ import annotations

from itertools import permutations
from typing import Any

from planforge.canonical import canonical_bytes, sha256_hex
from planforge.model import ContractError, PlanningRequest, Task
from planforge.planner import ALGORITHM, PLAN_SCHEMA, PLANNER_VERSION

VERIFICATION_SCHEMA = "planforge.verification.v1"
VERIFIER_ALGORITHM = "exhaustive-feasible-permutations-v1"


def _schedule(
    request: PlanningRequest, order: tuple[Task, ...]
) -> tuple[tuple[Task, int, int], ...] | None:
    selected: set[str] = set()
    cursor = request.start_minute
    blocks: list[tuple[Task, int, int]] = []
    for task in order:
        if not set(task.dependencies).issubset(selected):
            return None
        start = max(cursor, task.earliest_start_minute)
        end = start + task.duration_minutes
        if end > request.end_minute:
            return None
        blocks.append((task, start, end))
        selected.add(task.id)
        cursor = end
    return tuple(blocks)


def _quality(
    blocks: tuple[tuple[Task, int, int], ...], start_minute: int
) -> tuple[int, int, int, int, int]:
    total = sum(task.priority for task, _start, _end in blocks)
    on_time = sum(task.priority for task, _start, end in blocks if end <= task.due_minute)
    tardiness = sum(max(0, end - task.due_minute) for task, _start, end in blocks)
    completion = blocks[-1][2] if blocks else start_minute
    return (total, on_time, -tardiness, len(blocks), -completion)


def _expected_scheduled(
    blocks: tuple[tuple[Task, int, int], ...]
) -> list[dict[str, Any]]:
    return [
        {
            "dependencies": list(task.dependencies),
            "due_minute": task.due_minute,
            "end_minute": end,
            "priority": task.priority,
            "sequence": index,
            "start_minute": start,
            "tardiness_minutes": max(0, end - task.due_minute),
            "task_id": task.id,
            "title": task.title,
        }
        for index, (task, start, end) in enumerate(blocks, start=1)
    ]


def _expected_objective(
    blocks: tuple[tuple[Task, int, int], ...], start_minute: int
) -> dict[str, int]:
    completion = blocks[-1][2] if blocks else start_minute
    return {
        "completion_minute": completion,
        "on_time_priority": sum(
            task.priority for task, _start, end in blocks if end <= task.due_minute
        ),
        "scheduled_count": len(blocks),
        "total_priority": sum(task.priority for task, _start, _end in blocks),
        "total_tardiness_minutes": sum(
            max(0, end - task.due_minute) for task, _start, end in blocks
        ),
    }


def _expected_unscheduled(
    request: PlanningRequest, blocks: tuple[tuple[Task, int, int], ...]
) -> list[dict[str, Any]]:
    selected = {task.id for task, _start, _end in blocks}
    return [
        {
            "missing_dependencies": sorted(set(task.dependencies) - selected),
            "priority": task.priority,
            "reason": (
                "dependency_not_selected"
                if set(task.dependencies) - selected
                else "capacity_tradeoff"
            ),
            "task_id": task.id,
            "title": task.title,
        }
        for task in request.tasks
        if task.id not in selected
    ]


def _independent_optimum(
    request: PlanningRequest,
) -> tuple[tuple[tuple[Task, int, int], ...], int]:
    best: tuple[tuple[Task, int, int], ...] = ()
    feasible_sequences = 0
    for size in range(len(request.tasks) + 1):
        for order in permutations(request.tasks, size):
            blocks = _schedule(request, order)
            if blocks is None:
                continue
            feasible_sequences += 1
            quality = _quality(blocks, request.start_minute)
            best_quality = _quality(best, request.start_minute)
            order_ids = tuple(task.id for task, _start, _end in blocks)
            best_ids = tuple(task.id for task, _start, _end in best)
            if quality > best_quality or (quality == best_quality and order_ids < best_ids):
                best = blocks
    return best, feasible_sequences


def verify_plan(request: PlanningRequest, value: Any) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError("plan must be an object")
    expected_keys = {
        "algorithm",
        "objective",
        "planner_version",
        "proof",
        "request_sha256",
        "scheduled",
        "schema",
        "unscheduled",
    }
    if set(value) != expected_keys:
        raise ContractError("plan fields must be exact")
    request_sha = sha256_hex(canonical_bytes(request.to_document()))
    if (
        value["schema"] != PLAN_SCHEMA
        or value["algorithm"] != ALGORITHM
        or value["planner_version"] != PLANNER_VERSION
        or value["request_sha256"] != request_sha
    ):
        raise ContractError("plan identity does not match the supported contract")

    optimum, feasible_sequences = _independent_optimum(request)
    if value["scheduled"] != _expected_scheduled(optimum):
        raise ContractError("scheduled blocks disagree with the independent optimum")
    if value["objective"] != _expected_objective(optimum, request.start_minute):
        raise ContractError("objective disagrees with the independent optimum")
    if value["unscheduled"] != _expected_unscheduled(request, optimum):
        raise ContractError("unscheduled explanations disagree with the optimum")

    proof = value["proof"]
    proof_keys = {
        "candidate_schedules",
        "expanded_states",
        "optimal",
        "pruned_horizon",
        "pruned_priority_bound",
        "search_complete",
    }
    if type(proof) is not dict or set(proof) != proof_keys:
        raise ContractError("proof metrics have the wrong shape")
    if proof["optimal"] is not True or proof["search_complete"] is not True:
        raise ContractError("plan does not claim a completed exact search")
    for key in proof_keys - {"optimal", "search_complete"}:
        if type(proof[key]) is not int or proof[key] < 0:
            raise ContractError("proof metrics must be non-negative integers")
    if proof["expanded_states"] < 1 or proof["candidate_schedules"] != proof["expanded_states"]:
        raise ContractError("proof state accounting is inconsistent")

    plan_sha = sha256_hex(canonical_bytes(value))
    return {
        "independent_algorithm": VERIFIER_ALGORITHM,
        "objective": value["objective"],
        "plan_sha256": plan_sha,
        "request_sha256": request_sha,
        "schema": VERIFICATION_SCHEMA,
        "status": "verified",
        "verified_feasible_sequences": feasible_sequences,
    }
