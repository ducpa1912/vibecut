# Voice Room plan (revised 2026-11-01)

The Voice Room is the `voice-room` lane: port `8797`, data `~/vibecut-lanes/voice`, hidden behind `VIBECUT_FEATURES=voice_room`. See `docs/voice/lane.md` for running it.

## Built

| Area | What works | Where |
|---|---|---|
| Library | Stock voices per engine, cloned voices with Play, Rename and Delete, search and language filter | `/voices`, `voiceroom.js` |
| Cloning | From a recording or an upload (cleaned locally), and from a video through the clean-clip finder (fast search by default, the first 2:00 unless *whole video* is ticked) | `voiceclone.js`, `clipfinder.js`, `routes_voice_clone.py` |
| Cancel | Clip search, clone requests (`DELETE /api/voices/tasks/{id}`), and a sample still being made | same |
| Playback | One player with honest Play/Stop states; A/B compare on one line; recent previews; favorites | `compare.js`, `recent.js`, `favorites.js` |
| Setup | This app's own OpenRouter and OpenCode keys, engine status, and library backup and restore (ZIP) | `setup.js` |
| Language | Detected locally with Whisper right after a recording or an upload; a manual pick wins | `POST /api/voices/detect-language` |
| New shell | Left rail and mobile tabs, one persistent player, behind `/voices?ui=new` | `next.js`, `next.css`, `voices-next.html` |
| Founder tools | Finder launchers (`Voice Room Server.command`, `Record Voice Room.command`), Playwright recording, a guarded live check | `scripts/` |

## Fixed in the 2026-11-01 review

- `24c2176`: clone previews ignored the Rate control, while stock voices and the A/B compare used it. The server now also clamps a clone's rate to 0.5–2.0×.
- `eac98e9`: restoring the same backup twice cloned every voice again. Samples already in the library are now counted, not duplicated.
- `ac23a41`: tests for local language detection and the `?ui=new` shell (they had none).

## Open

1. **Founder checks**, by hand, with real files:
   - `docs/testing/voice-room-pass-1.md` (current UI, from the 09:22 recording). Its labels still match, but the Compare and Recent panels now sit between sections 02 and 03, and its step 4.1 (the new rate on a clone) only works since `24c2176`.
   - A **new recording of `?ui=new`** (`Record Voice Room.command`); the new shell has no founder script yet.
   - A recording of what pass 1 did not cover: cloning from a recording or upload, the clip finder, Rename and Delete, Cancel, backup and restore, language detection.
   - The damaged first recording `~/vibecut-lanes/recordings/voiceroom/2026-10-29-085746` needs redoing.
2. **Live OpenRouter check** of one clone (`scripts/voice_live_check.py`): waits for the founder's explicit OK.
3. **Pick one UI.** Two front ends now run side by side (`voiceroom.js` and `next.js`, about 1,600 lines that duplicate playback and library code). Once the founder approves the new shell from a recording, make it the default and retire the old page, or drop the new one.
4. **Tests that follow the founder's recordings.** The Chromium spec covers the old page only and builds tone files in a temp folder. Under the founder-only testing rule, decide whether automated tests may keep using synthetic audio. If not, replace them with fixtures the founder provides.
5. **Clip finder defaults.** Studio's Edit panel calls the same search without options, so it now searches only the first 2:00 of a longer video (with separation, not the fast path). Studio should say so, or pass `full`.
6. **Signatures and history.** Many lane commits from 2026-10-29/30 are unsigned, and `caa6758` merged `classic` into the lane on 2026-10-29 19:51. Both are in the pushed history and stay there (no force-push); studio integration sees them.

## Next build (proposal)

The founder's OpenCode review (2026-10-31) found that the room ends at "preview a voice": it is a good voice lab but not yet a creator workflow, and the avatar plan spans four kinds of products. The next step keeps to the voice:

1. **Script to voiceover** (one build, behind `?ui=new`): paste a script → pick a voice (A/B compare) → generate the full voiceover in chunks with progress and Cancel → listen and fix a line → export WAV/MP3 with SRT captions. It reuses the clone store, the one player and the cancel switches.
2. **Then** hand the voiceover to Classic or Studio as an audio track, so the existing render does captions and export.
3. **Avatar later**, through one surface with capability flags (`twin_from_video`, `portrait_lipsync`, `character_consistency`, `live_stream`), one provider first. Not before step 1 is used by the founder.

Each step ends with a founder recording and a script built from it, as for pass 1.

## Learning from VoiceStudio (2026-11-01)

VoiceStudio is AGPL-3.0, so we learn from it but take no code. Three notes:

- `docs/voice/clean-room-spec.md`: its UI and UX in plain words, plus the specs to build. OpenCode builds from this note only and never opens VoiceStudio's code.
- `docs/voice/cloud-first-plan.md`: stay on the cloud for now and match or beat its UX. This build order replaces the "Next build" list above.
- `docs/voice/local-future.md`: local cloning on Apple Silicon (lead: VoxCPM2), then any machine.
