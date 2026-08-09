"""Compatibility launcher for the source-checkout PlanForge dashboard."""

from pathlib import Path

from planforge.cli import main


if __name__ == "__main__":
    fixture = Path(__file__).resolve().parent / "examples" / "launch-day.request.json"
    raise SystemExit(main(["serve", "--request", str(fixture)]))
