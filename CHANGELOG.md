# Changelog

All notable maintained-source changes are recorded here. PlanForge follows
semantic versioning for the Python package.

## [Unreleased]

- Add contribution and maintenance boundaries.
- Add grouped weekly dependency maintenance for build/evidence tools and
  GitHub Actions.
- Require confirmation that historical provider credentials were revoked
  before the first release.

## [0.3.0] - 2026-08-09

_Source state only; no release has been published._

- Replace the original Todo prototype with a dependency-free exact
  dependency-aware planner and independently implemented exhaustive verifier.
- Add canonical private proof bundles, tamper detection, stable CLI receipts,
  and a secure loopback-only dashboard.
- Publish 11 byte-reproducible evidence files: real desktop/mobile/full-page
  Chromium captures, a three-state GIF, executed CLI output, exact charts,
  proof-flow architecture, plan/verification receipts, and source manifest.
- Verify 32 tests on Python 3.11–3.14, deterministic distributions, installed
  wheel behavior, CodeQL, and offline Chromium evidence drift.
- Remove all runtime use of historical credential material while documenting
  the required provider-side revocation.
