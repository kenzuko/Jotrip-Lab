# OpenPQ AI Guide V12 - Isolated Conversation & Audio Proof

**Status:** lab-only implementation, NOT the production AI Guide. The code has no Cloudflare AI bindings, no auth credentials, no microphone capture, no production publish script and no worker route.

## Purpose

Demonstrate a robust multi-turn conversation lifecycle without burning Workers AI free neurons or the VPS TTS queue.

- `src/turn-engine.mjs`: session/turn/generation fencing, explicit transcript confirmation by default, stale-response rejection, ordered audio acknowledgements, partial playback not committed as complete.
- `src/persistent-player.mjs`: one reusable HTML audio element, Safari-style rejected `play()` and interrupted playback reported as failure, no silent autoplay bypass.
- `src/turn-budget.mjs`: deterministic SINGLE-PROCESS simulator for one reservation per turn, bounded queue, idempotent chunk IDs, shared-hotel-IP neutrality. This is **not** production-grade multi-worker atomic enforcement.
- `proof/index.html`: human-readable iPhone test. Uses the existing approved pre-generated WAV at `https://ai.openphuquoc.com/assets/v113_adam_speed086.wav`; no inference calls or audio uploads.
- `tests/v12-proof.test.mjs`: Node built-in tests, no npm dependencies.

## Local commands (VPS-first, no GitHub Actions)

```bash
node --test tests/v12-proof.test.mjs
python3 -m http.server 18917
# Open http://localhost:18917/proof/
```

The lab proof fetches an existing public WAV file from AI Guide production without invoking any AI endpoint. For offline-only test, replace the sample URL in `proof/app.mjs` with a locally licensed WAV file. Do not copy or publish third-party audio without rights.

## Explicit protection gates

- **G0:** offline Node tests and 10 simulated turns pass; no external calls.
- **G1:** an actual iPhone Safari user tests 10 automatic turns and hears all 30 audio segments, Wi-Fi and mobile, including cancellation, background/foreground and audio route changes. Browser `ended` is not equivalent to human heard. **Unverified.**
- **G2:** implement a separately reviewed, distributed atomic turn budget; quota must be evaluated per turn not per segment. In-memory TurnBudget cannot be put directly behind Cloudflare Workers.
- **G3:** benchmark Vietnamese ASR/end-of-turn and TTS/LLM streaming on isolated resources, no impact on Core.
- **G4:** only after G0-G3 and explicit owner approval may V12 be wired to `ai.openphuquoc.com`.

**Transcript MASTER rule remains intact:** the engine defaults to `requireConfirmation: true`. Do not enable automatic submission of ASR text to AI without an explicit policy change.

## What this proof does NOT claim

It does not fix production V11.3, prove 10 audible Safari turns, create a paid-free unlimited AI service, implement server-side permission tokens, provide encryption/auth, or deploy any Worker. It is intentionally narrow and falsifiable.

## Rollback/containment

Removing this folder does not change OpenPQ Core V1.2, the CMS, other labs, or AI Guide Worker. Preserve existing production backups and secrets; never copy `wrangler.toml` or credentials into this lab.