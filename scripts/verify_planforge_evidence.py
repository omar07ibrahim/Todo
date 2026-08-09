"""Independently verify the complete PlanForge visual-evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET
from typing import Any

from PIL import Image

from planforge.canonical import canonical_bytes
from planforge.model import PlanningRequest
from planforge.verifier import verify_plan

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "mcr.microsoft.com/playwright/python@sha256:51d31fdfacb0cff99a1a724152e34ae408d2bd4e7da310ff157450f49261cc59"
OUTPUTS = (
    "docs/assets/planforge-dashboard.png", "docs/assets/planforge-mobile.png", "docs/assets/planforge-full-page.png", "docs/assets/planforge-interaction.gif", "docs/assets/planforge-cli.png", "docs/assets/planforge-gantt.svg", "docs/assets/planforge-horizon-curve.svg", "docs/assets/planforge-proof-flow.svg", "docs/assets/planforge-plan.json", "docs/assets/planforge-verification.json", "docs/assets/planforge-evidence.json",
)
HASHED_OUTPUTS = OUTPUTS[:-1]
LIMITS = {relative: 12_582_912 for relative in OUTPUTS}
LIMITS.update({relative: 262_144 for relative in OUTPUTS if relative.endswith(".svg")})
LIMITS.update({"docs/assets/planforge-plan.json": 1_048_576, "docs/assets/planforge-verification.json": 262_144, "docs/assets/planforge-evidence.json": 1_048_576})
REVISION = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise RuntimeError("evidence contains a symlink")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
        raise RuntimeError("evidence file escaped its bound")
    payload = path.read_bytes()
    after = path.stat()
    if len(payload) > limit or (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise RuntimeError("evidence changed while being read")
    return payload


def _inventory(root: Path) -> tuple[str, ...]:
    paths = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("evidence contains a symlink")
        if path.is_file():
            paths.append(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise RuntimeError("evidence contains a special file")
    return tuple(sorted(paths))


def _document(payload: bytes) -> dict[str, Any]:
    value = json.loads(payload)
    if type(value) is not dict or payload != canonical_bytes(value):
        raise RuntimeError("evidence JSON is not a canonical object")
    return value


def _png(payload: bytes, expected: tuple[int, int] | None) -> tuple[int, int]:
    with Image.open(io.BytesIO(payload)) as image:
        image.load()
        if image.format != "PNG" or image.mode != "RGB" or image.info:
            raise RuntimeError("PNG structure or metadata changed")
        size = image.size
    if expected is not None and size != expected:
        raise RuntimeError("PNG dimensions changed")
    return size


def _gif(payload: bytes) -> None:
    with Image.open(io.BytesIO(payload)) as image:
        if image.format != "GIF" or image.size != (1440, 1000) or getattr(image, "n_frames", 1) != 3:
            raise RuntimeError("interaction GIF contract changed")
        durations = []
        for index in range(3):
            image.seek(index)
            image.load()
            durations.append(image.info.get("duration"))
        if durations != [900, 900, 1300] or "comment" in image.info:
            raise RuntimeError("interaction GIF timing or metadata changed")


def _svg(payload: bytes) -> None:
    if not payload.isascii() or payload.count(b'xmlns="http://www.w3.org/2000/svg"') != 1:
        raise RuntimeError("SVG encoding or namespace changed")
    remote_scan = payload.replace(b'xmlns="http://www.w3.org/2000/svg"', b"", 1)
    if b"http://" in remote_scan or b"https://" in remote_scan:
        raise RuntimeError("SVG contains remote content")
    root = ET.fromstring(payload)
    allowed = {"svg", "title", "desc", "rect", "text", "line", "polyline", "path", "circle"}
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] not in allowed:
            raise RuntimeError("SVG contains an unexpected element")
        for attribute in element.attrib:
            local = attribute.rsplit("}", 1)[-1]
            if local in {"href", "style"} or local.startswith("on"):
                raise RuntimeError("SVG contains an active attribute")


def verify(root: Path, source_revision: str, source_tree: str) -> None:
    if REVISION.fullmatch(source_revision) is None or REVISION.fullmatch(source_tree) is None:
        raise RuntimeError("source identity is not canonical")
    if _inventory(root) != tuple(sorted(OUTPUTS)):
        raise RuntimeError("evidence inventory changed")
    payloads = {relative: _read(root / relative, LIMITS[relative]) for relative in OUTPUTS}
    manifest = _document(payloads["docs/assets/planforge-evidence.json"])
    if manifest.get("schema") != "planforge.evidence.v1" or manifest.get("generated_files") != list(OUTPUTS):
        raise RuntimeError("manifest contract changed")
    artifacts = manifest.get("artifacts")
    if type(artifacts) is not dict or set(artifacts) != set(HASHED_OUTPUTS):
        raise RuntimeError("artifact inventory changed")
    for relative in HASHED_OUTPUTS:
        if artifacts[relative] != {"bytes": len(payloads[relative]), "sha256": _digest(payloads[relative])}:
            raise RuntimeError("artifact identity changed")

    source = manifest.get("source")
    if type(source) is not dict or source.get("revision") != source_revision or source.get("tree") != source_tree:
        raise RuntimeError("source identity changed")
    bindings = source.get("bindings")
    if type(bindings) is not dict or not bindings:
        raise RuntimeError("source bindings are missing")
    for relative, identity in bindings.items():
        if type(relative) is not str or type(identity) is not dict:
            raise RuntimeError("source binding shape changed")
        payload = (ROOT / relative).read_bytes()
        if identity != {"bytes": len(payload), "sha256": _digest(payload)}:
            raise RuntimeError("source binding changed")

    request = PlanningRequest.from_document(json.loads((ROOT / "examples/launch-day.request.json").read_bytes()))
    plan = _document(payloads["docs/assets/planforge-plan.json"])
    expected_verification = verify_plan(request, plan)
    verification = _document(payloads["docs/assets/planforge-verification.json"])
    if verification != expected_verification or verification.get("status") != "verified":
        raise RuntimeError("plan verification changed")
    plan_identity = manifest.get("plan")
    if type(plan_identity) is not dict or plan_identity.get("plan_sha256") != _digest(payloads["docs/assets/planforge-plan.json"]):
        raise RuntimeError("manifest plan identity changed")

    _png(payloads["docs/assets/planforge-dashboard.png"], (1440, 1000))
    _png(payloads["docs/assets/planforge-mobile.png"], (390, 844))
    full_size = _png(payloads["docs/assets/planforge-full-page.png"], None)
    if full_size[0] != 1440 or not 1000 < full_size[1] < 10_000:
        raise RuntimeError("full-page dimensions changed")
    _png(payloads["docs/assets/planforge-cli.png"], (1440, 820))
    _gif(payloads["docs/assets/planforge-interaction.gif"])
    for relative in ("docs/assets/planforge-gantt.svg", "docs/assets/planforge-horizon-curve.svg", "docs/assets/planforge-proof-flow.svg"):
        _svg(payloads[relative])

    browser = manifest.get("browser")
    if type(browser) is not dict or browser.get("container_image") != CONTAINER or browser.get("playwright_version") != "1.62.0":
        raise RuntimeError("browser identity changed")
    assertions = browser.get("assertions")
    if type(assertions) is not dict or assertions.get("chromium_version") != "151.0.7922.34":
        raise RuntimeError("Chromium identity changed")
    desktop = assertions.get("desktop")
    mobile = assertions.get("mobile")
    if type(desktop) is not dict or desktop.get("document_requests") != 1 or desktop.get("console_errors") != [] or len(desktop.get("selected_task_ids", [])) != 3:
        raise RuntimeError("desktop browser assertions changed")
    if type(mobile) is not dict or mobile.get("document_requests") != 1 or mobile.get("label") != "Chromium mobile emulation":
        raise RuntimeError("mobile browser assertions changed")
    scenarios = manifest.get("scenarios")
    if type(scenarios) is not list or [point.get("horizon_minutes") for point in scenarios if type(point) is dict] != [240, 300, 360, 420]:
        raise RuntimeError("scenario sweep changed")
    commands = manifest.get("commands")
    if type(commands) is not list or len(commands) != 2 or [json.loads(item["stdout"])["status"] for item in commands] != ["solved", "verified"]:
        raise RuntimeError("captured CLI contract changed")
    serialized = payloads["docs/assets/planforge-evidence.json"] + payloads["docs/assets/planforge-plan.json"]
    if any(marker in serialized for marker in (b"/home/", b"/tmp/", b"file://", b"github_pat_", b"gho_", b"OPENWEATHER_API_KEY")):
        raise RuntimeError("evidence leaked a path or credential marker")
    print(f"PlanForge evidence independently verified ({len(OUTPUTS)} files)")


def compare(left: Path, right: Path) -> None:
    if _inventory(left) != tuple(sorted(OUTPUTS)) or _inventory(right) != tuple(sorted(OUTPUTS)):
        raise SystemExit(1)
    if any((left / relative).read_bytes() != (right / relative).read_bytes() for relative in OUTPUTS):
        raise SystemExit(1)
    print(f"PlanForge evidence bundles match ({len(OUTPUTS)} files)")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("root", type=Path)
    verify_parser.add_argument("--source-revision", required=True)
    verify_parser.add_argument("--source-tree", required=True)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("left", type=Path)
    compare_parser.add_argument("right", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "verify":
        verify(arguments.root, arguments.source_revision, arguments.source_tree)
    else:
        compare(arguments.left, arguments.right)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
