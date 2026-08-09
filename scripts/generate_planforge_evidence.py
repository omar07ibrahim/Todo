"""Generate real, deterministic CLI/browser/solver evidence for PlanForge."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from threading import Thread
from typing import Any
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont, __version__ as PILLOW_VERSION
from playwright.sync_api import sync_playwright

from planforge.canonical import canonical_bytes, sha256_hex
from planforge.model import PlanningRequest
from planforge.planner import solve
from planforge.verifier import verify_plan
from planforge.web import Dashboard, make_server

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "examples/launch-day.request.json"
CONTAINER = "mcr.microsoft.com/playwright/python@sha256:51d31fdfacb0cff99a1a724152e34ae408d2bd4e7da310ff157450f49261cc59"
OUTPUTS = (
    "docs/assets/planforge-dashboard.png",
    "docs/assets/planforge-mobile.png",
    "docs/assets/planforge-full-page.png",
    "docs/assets/planforge-interaction.gif",
    "docs/assets/planforge-cli.png",
    "docs/assets/planforge-gantt.svg",
    "docs/assets/planforge-horizon-curve.svg",
    "docs/assets/planforge-proof-flow.svg",
    "docs/assets/planforge-plan.json",
    "docs/assets/planforge-verification.json",
    "docs/assets/planforge-evidence.json",
)
HASHED_OUTPUTS = OUTPUTS[:-1]
SOURCE_BINDINGS = (
    "docs/planning-contract.md",
    FIXTURE,
    "planforge/__init__.py",
    "planforge/__main__.py",
    "planforge/canonical.py",
    "planforge/cli.py",
    "planforge/filesystem.py",
    "planforge/model.py",
    "planforge/planner.py",
    "planforge/verifier.py",
    "planforge/web.py",
    "requirements/evidence-browser-image.lock.json",
    "requirements/evidence-browser.txt",
    "scripts/generate_planforge_evidence.py",
    "scripts/verify_planforge_evidence.py",
)
MAXIMUM = {
    "docs/assets/planforge-dashboard.png": 4_194_304,
    "docs/assets/planforge-mobile.png": 2_097_152,
    "docs/assets/planforge-full-page.png": 12_582_912,
    "docs/assets/planforge-interaction.gif": 12_582_912,
    "docs/assets/planforge-cli.png": 4_194_304,
    "docs/assets/planforge-gantt.svg": 262_144,
    "docs/assets/planforge-horizon-curve.svg": 262_144,
    "docs/assets/planforge-proof-flow.svg": 262_144,
    "docs/assets/planforge-plan.json": 1_048_576,
    "docs/assets/planforge-verification.json": 262_144,
    "docs/assets/planforge-evidence.json": 1_048_576,
}


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(root: Path, relative: str, payload: bytes) -> None:
    if len(payload) > MAXIMUM[relative]:
        raise RuntimeError(f"generated evidence exceeded its bound: {relative}")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RuntimeError("evidence write was incomplete")
            view = view[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _normalized_png(payload: bytes) -> bytes:
    with Image.open(io.BytesIO(payload)) as source:
        source.load()
        image = source.convert("RGB")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _font() -> tuple[Path, dict[str, Any]]:
    completed = subprocess.run(
        ("fc-match", "-f", "%{file}\n%{family}\n%{style}\n", "DejaVu Sans Mono"),
        check=True,
        capture_output=True,
        text=True,
    )
    lines = completed.stdout.splitlines()
    if len(lines) < 3:
        raise RuntimeError("font identity is incomplete")
    path = Path(lines[0])
    payload = path.read_bytes()
    return path, {
        "bytes": len(payload),
        "family": lines[1],
        "file": path.name,
        "sha256": _digest(payload),
        "style": lines[2],
    }


def _terminal_png(commands: list[dict[str, Any]], plan: dict[str, Any]) -> bytes:
    font_path, _identity = _font()
    regular = ImageFont.truetype(str(font_path), 22)
    small = ImageFont.truetype(str(font_path), 18)
    image = Image.new("RGB", (1_440, 820), "#080d19")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 36, 1_398, 784), radius=24, fill="#0d1424", outline="#293550", width=2)
    draw.ellipse((76, 68, 94, 86), fill="#ff6b7a")
    draw.ellipse((104, 68, 122, 86), fill="#ffbd6b")
    draw.ellipse((132, 68, 150, 86), fill="#61d6a8")
    draw.text((178, 65), "planforge | executed CLI proof", font=regular, fill="#f7f8fc")
    lines = [
        ("$ python -m planforge solve --request launch-day.request.json --output proof", "#8da8ff"),
        (commands[0]["stdout"].strip(), "#b8c4dc"),
        ("", "#b8c4dc"),
        ("$ python -m planforge verify --bundle proof", "#8da8ff"),
        (commands[1]["stdout"].strip(), "#b8c4dc"),
        ("", "#b8c4dc"),
        (f"scheduled_priority={plan['objective']['total_priority']}  tasks={plan['objective']['scheduled_count']}  tardiness={plan['objective']['total_tardiness_minutes']}m", "#91f2cd"),
        (f"expanded_states={plan['proof']['expanded_states']}  admissible_prunes={plan['proof']['pruned_priority_bound']}  optimal=true", "#91f2cd"),
    ]
    y = 122
    for line, color in lines:
        chunks = [line[index : index + 104] for index in range(0, max(1, len(line)), 104)] or [""]
        for chunk in chunks:
            draw.text((78, y), chunk, font=small, fill=color)
            y += 34
        y += 8
    draw.text((78, 738), "Synthetic fixture | stdout captured byte-for-byte | stderr empty", font=small, fill="#7f8ba8")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def _gantt_svg(request: PlanningRequest, plan: dict[str, Any]) -> bytes:
    width, height, left, chart = 1_200, 520, 190, 940
    rows: list[str] = []
    for index, item in enumerate(plan["scheduled"]):
        y = 118 + index * 48
        x = left + round((item["start_minute"] - request.start_minute) * chart / request.horizon_minutes)
        block_width = round((item["end_minute"] - item["start_minute"]) * chart / request.horizon_minutes)
        color = ("#7c9cff", "#61d6a8", "#ffbd6b", "#e68cff")[index % 4]
        rows.append(f'<text x="34" y="{y + 24}" fill="#dce4f7" font-size="15">{escape(item["task_id"])}</text><rect x="{x}" y="{y}" width="{block_width}" height="34" rx="8" fill="{color}"/><text x="{x + 8}" y="{y + 22}" fill="#08101f" font-size="12" font-weight="700">{item["start_minute"] // 60:02d}:{item["start_minute"] % 60:02d}</text>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><title>Executed PlanForge schedule</title><desc>Gantt chart generated from the independently verified launch-day plan.</desc><rect width="1200" height="520" rx="24" fill="#080d19"/><text x="34" y="46" fill="#61d6a8" font-size="14" font-weight="700">EXECUTED OPTIMAL SCHEDULE</text><text x="34" y="78" fill="#f7f8fc" font-size="25" font-weight="700">Seven dependency-safe tasks inside one hard horizon</text><line x1="{left}" y1="98" x2="{left + chart}" y2="98" stroke="#33415f"/>{''.join(rows)}<text x="34" y="490" fill="#8290ac" font-size="13">Plan {plan['request_sha256'][:12]} | total priority {plan['objective']['total_priority']} | tardiness {plan['objective']['total_tardiness_minutes']}m</text></svg>'''
    return svg.encode("ascii")


def _horizon_svg(points: list[dict[str, int]]) -> bytes:
    width, height = 1_200, 600
    left, top, chart_w, chart_h = 110, 118, 980, 360
    max_priority = max(point["total_priority"] for point in points)
    coordinates: list[tuple[int, int]] = []
    labels: list[str] = []
    for index, point in enumerate(points):
        x = left + round(index * chart_w / (len(points) - 1))
        y = top + chart_h - round(point["total_priority"] * chart_h / max_priority)
        coordinates.append((x, y))
        labels.append(f'<circle cx="{x}" cy="{y}" r="9" fill="#61d6a8"/><text x="{x}" y="{y - 18}" text-anchor="middle" fill="#f7f8fc" font-size="16" font-weight="700">{point["total_priority"]}</text><text x="{x}" y="{top + chart_h + 34}" text-anchor="middle" fill="#9aa8c4" font-size="14">{point["horizon_minutes"]}m</text>')
    line = " ".join(f"{x},{y}" for x, y in coordinates)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><title>Verified horizon sensitivity curve</title><desc>Each point is a separately solved and independently verified scenario.</desc><rect width="1200" height="600" rx="24" fill="#080d19"/><text x="52" y="50" fill="#61d6a8" font-size="14" font-weight="700">COUNTERFACTUAL HORIZON SWEEP</text><text x="52" y="82" fill="#f7f8fc" font-size="25" font-weight="700">More time unlocks verified scheduled priority</text><line x1="{left}" y1="{top + chart_h}" x2="{left + chart_w}" y2="{top + chart_h}" stroke="#33415f"/><polyline points="{line}" fill="none" stroke="#7c9cff" stroke-width="6" stroke-linejoin="round"/>{''.join(labels)}<text x="52" y="560" fill="#8290ac" font-size="13">Exact solve + independent permutation verification at every point; synthetic inputs.</text></svg>'''
    return svg.encode("ascii")


def _proof_svg(plan: dict[str, Any], verification: dict[str, Any]) -> bytes:
    boxes = (
        (46, "Bounded request", "strict schema + DAG"),
        (326, "Exact planner", f"{plan['proof']['expanded_states']} states"),
        (606, "Independent verifier", f"{verification['verified_feasible_sequences']} feasible sequences"),
        (886, "Hash receipt", verification["plan_sha256"][:12] + "..."),
    )
    body = []
    for index, (x, title, subtitle) in enumerate(boxes):
        body.append(f'<rect x="{x}" y="170" width="230" height="150" rx="18" fill="#111a2d" stroke="#33415f"/><text x="{x + 20}" y="218" fill="#f7f8fc" font-size="19" font-weight="700">{escape(title)}</text><text x="{x + 20}" y="254" fill="#9aa8c4" font-size="13">{escape(subtitle)}</text>')
        if index < len(boxes) - 1:
            body.append(f'<path d="M{x + 230} 245H{x + 270}" stroke="#61d6a8" stroke-width="4"/><path d="M{x + 262} 237L{x + 274} 245L{x + 262} 253" fill="none" stroke="#61d6a8" stroke-width="4"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="500" viewBox="0 0 1200 500"><title>PlanForge proof architecture</title><desc>Source-bound architecture annotated with observed search metrics.</desc><rect width="1200" height="500" rx="24" fill="#080d19"/><text x="46" y="54" fill="#61d6a8" font-size="14" font-weight="700">OBSERVED PROOF PIPELINE</text><text x="46" y="91" fill="#f7f8fc" font-size="27" font-weight="700">One claim, two different algorithms, one receipt</text>{''.join(body)}<text x="46" y="438" fill="#8290ac" font-size="13">The verifier does not call the branch-and-bound solver; it enumerates feasible permutations independently.</text></svg>'''
    return svg.encode("utf-8")


def _capture(dashboard: Dashboard) -> tuple[dict[str, bytes], dict[str, Any]]:
    server = make_server(dashboard)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    assets: dict[str, bytes] = {}
    assertions: dict[str, Any] = {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, chromium_sandbox=False, args=["--disable-dev-shm-usage", "--force-color-profile=srgb"])
            desktop = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1, locale="en-US", timezone_id="UTC", service_workers="block")
            page = desktop.new_page()
            requests: list[str] = []
            errors: list[str] = []
            page.on("request", lambda request: requests.append(request.url))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            response = page.goto(url, wait_until="networkidle")
            if response is None or response.status != 200:
                raise RuntimeError("dashboard navigation failed")
            page.locator("text=independently verified").first.wait_for()
            assets["docs/assets/planforge-dashboard.png"] = _normalized_png(page.screenshot())
            selected: list[str] = []
            frames: list[Image.Image] = []
            task_ids = [item["task_id"] for item in dashboard.plan["scheduled"]]
            for task_id in (task_ids[0], task_ids[len(task_ids) // 2], task_ids[-1]):
                page.locator(f'[data-task="{task_id}"]').click()
                active = page.locator("[data-detail].active").get_attribute("data-detail")
                if active != task_id:
                    raise RuntimeError("dashboard interaction did not select the requested task")
                selected.append(task_id)
                shot = _normalized_png(page.screenshot())
                with Image.open(io.BytesIO(shot)) as frame:
                    frame.load()
                    frames.append(frame.convert("RGB"))
            full = _normalized_png(page.screenshot(full_page=True))
            assets["docs/assets/planforge-full-page.png"] = full
            gif = io.BytesIO()
            frames[0].save(gif, format="GIF", save_all=True, append_images=frames[1:], duration=[900, 900, 1300], loop=0, optimize=False, disposal=2)
            assets["docs/assets/planforge-interaction.gif"] = gif.getvalue()
            assertions["desktop"] = {"console_errors": errors, "document_requests": len(requests), "selected_task_ids": selected, "viewport": [1440, 1000]}
            desktop.close()

            mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, locale="en-US", timezone_id="UTC", service_workers="block")
            mobile_page = mobile.new_page()
            mobile_requests: list[str] = []
            mobile_page.on("request", lambda request: mobile_requests.append(request.url))
            mobile_response = mobile_page.goto(url, wait_until="networkidle")
            if mobile_response is None or mobile_response.status != 200:
                raise RuntimeError("mobile navigation failed")
            assets["docs/assets/planforge-mobile.png"] = _normalized_png(mobile_page.screenshot())
            assertions["mobile"] = {"document_requests": len(mobile_requests), "label": "Chromium mobile emulation", "viewport": [390, 844]}
            mobile.close()
            version = browser.version
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    if assertions["desktop"]["console_errors"] or assertions["desktop"]["document_requests"] != 1 or assertions["mobile"]["document_requests"] != 1:
        raise RuntimeError("browser evidence escaped its request/console contract")
    assertions["chromium_version"] = version
    return assets, assertions


def generate(output_root: Path, source_revision: str, source_tree: str, container_image: str) -> None:
    if container_image != CONTAINER or output_root.exists():
        raise RuntimeError("evidence destination or container identity is invalid")
    output_root.mkdir(parents=True, mode=0o700)
    fixture_payload = (ROOT / FIXTURE).read_bytes()
    request = PlanningRequest.from_document(json.loads(fixture_payload))

    with tempfile.TemporaryDirectory(prefix="planforge-evidence-") as temporary:
        bundle = Path(temporary) / "proof"
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        environment["PYTHONNOUSERSITE"] = "1"
        commands = []
        for argv, display in (
            ((sys.executable, "-m", "planforge", "solve", "--request", str(ROOT / FIXTURE), "--output", str(bundle)), ("python", "-m", "planforge", "solve", "--request", "launch-day.request.json", "--output", "proof")),
            ((sys.executable, "-m", "planforge", "verify", "--bundle", str(bundle)), ("python", "-m", "planforge", "verify", "--bundle", "proof")),
        ):
            completed = subprocess.run(argv, cwd=temporary, env=environment, check=False, capture_output=True)
            if completed.returncode != 0 or completed.stderr or not completed.stdout.isascii():
                raise RuntimeError("captured CLI command failed")
            commands.append({"argv": list(display), "exit_status": completed.returncode, "stderr": "", "stdout": completed.stdout.decode("ascii"), "stdout_sha256": _digest(completed.stdout)})
        plan = json.loads((bundle / "plan.json").read_bytes())
        verification = json.loads((bundle / "verification.json").read_bytes())

    dashboard = Dashboard.build(request)
    if dashboard.plan != plan or dashboard.verification != verification:
        raise RuntimeError("CLI and dashboard disagree")
    browser_assets, browser_assertions = _capture(dashboard)
    assets: dict[str, bytes] = dict(browser_assets)
    assets["docs/assets/planforge-cli.png"] = _terminal_png(commands, plan)
    assets["docs/assets/planforge-gantt.svg"] = _gantt_svg(request, plan)

    scenarios = []
    for horizon in (240, 300, 360, 420):
        document = request.to_document()
        document["horizon_minutes"] = horizon
        scenario_request = PlanningRequest.from_document(document)
        scenario_plan = solve(scenario_request)
        verify_plan(scenario_request, scenario_plan)
        scenarios.append({"horizon_minutes": horizon, "scheduled_count": scenario_plan["objective"]["scheduled_count"], "total_priority": scenario_plan["objective"]["total_priority"]})
    assets["docs/assets/planforge-horizon-curve.svg"] = _horizon_svg(scenarios)
    assets["docs/assets/planforge-proof-flow.svg"] = _proof_svg(plan, verification)
    assets["docs/assets/planforge-plan.json"] = canonical_bytes(plan)
    assets["docs/assets/planforge-verification.json"] = canonical_bytes(verification)
    for relative, payload in assets.items():
        _write(output_root, relative, payload)

    font_path, font_identity = _font()
    del font_path
    bindings = {}
    for relative in SOURCE_BINDINGS:
        payload = (ROOT / relative).read_bytes()
        bindings[relative] = {"bytes": len(payload), "sha256": _digest(payload)}
    manifest = {
        "artifacts": {relative: {"bytes": len(assets[relative]), "sha256": _digest(assets[relative])} for relative in sorted(assets)},
        "browser": {
            "assertions": browser_assertions,
            "container_image": container_image,
            "javascript_enabled": True,
            "network": "container-none-loopback-only",
            "outer_isolation": {"capabilities": "dropped", "new_privileges": False, "root_filesystem": "read_only", "runtime_user": "non_root"},
            "playwright_version": importlib.metadata.version("playwright"),
            "process_sandbox": False,
            "service_workers": "block",
        },
        "commands": commands,
        "environment": {"architecture": platform.machine(), "font": font_identity, "pillow_version": PILLOW_VERSION, "python_implementation": platform.python_implementation(), "python_version": platform.python_version()},
        "fixture": {"bytes": len(fixture_payload), "path": FIXTURE, "sha256": _digest(fixture_payload), "synthetic": True},
        "generated_files": list(OUTPUTS),
        "plan": {"plan_sha256": sha256_hex(canonical_bytes(plan)), "request_sha256": plan["request_sha256"], "verification_sha256": _digest(canonical_bytes(verification))},
        "scenarios": scenarios,
        "schema": "planforge.evidence.v1",
        "source": {"bindings": bindings, "revision": source_revision, "tree": source_tree},
    }
    serialized = canonical_bytes(manifest)
    forbidden = (b"/home/", b"/tmp/", b"file://", b"github_pat_", b"gho_", b"OPENWEATHER_API_KEY")
    if any(marker in serialized for marker in forbidden):
        raise RuntimeError("manifest leaked a path or credential marker")
    _write(output_root, "docs/assets/planforge-evidence.json", serialized)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--container-image", required=True)
    arguments = parser.parse_args()
    if len(arguments.source_revision) != 40 or len(arguments.source_tree) != 40:
        raise SystemExit(2)
    generate(arguments.output_root, arguments.source_revision, arguments.source_tree, arguments.container_image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
