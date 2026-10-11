# LivingPQ R20 - REAL Input WebGL Proof (11 October 2026)
**Status: TECHNICAL INPUT PASS / VISUAL FAIL-HOLD / NO DEPLOY**

## What was built
- Original R17G scene.sog preserved (1,073,388 B, single-image predicted depth, 221,184 image-derived Gaussian points).
- Genuine yaw/pitch perspective camera (R17G always looked at a fixed point).
- W/A/S/D and arrows to move, drag mouse/touch for look, landscape joystick for movement.
- Stops on input release, records coordinates and on-screen path; bounded navigation proxy x/z +-2m.
- Explicit disocclusion warning; the flat ground bounds are NOT surveyed street/collision.
- R19 smeared person-inpaint candidate was NOT used; source people remain baked into Gaussian photograph.
- Original R17G and production untouched.

## Real browser-input QA
Script: qa-r20-real-input.cjs; PlayCanvas WebGL in 844x390 headless Windows Edge (SwiftShader) with REAL keyboard and pointer events driven by Playwright.
Browser video: R20_REAL_INPUT_WEBGL_25S.webm, ~24.5 seconds, 2,490,108 bytes.
Input sequence: walk -> stop -> turn -> strafe -> stop -> backstep -> look back -> stop.
Screenshots: R20_00_front.png, R20_01_walk_stop.png, R20_02_turn.png, R20_03_lateral_stop.png, R20_04_backstep.png, R20_05_lookback_stop.png.
Data: R20_REAL_INPUT_QA.json.
9/9 technical checks PASS: WebGL asset, movement input, pointer look, stopping, >1m displacement stress, bounds, no errors, browser video, >=3 views.

## ACTUAL visual evaluation
**VISUAL FAIL** after viewing WebGL screenshots. Front recognizable but reveals rectangle-cut photographic boundaries. After ~2m translation, sky gaps, torn surfaces, floaters and stretched building fragments dominate. Lookback is almost all flat sky. This is a single-photo source limitation, not a controller bug.
R20 is NOT a photo-real 10x10m freewalking scene and R19 removal of people is NOT accepted.

## Mobile / performance
Landscape touch layout implemented but NOT physically tested on iPhone. Windows Edge FPS does not prove iPhone >=30fps. Local Windows loopback cannot be opened from iPhone on another device.

## Feasible next gate
Obtain continuous rights-cleared camera-translating imagery or a rights-cleared real 3D scan of the Apollo 5-10m frontage. R18 five-photo SIFT check had 0/10 accepted geometry pairs (best 14 F-inliers). Do not infer missing architectural surfaces from unrelated views or fake GPS. When adequate source becomes available, separate surveyed/observed architecture from inferred fill, physics/ground navigation proxy, and independent pedestrian/avatar actors. Only then retest >=1m parallax and actual iPhone hardware.

## Local run
Open PHUQUOCLUX folder C:\Users\Public\OpenPQ\living-r20-interactive-proxy-20261011.
Run: node server.cjs 4190
Open on PHUQUOCLUX itself: http://127.0.0.1:4190/
This is not a public deployment.

## Image and code provenance
Apollo daytime photograph Vivu Vietnam, Wikimedia Commons CC BY-SA 4.0 (derivative renders); Depth Anything V2 Small Apache 2.0; PlayCanvas MIT/SplatTransform MIT.
MASTER: NO MERGE, NO DEPLOY, NO PROD/Core 1.2/CMS/auth/schema, NO GitHub-hosted Actions or Cloudflare experiments, NO paid APIs, NO fake GPS. UniKey and PhuQuocLux apps/files preserved.
