# LivingPQ Apollo - WebGL evidence (R17G, not an R18 3D scan)

**R18 is a source-research pass and has NO reconstructed multi-view 3D asset.** This branch contains the most recent actual 3D WebGL proof, **R17G**, recorded on PHUQUOCLUX for viewing on mobile.

## Six-second 3D camera-motion video

[**Watch the R17G WebGL motion video (MP4, H.264, 960×540)**](LIVINGPQ_R17G_REAL_WEBGL_3D_MOTION_NOT_R18.mp4)

This is **an actual WebGL recording** with the camera moving from approximately -38 cm to +38 cm along X. It is not an AI illustration or a reconstructed multi-camera scan. The footage exposes current limitations of predicted hidden surfaces.

## Still screenshots
- [Front view](R17G_SMALL_FRONT.jpg)
- [Camera left](R17G_SMALL_LEFT.jpg)
- [Lateral 80 cm - failure/holes](R17G_SMALL_DETAIL.jpg)

## What this is / isn't
- Actual Apollo Café source photograph: **Vivu Vietnam**, Wikimedia Commons, CC BY-SA 4.0. [Original and credit](https://commons.wikimedia.org/wiki/File:Apollo_Cafe_daytime_street_view_Sunset_Town_Phu_Quoc_Vietnam.jpg).
- Derived single-image predicted inverse depth: Depth Anything V2 Small (Apache 2.0).
- 221,184 gaussians generated and compressed to SOG, rendered by PlayCanvas (MIT) in Edge.
- **NOT measured real-world geometry, NOT geolocated 100 m² freewalking, NOT full multiview reconstruction.** R18 photo matching did not pass the geometric acceptance gate.
- Transformation made: source photo -> monocular estimated depth -> image-derived gaussians -> real 3D WebGL -> H.264 screen recording.

Only an isolated documentation branch, no .github/workflows, no merge, no production deployment and no paid AI API.

License of derivative screenshots/video: original photo attribution and CC BY-SA 4.0 conditions apply.
