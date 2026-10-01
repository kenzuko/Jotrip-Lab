# PHU QUOC: PIXEL ISLAND - ART & WORLD BIBLE V1.0

Date: 2026-09-16
Status: VISUAL CONTRACT - FIRST VERTICAL SLICE

## 1. Visual objective

The world should feel like a crafted pixel interpretation of Phu Quoc: bright, warm, playful and recognizable without becoming noisy or toy-like.

It should look intentional at a glance. Pixel art is not permission for inconsistent scale, perspective or detail.

## 2. Visual hierarchy

Priority order:

1. player and immediate gameplay hazard
2. collectible / interaction target
3. recognizable destination anchor
4. environment detail
5. decorative motion

Background detail must never make hazards difficult to read.

## 3. Pixel discipline

Locked rules:

- crisp pixel edges
- nearest-neighbor display
- no browser smoothing on pixel sprites
- no arbitrary non-uniform stretching
- avoid fractional placement where it visibly softens small sprites
- one asset must not silently change pixel density between scenes
- no AI-upscaled blurry art presented as pixel art

Final source grid / tile dimensions are measured from approved artwork before being locked. Do not invent a tile size merely for architectural convenience.

## 4. Perspective and scale

Each scene must declare its visual perspective and scale contract.

Assets from different perspectives must not be mixed simply because they are available.

For gameplay scenes:

- character/vehicle scale must remain consistent relative to obstacles
- collision geometry is defined separately from decorative transparent pixels
- large destination landmarks can use controlled exaggeration for recognition

## 5. Color system

JoTrip brand colors may act as recurring UI accents:

- yellow: `#FCBC12`
- green: `#77944C`

They do not need to dominate the environment.

Environment colors should come from the location itself: sea, sky, vegetation, masonry, sunset, sand, market lights and other recognizable place cues.

UI contrast always wins over decorative palette fidelity.

## 6. Character direction

Characters should read clearly at gameplay scale through silhouette, pose and one or two memorable features.

Do not over-detail faces that will be displayed very small.

Retained character concepts:

- Traveler
- Explorer
- Uncle
- Grandma
- Kid
- Old Fisherman
- Phu Quoc Ridgeback
- Pepper

These names are character concepts, not permission to reuse the current runtime-generated SVG placeholders as final art.

Human characters must be treated as playful game archetypes rather than caricatures of ethnicity, nationality or social class.

## 7. Ken

Ken is a local-guide presence in the arrival flow.

The current generated SVG in `game-rebuild/asset-bridge.js` is a placeholder only.

Final Ken artwork requires explicit visual approval before production migration.

## 8. World map

The Phu Quoc map is a navigation surface first and geographic illustration second.

It should:

- retain a recognizable island silhouette
- keep destinations in broadly coherent relative positions
- prioritize legibility on phone screens
- make playable vs locked destinations obvious
- avoid decorative labels competing with active pins

The map is not a nautical or road-navigation chart and must not imply survey-grade positional accuracy.

## 9. Location identity

Every destination must have a small visual identity kit before a mini game is built:

```text
LOCATION ID
RECOGNITION ANCHORS
TIME / LIGHT
PRIMARY PALETTE
FOREGROUND MATERIALS
BACKGROUND LANDMARKS
LOCAL PROPS
MOTION CUES
SOUND CUES
DO-NOT-USE LIST
```

This prevents an AI agent from inventing a generic tropical scene and calling it Phu Quoc.

## 10. Sunset Town - first-slice direction

Purpose: first production-quality playable location.

Locked feeling:

- warm
- lively
- fast
- slightly chaotic
- readable while moving quickly

Gameplay must remain visually clearer than the architecture behind it.

Existing approved/reviewed prototype assets for Sunset Town, rides and props must be inventoried and visually compared before migration.

Do not recreate them from memory when an approved original exists.

## 11. Props and hazards

Hazards need a consistent readability rule:

- recognizable silhouette
- adequate contrast from road/background
- collision shape smaller and fairer than decorative bounds when appropriate
- no tiny decorative element may unexpectedly cause failure

Prototype concepts retained for evaluation:

- planter
- chair
- table
- menu/sign
- tripod
- suitcase

They are not automatically final simply because they existed in the old code.

## 12. Animation

Animation should be economical.

Prefer:

- a few strong frames
- readable anticipation/impact
- controlled loops
- environmental motion that supports atmosphere

Avoid:

- excessive frame counts that increase load without perceptible benefit
- animation on every background object
- sub-pixel tweening that makes pixel art look soft

## 13. UI art direction

Game UI should feel like part of Pixel Island rather than a separate corporate website.

Rules:

- short labels
- strong hierarchy
- large touch targets
- clear selected/locked/available states
- high contrast
- minimum decoration around immediate gameplay HUD

UI layout must respect phone safe areas.

## 14. Asset naming

Target naming convention:

```text
world.map.phu-quoc
location.sunset-town.background.main
character.traveler.idle
character.ken.wave
minigame.no-brakes.ride.frame-01
minigame.no-brakes.obstacle.planter
collectible.jo.frame-01
ui.button.primary
```

Names describe semantic ownership, not filenames from old prototypes.

## 15. Asset source-of-truth rule

Approved original files are source of truth.

Do not:

- screenshot an asset from a browser and reuse it as source
- repeatedly recompress an image across versions
- extract a visually degraded copy when the original is available
- replace approved art with a generated approximation without explicit approval

## 16. Placeholder rule

Placeholder assets are allowed to prove mechanics and layout only.

A placeholder must be documented as `approved: false` in the asset registry or inventory.

A placeholder can never silently become production art because a deadline arrived.

## 17. Visual QA gate

Before a scene is visually approved, test at minimum:

- target iPhone portrait viewport
- common Android portrait viewport
- desktop centered viewport
- scale up/down without blur
- high-motion gameplay screenshot
- obstacle readability
- HUD readability
- no accidental stretched sprites
- no mismatched pixel density

## 18. World expansion rule

Before a second destination enters implementation, Sunset Town must establish the reusable visual grammar for:

- map entry
- location loading
- intro
- gameplay framing
- HUD
- results
- return to island

Future destinations may look distinct, but they should still belong to the same Pixel Island universe.
