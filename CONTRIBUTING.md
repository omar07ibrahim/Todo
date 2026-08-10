# Contributing

PlanForge is a bounded exact-planning lab, not a general production scheduler.
Changes must preserve deterministic search, independent verification, private
proof files, and source-bound visual evidence.

## Development setup

Runtime supports CPython 3.11 through 3.14 and has no third-party dependencies.

```bash
python -m venv .venv
. .venv/bin/activate
python -m unittest discover -s tests -v
python -m compileall -q planforge tests
```

To review distributions, install only the exact build tools listed in
`requirements/build-tools.txt`, then run
`scripts/verify_distribution.py` against the generated archives.

## Contract rules

- Keep requests bounded, canonical, duplicate-key safe, acyclic, and limited
  to the documented nine-task exact-search scope.
- The verifier must remain algorithmically independent: do not call or import
  the primary planner from verification code.
- Preserve no-clobber proof directories and mode-`0600` files.
- Keep the dashboard loopback-only, read-only, CSP-bound, escaped, and free of
  remote assets, analytics, cookies, or account state.
- Use synthetic task labels only. Never commit real schedules, task data,
  secrets, provider credentials, local paths, or personal data.
- Treat all credentials from historical public commits as exposed; never copy
  or repeat them in code, tests, issues, or documentation.

## Visual evidence

Do not hand-edit files under `docs/assets/`. Source-affecting changes must
regenerate the complete 11-file candidate in the pinned, offline, non-root
Chromium container; pass the independent verifier; compare every byte with the
reviewed bundle; and receive original-resolution review of desktop, full-page,
mobile, CLI, GIF, diagrams, and visible claims. See
[docs/visual-evidence.md](docs/visual-evidence.md).
