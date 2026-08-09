from __future__ import annotations

import base64
from hashlib import sha256
import http.client
import json
from pathlib import Path
from threading import Thread
import unittest

from planforge.model import PlanningRequest
from planforge.web import CSP, CSS, JS, Dashboard, make_server, render_dashboard

ROOT = Path(__file__).resolve().parents[1]


def request_fixture() -> PlanningRequest:
    return PlanningRequest.from_document(json.loads((ROOT / "examples" / "launch-day.request.json").read_text()))


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dashboard = Dashboard.build(request_fixture())
        self.server = make_server(self.dashboard)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def exchange(self, method: str, path: str, *, host: str | None = None) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {} if host is None else {"Host": host}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        result = response.status, {key.lower(): value for key, value in response.getheaders()}, payload
        connection.close()
        return result

    def test_real_http_dashboard_is_self_contained_and_verified(self) -> None:
        status, headers, payload = self.exchange("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-security-policy"], CSP)
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(int(headers["content-length"]), len(payload))
        self.assertIn(b"independently verified", payload)
        self.assertIn(str(self.dashboard.plan["proof"]["expanded_states"]).encode(), payload)
        self.assertNotIn(b"https://", payload)
        self.assertNotIn(b"http://", payload)

    def test_csp_hashes_bind_the_exact_inline_sources(self) -> None:
        for source, directive in ((CSS, "style-src"), (JS, "script-src")):
            digest = base64.b64encode(sha256(source.encode()).digest()).decode()
            self.assertIn(f"{directive} 'sha256-{digest}'", CSP)

    def test_api_returns_the_exact_verified_plan(self) -> None:
        status, _headers, payload = self.exchange("GET", "/api/plan")
        self.assertEqual(status, 200)
        document = json.loads(payload)
        self.assertEqual(document["plan"], self.dashboard.plan)
        self.assertEqual(document["verification"], self.dashboard.verification)

    def test_bad_host_query_and_method_fail_closed(self) -> None:
        self.assertEqual(self.exchange("GET", "/", host="attacker.example")[0], 421)
        self.assertEqual(self.exchange("GET", "/?debug=1")[0], 404)
        self.assertEqual(self.exchange("POST", "/")[0], 405)

    def test_head_has_headers_without_a_body(self) -> None:
        status, headers, payload = self.exchange("HEAD", "/")
        self.assertEqual(status, 200)
        self.assertGreater(int(headers["content-length"]), 1_000)
        self.assertEqual(payload, b"")

    def test_untrusted_title_is_html_escaped(self) -> None:
        document = request_fixture().to_document()
        document["tasks"][0]["title"] = "<script>alert(1)</script>"
        request = PlanningRequest.from_document(document)
        dashboard = Dashboard.build(request)
        payload = render_dashboard(request, dashboard.plan, dashboard.verification)
        self.assertIn(b"&lt;script&gt;alert(1)&lt;/script&gt;", payload)
        self.assertNotIn(b"<script>alert(1)</script>", payload)


if __name__ == "__main__":
    unittest.main()
