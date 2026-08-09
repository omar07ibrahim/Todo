"""Validate source archives, wheels, and installed CLI behavior."""

from __future__ import annotations

import argparse
from importlib import metadata
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FILES = {
    "planforge/__init__.py", "planforge/__main__.py", "planforge/canonical.py",
    "planforge/cli.py", "planforge/filesystem.py", "planforge/model.py",
    "planforge/planner.py", "planforge/verifier.py", "planforge/web.py",
}
SOURCE_FILES = {
    "LICENSE", "README.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md",
    "docs/assets/planforge-dashboard.png", "docs/assets/planforge-mobile.png",
    "docs/assets/planforge-full-page.png", "docs/assets/planforge-interaction.gif",
    "docs/assets/planforge-cli.png", "docs/assets/planforge-gantt.svg",
    "docs/assets/planforge-horizon-curve.svg", "docs/assets/planforge-proof-flow.svg",
    "docs/assets/planforge-plan.json", "docs/assets/planforge-verification.json",
    "docs/assets/planforge-evidence.json", "docs/planning-contract.md",
    "examples/launch-day.request.json", "requirements/evidence-browser.txt",
    "requirements/evidence-browser-image.lock.json", "scripts/generate_planforge_evidence.py",
    "scripts/verify_planforge_evidence.py", "tests/test_planner.py",
}


def _run(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(arguments, cwd=cwd, env=environment, check=True, capture_output=True, text=True)


def _safe(path: PurePosixPath) -> None:
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise RuntimeError("distribution contains an unsafe path")


def verify(dist: Path) -> None:
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError("expected exactly one wheel and one sdist")
    wheel, sdist = wheels[0], sdists[0]
    if wheel.stat().st_size > 2_000_000 or sdist.stat().st_size > 20_000_000:
        raise RuntimeError("distribution artifact exceeded its bound")

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = tuple(archive.namelist())
        for info in archive.infolist():
            _safe(PurePosixPath(info.filename))
            mode = info.external_attr >> 16
            if mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise RuntimeError("wheel contains a link or special file")
        for required in PACKAGE_FILES:
            if required not in wheel_names:
                raise RuntimeError(f"wheel omitted {required}")
        metadata_names = [name for name in wheel_names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise RuntimeError("wheel metadata inventory changed")
        metadata_text = archive.read(metadata_names[0]).decode("utf-8")
        if "Name: planforge-exact\n" not in metadata_text or "Version: 0.3.0\n" not in metadata_text:
            raise RuntimeError("wheel identity changed")
        if "Requires-Dist:" in metadata_text:
            raise RuntimeError("runtime dependency was introduced")

    with tarfile.open(sdist, "r:gz") as archive:
        members = archive.getmembers()
        names = tuple(member.name for member in members)
        for member in members:
            _safe(PurePosixPath(member.name))
            if member.issym() or member.islnk() or (not member.isfile() and not member.isdir()):
                raise RuntimeError("sdist contains a link or special file")
        for required in PACKAGE_FILES | SOURCE_FILES:
            if not any(name.endswith("/" + required) for name in names):
                raise RuntimeError(f"sdist omitted {required}")

    with tempfile.TemporaryDirectory(prefix="planforge-dist-") as temporary:
        root = Path(temporary)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        executable = environment / ("Scripts/planforge.exe" if os.name == "nt" else "bin/planforge")
        _run(str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel), cwd=root)
        probe = _run(
            str(python),
            "-c",
            "import json,planforge;from importlib import metadata;from pathlib import Path;print(json.dumps({'module':str(Path(planforge.__file__).resolve()),'version':metadata.version('planforge-exact')},sort_keys=True))",
            cwd=root,
        )
        identity = json.loads(probe.stdout)
        if identity["version"] != "0.3.0" or Path(identity["module"]).is_relative_to(ROOT):
            raise RuntimeError("installed package probe escaped its environment")
        bundle = root / "proof"
        solved = _run(str(executable), "solve", "--request", str(ROOT / "examples" / "launch-day.request.json"), "--output", str(bundle), cwd=root)
        verified = _run(str(executable), "verify", "--bundle", str(bundle), cwd=root)
        if json.loads(solved.stdout)["status"] != "solved" or json.loads(verified.stdout)["status"] != "verified":
            raise RuntimeError("installed CLI did not preserve solve/verify behavior")
        if solved.stderr or verified.stderr:
            raise RuntimeError("installed CLI wrote unexpected stderr")
    print("wheel, sdist, and installed PlanForge CLI verified")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", required=True, type=Path)
    arguments = parser.parse_args()
    verify(arguments.dist)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
