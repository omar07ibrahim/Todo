from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "launch-day.request.json"


def command(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        (sys.executable, "-m", "planforge", *arguments),
        cwd=ROOT,
        check=False,
        capture_output=True,
    )


class CliBundleTests(unittest.TestCase):
    def test_solve_and_verify_publish_one_private_canonical_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "proof"
            solved = command("solve", "--request", str(FIXTURE), "--output", str(bundle))
            self.assertEqual(solved.returncode, 0, solved.stderr)
            self.assertEqual(solved.stderr, b"")
            summary = json.loads(solved.stdout)
            self.assertEqual(summary["status"], "solved")
            self.assertEqual(
                {entry.name for entry in bundle.iterdir()},
                {"plan.json", "request.json", "verification.json"},
            )
            self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o700)
            for path in bundle.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                payload = path.read_bytes()
                self.assertTrue(payload.isascii())
                self.assertTrue(payload.endswith(b"\n"))
                self.assertEqual(payload.count(b"\n"), 1)
            verified = command("verify", "--bundle", str(bundle))
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(verified.stderr, b"")
            verification = json.loads(verified.stdout)
            self.assertEqual(verification["status"], "verified")
            self.assertEqual(summary["plan_sha256"], verification["plan_sha256"])

    def test_output_bundle_is_no_clobber(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "proof"
            first = command("solve", "--request", str(FIXTURE), "--output", str(bundle))
            before = {path.name: path.read_bytes() for path in bundle.iterdir()}
            second = command("solve", "--request", str(FIXTURE), "--output", str(bundle))
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(json.loads(second.stderr)["error"], "invalid_input")
            self.assertEqual(before, {path.name: path.read_bytes() for path in bundle.iterdir()})

    def test_duplicate_json_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = root / "duplicate.json"
            request.write_text('{"schema":"planforge.request.v1","schema":"again"}\n')
            completed = command("solve", "--request", str(request), "--output", str(root / "out"))
            self.assertEqual(completed.returncode, 2)
            self.assertFalse((root / "out").exists())

    def test_tampered_plan_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "proof"
            self.assertEqual(command("solve", "--request", str(FIXTURE), "--output", str(bundle)).returncode, 0)
            plan_path = bundle / "plan.json"
            plan = json.loads(plan_path.read_text())
            plan["objective"]["total_priority"] += 1
            plan_path.write_text(json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n")
            os.chmod(plan_path, 0o600)
            completed = command("verify", "--bundle", str(bundle))
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, b"")

    @unittest.skipIf(not hasattr(os, "symlink"), "symlink support is unavailable")
    def test_symlink_request_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            link = root / "request.json"
            link.symlink_to(FIXTURE)
            completed = command("solve", "--request", str(link), "--output", str(root / "out"))
            self.assertEqual(completed.returncode, 2)
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
