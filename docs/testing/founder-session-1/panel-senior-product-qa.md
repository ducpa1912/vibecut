# Panel review — Senior product / QA, VibeCut Round 6

**Build:** `main` b3c0354. **Run:** 16:11–16:39, one server on 8811, scratch data, Playwright 1.64 Chromium, own HAR/trace (not the founder HAR). **Videos:** A `7610134fee5e`, C `25bb4aaa14e2`, B `97a5fd3744c0`, imported read-only by path.

## Verdict

Round 6 is demoable, and the Check cache freeze is fixed: every poll returned 202 running then 200 ready, with no frozen report. A 53 s AV1 video went import→Check in 200 s; C and B auto-opened Check after 78 s and 114 s.

But the founder's three headline problems remain. Time-to-first-story is dominated by 78–156 s of ingest reading, with no ETA. Edit still has no Back or Next. There is no finished-video library: the only “library” is a source-job picker with three files all named `source.mp4`. Two new defects are worse than cosmetic: Dub is selectable but cannot render because Studio never sends a target language; preflight still 404s on unedited stories, hiding “Before you publish”.

No P0 (no data loss or rights bypass). A's renders hit the machine's 5 GB disk reserve; C rendered both shapes on a scratch volume.

## Timeline

| Time | Did | Expected | Happened |
|---|---|---|---|
| 16:11 | Import A by path, tick rights | Read, then open Check | Reading 0→68% for 156 s; job ready in 155.6 s |
| 16:14 | Run Check A | Progress + estimate | 45 s. 5% held 23 s, 35% held 16 s, then report. No ETA |
| 16:17 | Stories A: Short, Find, 4:5 | 3 picks | 2 stories (“Only 2 … fit; requested 3”) |
| 16:17 | Edit A: play, switch story, Color, Effects | All work | All worked; proxies 5.8/9.1 s. No Back/Next |
| 16:20 | Finish A: Queue 4:5, 9:16 | Two renders | Failed on disk reserve: “Need 79777216 bytes but only 0 bytes … above 5368709120-byte reserve.” Header “Done · 1 failed” |
| 16:22 | Audio: Voice-over, Dub | Translation/voice | No target language, no script box |
| 16:31 | C: import, Check, Stories, Edit, Finish | Full pass | Auto-opened Check at 78 s; Check 70 s; 3 stories; 4:5 render 34 s, 9:16 85 s |
| 16:34 | B: same pass | Full pass | Auto-opened Check at 114 s; Check 30 s; 3 stories; preflight 404 on unedited story |
| 16:36 | Change video | Switch video | Opens “Your videos”; only source jobs, not renders. Three `source.mp4` rows |

## Ranked issues

### P1 — Dub is a dead end; Voice-over has no script

Edit → Audio → Mode = Dub says “Replace the spoken lines with a translated voice.” It then offers only Engine, Voice, rate and Preview voice; no source/target language or text field. Backend refuses it: `audio.py:2810-2811` raises `AudioError("Dub needs a target language.")`. Studio's plan is built at `static/studio/edit/layers/audio.js:797-807` (mode only); `model.js` has no language/script fields. A user can select Dub, see it saved, queue, then fail. Voice-over says “Speak a new voice line over the source”, but the panel has zero textareas (measured). That is a voice *sample* workflow, not voice generation.

Fix: target-language `<select>` passing `translate.target`; script textarea for Voice-over (or say it reads the existing transcript); block queueing with “Choose a target language”. Greenlight now.

### P1 — No library of finished videos

“Change video” opens a modal titled **Your videos** (`static/studio/shell.js:217-230`). `loadLibrary` calls `listJobs` (`shell.js:526-551`), so it lists source jobs only. After C had two completed renders, the modal still showed only sources with no render, shape, or version. Per-job artifacts work (`GET /api/jobs/a20e5322f700/artifacts` returned 9:16 and 4:5), but there is no cross-job listing and `GET /api/artifacts` is 404. Finished cuts live only under Finish → Versions for the open job.

Fix: a “Renders” tab backed by a cross-job artifacts query (thumbnail, title, shape, duration, version/date). Greenlight.

### P1 — Time-to-first-story is ingest, not Check; no ETA

Import reading took 155.6 s (A), 78 s (C), 114 s (B). Check itself was 45/70/30 s. The founder attributed the wait to Check; the 147/164/135 s they saw was the fixed cache freeze, but first story still needs 2–4 minutes. Check has no ETA: A held 5% for 23 s, then 35% for 16 s; B went 5→26→40→55→done. Copy says Check “takes a few minutes on a long video”, wrong for B (30 s) and understating C (70 s).

Fix: coarse estimate from `source_report.timings`/duration at ingest and Check (“about 1 min”), or an indeterminate bar. Show it on Import, not just the top strip.

### P2 — Edit has no Back or Next

The Edit header (`static/studio/edit/index.js:175-194`) has Story, 9:16/4:5, All stories, Undo — no “Back to Stories” or “Next: Finish”. Only the rail (`shell.js:23-29`) navigates. Add sticky Previous/Next in the header using the same `ctx.go()` gate; keep the rail.

### P2 — “Before you publish” still 404s on unedited stories

For A (has an Edit) Finish called `/edits/{id}/preflight` → 200 and showed notes. For B (story not edited in that shape) it fell back to `/jobs/da92300cde7f/preflight?story_id=st_0010625_0034375` → 404 `story_not_found`. `static/studio/finish.js:733` builds that fallback from the clip-set story id; `preflight.py:652` wants a saved story/render key. The UI then shows `RENDER_FIRST_NOTE` (“Render this story first”), hiding Check findings. Make preflight accept clip-set ids, or resolve the render key first; don't mask 404 as “render first”.

### P2 — Finish queue state under-reports shapes

C queued 4:5 and 9:16; both rendered (34 s, 85 s), but the header said “1 story queued in 9:16.” The header is per-queue, not per-job (`finish.js:2161`). The story row showed only “Queued · Version 1 · Final”, no shape; only the Queue card shows shape. 9:16 took 2.5× the 4:5 time.

Fix: summarise both shapes, show shape on the row, keep per-item ETA.

### P2 — Disk-full copy is machine language; summary contradicts

A: “Need 79777216 bytes but only 0 bytes are available above the 5368709120-byte reserve.” The page said “Done · 1 failed”; the item said “Done 100%” then “Failed”. Say “Not enough disk space. Free about 80 MB; VibeCut keeps 5 GB free.” One terminal state per item, Retry beside it.

### P3 — Minor

- Three source rows read `source.mp4`; no project name or job suffix.
- Finish is blank except “Reading renders…” for ~4 s; add a skeleton.
- After a report the button still says “Run Check”, no last-checked time; restarts a 30–70 s job.
- “Only 2 … fit; requested 3” sits next to Queue all while Stories says 3.

## Feature asks

**Greenlight now:** (1) Dub target language + Voice-over script box; (2) cross-job Renders library with shape/version/date and open/reveal/share; (3) Back/Next in Edit; (4) honest ingest/Check estimate.

**Defer:** translated captions and per-workflow Translate/Voice/Music engine order (backend has translation, Studio has no controls; ship the two above first); source-library rename/search/delete; batch queue ETA; rights status in the publish kit.

**Reject:** adding more voice engines before Dub has a target and Voice-over has a script — more selectable dead ends worsen the confusion. Also reject a separate media-library area that duplicates Finish → Versions; extend the artifact model.

## Explicit answers

**(a) Check speed/progress/ETA honesty.** Check is 30–70 s now, not 147–164 s; the cache fix is real (202 polls, then 200). The long wait is ingest: 78–156 s. Check progress is coarse and freezes (5% for 23 s, 35% for 16 s); no ETA is shown, so nothing is falsely estimated, but nothing helps the user wait.

**(b) Confusing interface.** Audio is the last Edit tab; Dub/Voice-over sit below a large music-brief card. “Change video” opens a source-job picker. Finish mixes per-shape summaries. Three identical `source.mp4` rows compound it.

**(c) No back/next in Edit.** Confirmed. Only the rail navigates. Add header Previous/Next.

**(d) No finished-video library.** Confirmed. “Your videos” lists source jobs only; finished renders live under Finish → Versions for one job. C's two completed artifacts were invisible from the library modal. `GET /api/artifacts` is 404.

**(e) Translation and voice generation.** Location: Edit → Audio (last tab). Exists: mode selector, engine list (Apple local, HeyGen, Fish, Gemini), 50+ locale voice picker, Preview voice. Missing: source/target language for Dub, a Voice-over script, translated captions, and any Studio control for the engine routes that exist in Classic Setup. Dub fails server-side with “Dub needs a target language”; Voice-over has no script field. It is buried and cannot complete the job it advertises.
