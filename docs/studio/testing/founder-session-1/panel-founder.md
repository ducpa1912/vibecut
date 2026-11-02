# Panel report — Founder, VibeCut Round 6

**Build:** `main` b3c0354 · **Run:** 2026-10-28 17:40–17:54 · port 8811 · one Chromium, Playwright 1.64.1, fresh scratch. Sources imported read-only: A `7610134fee5e`, C `25bb4aaa14e2`, B `97a5fd3744c0`.

## Verdict

The engine is fast enough: A yielded two stories and four cuts in about 2 min 20 s. Check freeze fixed (23 s). I would not run a weekly channel on this build: finished videos are hidden, Edit has no way forward, and Dub sells a language it cannot use. Demo-ready, not ship-ready.

## Timeline

| Time | Event | Result |
|---|---|---|
| 17:40:49 | A path import | Ready 17:41:15 — **26 s**; Check auto-opened |
| 17:41:38 | A Check | **22.9 s**; 136 text regions |
| 17:41:43 | Stories: Short, 4:5 | **4.1 s**; 2 stories |
| 17:41:45 | Edit: play, switch story, Color, Effects | Header/preview **<2 s**; saved; no Back/Next |
| 17:44:04 | Finish: 4:5 ×2, 9:16 ×2 | All done 17:45:10 — **66 s for four cuts** |
| 17:45:14 | Change video | “Your videos”: one `source.mp4`, no cuts |
| 17:45:17 | Edit → Audio | Voice-over, Dub inspected |
| 17:46:34 | C import | Ready 17:48:16 — **102 s**; Check done 17:49:52 — **96 s** |
| 17:49:58 | B import | Ready 17:50:48 — **52 s**; Check done 17:51:19 — **31 s** |
| 17:53:40 | A Dub queue test | Failed after **14.3 s** |

17:44 includes a two-minute harness pause, not product latency. Creator path: import → four renders in about **2 min 20 s**. A creator expects a 53 s source to make two posts in five minutes; A clears that. C does not: 3 min 18 s before stories exist.

## Ranked issues

### P0 — Dub is a dead end
Dub says “Replace the spoken lines with a translated voice,” then offers only engine, voice and rate. No source/target language, no script, no translated-line preview. Saved plan has no `translate`. A 9:16 render failed in 14.3 s; the row said **“Render failed.”** The manifest said **“Dub needs a target language.”**
Root: `static/studio/edit/layers/audio.js:259-273` builds no `translate`; `audio.py:2812` refuses; `story_queue.py:401` hides the reason.
Fix: target, script, translated captions, queue-time validation, real error.

### P1 — No finished-video library
After four ready renders, **Change video → Your videos** still listed one row: `source.mp4 · 0:53 · 2 stories · Open now`. No shape, version, date, download or share. `GET /api/artifacts` is 404; renders live only under the open job’s Finish → Versions.
Root: `static/studio/shell.js:534-546` fills the modal from `listJobs`; no cross-job artifact query.
Fix: a **Renders** tab fed by a global artifact index; sources separate.

### P1 — Edit has no Back or Next
Header has only Story, shape, Repair, All stories, Undo (`static/studio/edit/index.js:173-185`). Only the rail moves on.
Fix: sticky **Back to Stories** / **Next: Finish**, save state beside them.

### P1 — Progress is honest only after it finishes
A Check held 5% for 10 s, then 35% for 11 s. C held 5% for **32 s**, then jumped 23→34→46→57% → ready. C import sat at **68%, “Tracking crop · 50 / 50”, for 41 s** — it reads as done while work continues. B did the same for 9 s. No ETA or cancel. Copy says Check “takes a few minutes on a long video” for a 53 s clip; the honest number, “Checked in 22.6 s,” appears afterwards.
Root: crop owns only 0.66–0.68 (`pipeline.py:2392-2396`) while speech starts at 0.70; UI shows percent and stage only (`static/studio/check.js:551-560`, copy `:578`). Check also repeats Import’s read.
Fix: time-weighted stages, “about N s left” after 10%, heartbeat at 68%, cancel, reuse the import read.

### P1 — B’s speech vanishes, with wrong advice
B has Chinese speech, Speech was on, but the job ended `whisper:false`, `transcript:null`, language `null`. Check warned: **“Speech wasn't read… Import it again with Speech on.”** Speech was on. Captions and Dub are impossible for this source.
Root: language defaults to `en`; the warning cannot distinguish “off” from “engine returned nothing.”
Fix: auto-detect, expose language, retry in place, report the error.

### P2 — Finish contradicts itself
After queuing both shapes, the header said **“1 story queued in 9:16”** while four ran. Versions said **“No render for this story and shape yet”** while it was at 0–1%. After completion, “Before you publish” still said **“Render this story first”** although a 9:16 cut existed.
Root: per-queue summary (`finish.js:2161`), per-shape Versions card (`:1133`), preflight fallback (`:733`; `preflight.py:652`).
Fix: per-job summary tagged by shape, one terminal state per item, resolve clip-set ids.

### P3 — Copy mismatch
“Only 2 non-overlapping stories fit; requested 3” beside a two-story list.

## Feature asks

| Ask | Call |
|---|---|
| Finished-video library with shape/version/date/download | **Greenlight now** |
| Back/Next in Edit | **Greenlight now** |
| Stage-aware progress, ETA, cancel | **Greenlight now** |
| Dub target + voice-over script | **Greenlight now**; hide Dub otherwise |
| Speech auto-detect/retry | **Greenlight now** |
| Translated captions and preview | **Defer** until target/script exist |
| More voice engines, per-workflow routes | **Reject now** |
| Batch templates / reuse a look | **Defer** |
| Auto-publish | **Reject**; rights and approval must gate it |

## Explicit answers

**(a) Check speed/progress/ETA honesty.** Speed is acceptable for short sources: 23 s (A), 31 s (B), 96 s (C). Honesty is not. C sat at 5% for 32 s and at 68% for 41 s during import; B for 9 s. No ETA or cancel. “A few minutes” is wrong for A and B; the first honest number appears after completion. Check also doubles Import’s read.

**(b) Confusing interface.** Yes. Dub promises translation without a language control. Finish says “1 story queued in 9:16” for four queues, and Versions denies a running render. “All stories,” “Queue all stories” and per-shape Queue compete; “Only 2 fit; requested 3” sits beside a two-story list. Audio is buried last. Every source is `source.mp4`.

**(c) No back/next in Edit.** Confirmed. Only the rail navigates; add Back and Next with save state.

**(d) No finished-video library.** Confirmed live. Four ready and one failed artifact are invisible from “Your videos”; only the source job appears. Cuts exist only inside one job’s Finish → Versions.

**(e) Translation and voice generation.** In **Edit → Audio**, last tab: modes Original / with music / Voice-over / Dub / Music only; engine (Apple, HeyGen, Fish, Gemini), 50+ locale voices, rate, Preview voice, ducking and loudness. Missing: Dub source/target, voice-over script box (zero textareas), translated captions, translated-line preview, engine routing. Translation survives only in Classic (`?classic=1`). In Studio, Dub fails at render.

## Priority call

**Ship next:** finished-video library, Back/Next, honest Import/Check progress with ETA and cancel, Dub target/script or Dub hidden, B’s speech retry. These are trust fixes.

**Cut:** more voice engines, translated-caption UI, per-workflow routes, batch templates, social publishing.

**Do not promise:** “translation and voice generation” until a target and script exist; “all your finished videos”; “Check in seconds”; precise ETAs. Promise one short source to two shapes in under five minutes, longer sources in roughly twice real time, and a status that says when work is happening.
