# BUILD PLAN

Status: execution plan for the clean rebuild.

## Phase 0 - Architecture and technical spike

Goal: prove the foundation before moving gameplay.

Deliverables:

- project scaffold under `/phu-quoc-pixel`
- TypeScript + Vite
- candidate Phaser 4.2.1 pinned for the spike
- minimal BootScene and one empty scene transition
- GitHub Pages-compatible production build
- CI typecheck + build
- bundle-size report
- mobile browser smoke

Decision gate:

Keep Phaser 4.2.1 only if the spike is stable for the required browser, scaling, input and scene-lifecycle behavior. If a framework regression blocks the project, record an ADR before changing runtime. Do not switch frameworks inside a gameplay task.

## Phase 1 - Core shell

Goal: complete the non-game product loop.

Implement:

- Boot
- Loading
- Landing
- Airport
- Character Select
- Island Map
- shared navigation
- shared input actions
- ProgressStore
- AudioManager shell
- AssetRegistry
- error boundary / retry state

Gate:

A player can reach the map and refresh without state corruption.

## Phase 2 - Asset migration

Goal: inventory and normalize only the assets required for the first vertical slice.

Inventory:

- island map
- airport scene
- Ken
- approved characters
- Sunset Town background
- No Brakes ride frames
- obstacles
- JO collectible
- UI elements

For every asset record:

- stable key
- original file
- dimensions
- aspect ratio
- intended scene
- preload group
- approved / placeholder status

Gate:

No scene references raw paths. All first-slice assets load through AssetRegistry.

## Phase 3 - No Brakes rebuild

Goal: reproduce the approved gameplay intent without importing the old engine structure.

Implement in order:

1. player movement model
2. PRIMARY action
3. ground / jump state
4. obstacle pool
5. collision
6. training protection for first obstacles
7. scoring
8. JO collectible
9. difficulty curve
10. results
11. retry
12. exit to map

Gate:

The mini game can be entered, retried repeatedly and exited without leaking listeners, timers, audio or state.

## Phase 4 - Vertical slice polish

Goal: make one slice feel like a real game rather than a prototype.

Polish:

- first-load experience
- transitions
- readable tutorial
- responsive HUD
- pixel rendering quality
- animation timing
- sound
- accessibility basics
- loading feedback
- failure / retry states
- safe area handling

Gate:

The complete flow works on production:

```text
Landing
-> Airport
-> Character
-> Map
-> Sunset Town
-> No Brakes
-> Result
-> Map
```

## Phase 5 - QA hardening

Automate and verify:

- unit tests for score / progression / location data
- scene transition integration tests
- browser E2E happy path
- repeated retry test
- back-to-map cleanup test
- orientation / resize test
- console error detection
- production smoke

Performance checks:

- first screen is usable without full island preload
- no unbounded objects
- no duplicate input listeners after retries
- no audio loop survives scene exit
- stable frame behavior on target phones

Gate:

No second mini game until this phase passes.

## Phase 6 - World expansion

Only after the vertical slice is locked.

Add future locations through the location registry and mini-game contract.

Candidate sequence is decided by product value, not by what is easiest to code.

Possible future modules:

- Hon Thom
- Bai Sao
- An Thoi Islands
- Night Market
- Grand World
- Safari

Each new module must reuse shared services and pass the same lifecycle contract.

## What we explicitly do not do now

- account login
- backend progression
- multiplayer
- chat
- large open-world streaming
- complex inventory economy
- procedural island generation
- JoTrip booking integration inside the game loop
- multiple mini games in parallel before the vertical slice is stable

## Execution sequence

```text
PX-001 scaffold
PX-002 CI and deploy preview
PX-003 core scene router
PX-004 input abstraction
PX-005 progress store
PX-006 asset registry
PX-007 shell scenes
PX-008 asset inventory and migration
PX-009 No Brakes movement
PX-010 No Brakes obstacles and collision
PX-011 No Brakes scoring and JO
PX-012 result / retry / exit
PX-013 audio lifecycle
PX-014 responsive and safe areas
PX-015 E2E and production smoke
PX-016 performance hardening
PX-017 vertical-slice release candidate
```

Every PX task must be issued using `AI_EXECUTION_PROTOCOL.md`.
