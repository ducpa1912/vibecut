# VibeCut — Round 6: founder-session persona panel

**Date:** 2026-10-28
**Build:** `main` at `b3c0354` (voice/music fallback without MiniMax; Check cache fix `3da8ac3`)
**Method:** five personas replayed the recorded founder session, one at a time, each with one server on port 8811, one Chromium, Playwright 1.64, and its own scratch data. Sources imported read-only by path. No code changes.
**Evidence:** founder `actions.js`, `network-summary.md`, and the 37 MB HAR read in place; five live panel reports under `docs/studio/testing/founder-session-1/panel-*.md`; per-persona HARs, traces, screenshots, and logs kept in scratch only.
**Caveat:** the harness restarted several times. Some personas re-ran phases; host load reached 18–40 during one long-form A run (`Check` 182 s), and one client run hit a deliberate disk-reserve test. Absolute times below are given as ranges, not one benchmark.

---

## Executive verdict

**DEMO-READY, NOT SHIP-READY.**

The founder path works. Path import, the rights gate, Check, Short/4:5 stories, Edit colour/effects, both render shapes, and Change video all completed on A. On an unloaded run A went import → two stories → four finished cuts in about **2 min 20 s**. The frozen-Check cache bug is fixed: every persona saw 202 running polls turn into a 200 ready report, and progress moves.

Four defects still break the product promise:

1. **Dub is a dead end.** Every persona could select Dub; none could render it. Studio never sends a target language, and the backend refuses with `Dub needs a target language.` The queue row says only “Render failed.”
2. **Finished videos have no library.** After four ready renders, “Change video → Your videos” still listed only `source.mp4`. Cuts live inside one job’s Finish → Versions.
3. **Edit has no Back or Next.** The rail is the only way out.
4. **Import and Check still look hung.** Percent plateaus at 5%, 35%, and 68% for 10–41 s; no ETA, no cancel; Check repeats Import’s read.

For a repurposer, the missing Chinese speech on B is a fifth blocker. For a client editor, the missing approval state and delivery log make paid work unsafe even after the library ships.

No persona found data loss or a rights bypass. The render engine is healthy. This round is about product surface, state honesty, and navigation, not throughput.

---

## Ranked fixes

Duplicates are merged. Persona tags: **SR** short-form repurposer, **LF** long-form creator, **QA** senior product/QA, **CE** client editor, **F** founder.

| # | Sev | Fix | Raised by |
|---|---|---|---|
| 1 | **P0** | **Make Dub honest: target language, source confirmation, editable script, translated-caption toggle, and a queue-time block when no target exists. If that cannot ship now, hide Dub.** Backend already supports `audio.translate`; Studio writes only the mode. Show the server reason, not “Render failed.” | SR, LF, QA, CE, F |
| 2 | **P0** | **Ship a finished-video library.** One cross-job list of artifacts with thumbnail, story, shape, quality, version, date, download/share, and review state. Sources get a separate tab. `GET /api/artifacts` is currently 404; “Your videos” is a source-job picker. | SR, LF, QA, CE, F |
| 3 | **P1** | **Add sticky Back to Stories / Next: Finish in Edit**, with save state beside them. Keep the rail, but stop making it the only route. | SR, LF, QA, CE, F |
| 4 | **P1** | **Make Import/Check progress stage-weighted and honest.** ETA after 10%, heartbeat during crop/speech, no 68% “Tracking crop · 50 / 50” plateau, cancel, and one read instead of Import then Check. Copy must stop saying “a few minutes on a long video” for a 53 s source. | SR, LF, QA, CE, F |
| 5 | **P1** | **Fix speech on non-English sources.** B has Chinese speech, Speech was on, yet `transcript:null`, `whisper:false`; Check wrongly says “Import it again with Speech on.” Auto-detect or expose language, retry STT in place, surface the engine error. | SR, LF, F |
| 6 | **P1** | **Make queueing idempotent and the summary truthful.** Queue all twice must attach to the active item, not create a failed “already rendering” row or Version 2. Finish must not say “1 story queued in 9:16” while four items run. | SR, QA, F |
| 7 | **P2** | **Resolve clip-set story ids in preflight.** `GET /preflight?story_id=st_…` still 404s on unedited stories, so “Before you publish” is hidden or replaced by “Render this story first.” | SR, LF, QA, F |
| 8 | **P1/P2** | **Fix the disk preflight.** A 64 MB path import was refused with “0 bytes available” while 4.3 GB was free. Report free, reserve, and shortfall in GB; offer cleanup; do not demand the full 5 GB reserve for an in-place import that copies nothing. | QA, CE |
| 9 | **P2** | **Add client approval and a delivery log.** Review links are pinned and expiring — a good foundation — but there is no Approved / Changes requested state, comments, per-client link list, or record that version 3 was viewed. | CE |
| 10 | **P2** | **Replace boolean-only rights with a per-source rights record:** license/scope, credit, territory, expiry, source URL, allowed platforms; show it on the artifact and publish kit. Keep the hard watermark rule. | SR, CE |
| 11 | **P2** | **Clean up the confusing surfaces.** Audio is last and mixes music above voice; Dub and Voice-over differ by one sentence; Stories gives Queue all / Render / Edit equal weight; Finish contradicts itself; all three sources are named `source.mp4`; “All stories” is ambiguous. | SR, LF, QA, CE, F |
| 12 | **P3** | **Fix copy and defaults.** “Only 2 non-overlapping stories fit; requested 3” beside a two-story list; no last-checked time; Finish blank for ~4 s; “Run Check” still offered after a report. | QA, F |

### Root causes worth naming

- Dub: `static/studio/edit/layers/audio.js:259-274,797-807` writes mode/voice/music and no `translate`; `audio.py:2810-2813` correctly refuses; `story_queue.py:401` hides the reason.
- Library: `static/studio/shell.js:526-575` fills “Your videos” from `listJobs`; renders are only read per job under `static/studio/finish.js:1116`.
- Back/Next: `static/studio/edit/index.js:172-194` has no step controls; `shell.js:23-29` is the only navigator.
- Progress: crop progress is capped at `0.66 + 0.02 × fraction` (`pipeline.py:2392-2396`) while speech starts at `0.70` (`stt.py:1843`); UI shows percent and stage only (`static/studio/check.js:551-560`).
- Speech: language defaults to `en` (`pipeline.py:2405-2409`); the warning at `detect.py:1305` cannot distinguish “off” from “engine returned nothing.”
- Queue: `app.py:8106-8109` returns 409 for an active render while `story_queue.py:8-10` says duplicates should be waited on; the header is per-queue (`finish.js:2161`).
- Preflight: `static/studio/finish.js:733` passes a clip-set story id; `preflight.py:652` resolves only saved stories/render keys.
- Disk: the reserve is hard-capped at 5 GB (`disk.py:116-121`) and the message quotes available-above-reserve as “0 bytes.”

---

## Role verdicts

### Short-form repurposer — **HOLD for reused footage**

The founder path completes on A, C, and B. The money workflow does not. Dub is selectable but cannot render; B’s Chinese speech is silently missing; duplicate queueing creates false failures or duplicate versions; rights are a single boolean with no scope or credit; finished cuts have no library. Ingest/Check waits reach minutes with percent-only feedback. The renderer itself is fine (7–67 s per story, sub-second Edit proxy). Verdict: **not usable for paid repurposing until Dub, speech, library, and queue correctness ship.**

### Long-form creator — **HOLD for weekly use**

Own-footage handling is right: path import reads in place, rights is mandatory, nothing uploads by default. Story quality is usable (A two stories, B/C three), though A’s second story reads like an ad. Colour and effects are per story and do not carry to the next video, so weekly reuse stays manual. Check duplicates Import’s read; there is no library of finished renders; Dub is a dead end. Verdict: **one-off demos work; a three-videos-a-week channel does not.**

### Senior product / QA — **DEMOABLE, NOT PAID-SAFE**

No P0 data loss or rights bypass. The Check cache freeze is genuinely fixed. But Dub is a selectable dead end, the finished-video library does not exist, Edit has no step controls, preflight still 404s on unedited stories, and queue summaries under-report shapes. Disk-full copy is machine language. Verdict: **ship the trust fixes before calling the workflow complete.**

### Client editor — **REJECT for paid delivery**

Studio can shape a story and render a cut. It cannot run a paid job end to end. Finished cuts have no client-facing library; Dub cannot render; Import/Check give long silences; the disk reserve can refuse a small path import; review links exist but carry no approval, comments, or delivery record. Verdict: **a paying client would see a demo, not a service.**

### Founder — **DEMO-READY, NOT SHIP-READY**

A 53 s source produced two posts in about 2 min 20 s; a solo creator expects five minutes, so the core promise is close. C took 3 min 18 s before stories existed. Four ready renders were invisible from “Your videos,” Edit had no forward control, and Dub sold a language it could not use. Verdict: **ship the trust fixes; do not add surface area.**

---

## What works

- Path import, mandatory rights tick, local-first handling; nothing uploads by default.
- Check cache freeze fixed (`3da8ac3`): 202 running then 200 ready, no frozen report.
- A end-to-end: import 26 s, Check 23 s, two stories, four cuts in 66 s (founder run).
- Renders: 7–67 s per story; 9:16 about 2.5× the 4:5 time on C.
- Story switching, colour (Vivid pop, Teal and orange), motion and effects all work.
- Review links are pinned to one artifact and support expiry and labels.
- Disk guard and watermark rules exist; they need better copy, not removal.

---

## Feature calls

### Greenlight now

- Finished-video library with shape, version, date, download/share.
- Dub target language, editable script, translated-caption toggle, and queue-time validation — or hide Dub.
- Back to Stories / Next: Finish in Edit.
- Stage-weighted Import/Check progress, ETA after 10%, cancel, and a single read.
- Speech language detection and retry in place.
- Idempotent queue and a truthful per-job summary.
- Client approval state, comments, and a delivery log on review links.
- Minimal rights record per source; show it on the artifact.

### Defer

- Translated captions and translated-line preview until Dub has a target and a script.
- Per-workflow Translate / Voice / Music engine routing.
- Batch templates and reusable looks.
- Per-client workspaces, roles, and a full delivery ledger.
- Source-library rename, search, and delete.
- A separate media-library area that duplicates Finish → Versions; extend the artifact model instead.

### Reject now

- More voice engines before Dub can render and Voice-over has a script.
- Auto-Dub with a cloud default.
- Auto-publish to social platforms; rights and approval must gate it.
- Removing the rights gate or watermark rule.
- Auto-queueing every shape on import (version spam).

---

## What to promise today

**Can say**

- One short source to two shapes in under five minutes; A did it in about 2 min 20 s.
- Longer sources take roughly twice real time before stories exist.
- Check now reports progress and does not freeze its cached report.
- Renders are local, immutable artifacts; old review links stay valid.
- Rights are required before import.

**Cannot say**

- “Translation and voice generation” while Dub has no target and Voice-over has no script.
- “All your finished videos” while the library lists sources only.
- “Check in seconds” or any precise ETA.
- “Back/Next” or “saved and safe to leave.”
- “Client-ready delivery” without approval state and a delivery log.
- “Speech works for every language.”

---

## Tests required

1. **Dub:** selecting Dub without a target disables Queue with a reason; with a target the render succeeds; the queue row shows the server error, not “Render failed.”
2. **Library:** after renders in two jobs and both shapes, `GET /api/artifacts` (or the replacement) returns them with job, story, shape, version, date; sources stay separate.
3. **Back/Next:** Playwright from Edit to Stories and Finish; autosave completes; unsaved state blocks or warns.
4. **Progress:** stage-weighted percent is monotonic; no plateau over 10 s without a heartbeat; ETA error bound; Cancel stops ffmpeg and leaves a terminal state.
5. **Single read:** Check reuses Import’s OCR/speech where possible; no duplicate frame sampling.
6. **Speech:** a Chinese source with Speech on yields a transcript or an actionable error; retry in place works; the warning distinguishes “off” from “engine failed.”
7. **Queue idempotency:** Queue all twice; no failed duplicate row; no Version 2; the summary counts both shapes.
8. **Preflight:** a clip-set story id returns 200 and real findings, or an explicit unsupported state — never a masked 404.
9. **Disk:** a path import smaller than free space succeeds; the message shows free, reserve, and shortfall in GB; cleanup unblocks.
10. **Client delivery:** approval state persists; comments attach to an artifact version; the delivery log records sent/viewed/approved.
11. **Rights:** a source with license scope and credit surfaces both on the artifact and publish kit; the watermark rule still blocks removal.
12. **Regression:** A/C/B import → Check → Stories → Edit → Finish → Change video on a clean machine with one server.

---

## Founder line

> “The engine is fast enough. I would not run a weekly channel on this build: finished videos are hidden, Edit has no way forward, and Dub sells a language it cannot use.”

**Decision:** fix the five trust gaps first — Dub, library, Back/Next, progress honesty, speech — then ship the client approval layer. Do not add voice engines, translated-caption UI, batch templates, or publishing until those are done.

**No code changes were made during this review.**
