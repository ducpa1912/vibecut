# QA round 1: Batch 1 fixes

**Source list:** `docs/shared/testing/qa-round1.md` (#1–#25). Raw evidence is in `docs/shared/testing/qa-round1-raw/`.

**Branch:** `worktree-agent-a579715a585103098`, based on `main` at `2782654`.

**Suite at the end:** `/opt/homebrew/bin/python3.11 -m pytest -q -p no:cacheprovider` gives 1331 passed, 7 skipped. The baseline was 1244 passed, 7 skipped. Every changed `.js` file passes `node --check`.

**New test files:**
- `tests/test_studio_js.py` imports the no-build Studio modules under Node and tests their pure helpers. It is skipped when Node is not installed.
- `tests/conftest.py` gained an autouse `sources_present` fixture. Most tests use placeholder source paths, and the fixture treats those paths as present. The tests for #11 restore the real file check.

**Live smoke test:** run on a scratch server (`VIBECUT_DATA=/private/tmp/vibecut-qa1-data`, port 8811, stopped afterwards) with a synthetic 30 s clip. Confirmed:
- #2: the main pane scrolls.
- #24: `?studio=1` is dropped from the URL, a reload resumes on Check, Recent videos refreshes on its own, and Import is disabled while a video is reading.
- #10: Cancel reading appears in the top strip.
- #25: the rights record is stored with `source: import`.
- #11: a moved file shows "Original file missing" and Check returns 409 with the file's path.
- #23: a folder path returns the folder message.

No server errors were logged.

## Per item

| # | Status | Root cause (one line) | Commit | Tests added |
|---|---|---|---|---|
| 1 | Fixed | `_wrap_caption` called PIL `textlength()` on cue text that contains `\n`, which PIL refuses for multiline text. | `eaeb781` | `test_render_layers.py`: wrap keeps line breaks; word then character wrap; a two-row layer raster; a real-ffmpeg frame endpoint plus final render with a two-line cue. |
| 2 | Fixed | `.st-shell` grid had no bounded row, and `.st-main-wrap` had `min-height:0` only under 900 px, so `.st-main` never scrolled. | `719c10b` | `test_studio_layout.py` (CSS rule checks), plus the live check. |
| 3 | Fixed | A story Edit starts with captions `enabled` but no track, and a missing track renders as captions off. | `a6a1b02` | `test_story_edit_render.py`: a new Edit gets the default track when the job has speech; no speech gives no track; `enabled:false` is respected; a render upgrades an older Edit that has no track. |
| 4 | Fixed | Build used `packetArtifact()` without the displayed `ready[0]` fallback and sent no `story_id`. `errorDetail` ignored `{detail:{message}}`. | `7704184` | `test_packet_v2.py` (the route takes `story_id` from the artifact); `test_studio_js.py` (`errorDetail`). |
| 5 | Fixed | The `<video>` existed only in the 2+ compare view, failed rows showed only the status, and the banner always reported success. | `814680b` | `test_artifacts.py` (new `POST …/artifacts/{id}/reveal`); `test_studio_js.py` (banner counts, failure reason, download name). |
| 6 | Fixed (approximation) | Preview `draw()` painted only the proxy, filter, safe zones and selection. | `a12389b` | `test_studio_js.py`: active text, fx and caption cue; rect math matches the server; wrap keeps breaks. Stickers are not drawn live. |
| 7 | Fixed | Apply to all copied caption style only onto stories that already had a track, and always said "Applied to N". | `3603526` | `test_studio_js.py` (`applySummary` reports what changed and what was skipped). |
| 8 | Fixed | Sentences inside a Whisper segment were timed by character share, so cuts landed mid-word. Words were captioned in every clip they overlapped. The SRT sidecar spread whole-scene text over each clip. | `bdf8e10` | `test_caption_words.py` (9 tests: word-edge sentence bounds, one word per clip, first word kept, no guessed text, sidecar from cut words, legacy sets keep their fingerprint). |
| 9 | Fixed | No speech gate, a 300 s route timeout on a 2 s clip, the Hugging Face hub was not offline, and no progress was emitted when STT started. | `4a35ca6` | `test_stt.py`: loudness gate; a silent file skips every engine; "Transcribing speech" comes first; offline environment only when the model is cached; relative timeout. |
| 10 | Fixed | `ANALYSIS_CANCELS` had no route or control, and Whisper could not be interrupted. | `aab0c42` | `test_reading_cancel.py` (8 tests: queued and running cancel, retry, moved source, a cancelled engine reads as cancelled, the child process is killed). `test_studio_js.py` (`readingAction`). |
| 11 | Fixed | The source path was never checked with `stat`. Only app-initiated deletes were flagged. | `0350ad3` | `test_source_missing.py` (status, job and library flags; Check, clip sets and `_queue_render` refuse with 409). |
| 12 | Fixed | One regular-weight Arial Unicode font with no colour glyphs. `style.weight` was never read, and the caption stroke width and font were dropped in compile. | `0fd6849` | `test_text_fonts.py` (weight changes ink, colour emoji, script runs, stroke width, caption style compile, outline drawn); `test_studio_js.py`. |
| 13 | Partial | The count was capped at 3–6 with a fixed 20–75 s window, and scoring had no housekeeping or opener penalty. | `9c470b9` | `test_story_picks.py` (12 stories, presets bound durations, 15–90 s bounds, CTA and opener penalty, a giveaway story loses). `test_studio_js.py` (presets mirror the server). |
| 14 | Fixed (story cards) | The backend accepted sentence patches, but no control used them. | `281e8d3` | `test_story_picks.py` (the PATCH extends by one sentence); `test_studio_js.py` (`adjustSentences`). |
| 15 | Fixed | No word-pop rule: short, large, centred words fell into the screen-text rules. Check sampled at 0.5 fps. Low-confidence OCR junk was kept. | `7d127fe` | `test_detect_wordpop.py` (word pop over a screen recording, UI text unchanged, junk filter, merge skips junk); `test_studio_js.py` (`checkFps`). |
| 16 | Fixed | The Vision helper read every frame in one call, with progress reported only before and after. | `5f17f66` | `test_check_progress.py` (frame N / M in batches of 24; progress mapped into Check's band). |
| 17 | Fixed | Uncovered text outside the cut fell back to window (0, duration). A 404 was shown as "could not run". | `8cc2a02` | `test_preflight_window.py`; `test_studio_js.py` (`checksFailedNote`). |
| 18 | Partial | Queue progress counted only finished items. | `c33e966` | `test_queue_progress.py` (running item progress and ETA, queue ETA); `test_studio_js.py`. |
| 19 | Fixed | A 450 ms debounce with no unload flush, and each PATCH created a version. | `45fe4db` | `test_edits.py` (autosaves fold; the first version and an old head never fold); `test_studio_js.py` (`editChain`). |
| 20 | Fixed | Every text kind started at the playhead with a placeholder and thin default style. | `de9a280` | `test_studio_js.py` (hook at 0 with the story hook, bold; the server accepts the style). |
| 21 | Partial | The shell watcher fetched status, check and clip-sets on every tick and every step change. | `036e13b` | `test_studio_js.py` (`canReuseSteps`). |
| 22 | Fixed | `say -v ?` was listed raw and sorted by language only. | `269923f` | `test_tts.py` (novelty voices hidden, natural voices first). |
| 23 | Fixed | Raw ffprobe stderr was re-raised, the speech warning had one branch, plurals were hard-coded, and a folder path got "not found". | `f2ef607` | `test_plain_errors.py` (folder, unreadable file, no_audio / no_speech / unknown). |
| 24 | Fixed | Boot defaulted to `import`, the recent list loaded once, and Import re-enabled while reading. | `5226b03` | `test_studio_js.py` (`bestStepFor`, `isReadingStatus`), plus the live check. |
| 25 | Fixed | The attestation lived only in localStorage, and the import routes had no rights field. | `e9ada93` | `test_import_rights.py` (path with rights, without rights, explicit false, upload form field). |

## What remains

- **#6:** stickers are not drawn in live playback. Fonts are approximated in the browser, and the exact frame stays the source of truth.
- **#13:**
  - Not done: preferring a closing sentence when a list continues ("It could be…" after the pick's end).
  - Not done: explicit spreading of picks across the whole video, beyond the existing proximity term.
- **#14:** the Edit timeline has no trim controls; the controls are on story cards only. Changing a story's range starts a fresh Edit, because the clip hash changes.
- **#18:** the slow Final render of 1440p AV1 (2 min 50 s for 26 s) was not investigated. The decode path is the suspect.
- **#21:** there is no shared per-job cache for panel reads (Finish and Stories still fetch clip-sets themselves). Only the idle shell watcher was slimmed.
- **#12:**
  - CJK runs use Arial Unicode or Hiragino at regular weight. SF does not cover CJK.
  - ZWJ emoji sequences and flags draw as their component emoji, because PIL is built without raqm.
- **#9:**
  - The loudness gate skips only true silence or near-silence (below −45 dBFS). Music-only audio still runs STT, within the new relative timeout.
  - Per-stage timeouts other than Whisper's are unchanged.
- **#15:** the 1 fps sample rate applies to sources of 10 minutes or less. Longer sources stay at 0.5 fps, so Check time does not double.
- **#8:** older clip sets keep character-share sentence timing until stories are found again. They are marked by the absence of `sentence_timing: "words"`.
- **Cache keys:** master and layer cache keys changed (`layers-v2`, `text_skin`). The first render of each story after upgrading re-encodes once.
- **Founder decisions:** the Import gate for reused content and the later feature asks are unchanged.

## Founder retest

The rights note on Import is required, as before. Use your own footage with speech for the caption items.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | Edit → Captions → Build captions (Bold). Pick a cue with two lines in the cue list, pause on it, then Finish → Queue 9:16. | Multiline captions no longer crash. | The preview badge says "Exact frame" and shows both lines. The render finishes, and the two-line caption is burned in. | |
| 2 | Open Check, Edit and Finish in a normal laptop window (about 1280×800) and scroll with the mouse wheel. | The main pane scrolls. | The content scrolls while the rail and top bar stay fixed. Finish's Publish kit, Review link and Apply to all can be reached. | |
| 3 | Find stories on a video with speech, then Finish → Queue all stories · 9:16 without opening Edit. | Captions are on by default. | Every finished short has captions burned in, in the default style. | |
| 4 | Finish → Publish kit: leave the shown cut and press Build publish kit once. | The kit builds on the first click. | "Publish kit ready…" appears with a Download link. Any error shows a real sentence, never "Request failed (400)". | |
| 5 | Finish → Versions on a story with one finished render; then a story whose render failed. | Play, download, see why it failed, retry. | One cut shows a player. Each version has Download and Show in Finder, and Versions has Download all. A failed row shows the reason and Retry. The banner says "N of M … failed" when something failed. | |
| 6 | Edit → add a Hook card and build captions, then press ▶. | See edits while playing. | The hook text and the current caption line are drawn over the 540p playback. | |
| 7 | Finish → Apply to all stories: tick Caption style, copy from a story with captions. | Style reaches every story. | Stories without captions get them built in the same style. The notice lists what changed and what was skipped, with reasons. | |
| 8 | Edit → Captions on a story that starts mid-segment; read the cue list. Then open the SRT in a Finish version. | Each word appears exactly once. | The first word of each sentence is present, and no word repeats across cue boundaries. The SRT holds only the cut's speech, at the cut's times. Find stories again first on older videos. | |
| 9 | Import a short clip with no sound (Speech ticked). | Silence does not stall the queue. | The read finishes in seconds. Check says "No speech found." The top bar says "Transcribing speech · …" while STT runs on a normal video. | |
| 10 | While a video is reading, press Cancel reading in the top bar; then press Read again. | Free the analysis slot. | The status reads "Reading stopped. Other videos can read now." and the next import starts. Read again restarts the read. | |
| 11 | Move a video's file in Finder, then open that video in Studio. | A missing file is named. | The top bar says "Original file missing". Check, Stories, Edit and Finish are locked with the file's path. Running Check shows the same message. | |
| 12 | Edit → Text → Hook card: type `STOP paying 🛑`, set Weight 400 then 900 and an Outline colour, and look at the exact frame. | Weight, outline and emoji render. | The emoji is in colour, not a box. 900 is visibly heavier than 400, and the outline is visible. | |
| 13 | Stories → How many 12 with Length Short on a long video. | More and shorter picks. | Up to 12 stories of 15–30 s. Giveaway, CTA and "subscribe" segments rank lower, and fewer picks open on "And…". | |
| 14 | Stories → on a card press + end, then − start. | Adjust a story by one sentence. | The range and length update on the card, with a status line giving the new range. | |
| 15 | Check on a short video with word-pop captions mid-frame. | Old word-pop captions can be cleaned. | They are listed as Burned-in subtitles, not Screen interface, and there is much less OCR junk. | |
| 16 | Run Check on a long video and watch the progress. | Visible progress. | "Reading text · frame N / M" climbs steadily. | |
| 17 | Finish on a story with no render yet; then on a rendered story. | Clear preflight states. | Without a render: "Render this story first; checks run on the render." With one: only text inside the story, at story times. | |
| 18 | Finish → Queue all stories and watch the queue card. | Live progress. | The running item shows "42% · about 1 min left", and the queue shows the time left. | |
| 19 | Edit → type a hook quickly and press Cmd+R within half a second. Then open Finish → Edit history. | Edits survive a reload, and history is not noise. | The typed text is still there after the reload. A burst of typing is one version, not one per keystroke. | |
| 20 | Edit → scrub to the middle → Text → Hook card → Add text. | Hook defaults. | The card runs 0–3 s, reads the story's hook line, and is bold on a dark plate. | |
| 21 | Sit idle on Edit for 2 minutes with the Network tab open. | Less chatter. | Only `/status` is polled, about every 15 s. | |
| 22 | Edit → Audio → Voice → Apple voices. | Usable voices only. | No Zarvox, Bells, Bad News and so on. Natural voices are listed first. | |
| 23 | Import → Path: paste a folder path; then a text file renamed `.mp4`. | Plain errors. | "That path is a folder; choose a video file." and "This file isn't a readable video…". | |
| 24 | With a video open, reload `http://localhost:…/` (no `#/…`); watch Recent videos while a video reads. | Resume and live list. | Studio opens on the step where work stopped. Recent videos update without pressing Refresh, and Import is disabled while a video reads. | |
| 25 | Import with the rights box ticked, then open Check. | The rights note is stored on the server. | Check already shows the rights note as recorded. Clean is unlocked for your own footage, and watermarks are still refused. | |
