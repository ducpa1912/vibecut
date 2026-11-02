# QA round 1: consolidated fix list

**Build tested:** `01e0d2f`.

**Testers:** three agent personas, each on its own isolated server:

| Code | Persona | Port | Report |
|---|---|---|---|
| SF | Short-form repurposer | :8801 | `qa-report-shortform.md` |
| LF | Long-form creator (24-min video) | :8802 | `qa-report-longform.md` |
| PQ | Senior product QA | :8803 | `qa-report-product.md` |

The three raw reports are in the session scratchpad. This file keeps one ranked list with duplicates merged. Each tag shows which reports raised the item.

**Verdict, all three:** don't ship. No path produces one finished, captioned short.

## Batch 1: fix now

Ordered by priority. **Area** names the files involved.

| # | Sev | Area | Problem | Fix | Tags |
|---|---|---|---|---|---|
| 1 | P0 | `render.py:588` `_wrap_caption` | Any caption cue containing `\n` raises `ValueError: can't measure length of multiline text`. Both the exact-frame endpoint (500) and the final render fail. | Wrap each line on its own, or split on `\n` before `textlength`. Add tests with multiline cues for the frame endpoint and the render. | SF1, LF1 |
| 2 | P0 | `studio.css:68-72`, `:221-226` | The main pane can't scroll at desktop widths. The Edit timeline and the Finish publish kit, review link and Apply to all are all unreachable. | Add `grid-template-rows: minmax(0,1fr)` to `.st-shell`, and `min-height:0; overflow:hidden` to `.st-main-wrap` at every width. | PQ P0-1, SF25 |
| 3 | P0 | Studio Edit + story render | Renders come out with no burned-in captions by default (`captions:false`; only an SRT sidecar is written). | When a story Edit is created and the job has a transcript, build that story's caption track in the default style. Burn captions by default. | LF2 |
| 4 | P0 | `finish.js:1218-1256`, `api.js:40-58` | Build publish kit does nothing on the first click, then returns 400 `story_id_invalid`. Errors that come back as `{detail:{message}}` show as a generic "Request failed (400)". | Use the displayed artifact. Send `story_id`. In `errorDetail`, read `detail.message` / `detail.code`. | SF4 |
| 5 | P0/P1 | `finish.js:874-912`, `:524`, `:1179` | A single finished render has no player and no Download. A failed render shows only "Render failed." with no reason or Retry. The success banner shows even when some renders failed. | Add a player, Download and Reveal on every ready version, plus Download all. Show the real `error` text and a Retry button. Make the banner count failures. | SF8, SF9 |
| 6 | P1 | `edit/preview.js:276-301` | Proxy playback draws none of the edits: no text, graphics or captions. | Draw text and graphic layers, plus the active caption cue, on the canvas over the proxy frame. It is an approximation; the exact frame stays the source of truth. | SF5, LF3 |
| 7 | P1 | Finish "Apply to all" | Caption style is not applied to stories that have no caption track, but the message still says "Applied to N stories". | Build the caption track with the same style on those stories. Report what actually changed and what was skipped. | SF7, LF9 |
| 8 | P1 | `captions.py` cue chunking, SRT sidecar | The first word of a sentence is dropped. Words repeat at cue boundaries. The SRT includes speech from before the story starts, ends mid-word, and uses synthetic uniform timing. | Chunk from word timings inside the story clips only. Each word appears exactly once. | SF12, LF10, LF11 |
| 9 | P1 | `stt.py:238-254`, `:1343`, `:1494` | A silent 2 s clip takes about 5 min to read, because Whisper runs anyway. The Whisper child opens outbound HTTPS. The progress text keeps showing the previous stage. | Gate on loudness/VAD before STT: no speech gives an empty transcript. Set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` when the model is cached. Cap the timeout relative to clip length. Emit "Transcribing speech · <engine>" at the start. | PQ P1-1, P1-3, P2-3 |
| 10 | P1 | `app.py:92-100` analysis pool | One stuck job blocks every other import, and Studio has no cancel. | Add a **Cancel reading** control to the shell progress strip, wired to `ANALYSIS_CANCELS`. Add per-stage timeouts. | PQ P1-2 |
| 11 | P1 | Job open / Check / render | When the source file is moved or deleted, Check still reports "Checked" and Stories finds 0 with no reason. | Stat the source on job GET and before Check or render. Set `source_missing` + path. Lock the steps with "The original file was moved or deleted: <path>". | PQ P1-4 |
| 12 | P1 | `render.py:531`, `:570-578`, `overlays.py:388` | Emoji render as □. Font weight and stroke are ignored. | Use a font stack with weights (SF Pro / Helvetica Neue / Inter if bundled) and an Apple Color Emoji fallback for emoji runs. Honour `style.weight` and stroke. | PQ P1-5, SF14 |
| 13 | P1 | `clipset.py`, `stories.js` | The count is capped at 3–6. There is no length preset (story length is fixed at 20–75 s). Picks include CTA, giveaway and housekeeping segments. Picks end mid-list or start on a dangling "And…". Picks cluster in one part of the video. | Allow up to 12. Add length presets (Short 15–30 s / Medium 30–60 s / Long 45–90 s). Penalise CTA, sponsor and giveaway language. Prefer a closing sentence as the end. Penalise starts on conjunctions. Spread picks across the video. | SF10, LF4-7 |
| 14 | P1 | `stories.js`, `edit/timeline.js` | A story's start and end can't be adjusted. | Add "± sentence" controls for the start and end on story cards, using the existing clip-set `stories` PATCH. Show the duration. | LF8 |
| 15 | P1 | `detect.py` classification, Check `fps` | Mid-frame word-pop captions on video A are classified as `screen_text`, so they can never be cleaned. Short caption words are missed at 0.5 fps. OCR returns junk regions. | Treat short (1–4 word), large-font, centred text that changes every 0.3–1.5 s as `subtitle` even over a screen recording. Sample at 1 fps or more in the caption band. Raise the OCR confidence floor and drop non-word junk. | SF3 (detection part), SF16, LF17 |
| 16 | P1 | `routes_check.py` | Check sits at 5% for about 4.5 min, then jumps. | Report progress per sampled frame. | LF12, PQ P2-3 |
| 17 | P2 | Preflight | It lists source text from outside the story window, all stamped 0:00. A 404 shows as "Checks could not run". | Filter to the story window, use story-relative times, and give a clear "render first" state. | SF15, PQ P2-8, LF19 |
| 18 | P2 | Story queue | Progress sits at 50% with no per-item progress or ETA. | Add per-item progress and an ETA. Also find out why a Final render of a 26 s story from 1440p AV1 takes 2 min 50 s (decode path?). | SF11 |
| 19 | P2 | `edit/index.js:465`, `:890` | An edit typed less than 450 ms before a reload is lost. Every keystroke creates a new version. | Flush saves on `pagehide`/`visibilitychange`. Coalesce versions made within a few seconds. | SF21, SF22 |
| 20 | P2 | Text → Hook card | The hook starts at the playhead with the placeholder "Your hook". | Start at 0 and use the story's hook sentence as the default text. Make the default hook style bold. | PQ P2-5, LF13 |
| 21 | P2 | `shell.js` watcher + panels | Too many requests: 167 to 472 in one session. | When idle, poll status only. Cache the clip-set and Check reads per job, and invalidate them on writes. | PQ P3-10, LF21 |
| 22 | P2 | Voices | Apple novelty voices (Zarvox, Bells, …) are listed. | Filter them out and list natural voices first. | SF20 |
| 23 | P2 | Copy / errors | Raw ffprobe errors are shown to the user. Speech-unknown wording is wrong for silent or no-audio videos. Plurals are wrong ("1 moments"). A folder path gives "File not found". | Plain-language copy for each case. | PQ P2-2, P2-4, P3-3, P3-11 |
| 24 | P3 | Boot route, import list | A reload always lands on Import. Recent videos don't auto-refresh. Import can be clicked twice while a video is reading. | Resume at the best step. Auto-refresh the list. Disable Import while a video is reading. | PQ P3-8, P3-9, LF16, LF22 |
| 25 | P2 | Rights record | The Studio attestation lives only in localStorage. The import API takes no rights field. | Accept `rights` in the import bodies and persist it to `job["rights"]` with source `import`. Prefill Check from it. Policy is unchanged; see the founder decisions below. | PQ P2-1, SF2 |

## Founder decisions needed (not fixed in batch 1)

- **Import gate for reused content.**
  - The Studio Import button needs "I own this footage". For a repurposer that blocks step 1, while the API imports without it.
  - Options:
    - (a) keep the gate at Import;
    - (b) let anyone import and lock only Clean.
  - Clean stays locked without attestation either way, and watermarks are always refused.
- **Feature asks, later batch:**
  - karaoke / word-highlight caption styles;
  - dub target-language picker with editable translated lines;
  - built-in royalty-free music beds;
  - hook card templates;
  - topic-aware publish-kit titles and hashtags.
