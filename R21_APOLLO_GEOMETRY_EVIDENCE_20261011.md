# LivingPQ R21 - Apollo geometry gate, 11 October 2026
**STATUS: SOURCE STILL BLOCKED / VISUAL HOLD / NO DEPLOY**

## Real source pairing results
Windows PHUQUOCLUX, OpenCV SIFT + CLAHE + RANSAC on real Apollo photographs from Wikimedia Commons (Vivu Vietnam, CC BY-SA 4.0):
- Two drone photos DJI 0028 and DJI 0031: full view 55 F-inliers, Apollo ROI 65, RootSIFT ROI 62. Corresponding H-inliers 45/49/48.
- Ground photo 06 vs 07: 11, 10, 9 F-inliers respectively, insufficient geometry.
- Drone DJI 0028 vs ground photo 06: 12, 14, 14 F-inliers.

## Important structure-only follow-up
Many aerial whole-image matches are on paving, garden and possibly moving vehicles, not static facade. Heuristic bounded ROI recheck yields only 7 F-inliers in the wide Apollo facade region, 7 on glass tower core, 8 after excluding low roadway, vs 70 on all features. These masks are approximate, not verified precise segmentation. Do NOT call 65/70 a passed architectural reconstruction.

## Learned matcher resource stop
R18 DISK-LightGlue ONNX (~50MB), loaded via isolated local OnnxRuntime 1.20.1, 448px CPU. First inference produced NO RESULT after around 142s; PHUQUOCLUX had only ~266 MB free system RAM. Our own inference PID 7236 was stopped and free system RAM recovered to ~1191 MB. No score. Do not repeat this model on the 4GB Windows host.

## What exists / what does not
R17G SOG single-photo Gaussian ~1.07MB and R20 real 24.5s keyboard/mouse WebGL recording preserved. R20 technical input 9/9 PASS, visual large translations and lookback FAIL (gaps, torn architecture). R19 people inpainting ghosted and stays rejected.
No photo-real 10x10m Apollo freewalking scene, surveyed ground collision, verified calibrated multiview camera poses, 3DGS reconstruction, or physical iPhone test. No 'walkable world' claim.

## Required independent source before further reconstruction
A legally reusable continuous camera-translating 5-10m outdoor ground-level sequence near Apollo (e.g. 60-100s of 4K footage) or permissioned point-cloud/mesh/CAD that shows front, side and previously hidden surfaces. No need to capture the whole island. Explicit 3D derivative/republication rights needed. After acquisition: R13 capture prescreen, verify 3+ distinct camera poses and >=1m observed parallax, build separate proxy collision, demonstrate real WebGL 20-30s action on physical landscape iPhone.

## Evidence files
R21_OPENCV_ROI_GEOMETRY_QA.json; R21_STATIC_ARCHITECTURE_ONLY_GATE.json; r21-roi-opencv.py; r21-static-architecture-gate.py; screenshot of aerial inlier correspondences. These are source audit assets, not reconstructed 3D.

## MASTER LOCK
NO MERGE / DEPLOY / PROD / Cloudflare / Core V1.2 / ID CMS AUTH SCHEMA / GitHub Actions / paid AI / fake GPS. Do not touch UniKey or PhuQuocLux.