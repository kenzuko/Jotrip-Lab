# LivingPQ R20 - Apollo Multi-view Source Gate (2026-10-11)

## Status
**SOURCE BLOCKED / VISUAL HOLD**. This is NOT a 3D reconstruction, deploy, or iPhone gameplay proof. R20 real keyboard/mouse input proof (9/9 technical checks) is retained, but R17G imagery still tears beyond its narrow source view cone.

## Direct discovery - evidence
Research location: isolated PHUQUOCLUX `C:\Users\Public\OpenPQ\living-r20-source-gate-20261011`. No Cloudflare or GitHub Actions used.

- Panoramax public STAC search three bbox checks: **0 items** at 104.004..104.011/10.027..10.033, 103.979..103.986/10.028..10.034, and expanded 103.97..104.06/9.95..10.06. Only these checked ranges and API snapshots were tested.
- KartaView public v2 /photo: **empty response, apiCode 601** for the two prior Apollo photo geopins, radius 500 m, plus zoomLevel=17 query. GPS in Commons records conflicts by around 2.7 km and is not used as geometry truth.
- Wikimedia Commons API video file searches: **0** matches for `Apollo Cafe Sunset Town filetype:video` and `Sunset Town Phu Quoc filetype:video`. This is not a claim that no videos exist elsewhere.
- Commons search yielded **two additional openly licensed images** absent from R18 source gate:
  - `File:DJI 20260214173529 0028 D SUNSHINE.jpg` (Vivu Vietnam; CC BY-SA 4.0), close-height drone photo of Apollo.
  - `File:S7509601.jpg` (CC BY-SA 4.0), shows a cafe interior at night, **not useful** for 10x10m outdoor road scene.
- `R20_NEW_SOURCE_VISUAL_CONTACT.jpg` compares these images with R13 drone 0031, ground 07 and ground 06. Looks only, does not imply any reconstructed geometry.

## Actual new pair geometry test
`R20_NEW_SOURCE_PAIR_QA.json`: SIFT (1300px/2200 features each; CLAHE; bidirectional ratio 0.80), F matrix RANSAC threshold 2.4 px, H RANSAC 4.5 px. 10 pairs checked using 5 photos. Candidate heuristic requires >=45 F-inliers, >=0.20 image-region coverage, F-H >12. Further essential gates (camera baseline, physically interpretable pose, static common structure) have **not been met**.

Best new pair: `DJI 0028` vs `DJI 0031`: 48 mutual descriptor matches, **29 F-inliers**, 24 H-inliers, spatial coverage 0.486. Heuristic **REJECT**, because its overlap is weaker than required and there is no demonstrated ground-level baseline or calibratable real camera bundle. Aerial pair cannot independently show building sides or road behind Apollo.

New drone vs street-level 07: 9 F-inliers.
New drone vs exterior ground 06: 13 F-inliers.
Night interior S7509601 vs other views: only 7-9 F-inliers.

No new multiview 3DGS, camera pose optimization, scan, or reliable collision geometry created. Nothing promoted to visual PASS.

## Scope decision
1. STOP looping on new single-photo Gaussian, inpainting and gameplay controllers. R17G and R20 controller preserved as proofs, not false 100m² scenes.
2. Continue only if a reusable continuous ground-level **camera-translating** sequence of 5-10m Apollo perimeter or a rights-cleared local scan is found. Unlicensed videos / standard copyright published walk-throughs can inform the scene but cannot be reprocessed as inputs without permission.
3. Minimal source acceptance: 60-100 s 4K footage showing sideways camera translation, two sides of building plus walkway, faces and plates handled appropriately, at least 3 measurable view poses with >1m visual-safe parallax, distinct street/collision proxy geometry, actual iPhone landscape FPS. Physical user recording would be a *small microcell*, not an island-wide shoot.
4. For any source from Sun World/Apollo operator, obtain explicit reuse, derivative 3D reconstruction and redistribution permissions before scanning/releasing.
5. Upgrade to full microcell only after 3 real camera screenshots and 20-30 seconds of actual interactive navigation show observed/fairly characterized surfaces without tearing or people glued into architecture.

## Reproduction (local only)
- `python check-open-sequences.py` generates `R20_OPEN_SEQUENCE_SOURCE_GATE.json`.
- `python fetch-two-candidates.py` obtains licensed Commons thumbnails (credit source metadata).
- `python check-r20-new-pairs.py` generates `R20_NEW_SOURCE_PAIR_QA.json` and a visual contact sheet.

## Licenses and sourcing
- CC BY-SA Wikimedia Commons images attributed to their named photographers, derivatives share-alike.
- https://commons.wikimedia.org/wiki/File:DJI_20260214173529_0028_D_SUNSHINE.jpg
- https://commons.wikimedia.org/wiki/File:S7509601.jpg
- https://commons.wikimedia.org/wiki/File:DJI_20260214173618_0031_D_SUNSHINE.jpg
- KartaView CC BY-SA: https://kartaview.org/terms
- Panoramax accepted image licenses: https://docs.panoramax.fr/federated-catalog/

## MASTER LOCK
No prod, no Core 1.2, no CMS/ID/auth/schema, no Cloudflare quota tests, no deploy or merge, no GitHub-hosted Actions, no paid AI, no fake GPS. UniKey and PhuQuocLux untouched.
