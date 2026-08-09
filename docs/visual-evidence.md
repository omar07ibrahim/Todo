# PlanForge visual evidence provenance

The committed visual bundle contains 11 exact files. Ten result artifacts are hash-bound by `planforge-evidence.json`; the manifest is canonical ASCII JSON and binds the source revision/tree, every renderer/verifier/runtime source input, fixture identity, CLI stdout hashes, browser/container/runtime versions, actual font bytes, browser assertions, counterfactual scenarios, and artifact byte hashes.

## File-by-file meaning

- `planforge-dashboard.png` — real 1440×1000 Chromium viewport after a successful loopback navigation.
- `planforge-mobile.png` — real 390×844 Chromium mobile-emulation viewport.
- `planforge-full-page.png` — real full-document Chromium capture; its measured height is structurally checked.
- `planforge-interaction.gif` — three real viewport frames after clicks on three distinct task controls; selected IDs and durations are recorded.
- `planforge-cli.png` — a raster rendering of exact captured solve/verify stdout plus executed command labels; the underlying stdout bytes remain in the manifest.
- `planforge-gantt.svg` — vector schedule generated only from the verified plan blocks.
- `planforge-horizon-curve.svg` — vector plot of four separate exact solve + independent verify scenarios.
- `planforge-proof-flow.svg` — source-bound architecture annotated with observed state/sequence/hash evidence.
- `planforge-plan.json` — canonical executed plan.
- `planforge-verification.json` — canonical independent verification receipt.
- `planforge-evidence.json` — manifest and source/environment provenance.

## Adoption and drift policy

The initial hosted adoption rendered candidates A and B in separate isolated container invocations, independently verified both, required all 11 files to match byte-for-byte, allowed only the exact bounded inventory into the commit, and set author and committer to Omar Ibrahim. That one-shot write workflow was then deleted.

The permanent workflow has read-only repository permission. On every pull request and `main` push it derives the last source-binding revision, regenerates the entire bundle inside the pinned offline container, runs the independent evidence verifier, and compares every candidate byte with the committed review set. It cannot silently refresh images.

## Visual review record

At adoption, the desktop, full-page, 390×844 mobile, CLI, and three-frame interaction evidence were opened and inspected. Text is legible, the full-page footer is present, the desktop viewport has no clipping, the mobile reflow is coherent, the CLI output is visible, and no secret, personal path, real task data, port, or environment value appears. The fixture uses synthetic release-planning labels only.

SVGs are ASCII, contain a fixed passive element allow-list, and have no URL-bearing, event-handler, or style attributes. PNGs are normalized RGB without metadata. The GIF has exact dimensions, frame count, and durations and no comment metadata.
