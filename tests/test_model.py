from __future__ import annotations

import copy
import unittest

from planforge.canonical import canonical_bytes, sha256_hex
from planforge.model import ContractError, PlanningRequest


def valid_document() -> dict[str, object]:
    return {
        "schema": "planforge.request.v1",
        "start_minute": 540,
        "horizon_minutes": 480,
        "tasks": [
            {
                "id": "design",
                "title": "Design review",
                "duration_minutes": 60,
                "priority": 70,
                "due_minute": 720,
                "earliest_start_minute": 540,
                "dependencies": [],
            },
            {
                "id": "ship",
                "title": "Ship release",
                "duration_minutes": 45,
                "priority": 100,
                "due_minute": 900,
                "earliest_start_minute": 600,
                "dependencies": ["design"],
            },
        ],
    }


class PlanningRequestTests(unittest.TestCase):
    def test_valid_request_is_normalized_and_canonical(self) -> None:
        document = valid_document()
        document["tasks"] = list(reversed(document["tasks"]))  # type: ignore[index]
        request = PlanningRequest.from_document(document)
        self.assertEqual([task.id for task in request.tasks], ["design", "ship"])
        payload = canonical_bytes(request.to_document())
        self.assertTrue(payload.isascii())
        self.assertTrue(payload.endswith(b"\n"))
        self.assertEqual(len(sha256_hex(payload)), 64)

    def test_unknown_root_field_fails_closed(self) -> None:
        document = valid_document()
        document["surprise"] = True
        with self.assertRaises(ContractError):
            PlanningRequest.from_document(document)

    def test_boolean_is_not_an_integer(self) -> None:
        document = valid_document()
        document["horizon_minutes"] = True
        with self.assertRaises(ContractError):
            PlanningRequest.from_document(document)

    def test_duplicate_identifier_is_rejected(self) -> None:
        document = valid_document()
        tasks = document["tasks"]
        assert isinstance(tasks, list)
        tasks[1]["id"] = "design"
        with self.assertRaises(ContractError):
            PlanningRequest.from_document(document)

    def test_unknown_dependency_is_rejected(self) -> None:
        document = valid_document()
        tasks = document["tasks"]
        assert isinstance(tasks, list)
        tasks[1]["dependencies"] = ["missing"]
        with self.assertRaises(ContractError):
            PlanningRequest.from_document(document)

    def test_cycle_is_rejected(self) -> None:
        document = valid_document()
        tasks = document["tasks"]
        assert isinstance(tasks, list)
        tasks[0]["dependencies"] = ["ship"]
        with self.assertRaises(ContractError):
            PlanningRequest.from_document(document)

    def test_control_character_is_rejected(self) -> None:
        document = valid_document()
        tasks = document["tasks"]
        assert isinstance(tasks, list)
        tasks[0]["title"] = "unsafe\nlabel"
        with self.assertRaises(ContractError):
            PlanningRequest.from_document(document)

    def test_non_slot_duration_is_rejected(self) -> None:
        document = valid_document()
        tasks = document["tasks"]
        assert isinstance(tasks, list)
        tasks[0]["duration_minutes"] = 17
        with self.assertRaises(ContractError):
            PlanningRequest.from_document(document)

    def test_input_object_is_not_mutated(self) -> None:
        document = valid_document()
        before = copy.deepcopy(document)
        PlanningRequest.from_document(document)
        self.assertEqual(document, before)


if __name__ == "__main__":
    unittest.main()
