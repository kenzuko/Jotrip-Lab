# PHU QUOC: PIXEL ISLAND - GAME DESIGN BIBLE V1.0

Date: 2026-09-16
Status: PRODUCT LOCK FOR FIRST VERTICAL SLICE

## 1. Product fantasy

The player has just arrived in Phu Quoc and can jump around a playful pixel version of the island, discovering recognizable places through short mini games.

The product should feel like a tiny holiday playground, not a large RPG and not a tourism brochure disguised as a game.

## 2. Player promise

Within the first few seconds the player should understand:

- this is Phu Quoc
- this is playful
- they can choose where to go
- interaction is simple
- nothing needs to be installed

Within 30 seconds they should already have done something meaningful in the game.

## 3. Core loop

```text
ARRIVE
-> CHOOSE IDENTITY
-> OPEN ISLAND MAP
-> PICK A DESTINATION
-> PLAY A SHORT GAME
-> EARN A SMALL RESULT / JO / DISCOVERY
-> RETURN TO MAP
-> TRY ANOTHER PLACE
```

The loop must remain understandable without a long tutorial.

## 4. Session design

Target mini-game session:

- fast comprehension: seconds
- normal run: roughly 30 seconds to 3 minutes
- instant retry
- no long setup
- no forced account
- no mandatory narrative before replay

A player waiting for a car or flight should be able to enjoy a complete run.

## 5. First 10 seconds rule

Every mini game must teach itself through play.

For the first vertical slice, No Brakes keeps the approved principle that the first obstacles teach timing without immediately ending the run.

Avoid instruction walls. Prefer one short action sentence such as:

`TAP TO HOP`

## 6. Control rule

A mini game should have one dominant mechanic unless there is a strong product reason to add another.

For No Brakes:

```text
PRIMARY = tap / click / Space
PRIMARY while grounded = hop
```

Do not add steering, braking, inventory or combo systems to No Brakes during the first vertical slice.

## 7. Failure rule

Failure should be funny or motivating, not punishing.

Required behavior:

- result appears quickly
- score is understandable
- retry is immediate
- player can always return to the map
- no lost long-form progress

## 8. Progression

V1 progression signals:

- JO
- best score per mini game
- map pieces
- achievements
- unlocked destinations later

Progression exists to encourage exploration, not to turn the project into an economy simulator.

The first version must not require grinding to access the basic island experience.

## 9. Island structure

Pixel Island is one shared world shell with independent mini-game modules.

The map is the mental model. It should make the player feel that each game belongs to a real place on Phu Quoc.

Initial destination concepts retained from the approved prototype direction:

- Sunset Town
- Hon Thom
- Bai Sao
- Night Market
- Grand World
- Safari

Only Sunset Town is playable in the first vertical slice.

## 10. First mini game - No Brakes

### Fantasy

A fast, slightly chaotic ride through Sunset Town.

### Core action

Hop over obstacles while the run becomes faster.

### First-slice rules retained

- automatic forward movement
- one-button hop
- first two obstacles are protected training obstacles
- score increases when obstacles are passed
- JO can be collected during the run
- difficulty escalates over time
- failure opens result
- retry or back to map

### Rules not yet locked

- final numeric speed curve
- exact obstacle spacing
- exact jump velocity / gravity
- collectible frequency
- achievement thresholds

Those are tuned through playtesting, not copied blindly from prototype constants.

## 11. Tone

Tone is playful, light and confident.

Good:

- short English lines
- dry jokes
- local flavor through situations and places
- occasional surprise

Avoid:

- corporate tourism copy
- long explanations
- fake local folklore
- stereotypes of residents or visitor nationalities
- jokes that make real communities the punchline
- excessive JoTrip sales messages

## 12. JoTrip presence

JoTrip should feel like the maker / guide behind the experience, not an advertisement blocking play.

V1 priority:

```text
Phu Quoc first
fun second
JoTrip quietly present
sales later and outside the core game loop
```

A future handoff to useful JoTrip services can exist outside the immediate play loop, but booking integration is explicitly out of scope for the clean-rebuild vertical slice.

## 13. Destination storytelling rule

A location earns a mini game when its gameplay idea is connected to something recognizable about the place.

Do not create a generic game and merely rename it after a destination.

The game does not need literal geographic simulation, but the player should recognize the destination through visual anchors, situation, sound or activity.

## 14. Replayability

Replayability should come from:

- getting better
- short score chase
- variation in obstacle sequence
- small collectibles
- achievements
- curiosity about other destinations

Do not create artificial replayability through long cooldowns, forced ads or grind.

## 15. Difficulty philosophy

The first moments are welcoming. The run should become clearly harder once the player understands the rhythm.

Difficulty changes must remain readable. Randomness must not create unavoidable failure.

## 16. Game module acceptance rule

A mini game is product-ready only when a first-time player can answer these without explanation:

1. What do I do?
2. What can hurt/end the run?
3. What am I trying to improve or collect?
4. How do I retry?
5. How do I go back to the island?

## 17. Scope guard

Until the first vertical slice ships, do not add:

- quests
- dialogue trees
- inventory economy
- crafting
- multiplayer
- open-world walking simulation
- account progression
- complex NPC schedules
- procedural world generation
- more than one active mini game

The first goal is not to prove how much a game can contain. It is to prove that Pixel Island can feel polished, instant and expandable.
