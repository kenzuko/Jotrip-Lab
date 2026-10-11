# OpenPQ AI - Sóng V12.1 voice-session implementation

Date: 2026-10-11. UX source-of-truth: `OPENPQ_AI_SONG_UX_MASTER_V1_0_20261011.md` (approved concept; unchanged).

This directory is a **tracked technical snapshot** of the verified `ai.openphuquoc.com` experiment. It is **not a deployment command**. No secrets or credential files are included. Core V1.2, CMS, weather, airport, transit and identity remain locked. The current active Worker is `openpq-ai-guide-edge-preview`; snapshot version `3ebe70ff-e8dd-4fb7-b0cf-7d74c6fcf5dd`.

## What changed

- `public/index.html`: S0 welcome, S1 conversation, S2 factual result. Approved pearl/wave Sóng artwork is referenced as `/song-approved.webp` from the owner-approved visual handoff and must not be redrawn.
- `public/song-v1.css`: mobile-first appearance, safe-area keyboard lift, dark mode, reduced-motion.
- `public/song-v1.js`: text and voice paths; Whisper transcript edit/confirmation is **still mandatory**; one user-initiated voice session can attempt automatic microphone rearm after audible playback. Clear stop, error, permission and background fallbacks. WebAudio applies a gentle 95Hz high-pass, +2.3dB highshelf at 2.85kHz, and 0.84 output gain per user preference. Distortion in the source TTS remains an open issue, not a demonstrated fix.
- `worker.mjs`: one signed `speakSegments` permit per answer with `speechText(answer)`; prevents 2-3 segment calls from exhausting 3/min/IP TTS quotas on the first answer. Other Worker policy and signed TTS bridge unchanged.
- `asr-quality.mjs`: guards malformed/implausibly verbose Whisper transcripts; microphone cropping and safety behavior in existing project remain in place.
- `test_v121_voice_release.mjs`: three offline behavior/invariant tests.

## Verified

- Offline: 3/3 V12.1 and 9/9 ASR tests pass.
- Browser Chrome mobile emulation: ten typed turns on each of 320x640, 390x844 and 1440x900; no overflow.
- Fake audio/micro Chrome test: two complete voice cycles **with automatic microphone rearm**, 2 ASR, 2 LLM and 2 TTS requests, no JS errors. Mocked API/voice inputs are not evidence of Safari behavior.
- HTTP real Worker: two successive Gemma + VieNeu turns succeeded, **one WAV each**: turn 1 2,152ms LLM + 9,395ms TTS; turn 2 2,100ms LLM + 8,206ms TTS. HTTP and WAV integrity do not prove actual human audibility.
- Real WebAudio on Chrome mobile emulation played two WAV samples successively, both onended.
- Live smoke: `/`, `/song-v1.js?v=1211`, `/song-v1.css?v=1211`, `/guide-legacy`, `/api/health`: 200.

## Still open / do not claim

1. Physical iPhone Safari test: microphone, transcription in Southern Vietnamese, auto-rearm, keyboard, Bluetooth routing, second-turn audio and tab interruptions.
2. Source TTS distortion and 8-9 seconds CPU TTS latency; EQ filtering cannot replace a quality model nor guarantee noise-free voice.
3. Live data contracts (weather/airport/transit) not wired in, no invented real-time data.
4. Production wordmark vector from brand handoff is not available; raster crop of approved reference currently used.

## Reproduce offline

```sh
node --test test_v121_voice_release.mjs
```

Tests import adjacent existing Worker modules; assemble this snapshot with the isolated Worker directory to execute. Do not run GitHub-hosted Actions or deploy Core. For real iPhone, use `ai.openphuquoc.com` then Settings > Copy diagnostic log after two spoken turns. The log contains timing/status metadata only and no conversation transcript.

## Rollback

Preserved prior visible legacy UI at `https://ai.openphuquoc.com/guide-legacy`. Previous Worker version `69fe00e0-2981-475d-b1ce-ebca48e57cff`. Confirm current Cloudflare version before any rollback.
