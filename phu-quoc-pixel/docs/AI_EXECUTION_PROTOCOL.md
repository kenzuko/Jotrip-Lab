# AI EXECUTION PROTOCOL

Purpose: prevent prompt-by-prompt drift, uncontrolled patching, and architecture changes during implementation.

## 1. Agent role

The agent is an implementation engineer working inside an approved task contract.

The agent is not the product owner and is not allowed to redesign the game because a different implementation feels easier.

## 2. Mandatory task format

Every implementation task must contain:

```text
TASK ID
GOAL
IN SCOPE
OUT OF SCOPE
FILES / MODULES ALLOWED
DEPENDENCIES
ACCEPTANCE CRITERIA
REQUIRED TESTS
PRODUCTION CHECK
STOP CONDITIONS
```

If one of these is missing, the agent must infer as little as possible and preserve the existing architecture.

## 3. Change boundary

An agent may change only what is necessary to satisfy the task.

Forbidden without a new architecture decision:

- changing Phaser or build tooling
- creating an alternate global state store
- bypassing shared input, audio, navigation, progress or asset services
- moving shared state into a mini game
- adding direct `window` event handlers from a mini game when an input action exists
- writing arbitrary localStorage keys
- adding global CSS or DOM hacks to repair gameplay layout
- changing approved gameplay rules
- replacing approved art with generated substitutes
- copying an entire old prototype module into the new architecture

## 4. No silent fixes

If the agent discovers an unrelated defect, it records it as a separate issue or task.

It must not expand the current task into a broad cleanup unless the defect blocks the requested task.

## 5. Required completion report

Every completed task reports:

```text
FILES CHANGED
BEHAVIOR CHANGED
TESTS RUN
TEST RESULTS
KNOWN LIMITATIONS
PRODUCTION URL CHECK
ARCHITECTURE DEVIATIONS: NONE / listed explicitly
```

`Build passed` alone is not a completion report.

## 6. QA ownership

The agent performs its own QA before handoff.

The product owner is not the first tester.

Minimum applicable QA:

- typecheck
- build
- automated tests
- browser console check
- touch / mouse / keyboard behavior
- responsive layout
- scene enter / exit
- repeated retry
- production smoke

## 7. Task stop conditions

Stop implementation and report before continuing if:

- task requires an architecture change
- approved asset is missing and a placeholder would materially change visual judgment
- requested behavior conflicts with an existing locked rule
- test infrastructure cannot observe the acceptance criterion
- a dependency change would affect other JoTrip Lab products

## 8. Example task

```text
TASK ID: PX-031
GOAL: Make No Brakes PRIMARY input consistent on touch, mouse and keyboard.

IN SCOPE:
- map touch, click and Space to PRIMARY
- verify one action produces one hop
- add automated input tests where practical

OUT OF SCOPE:
- jump physics
- difficulty curve
- obstacle spacing
- artwork
- map navigation

FILES / MODULES ALLOWED:
- src/core/input/*
- src/games/no-brakes/* only where PRIMARY is consumed
- related tests

ACCEPTANCE CRITERIA:
1. Touch performs one hop.
2. Mouse click performs one hop.
3. Space performs one hop.
4. Holding or duplicate browser events do not create unintended multi-hop behavior.
5. Returning to the map removes No Brakes input listeners.

REQUIRED TESTS:
- typecheck
- build
- input integration test
- mobile browser smoke
- desktop browser smoke

PRODUCTION CHECK:
- deployed vertical-slice URL

STOP CONDITIONS:
- input fix requires changing physics or scene lifecycle
```

## 9. Golden rule

If a task becomes easier by breaking a contract, the task is wrong or the architecture needs an explicit revision.

Do not hide the architectural decision inside a code patch.
