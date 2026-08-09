from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "planforge"


class CurrentTreeSecurityTests(unittest.TestCase):
    def test_runtime_has_no_legacy_network_or_secret_dependency(self) -> None:
        payload = b"\n".join(path.read_bytes() for path in sorted(RUNTIME.glob("*.py")))
        for marker in (b"flask", b"sqlalchemy", b"requests", b"OPENWEATHER", b"TODO_SECRET_KEY"):
            self.assertNotIn(marker.lower(), payload.lower())
        self.assertIsNone(re.search(rb"(?i)\b[0-9a-f]{32}\b", payload))

    def test_runtime_import_roots_are_stdlib_or_planforge(self) -> None:
        allowed = {
            "argparse", "base64", "dataclasses", "hashlib", "html", "http", "itertools",
            "json", "os", "pathlib", "planforge", "re", "stat", "sys", "typing",
            "unicodedata", "urllib",
        }
        roots: set[str] = set()
        for path in sorted(RUNTIME.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    roots.update(alias.name.split(".", 1)[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".", 1)[0])
        self.assertEqual(roots - allowed, set())

    def test_actions_are_immutable_and_credentials_are_not_persisted(self) -> None:
        actions = re.compile(r"uses:\s+[^@\s]+@([0-9a-f]{40})\s")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("@main", source)
            self.assertNotIn("@master", source)
            self.assertGreaterEqual(len(actions.findall(source)), 1)
            if "actions/checkout" in source:
                self.assertIn("persist-credentials: false", source)

    def test_historical_revocation_boundary_is_documented(self) -> None:
        for relative in ("README.md", "SECURITY.md"):
            document = (ROOT / relative).read_text(encoding="utf-8").lower()
            self.assertIn("git history", document)
            self.assertIn("revoke", document)

    def test_fixture_is_explicitly_synthetic_in_evidence(self) -> None:
        manifest = (ROOT / "docs" / "assets" / "planforge-evidence.json").read_text(encoding="ascii")
        self.assertIn('"synthetic":true', manifest)
        self.assertNotIn("/home/", manifest)
        self.assertNotIn("/tmp/", manifest)


if __name__ == "__main__":
    unittest.main()
