"""Dependency-free command line interface for exact plans and receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from planforge.canonical import canonical_bytes
from planforge.filesystem import publish_bundle, read_bundle, read_regular
from planforge.model import ContractError, MAX_REQUEST_BYTES, PlanningRequest
from planforge.planner import solve
from planforge.verifier import verify_plan

BUNDLE_FILES = frozenset({"plan.json", "request.json", "verification.json"})
BUNDLE_LIMITS = {
    "plan.json": 1_048_576,
    "request.json": MAX_REQUEST_BYTES,
    "verification.json": 262_144,
}


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("JSON object contains a duplicate key")
        result[key] = value
    return result


def _load(payload: bytes) -> Any:
    try:
        text = payload.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ContractError("non-finite JSON number is forbidden")
            ),
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ContractError("input is not strict UTF-8 JSON") from error


def _summary(status: str, verification: dict[str, Any]) -> bytes:
    return canonical_bytes(
        {
            "objective": verification["objective"],
            "plan_sha256": verification["plan_sha256"],
            "request_sha256": verification["request_sha256"],
            "status": status,
        }
    )


def _solve(request_path: Path, output: Path) -> bytes:
    request = PlanningRequest.from_document(
        _load(read_regular(request_path, MAX_REQUEST_BYTES))
    )
    plan = solve(request)
    verification = verify_plan(request, plan)
    publish_bundle(
        output,
        {
            "plan.json": canonical_bytes(plan),
            "request.json": canonical_bytes(request.to_document()),
            "verification.json": canonical_bytes(verification),
        },
    )
    return _summary("solved", verification)


def _verify(output: Path) -> bytes:
    payloads = read_bundle(output, BUNDLE_FILES, BUNDLE_LIMITS)
    request = PlanningRequest.from_document(_load(payloads["request.json"]))
    if payloads["request.json"] != canonical_bytes(request.to_document()):
        raise ContractError("bundled request is not canonical")
    plan = _load(payloads["plan.json"])
    if payloads["plan.json"] != canonical_bytes(plan):
        raise ContractError("bundled plan is not canonical")
    expected = verify_plan(request, plan)
    receipt = _load(payloads["verification.json"])
    if payloads["verification.json"] != canonical_bytes(receipt) or receipt != expected:
        raise ContractError("verification receipt does not match the bundle")
    return _summary("verified", expected)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="planforge")
    subparsers = parser.add_subparsers(dest="command", required=True)
    solve_parser = subparsers.add_parser("solve", help="solve and publish a new bundle")
    solve_parser.add_argument("--request", required=True, type=Path)
    solve_parser.add_argument("--output", required=True, type=Path)
    verify_parser = subparsers.add_parser("verify", help="independently verify a bundle")
    verify_parser.add_argument("--bundle", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "solve":
            payload = _solve(arguments.request, arguments.output)
        else:
            payload = _verify(arguments.bundle)
    except (ContractError, OSError, ValueError):
        sys.stderr.buffer.write(canonical_bytes({"error": "invalid_input", "status": "error"}))
        return 2
    sys.stdout.buffer.write(payload)
    return 0
