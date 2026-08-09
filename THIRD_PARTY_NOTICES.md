# Third-party notices

PlanForge has no runtime dependencies. The installed wheel uses only Python's standard library.

The reproducible evidence lane, which is not shipped as runtime code, uses:

- Microsoft Playwright Python 1.62.0 (Apache-2.0) and its Chromium 151.0.7922.34 image, pinned to the recorded linux/amd64 platform digest;
- Pillow 12.3.0 (HPND) to normalize screenshots, render the captured CLI output, and assemble real interaction frames;
- pyee 13.0.0, greenlet 3.2.4, and typing-extensions 4.15.0 as hash-locked Playwright dependencies;
- the DejaVu Sans Mono font selected inside the pinned container; its exact filename, byte count, and SHA-256 are recorded in `docs/assets/planforge-evidence.json`.

Evidence screenshots and GIFs contain rasterized pixels, not redistributed browser or font binaries. Exact package hashes and browser image identities live in `requirements/` and the evidence manifest.
