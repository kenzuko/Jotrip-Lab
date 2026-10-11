# LivingPQ R22 - Source Intake and Offline Geometry Gate
Date: 2026-10-11. Branch from R21. **NO MERGE / NO DEPLOY / NO PRODUCTION**.

## Actual delivered local artifact
`LIVINGPQ_R22_SOURCE_GATE_20261011.zip` was created as a downloadable artifact in the R22 ChatGPT continuation conversation. This branch is a checkpoint; ZIP files and exact source are supplied in the chat artifact, not uploaded to production.
Archive includes `intake.html`, `r22_gate.py`, `test_r22_gate.py`, `qa_r22_js_logic.cjs`, `qa_r22_browser.py`, `README_R22.md`, `R22_SOURCE_RIGHTS_REQUEST.md`, `R22_TEST_SUMMARY.json`.

## What works
- Local, dependency-free source intake interface to read metadata of user-selected photos/videos and export a JSON receipt. It never uploads images or claims rights/camera calibration.
- Bounded offline OpenCV SIFT+F/H RANSAC video/frame matching precheck, with frame/edge summaries, contact sheet, warnings for planar/pure-orbit candidates, and machine-readable result.
- 5/5 Python synthetic regression tests PASS: identical frames rejected, planar homography rejected, too few views held, source immutable, and license claim not treated as verified.
- Node syntax check PASS; 11/11 simulated DOM-state interaction checks PASS.
- A synthetic 5s 640x360 test clip returned SOURCE_INCOMPLETE_HOLD, not an accepted 3D result.

## NOT YET DONE
- Actual Chromium runtime browser QA blocked by the execution environment browser security (`ERR_BLOCKED_BY_ADMINISTRATOR` for both file:// and localhost). No real browser PASS.
- Physical iPhone Safari/landscape video selection remains untested.
- No new original multiview Apollo source, no Apollo 3DGS, no reconstructed 10x10 m street, no authentic hidden building surfaces.
- Remote Desktop Commander linked-account authorization currently fails (`link_id must identify an eligible linked account`), so PHUQUOCLUX has **not been modified in this R22 session**.

## Source decision
R21 drone full-image F-inliers (65+) must NOT be promoted to usable architecture: static facade/tower ROI had ~7-8 F-inliers. An actual licensed ground-translating source or owner-approved 3D mesh remains required.
COLMAP capture guidance: https://colmap.github.io/tutorial.html
Operator outreach (NOT SENT): official Sun World Hon Thom contact https://sunworld.vn/en/hon-thom/contact-us; primary official mail `thomisland@sunworld.vn` - contacting them does not prove that they own every IP right in architecture/source files.

## MASTER LOCK
Do not merge/deploy, no production changes, Core V1.2/CMS/ID/auth/schema locked, no Cloudflare tests, no GitHub-hosted Actions, no paid AI, no fake GPS, no unsupported scan claims. Preserve UniKey and PhuQuocLux apps and documents.