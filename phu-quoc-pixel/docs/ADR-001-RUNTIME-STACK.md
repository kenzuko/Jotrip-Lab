# ADR-001 - Runtime Stack Lock

Date: 2026-09-16
Status: ACCEPTED

## Decision

The Phu Quoc Pixel Island clean rebuild uses:

- Phaser 4.2.1
- TypeScript
- Vite 8.3.x
- static deployment compatible with GitHub Pages

## Evidence

The foundation spike passed:

- TypeScript check
- production build
- isolated GitHub Pages deployment
- production HTTP smoke
- Chrome headless mobile smoke at 430x932
- Chrome headless desktop smoke at 1440x900
- visual screenshot inspection on both viewports

The logical game viewport remains 540x960 for the first portrait mini game and is scaled with Phaser Scale Manager rather than treated as a fixed physical screen size.

## Consequences

1. Gameplay tasks may not switch frameworks.
2. A runtime change requires a new ADR with a demonstrated blocker and migration impact.
3. New mini games must use Phaser scene lifecycle and shared Pixel Island contracts.
4. UI, input, storage and asset loading must not fall back to ad-hoc global browser code when a shared service exists.

## Non-decision

This ADR does not lock art direction, gameplay tuning, asset byte budgets or future account/backend architecture. Those remain separate decisions.
