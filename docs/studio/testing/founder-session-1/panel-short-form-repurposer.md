# Panel report — Short-form repurposer

**Build:** `main` b3c0354 · **Run:** 2026-10-28 14:21–14:42 · **Port:** 8811 · one server, one Chromium, Playwright 1.64.1, fresh scratch data. Imported read-only by path: A → C → B.

## Verdict

The founder path completes on all three sources. A reused-footage repurposer cannot ship: Dub is selectable but cannot render, ingest/Check looks hung for minutes, duplicate queueing yields false failures, and finished videos have no library. The render engine is healthy (7–67 s per story, local Edit proxy under 1 s). These are product-surface gaps, not throughput limits. The old frozen Check poll and broken UI preflight are fixed.

## Timeline

| Time | Event |
|---|---|
| 14:21 | Server up |
| 14:25:56–14:26:16 | A ingest, 20.0 s |
| 14:27 | A Check: 21.9 s server, 26 s visible |
| 14:28 | A Stories 2.2 s, Edit 2.7 s, Finish 4:5 in 7.2 s |
| ~14:34–14:35 | C ingest 38.9 s; Check 40.9 s server, 42.4 s visible |
| 14:36:43–14:38:15 | B ingest 91.8 s |
| 14:38–14:39:54 | B Check 77.9 s server, 79.5 s visible |
| 14:39:54–14:41:12 | B Stories, Edit, Finish both shapes |
| 14:42 | Setup checked; server stopped |

## Ranked issues

### P0 — Dub saves, then every render fails

Selected **Dub** on A story 01. Saved edit has `audio.mode = "dub"` and no `translate.target`. The 9:16 queue item failed in 14.4 s with only **"Render failed."** Server log shows the real cause: `audio.AudioError: Dub needs a target language.` (14:43:37). The mode the founder asked for is unusable.

Root cause: `static/studio/edit/layers/audio.js:797-805` saves the mode without a target; `audio.py:2812` correctly refuses it. UI promises "translated voice" (`audio.js:44`) but offers no language choice.

Fix: source/target language, translated-caption toggle, disable Dub until a target exists, preview the translated line, and show the server reason in the queue row.

### P1 — Ingest and Check look hung; 68% plateau; no ETA

Ingest A/C/B: **20.0 / 38.9 / 91.0 s**. Check server: **21.9 / 40.9 / 77.9 s**; visible **26 / 42.4 / 79.5 s**. B sat **30.3 s at 68% "Tracking crop · 48 / 48"**, then jumped to speech. B needed ~171 s to usable Check.

Crop tracking is the heaviest stage (8.8 / 18.2 / 37.3 s), but progress is capped at `0.66 + 0.02 × fraction` (`pipeline.py:2392-2394`), and speech starts at 0.70 (`stt.py:1843`). UI shows percent only (`import.js:390-395`, `check.js:551-560`). Fix: time-weighted stages, heartbeat during crop/speech setup, "about N s left" after 10%, cancel. Consider deferring crop tracking until stories exist.

### P1 — Speech silently missing on B; wrong recovery advice

B has Chinese speech. Import had `transcribe: true`, yet the job ended `transcript: null`, `speech_language: "en"`, `whisper: false`. Check says **"Speech wasn't read… Import it again with Speech on"** — Speech *was* on. Captions and dub are impossible for this source.

Language defaults to `en` with no import control (`pipeline.py:2405-2409`); the warning at `detect.py:1305` cannot distinguish "off" from "engine returned nothing." Fix: auto-detect/select language, retry STT in place, report the real engine error.

### P1 — Duplicate queue actions create false failures or duplicate versions

C: Stories "Queue all", then Finish "Queue all stories · 4:5" became a queue item marked **failed — "That reel is already rendering."** B: same pattern produced **Version 2** for a story already queued, wasting a render.

`app.py:8106-8109` returns 409 for an active render, while `story_queue.py:8-10` says duplicates should be waited on. Make queueing idempotent: attach to the active item, disable buttons for queued/rendered shapes, never write a failed row for a duplicate.

### P1 — Edit has no Back or Next

The header has only Story, shape, **All stories**, Undo (`static/studio/edit/index.js:172-187`). Stories/Finish are reachable only through the rail. Add "Back to Stories" and "Next: Finish."

### P1 — No finished-video library

"Change video" opens **Your videos**, listing source jobs only: name, duration, story count (`shell.js:553-575`). Renders live only under Finish → Versions. Three imports all named `source.mp4` are indistinguishable. Build a library of artifacts with thumbnail, title, shape, quality, date, download and share; keep sources in a separate tab.

### P1 — Translation and voice workflow incomplete

Audio has Voice-over/Dub, four voice engines, voice picker, preview, ducking and loudness. Missing: Dub target language, translated captions, a voice-over **script box**, and translation engine/route control. Setup claims "translation" (`setup.js:253`) but offers no control. Translation exists only in Classic (`static/app.js:3471`). Voice-over re-voices the transcript, with no script box. Add one Translate card: source → target, caption preview, voice, engine route.

### P2 — ETA oscillates

Live poll: 15 → 23.1 → 21 → 14.4 → 18.5 s while progress rose; next item 30 → 47.7 → 34.4 → 0 s. The formula assumes linear progress (`app.py:1917-1919`), but renders move in stage steps. Smooth over a window, use stage weights, hide ETA until enough samples.

### P2 — Interface ambiguities

Stories gives **Queue all 2**, **Render this story**, and **Edit this story** equal weight. Finish's Versions stayed on 9:16 after queueing 4:5, saying "No render" while that queue was at 87%. "All stories" in Edit is ambiguous. Duplicate failed rows sit beside successful runs.

### P2 — Rights friction for reused footage

Each import needs one boolean tick (`import.js:182-184`; `rights.py:79-106`). No license type, credit, territory, expiry, source URL or allowed platforms. A repurposer needs to prove scope, not assert ownership; the tick does not reach Finish or the publish kit, so no credit reminder appears. Greenlight a per-source rights record and reuse manifest; keep the hard watermark rule.

### P3 — Preflight still 404s for story ids

`GET /api/jobs/{id}/preflight?story_id=st_0000000_0020880` (valid on A) returns `story_not_found`; the edit-scoped preflight used by the UI returns 200. Low impact; fix or retire the contract.

## Feature asks

| Ask | Call |
|---|---|
| Dub target language, translated captions, voice-over script | **Greenlight** — backend exists |
| Finished-video library | **Greenlight** — founder ask |
| Back/Next in Edit | **Greenlight** — small, high relief |
| Stage-aware progress, ETA, cancel | **Greenlight** — fix |
| Speech language auto-detect/retry | **Greenlight** — blocks non-English reuse |
| Rights metadata + reuse manifest | **Greenlight minimal fields**, defer enforcement |
| Idempotent queue | **Greenlight** — correctness |
| Campaign/batch templates | **Defer** |
| Direct auto-publish | **Reject** — rights/API risk |

## Explicit answers

**(a) Check speed/progress/ETA.** Server 21.9 / 40.9 / 77.9 s; visible 26 / 42.4 / 79.5 s; ingest adds 20 / 38.9 / 91.0 s. Percent and stage text, no ETA; B froze 30 s at 68%. Poll freeze is fixed; perceived speed is not, because the heaviest stage owns the smallest progress band.

**(b) Confusing interface.** Yes: Queue all vs Render vs Edit; Versions ignores the queued shape; duplicate failed rows; every library row named `source.mp4`; "All stories" unclear.

**(c) No back/next in Edit.** Confirmed. Only "All stories", Undo and the rail.

**(d) No finished-video library.** Confirmed. "Your videos" lists sources; completed renders are per job under Finish → Versions.

**(e) Translation/voice gaps.** Audio tab exists, but Dub has no target language, Voice-over has no script, translated captions are absent, and Setup's translation claim has no control. Classic-only translation is undiscoverable from Studio.
