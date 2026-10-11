# LivingPQ R20 - Apollo Real Input WebGL Evidence

**Status: INPUT TECHNICAL PASS / VISUAL FAIL / RESEARCH ONLY.** This branch is not deployed and not a free-walkable scanned Sunset Town.

## Open the proof
- [Browser-recorded 24.5-second WebGL keyboard-and-mouse session](R20_REAL_INPUT_WEBGL_25S.webm). Real Playwright-driven player inputs and stops, **not** an autonomous orbit camera.
- [Original viewpoint WebGL](R20_00_front.png)
- [Lateral stress viewpoint (torn geometry)](R20_03_lateral_stop.png)
- [Lookback viewpoint (unobserved sky)](R20_05_lookback_stop.png)
- [Recorded input, view positions, technical checks](R20_REAL_INPUT_QA.json)
- [Post-minified build smoke verification](README_R20.md)

## What passed
PlayCanvas WebGL loaded R17G SOG successfully. WASD, mouse-look, stopping, +/-2m bounded navigation proxy, recorded position trace and video worked. The 24.537-second WebM is browser-recorded from Edge headless with real keyboard/mouse events; nine technical QA checks passed. Post-build smoke after esbuild minification also passed movement and camera look. **Real iPhone landscape frame rate remains untested.**

## Why this is not finished
R17G's 221,184 Gaussian points come from ONE Apollo photograph with inferred monocular depth, **not a true multi-camera reconstruction**. The main view retains architectural recognition, but moving 1-2m exposes missing surfaces, gaps, floaters and stretched façades. Looking back reveals almost no real architecture. People are still baked into photo source. R19 removal attempts smeared the street and were deliberately not promoted.

Navigation bounds are a labeled flat **PROXY**, NOT surveyed road or collision. No true 10x10m architectural free-walk visual pass. Next step requires rights-cleared overlapping, translated camera capture or real multi-view scene scan.

## Source and reproducibility
Original Apollo Café photograph: Vivu Vietnam, Wikimedia Commons, CC BY-SA 4.0; transformative depth and Gaussian work derived from that source. Depth Anything V2 Small Apache 2.0. PlayCanvas and SplatTransform MIT. Static image provenance is detailed in README_R20.md.
The research viewer sources are main.js, minified app.js, index.html, scene.sog, server.cjs. Locally run `node server.cjs 4190` and open `http://127.0.0.1:4190/`. This is **not publicly deployed**.

R17G evidence remains intact in [its original research branch](https://github.com/kenzuko/Jotrip-Lab/tree/livingpq-r17g-apollo-evidence-20261010).

**MASTER LOCK:** No merge, deploy, production change, Cloudflare, GitHub-hosted Actions, paid AI API, fake GPS or alterations to OpenPQ Core 1.2, UniKey or PhuQuocLux.
