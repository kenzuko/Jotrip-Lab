# PHU QUOC: PIXEL ISLAND

Status: ARCHITECTURE LOCK - implementation must not begin outside the approved vertical slice.

## Product role

PHU QUOC: PIXEL ISLAND is the entertainment and destination-storytelling layer of the JoTrip ecosystem.

It is not the JoTrip booking app, not a simulation platform, and not a large open-world game. The product is a lightweight web-first pixel world that lets visitors discover Phu Quoc through short, replayable mini games.

Primary target session: 30 seconds to 3 minutes per mini game.

Primary outcome: the player should understand the game in seconds, enjoy it immediately, recognize Phu Quoc, and want to try another location.

## Locked product principles

1. Web-first and instant entry.
2. Desktop and mobile are first-class targets.
3. English is used for all player-facing game and web UI text.
4. The island is a shared shell. Mini games are isolated modules.
5. No mini game may own global navigation, save data, audio state, loading state, or profile state.
6. No patching of R5, R5.1, or the current `game-rebuild` implementation.
7. Existing artwork and concepts may be reused only after being mapped into the new asset contract.
8. A task is not complete because it builds. It is complete only after automated checks and direct production QA pass.
9. Performance and loading are product requirements, not cleanup work.
10. AI agents implement contracts. They do not redesign architecture.

## Repository rule

The existing `/game-rebuild` directory is frozen as reference material.

All new work belongs under `/phu-quoc-pixel` until the replacement is approved for production.

## Product structure

```text
Pixel Island Shell
  -> Landing / fast entry
  -> Airport arrival scene
  -> Character identity
  -> Phu Quoc map hub
       -> Sunset Town mini game
       -> Hon Thom mini game
       -> Bai Sao mini game
       -> An Thoi / island mini game
       -> Future locations
  -> Shared results / JO / achievements
  -> Back to map
```

The world can grow, but each playable activity remains short and independently loadable.

## First vertical slice

The first production-quality slice is intentionally small:

```text
Boot
-> Landing
-> Airport
-> Character
-> Island Map
-> Sunset Town
-> NO BRAKES
-> Result
-> Return to Island Map
```

No second mini game is implemented until this complete loop passes the QA gate.

## Technical direction

See `ARCHITECTURE.md`.

## AI implementation rules

See `docs/AI_EXECUTION_PROTOCOL.md`.

## Build order

See `docs/BUILD_PLAN.md`.
