"""Loopback-only dashboard for one independently verified PlanForge result."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any
from urllib.parse import urlsplit

from planforge.canonical import canonical_bytes
from planforge.model import PlanningRequest
from planforge.planner import solve
from planforge.verifier import verify_plan

CSS = """
:root{color-scheme:dark;--ink:#f7f8fc;--muted:#a9b2c7;--panel:#11182a;--line:#28334d;--a:#7c9cff;--b:#61d6a8;--c:#ffbd6b;--danger:#ff8095}*{box-sizing:border-box}body{margin:0;background:#080d19;color:var(--ink);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:1180px;margin:0 auto;padding:42px 28px 64px}.eyebrow{color:var(--b);font-size:12px;font-weight:800;letter-spacing:.16em;text-transform:uppercase}.hero{display:grid;grid-template-columns:1.45fr .55fr;gap:24px;align-items:end;margin-bottom:30px}h1{font-size:clamp(38px,6vw,70px);line-height:.96;margin:10px 0 16px;letter-spacing:-.05em}.lede{color:var(--muted);font-size:18px;max-width:720px}.verified{justify-self:end;border:1px solid #2d6e5b;background:#0b251f;color:#91f2cd;border-radius:999px;padding:10px 16px;font-weight:800}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.metric,.panel{background:linear-gradient(160deg,#131b2e,#0d1424);border:1px solid var(--line);border-radius:18px}.metric{padding:18px}.metric strong{display:block;font-size:30px;letter-spacing:-.04em}.metric span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}.panel{padding:22px;margin-top:16px}.panel-head{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:18px}.panel h2{margin:0;font-size:22px}.panel p{margin:4px 0 0;color:var(--muted)}.hash{font:12px ui-monospace,SFMono-Regular,Consolas,monospace;color:#91a2c5}.timeline{width:100%;height:auto;background:#0a1020;border-radius:14px;border:1px solid #1f2941}.axis{fill:#7f8ba8;font-size:11px}.block{stroke:#0a1020;stroke-width:3}.tone-0{fill:#7c9cff}.tone-1{fill:#61d6a8}.tone-2{fill:#ffbd6b}.tone-3{fill:#e68cff}.block-label{fill:#09101f;font-size:11px;font-weight:900}.grid{display:grid;grid-template-columns:1.15fr .85fr;gap:16px}.task-list{display:grid;gap:8px}.task{width:100%;display:grid;grid-template-columns:42px 1fr auto;gap:12px;align-items:center;text-align:left;color:var(--ink);background:#0b1221;border:1px solid #25304a;border-radius:13px;padding:12px;cursor:pointer}.task:hover,.task.selected{border-color:var(--a);background:#121d36}.seq{display:grid;place-items:center;width:34px;height:34px;border-radius:10px;background:#202d4d;color:#b9c8ff;font-weight:900}.task small{display:block;color:var(--muted)}.priority{color:#91f2cd;font-weight:900}.detail{display:none;min-height:230px;padding:18px;border-radius:14px;background:#0a1020;border:1px solid #202b44}.detail.active{display:block}.detail h3{margin-top:0;font-size:24px}.detail dl{display:grid;grid-template-columns:1fr 1fr;gap:12px}.detail dt{color:var(--muted);font-size:11px;text-transform:uppercase}.detail dd{margin:2px 0;font-weight:800}.excluded{border-color:#603345;background:#21121c}.excluded strong{color:#ff9aac}.proof{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.proof div{padding:12px;background:#0a1020;border-radius:12px}.proof strong{display:block;font-size:20px}.proof span{color:var(--muted);font-size:11px}.foot{display:flex;justify-content:space-between;gap:20px;margin-top:26px;color:var(--muted);font-size:12px}@media(max-width:760px){main{padding:26px 16px 44px}.hero,.grid{grid-template-columns:1fr}.verified{justify-self:start}.metrics{grid-template-columns:1fr 1fr}.proof{grid-template-columns:1fr 1fr}.panel{padding:16px}.panel-head,.foot{align-items:start;flex-direction:column}.task{grid-template-columns:38px 1fr}.priority{grid-column:2}.timeline{min-width:700px}.timeline-wrap{overflow-x:auto}}
""".strip()

JS = """
(()=>{const buttons=[...document.querySelectorAll('[data-task]')];const details=[...document.querySelectorAll('[data-detail]')];function select(id){buttons.forEach(button=>{const active=button.dataset.task===id;button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));});details.forEach(detail=>detail.classList.toggle('active',detail.dataset.detail===id));}buttons.forEach(button=>button.addEventListener('click',()=>select(button.dataset.task)));if(buttons.length){select(buttons[0].dataset.task);}})();
""".strip()


def _hash_source(source: str) -> str:
    return base64.b64encode(sha256(source.encode("utf-8")).digest()).decode("ascii")


CSP = "; ".join(
    (
        "default-src 'none'",
        f"style-src 'sha256-{_hash_source(CSS)}'",
        f"script-src 'sha256-{_hash_source(JS)}'",
        "img-src 'none'",
        "font-src 'none'",
        "connect-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _objective(plan: dict[str, Any], key: str) -> int:
    value = plan["objective"][key]
    if type(value) is not int:
        raise RuntimeError("planner objective changed type")
    return value


def render_dashboard(
    request: PlanningRequest,
    plan: dict[str, Any],
    verification: dict[str, Any],
) -> bytes:
    scheduled = plan["scheduled"]
    unscheduled = plan["unscheduled"]
    proof = plan["proof"]
    width = 1_040
    left = 40
    blocks: list[str] = []
    for index, item in enumerate(scheduled):
        x = left + round(
            (item["start_minute"] - request.start_minute) * width / request.horizon_minutes
        )
        block_width = max(4, round((item["end_minute"] - item["start_minute"]) * width / request.horizon_minutes))
        label = escape(item["task_id"])
        blocks.append(
            f'<rect class="block tone-{index % 4}" x="{x}" y="62" width="{block_width}" height="68" rx="9"><title>{escape(item["title"])}</title></rect>'
            f'<text class="block-label" x="{x + 8}" y="88">{label}</text>'
            f'<text class="block-label" x="{x + 8}" y="108">{_clock(item["start_minute"])}</text>'
        )
    ticks: list[str] = []
    for minute in range(request.start_minute, request.end_minute + 1, 60):
        x = left + round((minute - request.start_minute) * width / request.horizon_minutes)
        ticks.append(
            f'<path d="M{x} 44V148" stroke="#202b44"/><text class="axis" x="{x}" y="166" text-anchor="middle">{_clock(minute)}</text>'
        )

    task_buttons: list[str] = []
    task_details: list[str] = []
    for item in scheduled:
        task_id = escape(item["task_id"])
        title = escape(item["title"])
        dependency_text = ", ".join(item["dependencies"]) or "none"
        status = "on time" if item["tardiness_minutes"] == 0 else f'{item["tardiness_minutes"]}m late'
        task_buttons.append(
            f'<button class="task" type="button" data-task="{task_id}" aria-pressed="false"><span class="seq">{item["sequence"]}</span><span><strong>{title}</strong><small>{_clock(item["start_minute"])}–{_clock(item["end_minute"])} · {status}</small></span><span class="priority">P{item["priority"]}</span></button>'
        )
        task_details.append(
            f'<section class="detail" data-detail="{task_id}"><div class="eyebrow">Decision trace</div><h3>{title}</h3><p>The exact solver placed this task after all selected prerequisites and compared the complete schedule against every feasible topological sequence.</p><dl><div><dt>Window</dt><dd>{_clock(item["start_minute"])}–{_clock(item["end_minute"])}</dd></div><div><dt>Due</dt><dd>{_clock(item["due_minute"])}</dd></div><div><dt>Dependencies</dt><dd>{escape(dependency_text)}</dd></div><div><dt>Outcome</dt><dd>{escape(status)}</dd></div></dl></section>'
        )

    excluded_cards = "".join(
        f'<div class="panel excluded"><div class="eyebrow">Capacity trade-off</div><h2><strong>{escape(item["title"])}</strong> remains unscheduled</h2><p>Reason: {escape(item["reason"].replace("_", " "))}. Priority {item["priority"]}; missing dependencies: {escape(", ".join(item["missing_dependencies"]) or "none")}.</p></div>'
        for item in unscheduled
    )
    plan_sha = verification["plan_sha256"]
    request_sha = verification["request_sha256"]
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>PlanForge verified schedule</title><style>{CSS}</style></head>
<body><main><header class="hero"><div><div class="eyebrow">Classical AI · exact planning</div><h1>Ship the day,<br>with proof.</h1><p class="lede">A bounded dependency-aware scheduler explored the feasible plan space, optimized a public lexicographic objective, and passed an independent exhaustive verifier.</p></div><div class="verified">✓ independently verified</div></header>
<section class="metrics" aria-label="Plan metrics"><div class="metric"><strong>{_objective(plan,"total_priority")}</strong><span>scheduled priority</span></div><div class="metric"><strong>{_objective(plan,"on_time_priority")}</strong><span>on-time priority</span></div><div class="metric"><strong>{_objective(plan,"scheduled_count")}/{len(request.tasks)}</strong><span>tasks selected</span></div><div class="metric"><strong>{proof["expanded_states"]}</strong><span>states expanded</span></div></section>
<section class="panel"><div class="panel-head"><div><div class="eyebrow">Optimal timeline</div><h2>{_clock(request.start_minute)}–{_clock(request.end_minute)} hard horizon</h2><p>Non-preemptive blocks; dependencies always complete first.</p></div><div class="hash">plan {plan_sha[:12]}…</div></div><div class="timeline-wrap"><svg class="timeline" viewBox="0 0 1120 190" role="img" aria-label="Verified task schedule"><title>Verified PlanForge task schedule</title>{''.join(ticks)}{''.join(blocks)}</svg></div></section>
<section class="panel"><div class="panel-head"><div><div class="eyebrow">Explainable sequence</div><h2>Inspect each scheduling decision</h2></div><p>Select a task to expose its constraints.</p></div><div class="grid"><div class="task-list">{''.join(task_buttons)}</div><div>{''.join(task_details)}</div></div></section>
{excluded_cards}
<section class="panel"><div class="panel-head"><div><div class="eyebrow">Search certificate</div><h2>Closed exact search</h2></div><p>No learned model and no opaque score.</p></div><div class="proof"><div><strong>{proof["candidate_schedules"]}</strong><span>candidates scored</span></div><div><strong>{proof["pruned_horizon"]}</strong><span>horizon prunes</span></div><div><strong>{proof["pruned_priority_bound"]}</strong><span>admissible bound prunes</span></div><div><strong>{verification["verified_feasible_sequences"]}</strong><span>independent feasible sequences</span></div></div></section>
<footer class="foot"><span>planforge.plan.v1 · synthetic launch-day fixture</span><span class="hash">request {request_sha[:12]}… · offline loopback UI</span></footer></main><script>{JS}</script></body></html>
"""
    return html.encode("utf-8")


@dataclass(frozen=True, slots=True)
class Dashboard:
    request: PlanningRequest
    plan: dict[str, Any]
    verification: dict[str, Any]
    html: bytes
    api: bytes

    @classmethod
    def build(cls, request: PlanningRequest) -> "Dashboard":
        plan = solve(request)
        verification = verify_plan(request, plan)
        return cls(
            request=request,
            plan=plan,
            verification=verification,
            html=render_dashboard(request, plan, verification),
            api=canonical_bytes(
                {
                    "plan": plan,
                    "request": request.to_document(),
                    "verification": verification,
                }
            ),
        )


class _LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def _host_is_loopback(value: str | None) -> bool:
    if value is None or len(value) > 80 or any(character.isspace() for character in value):
        return False
    host = value
    if value.startswith("["):
        closing = value.find("]")
        if closing < 0:
            return False
        host = value[: closing + 1]
        suffix = value[closing + 1 :]
        if suffix and (not suffix.startswith(":") or not suffix[1:].isdigit()):
            return False
    elif ":" in value:
        host, port = value.rsplit(":", 1)
        if not port.isdigit():
            return False
    return host.lower() in {"127.0.0.1", "localhost", "[::1]"}


def make_server(dashboard: Dashboard, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1"} or type(port) is not int or not 0 <= port <= 65_535:
        raise ValueError("dashboard server is loopback-only")

    class Handler(BaseHTTPRequestHandler):
        server_version = "PlanForge"
        sys_version = ""

        def log_message(self, _format: str, *_arguments: object) -> None:
            return

        def _send(self, status: int, content_type: str, payload: bytes, *, head: bool = False) -> None:
            self.send_response(status)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Content-Type", content_type)
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not head:
                self.wfile.write(payload)

        def _dispatch(self, *, head: bool) -> None:
            if not _host_is_loopback(self.headers.get("Host")):
                self._send(421, "application/json", canonical_bytes({"error": "invalid_host"}), head=head)
                return
            target = urlsplit(self.path)
            if target.query or target.fragment:
                self._send(404, "application/json", canonical_bytes({"error": "not_found"}), head=head)
            elif target.path == "/":
                self._send(200, "text/html; charset=utf-8", dashboard.html, head=head)
            elif target.path == "/api/plan":
                self._send(200, "application/json", dashboard.api, head=head)
            elif target.path == "/healthz":
                self._send(
                    200,
                    "application/json",
                    canonical_bytes(
                        {
                            "request_sha256": dashboard.verification["request_sha256"],
                            "status": "ok",
                        }
                    ),
                    head=head,
                )
            else:
                self._send(404, "application/json", canonical_bytes({"error": "not_found"}), head=head)

        def do_GET(self) -> None:
            self._dispatch(head=False)

        def do_HEAD(self) -> None:
            self._dispatch(head=True)

        def do_POST(self) -> None:
            self._send(405, "application/json", canonical_bytes({"error": "method_not_allowed"}))

    return _LoopbackServer((host, port), Handler)
