# PHU QUOC: PIXEL ISLAND - MASTER ARCHITECTURE V1.0

Date: 2026-09-16
Status: proposed lock for clean rebuild

## 1. Why the current rebuild stops here

The current `/game-rebuild` version is useful as a gameplay and visual reference, but it keeps screen navigation, audio, asset loading, gameplay loop, physics-like collision, local storage, rendering, score and mini-game state inside one large browser script. That structure is acceptable for one prototype but becomes fragile when the island grows.

The clean rebuild separates product shell, world, shared services and mini games so one game cannot break the rest of Pixel Island.

## 2. Stack decision

### Runtime

- Phaser 4.x, pinned to a tested patch version during implementation.
- TypeScript.
- Vite.
- Static web deployment compatible with GitHub Pages.

### Why Phaser

Pixel Island is a 2D browser-first game. Phaser provides scene lifecycle, input, loader, audio, cameras, animation, texture management and 2D physics in one maintained framework. This removes custom engine code that the project does not need to own.

### Why TypeScript

The main reason is not type purity. It is contract enforcement between the shell, shared services and independently developed mini games. It also reduces accidental interface drift when AI agents modify separate modules.

### Why Vite

Fast local development, predictable static production output, code splitting and straightforward GitHub Pages deployment.

## 3. Architectural boundary

```text
Browser
  |
  +-- App Shell
  |     +-- Boot
  |     +-- Loading
  |     +-- Landing
  |     +-- Airport
  |     +-- Character Select
  |     +-- Island Map
  |     +-- Results Overlay
  |
  +-- Shared Core
  |     +-- Router / Scene Flow
  |     +-- Player Profile
  |     +-- Progress Store
  |     +-- Audio Manager
  |     +-- Input Manager
  |     +-- Asset Registry
  |     +-- Telemetry Adapter
  |     +-- Performance Monitor
  |
  +-- World
  |     +-- Phu Quoc Map
  |     +-- Location Registry
  |     +-- Unlock Rules
  |
  +-- Mini Games
        +-- Sunset Town / No Brakes
        +-- Hon Thom / future
        +-- Bai Sao / future
        +-- An Thoi / future
```

A mini game may call shared services through typed interfaces. It may not directly edit global DOM, global localStorage keys, global audio, global navigation or another mini game's state.

## 4. Scene lifecycle

Every playable module follows the same lifecycle:

```text
registered
-> preload
-> ready
-> intro
-> playing
-> paused
-> result
-> exit
-> disposed
```

`disposed` matters. When the player returns to the map, timers, listeners, textures that are local-only, physics bodies and audio loops owned by that mini game must be released.

## 5. Mini-game contract

Each mini game exports a descriptor and one scene package.

Conceptual interface:

```ts
interface MiniGameDefinition {
  id: string;
  locationId: string;
  title: string;
  preloadGroup: string;
  createScene(): Phaser.Scene;
  getResult(): MiniGameResult | null;
}

interface MiniGameResult {
  score: number;
  joEarned: number;
  achievements: string[];
  durationMs: number;
}
```

Mini games receive player/profile state through the core. They return a result object. They never write progress directly.

## 6. State ownership

### Global persistent state

Owned only by `ProgressStore`:

- player display name
- selected character
- total JO
- unlocked locations
- map pieces
- achievements
- per-game best scores
- settings

### Session state

Owned by the active mini game:

- current score
- current obstacle list
- velocity
- temporary timers
- temporary collectibles
- current run state

### Rule

No arbitrary localStorage writes from scenes.

Storage key namespace:

```text
pqpi:v1:profile
pqpi:v1:progress
pqpi:v1:settings
```

The storage adapter must support schema migration later.

## 7. World and location registry

Locations are data, not hard-coded buttons.

Example:

```ts
{
  id: 'sunset-town',
  label: 'SUNSET TOWN',
  mapPosition: { x: 0.31, y: 0.72 },
  status: 'available',
  miniGameId: 'no-brakes',
  assetGroup: 'location-sunset-town'
}
```

The map renders from this registry. Adding a location must not require editing map navigation logic.

## 8. Asset architecture

### Asset groups

```text
core-ui
characters
world-map
location-airport
location-sunset-town
minigame-no-brakes
location-hon-thom
...
```

### Loading rule

Boot loads only the minimum required to show a responsive first screen.

The app does not preload the whole island.

Recommended flow:

```text
BOOT
  -> core-ui + tiny loading assets
LANDING
  -> airport critical assets in background
AIRPORT
  -> characters in background
MAP
  -> world map assets
PLAYER SELECTS LOCATION
  -> only that location + mini-game bundle
```

### Asset manifest

Every asset is registered by stable key, source path, dimensions, role and group. Scenes never invent asset URLs.

### Pixel rules

- nearest-neighbor rendering
- image smoothing disabled
- integer-friendly positioning for pixel sprites where practical
- source sprite dimensions are never silently stretched into unrelated aspect ratios
- generated placeholders are allowed only during development and must be marked as placeholders

## 9. Rendering and viewport

Pixel Island must not use a single fixed 540x960 assumption for all screens.

### Game viewport

Use one logical gameplay canvas with responsive scale management.

Target reference orientation for No Brakes: portrait.

The shell must support:

- iPhone portrait
- Android portrait
- desktop browser with centered game viewport
- safe areas
- orientation change without state corruption

The map and shell UI can use responsive scene coordinates and DOM-free Phaser UI where practical.

## 10. Input abstraction

Mini games do not bind raw window events.

Shared input actions:

```text
PRIMARY
SECONDARY
PAUSE
BACK
LEFT
RIGHT
UP
DOWN
```

For No Brakes:

```text
PRIMARY = tap OR click OR Space
```

This keeps touch, mouse and keyboard behavior identical.

## 11. Audio architecture

One `AudioManager` owns:

- master mute
- music volume
- SFX volume
- lifecycle pause/resume
- user-gesture unlock for mobile browsers

A mini game requests named sounds. It does not create unmanaged WebAudio oscillators or long-lived audio nodes.

## 12. Performance budget

Initial targets for the first vertical slice:

- responsive first paint before all game assets are loaded
- no full-island preload
- 60 FPS target on modern phones, 30 FPS minimum graceful floor on weaker devices
- no unbounded particle arrays, timers or listeners
- no repeated image decoding for the same registered texture
- scene exit must stop owned update loops and audio
- production build must expose bundle sizes during CI

Exact byte budgets are set after the first real asset inventory. Do not fake a budget before measuring the approved artwork.

## 13. Error isolation

If a mini game fails to load:

1. keep the shell alive
2. show a friendly retry state
3. allow BACK TO MAP
4. log the error through the telemetry adapter

A mini-game error must not require reloading the entire Pixel Island app.

## 14. Save and progression

JO, map pieces and achievements are fun progression signals. They must not block basic exploration in the first version.

The first vertical slice stores progress locally only. Cloud identity or JoTrip account integration is a later product decision and must not enter the core rebuild now.

## 15. Repository layout

```text
phu-quoc-pixel/
  package.json
  tsconfig.json
  vite.config.ts
  index.html
  public/
    assets/
  src/
    main.ts
    app/
      game-config.ts
      scene-keys.ts
    core/
      assets/
      audio/
      input/
      progress/
      performance/
      telemetry/
      navigation/
    scenes/
      BootScene.ts
      LoadingScene.ts
      LandingScene.ts
      AirportScene.ts
      CharacterScene.ts
      IslandMapScene.ts
      ResultScene.ts
    world/
      locations.ts
      unlocks.ts
    games/
      no-brakes/
        NoBrakesScene.ts
        config.ts
        types.ts
    ui/
    types/
  tests/
    unit/
    e2e/
  docs/
```

No `misc`, `temp-final`, `v2-final-final`, or duplicate engine folders.

## 16. Test layers

### Unit

- progress schema
- location registry
- unlock rules
- scoring rules
- difficulty curve
- result calculation

### Integration

- scene transitions
- mini-game enter/exit
- progress persistence
- mute / resume lifecycle
- orientation / resize state preservation

### Browser E2E

Minimum flow:

```text
open
-> enter island
-> airport
-> select character
-> open map
-> enter Sunset Town
-> start No Brakes
-> trigger input
-> reach result
-> retry
-> return to map
```

### Production smoke

The deployed URL must be tested, not only localhost.

## 17. Definition of done

A feature is done only when all applicable conditions pass:

- acceptance criteria pass
- TypeScript check passes
- build passes
- unit tests pass
- browser E2E passes
- no new console errors
- mobile input works
- desktop input works
- resize/orientation does not corrupt state
- scene cleanup passes
- production smoke passes
- approved art is rendered correctly

## 18. Architecture rules for AI agents

AI agents may implement, refactor within a task boundary, add tests and report blockers.

AI agents may not silently:

- change the framework
- introduce a second state system
- bypass the asset registry
- write direct global localStorage keys
- make a mini game own global navigation
- replace approved artwork
- change gameplay rules outside the task
- mark a task complete without the required tests

See `docs/AI_EXECUTION_PROTOCOL.md`.

## 19. Migration from existing prototype

Reusable:

- approved product flow
- approved pixel artwork after inventory
- approved copy after review
- No Brakes gameplay intent
- difficulty observations
- character concepts
- Phu Quoc location concepts

Not reusable as architecture:

- current monolithic `game.js`
- direct DOM screen router
- unmanaged WebAudio code
- direct localStorage writes from gameplay
- one-shot preload of mini-game assets at module startup
- fixed-screen assumptions

## 20. First lock

Do not implement Hon Thom, Bai Sao, Grand World, Safari or additional games until the Sunset Town vertical slice is stable on production.

Scale by cloning the contract, not by cloning code.
