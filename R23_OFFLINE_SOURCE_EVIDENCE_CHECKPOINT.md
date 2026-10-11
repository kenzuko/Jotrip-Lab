# LivingPQ R23 - Offline Capture Evidence Gate
Date: 11 October 2026. Successor to R22, not a LivingPQ restart.
**STATUS: CAPTURE-GATE IMPLEMENTED & TESTED; APOLLO 10x10m VISUAL HOLD; NO DEPLOY**

## Code deliverable
Full independent source code and screenshots are in the verified conversation artifact: `LIVINGPQ_R23_GEOMETRY_SOURCE_GATE_20261011.zip` (~928 KB, 17 entries, ZIP CRC verified). The artifact is attached to the R23 ChatGPT conversation; **this GitHub branch contains only a checkpoint, not the entire source ZIP**.
R23 bundle: `r23_gate.py`, `r22_gate.py`, `intake.html`, Python tests, Chromium test, synthetic QA output, actual Chromium 844x390 and 390x844 screenshots, source leads, README.

## What genuinely passed
- OpenCV/NumPy offline gate now rejects exact and near-identical image sequences before running degenerate F/H solvers. Handles F/H OpenCV failures and never invents camera pose or physical baseline.
- Adds potential multi-depth correspondence test (F matches not explained by one homography), thumbnail difference, 3-view feature tracks, inlier count, temporal overlap. These are **heuristics, not proof of static scene reconstruction**.
- Reports image folder capture times as **unknown** rather than manufacturing seconds between frames.
- Synthetic Python regression: **13/13 PASS**, includes R22 retained tests and R23 new duplicate, planar, file immutability, licensing, sample-bound and unknown-timestamp assertions.
- Real Chromium **10/10 PASS** using `page.set_content` in-memory to avoid blocked localhost. Tests actual H264 MP4 metadata, long 1080p synthetic candidate, short synthetic hold, photo collection, exported JSON, reset, declared rights still UNVERIFIED, landscape/portrait no overflow, no JS/browser or outbound network errors.
- OpenCV source gate on synthetic near-still video returns **SOURCE_HOLD**. No video/audio/images uploaded.

## Not delivered / don't claim
- NOT run on physical iPhone Safari (simulated browser widths only). NOT tested against a newly obtained real Apollo 3D scan or real ground-translating camera sequence.
- No rendered 10x10m photo-real Apollo walking scene, no geometry mesh/real camera poses, no verified licensing, no verified GPS, no 30FPS on iPhone, no merge/deploy.
- Wikimedia aerial Apollo reference and R21 static-region geometric QA remain `SOURCE_BLOCKED`; no source passed real architectural structure gate.
- PHUQUOCLUX Remote Desktop Commander connector auth returned `link_id must identify an eligible linked account`. **No remote computer changes in R23**.

## Clear path
Obtain a rights-cleared 5-10m camera-translating **street-level** Apollo sequence or owner-permissioned GLB/PLY/scan including hidden facets, first precheck with R23, then separately validate calibrated camera poses, 1-2m observed parallax, collision, WebGL real interaction for 20-30 seconds and physical landscape iPhone FPS. Do not substitute 2.5D single-photo Gaussian for those gates.

## MASTER LOCK
NO PRODUCTION, NO MERGE, NO DEPLOY, NO Core V1.2, CMS, identity/auth/schema changes, NO Cloudflare quota tests, NO GitHub Actions or paid AI APIs. UniKey and PhuQuocLux files untouched.