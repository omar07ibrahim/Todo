"""Strict bounded input contract for the PlanForge exact planner."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any

from planforge.canonical import canonical_bytes

REQUEST_SCHEMA = "planforge.request.v1"
MAX_REQUEST_BYTES = 65_536
MAX_TASKS = 9
_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


class ContractError(ValueError):
    """Raised when untrusted planning input escapes the public contract."""


def _object(value: Any, *, name: str, keys: frozenset[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise ContractError(f"{name} must be an object")
    if frozenset(value) != keys:
        raise ContractError(f"{name} fields must be exact")
    return value


def _integer(value: Any, *, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ContractError(f"{name} is outside its integer bounds")
    return value


def _text(value: Any, *, name: str, maximum: int) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ContractError(f"{name} must be non-empty and trimmed")
    if len(value) > maximum or any(
        unicodedata.category(character).startswith("C") for character in value
    ):
        raise ContractError(f"{name} contains forbidden or excessive text")
    return value


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    title: str
    duration_minutes: int
    priority: int
    due_minute: int
    earliest_start_minute: int
    dependencies: tuple[str, ...]

    def to_document(self) -> dict[str, Any]:
        return {
            "dependencies": list(self.dependencies),
            "due_minute": self.due_minute,
            "duration_minutes": self.duration_minutes,
            "earliest_start_minute": self.earliest_start_minute,
            "id": self.id,
            "priority": self.priority,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class PlanningRequest:
    start_minute: int
    horizon_minutes: int
    tasks: tuple[Task, ...]

    @property
    def end_minute(self) -> int:
        return self.start_minute + self.horizon_minutes

    def to_document(self) -> dict[str, Any]:
        return {
            "horizon_minutes": self.horizon_minutes,
            "schema": REQUEST_SCHEMA,
            "start_minute": self.start_minute,
            "tasks": [task.to_document() for task in self.tasks],
        }

    @classmethod
    def from_document(cls, value: Any) -> "PlanningRequest":
        root = _object(
            value,
            name="request",
            keys=frozenset({"schema", "start_minute", "horizon_minutes", "tasks"}),
        )
        if root["schema"] != REQUEST_SCHEMA:
            raise ContractError("request schema is unsupported")
        start = _integer(root["start_minute"], name="start_minute", minimum=0, maximum=1_380)
        horizon = _integer(
            root["horizon_minutes"],
            name="horizon_minutes",
            minimum=60,
            maximum=720,
        )
        if start % 15 or horizon % 15 or start + horizon > 1_440:
            raise ContractError("planning horizon must use 15-minute slots within one day")
        raw_tasks = root["tasks"]
        if type(raw_tasks) is not list or not 1 <= len(raw_tasks) <= MAX_TASKS:
            raise ContractError("tasks must be a bounded non-empty array")

        tasks: list[Task] = []
        seen: set[str] = set()
        task_keys = frozenset(
            {
                "id",
                "title",
                "duration_minutes",
                "priority",
                "due_minute",
                "earliest_start_minute",
                "dependencies",
            }
        )
        for index, raw_task in enumerate(raw_tasks):
            item = _object(raw_task, name=f"tasks[{index}]", keys=task_keys)
            task_id = _text(item["id"], name=f"tasks[{index}].id", maximum=32)
            if _ID.fullmatch(task_id) is None or task_id in seen:
                raise ContractError("task identifiers must be unique canonical slugs")
            seen.add(task_id)
            title = _text(item["title"], name=f"tasks[{index}].title", maximum=80)
            duration = _integer(
                item["duration_minutes"],
                name=f"tasks[{index}].duration_minutes",
                minimum=15,
                maximum=240,
            )
            if duration % 15:
                raise ContractError("task durations must use 15-minute slots")
            priority = _integer(
                item["priority"],
                name=f"tasks[{index}].priority",
                minimum=1,
                maximum=100,
            )
            due = _integer(
                item["due_minute"],
                name=f"tasks[{index}].due_minute",
                minimum=start + 15,
                maximum=1_440,
            )
            earliest = _integer(
                item["earliest_start_minute"],
                name=f"tasks[{index}].earliest_start_minute",
                minimum=start,
                maximum=start + horizon,
            )
            raw_dependencies = item["dependencies"]
            if type(raw_dependencies) is not list or len(raw_dependencies) > MAX_TASKS - 1:
                raise ContractError("dependencies must be a bounded array")
            dependencies: list[str] = []
            for raw_dependency in raw_dependencies:
                dependency = _text(raw_dependency, name="dependency", maximum=32)
                if _ID.fullmatch(dependency) is None:
                    raise ContractError("dependency identifiers must be canonical slugs")
                if dependency == task_id or dependency in dependencies:
                    raise ContractError("dependencies cannot be self-referential or repeated")
                dependencies.append(dependency)
            tasks.append(
                Task(
                    id=task_id,
                    title=title,
                    duration_minutes=duration,
                    priority=priority,
                    due_minute=due,
                    earliest_start_minute=earliest,
                    dependencies=tuple(sorted(dependencies)),
                )
            )

        identifiers = {task.id for task in tasks}
        if any(set(task.dependencies) - identifiers for task in tasks):
            raise ContractError("every dependency must identify a task in the request")
        by_id = {task.id: task for task in tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ContractError("task dependencies must be acyclic")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in by_id[task_id].dependencies:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in sorted(by_id):
            visit(task_id)

        request = cls(
            start_minute=start,
            horizon_minutes=horizon,
            tasks=tuple(sorted(tasks, key=lambda task: task.id)),
        )
        if len(canonical_bytes(request.to_document())) > MAX_REQUEST_BYTES:
            raise ContractError("canonical request exceeds its byte limit")
        return request
