# Panel review — long-form creator (sequential round 6)

**Build:** `main` b3c0354. **Run:** 2026-10-28 14:51–15:10, port 8811, scratch data. **Sources:** A 52.9 s AV1, C 111.7 s HEVC, B 88.8 s H.264; imported by path, read-only.

## Verdict

Flow completes on all three videos: path import, rights, Check, Short/4:5 stories, Edit colour/effects, 4:5 + 9:16 queues. Frozen 5% Check is fixed: progress now moves. But the founder's job still fails. Check has no honest duration and duplicates Import's read. Edit has no Back or Next. Finished videos have no cross-job library. Dub is a dead end: it offers translation, cannot set a language, and the render fails with `Dub needs a target language.` Not ready for weekly use.

Own-footage handling is right: path import reads in place, rights is mandatory, nothing uploads by default. Story quality is usable (A 2 stories, B/C 3) but A's second reads like an ad. Colour/effects are per story and do not carry to the next video, so weekly reuse stays manual.

## Timeline

| Time | Did | Expected | Happened |
|---|---|---|---|
| 14:51 | Import A by path, rights | Read in place → Check | Worked; Check page ~31 s |
| 14:52:04 | Run Check A once | Progress + estimate | 5% then moving; server 182.2 s under host load 18–40 |
| 14:52–14:53 | Stories Short/4:5 → Edit play, switch story, Vivid pop, Teal and orange, Add motion, Add effect | Founder pass | All worked; first frame ~4 s; no Back/Next |
| 14:53 | Finish Queue 4:5, 9:16, Queue all | 2 shapes | Worked; 4:5 ~22 s, 9:16 ~24 s; ETA inconsistent |
| 14:53:20 | Import C | Ready quickly | "Reading" 5→68%, ready 14:57:28 (**247 s**), no ETA |
| 14:59:44 | Check C | ~30 s | 45.1 s server; 5→46% then ready; no freeze |
| 15:00 | Stories 3, Edit, Finish queues | One pass | Worked; 5–35 s each; preflight 404 |
| 15:01:22 | Import B | Ready quickly | Ready 15:03:17 (**115.5 s**), stalled at "Reading 68%" |
| 15:03:22 | Check B, Edit, Finish, Change video | Library of work | Check 27.8 s; only sources listed, no renders |
| 15:04:50 | Edit A → Audio → Voice-over, Dub | Translation + script | No language or script controls; Dub render failed |

## Ranked issues

### P0 — Dub mode cannot render
**Evidence:** Audio → Mode → Dub promises a "translated voice", but the panel has only Mode, Music, Voice: no target language, no script (`shots/08-audio-dub.png`). A draft queued via API failed as `art_bebd4c75ce7266d031dca53d`: `Dub needs a target language.` **Root cause:** `audio.py:2811` raises when `audio_plan.translate.target` is empty; `audio.js:808` has no target field, though `edits.py:1007-1023` accepts `audio.translate`. **Fix:** target-language select plus script beside Mode; PATCH `audio.translate`; block Queue with a reason.

### P1 — Check is slow, unbounded, and repeats Import's read
**Evidence:** Server totals A 182.2 s, C 45.1 s, B 27.8 s (`source_report.timings`); founder measured 23.4/32.3/17.2 s. A ran at host load 40, so its absolute value is contaminated, but C/B were still 1.4–1.6×. Import took 247 s (C) and 115 s (B) with percent only. Import already reads text, speech, faces and crop (`import.js:177`); Check re-reads "Pulling frames to read text" (`routes_check.py:108`). **Fix:** reuse the import read or merge the passes; add an ETA from frames done/total. The freeze fix (`3da8ac3`) works.

### P1 — Edit has no Back or Next
**Evidence:** Edit header contains only Story select, 9:16/4:5, Repair, All stories, Undo trim, Undo (`shots/03-edit.png`; `edit/index.js:165-187`). The founder reached Finish only through the rail. **Fix:** footer with "Back to Stories" and "Next: Finish".

### P1 — No finished-video library
**Evidence:** "Your videos" lists only inputs (`source.mp4 1:29`, `source.mp4 1:52`, `source.mp4 0:53`), with story counts, no render status, thumbnail or download. Finished cuts exist only under each job's Finish → Versions (`finish.js:1116`). **Fix:** a "Finished" library fed by artifacts across jobs, with shape/version/date/download/share — the weekly-repeat blocker.

### P1 — Preflight still 404s for clip-set stories
**Evidence:** `GET /preflight?story_id=st_…` returned 404 on C and B (`responses2.json` 67.2, 267.2), as in the founder HAR. **Root cause:** `_select_story` resolves render keys, artifacts and saved stories, not clip-set story ids (`preflight.py:652`); Finish passes `story_id=<clip-set id>` (`finish.js:733`). UI now degrades to "Render this story first", but pre-publish checks remain impossible before a render. **Fix:** resolve `story_ref.set_id + story_id` in `_context`.

### P2 — Queue ETA contradicts itself
**Evidence:** In B the queue header said "39% · 24 s left" while its item said "18% · 11 s left" (`shots2/08-finish-B.png`). The founder HAR showed 21.8 → 30.6 → 11.5 → 0.0 at 33% → gone. Root: the queue row uses `queue.eta` (`finish.js:1065`), the item uses `item.eta` (`finish.js:287`), and stage steps reset the sample. **Fix:** one ETA source, hide across stage boundaries, "estimating" until 20%.

### P2 — Check screen is confusing while running
Rail says "Check · Optional · not run" while the page says "Checking…" at 5%; the message appears twice. Import stalls at "Reading frames · text + subject" 63% and "Reading 68%" for 30+ s with no explanation. **Fix:** one status line, real ETA, and a clear "you can keep working" note.

### P3 — Story defaults and names
Stories defaults to 3 but A fits 2 ("Only 2 non-overlapping stories fit; requested 3"); Edit and Render have equal weight. All inputs show as `source.mp4`; use original filenames and thumbnails.

## Feature asks

- **Greenlight now:** Dub target + script UI (P0); Back/Next in Edit; finished-render library; Check/Import single read + ETA; preflight story-id fix.
- **Defer:** batch multi-language exports, auto-translated captions, publishing integrations, AI hook rewrite.
- **Reject:** auto-Dub with cloud default, removing the rights gate, auto-queueing every shape on import (version spam).

## Explicit answers

**(a) Check speed/progress/ETA honesty.** The freeze is gone: C/B advanced 5→23→34→46→ready and A no longer sat at 5% forever. Honesty is still poor: no ETA, "a few minutes" copy for a 53 s clip, Import and Check read the same frames, and Import gives no estimate for 2–4 minute waits. Queue ETA is also dishonest (P2).

**(b) Confusing interface.** Rail state disagrees with the page; duplicate progress text; six Edit tabs with Audio last and voice below a full music card; Stories has two equal primary buttons; Finish mixes per-story Queue with Queue all and buries Versions.

**(c) No back/next in Edit.** Confirmed. Only the rail moves between steps; the Edit header has none (`edit/index.js:165-187`).

**(d) No finished-video library.** Confirmed. Change video = sources only. Renders live under each job's Finish → Versions; no page lists all completed videos or offers a global download.

**(e) Translation and voice generation.** They are in Edit → Audio (last tab): Voice-over and Dub modes, engine/voice/rate, Preview voice, music and mix. Missing: target language, translated captions, editable script, engine routing; voice-over re-speaks the source transcript only. Dub without a target fails (`audio.py:2811`). The working path remains Classic (`?classic=1`) → render panel language list and Setup routes; Studio shows status only.

**Repeat-use fit:** rights and local-first handling are right, but without a finished library, reusable looks, or working Dub, a creator cannot ship three videos a week without repeating every manual step.
