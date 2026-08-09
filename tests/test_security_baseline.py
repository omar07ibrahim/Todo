from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
TEMPLATE = ROOT / "templates" / "index.html"


class SanitizedSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = APP.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_runtime_secrets_come_from_named_environment_variables(self) -> None:
        self.assertIn('os.environ.get("TODO_SECRET_KEY")', self.source)
        self.assertIn('os.environ.get("OPENWEATHER_API_KEY")', self.source)
        self.assertNotRegex(self.source, re.compile(r"(?i)\b[0-9a-f]{32}\b"))

    def test_outbound_request_has_params_and_bounded_timeout(self) -> None:
        calls = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "requests"
            and node.func.attr == "get"
        ]
        self.assertEqual(len(calls), 1)
        keywords = {keyword.arg for keyword in calls[0].keywords}
        self.assertIn("params", keywords)
        self.assertIn("timeout", keywords)

    def test_mutating_routes_are_post_only_in_the_template(self) -> None:
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn('href="/delete_task/', template)
        self.assertNotIn('href="/toggle_task/', template)
        self.assertIn('method="post" action="/delete_task/', template)
        self.assertIn('method="post" action="/toggle_task/', template)

    def test_local_secret_and_database_files_are_ignored(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env", ignored)
        self.assertIn("instance/", ignored)
        self.assertIn("tasks.db", ignored)


if __name__ == "__main__":
    unittest.main()
