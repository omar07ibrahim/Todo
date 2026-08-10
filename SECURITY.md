# Security policy

Please use [GitHub private vulnerability reporting](https://github.com/omar07ibrahim/Todo/security/advisories/new) instead of a public issue for security-sensitive reports.

## Supported boundary

Only the latest protected `main` branch is supported. PlanForge is a local, dependency-free planner, not an internet service. Its HTTP dashboard binds only to `127.0.0.1` or `::1`, rejects non-loopback Host headers, serves three exact read-only routes, and attaches a hash-bound Content Security Policy plus no-store, nosniff, same-origin, no-referrer, and restrictive permissions headers.

Planning JSON is untrusted. The parser enforces exact fields, strict types, a 64 KiB canonical request bound, 1–9 tasks, 15-minute slots, one-day horizons, canonical identifiers, bounded control-free titles, known dependencies, and an acyclic graph. CLI reads reject symlinks, changing files, multi-link inputs, oversized content, duplicate JSON keys, and non-finite numbers. Output directories are no-clobber and files are mode `0600`; an interrupted partial directory is rejected because the verifier requires the exact three-file inventory.

The browser evidence lane is CI-only. It uses synthetic data, a platform-digest-pinned Playwright/Chromium image, hash-locked Python wheels, no container network, a read-only root filesystem, a non-root user, dropped capabilities, no new privileges, and no repository write token. The runtime wheel contains none of those evidence dependencies.

## Data and claim limits

Task titles can be sensitive. Plan bundles and dashboard output reproduce them, so keep bundles private when source data is private. Hash receipts prove exact byte relationships and independent recomputation; they do not prove that human estimates, priorities, or deadlines are correct.

## Historical credential notice

The 2023 prototype committed credential material before this rewrite. Current `main` contains no runtime credential and never calls that provider, but deletion from the tip does not purge public Git history. Every historical provider credential must be treated as exposed and revoked by Omar at the provider. Do not reuse it.
