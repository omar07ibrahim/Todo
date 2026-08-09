from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from planforge.model import ContractError, PlanningRequest
from planforge.planner import solve
from planforge.verifier import verify_plan

ROOT = Path(__file__).resolve().parents[1]


def demo_request() -> PlanningRequest:
    document = json.loads((ROOT / "examples" / "launch-day.request.json").read_text())
    return PlanningRequest.from_document(document)


class ExactPlannerTests(unittest.TestCase):
    def test_demo_is_globally_verified_and_capacity_selective(self) -> None:
        request = demo_request()
        plan = solve(request)
        verification = verify_plan(request, plan)
        self.assertEqual(verification["status"], "verified")
        self.assertEqual(plan["objective"]["total_priority"], 460)
        self.assertEqual(plan["objective"]["scheduled_count"], 7)
        self.assertEqual(
            [item["task_id"] for item in plan["unscheduled"]], ["experiment"]
        )
        self.assertTrue(plan["proof"]["optimal"])
        self.assertGreater(plan["proof"]["expanded_states"], 1)

    def test_input_task_order_cannot_change_the_plan(self) -> None:
        request = demo_request()
        document = request.to_document()
        reversed_document = copy.deepcopy(document)
        reversed_document["tasks"].reverse()
        self.assertEqual(
            solve(request),
            solve(PlanningRequest.from_document(reversed_document)),
        )

    def test_lexicographic_identifier_breaks_a_complete_tie(self) -> None:
        document = {
            "schema": "planforge.request.v1",
            "start_minute": 540,
            "horizon_minutes": 60,
            "tasks": [
                {
                    "id": task_id,
                    "title": task_id.title(),
                    "duration_minutes": 60,
                    "priority": 10,
                    "due_minute": 600,
                    "earliest_start_minute": 540,
                    "dependencies": [],
                }
                for task_id in ("beta", "alpha")
            ],
        }
        plan = solve(PlanningRequest.from_document(document))
        self.assertEqual(plan["scheduled"][0]["task_id"], "alpha")

    def test_dependencies_precede_their_consumers(self) -> None:
        plan = solve(demo_request())
        positions = {
            item["task_id"]: item["sequence"] for item in plan["scheduled"]
        }
        for item in plan["scheduled"]:
            for dependency in item["dependencies"]:
                self.assertLess(positions[dependency], positions[item["task_id"]])

    def test_tampered_schedule_is_rejected(self) -> None:
        request = demo_request()
        plan = solve(request)
        plan["scheduled"][0]["start_minute"] += 15
        with self.assertRaises(ContractError):
            verify_plan(request, plan)

    def test_tampered_objective_is_rejected(self) -> None:
        request = demo_request()
        plan = solve(request)
        plan["objective"]["total_priority"] += 1
        with self.assertRaises(ContractError):
            verify_plan(request, plan)

    def test_false_optimality_claim_is_rejected(self) -> None:
        request = demo_request()
        plan = solve(request)
        plan["proof"]["optimal"] = False
        with self.assertRaises(ContractError):
            verify_plan(request, plan)


if __name__ == "__main__":
    unittest.main()
