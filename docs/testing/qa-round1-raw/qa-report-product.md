# VibeCut Studio — product QA report (build `01e0d2f`, Studio fix `f40de21`)

**Test suite:** `/opt/homebrew/bin/python3.11 -m pytest -q -p no:cacheprovider` → **1244 passed, 7 skipped, 5 warnings in 63.90s, exit 0.**

**Environment:** isolated server `http://localhost:8803` (scratch data dir), built-in browser tab-5. Viewports tested: pane default 1062×880, 1280×800, 1024×768, 1280×1300.
**Media:** Alice intro (11 s, 1080p), JOYLO (53 s, vertical, baked text), `qa-edge/two_sec_silent.mp4` (2 s testsrc, silent AAC), `qa-edge/no_audio.mp4` (8 s, no audio track), `qa-edge/fake.mp4` (text file).

**Rights gate:** I did not tick the rights box and did not POST `/rights`. The Studio Import button stays disabled until the box is ticked, so I created test jobs with `POST /api/jobs/path`. That route has no rights field, and that gap is itself finding P2-1.

---

## P0 — blocker

| # | Area | Steps to reproduce | Actual | Expected | Root cause | Suggested fix |
|---|---|---|---|---|---|---|
| P0-1 | Layout, every screen | 1. Open any screen taller than the window, e.g. Check, Edit or Finish, at 1280×800 or 1062×880. 2. Scroll the mouse wheel over the content. | Nothing scrolls. `#st-main` reports `scrollTop 0`, `scrollHeight == clientHeight`, measured as follows. **Check:** 1124 px of content in an 800 px window. **Edit:** 1215 px; at 1280×800 the ▶ button sits at y=793 and the **Timeline** at y=887, both off screen. **Finish:** 3265 px, so Publish kit, Review link and Apply to all are off screen even at 1280×1300. **Import:** the 3rd "Recent videos" row is cut off. Focusing an input scrolls `#studio-root` (`overflow:hidden`) by 24 px, which clips the top bar, and the user cannot scroll it back. | The main pane scrolls, and the rail and top bar stay fixed. | `static/studio/studio.css:68-72`: `.st-shell` is a grid with `height:100dvh` but no `grid-template-rows`, so the implicit row grows to fit the content. `.st-main-wrap` (`studio.css:221-226`) lacks `min-height:0`, which is only set inside the `@media (max-width:900px)` block at `studio.css:896`. As a result `.st-main` (`overflow-y:auto`) never gets a bounded height. This predates `f40de21`. | Add `grid-template-rows: minmax(0,1fr)` to `.st-shell` and `min-height:0; overflow:hidden` to `.st-main-wrap` at all widths. Add a layout test that checks `#st-main.scrollHeight > clientHeight` on Finish. |

## P1 — major

| # | Area | Steps to reproduce | Actual | Expected | Root cause | Suggested fix |
|---|---|---|---|---|---|---|
| P1-1 | Import / reading, edge: no speech | Import `two_sec_silent.mp4` with Speech ticked (the default). | The job stays at `reading 0.68 "Tracking crop · 2 / 2"` for about 5 min. Server log: `job 61b43666a644 ready in 301.7s` (Alice, 11 s of speech: `ready in 4.6s`). During that time an `mlx_whisper … whisper-large-v3-turbo` child sat at about 0.6% CPU. | A silent 2 s clip reads in seconds. Silence is detected first, or STT is skipped when there is no speech energy. | STT falls through to `mlx_whisper` for silent audio. The timeout is generous (`stt.py:1343` uses `timeout or 1800`; see also `stt.py:980`, `stt.py:1049`). There is no silence/VAD short-circuit before the Whisper route. | Run a VAD or loudness gate before STT and return an empty transcript when there is no speech. Cap the Whisper timeout relative to clip length. |
| P1-2 | Queue | While P1-1 is stuck, import `no_audio.mp4` and the 53 s JOYLO video. | Both stay `queued 0.0 "Queued"` for the whole 5 min. One stuck job blocks every other import. | Other videos keep reading, or the user can cancel the stuck one. | `app.py:92-94`: `analysis_pool = job_queue.Scheduler("analysis", max_workers=1, …)`. Studio has no cancel for a local read: `ANALYSIS_CANCELS` (`app.py:100`) exists, but no Studio control uses it. | Add a **Cancel reading** button in the top-bar progress strip that sets the cancel event. Add per-stage timeouts so one job cannot hold the single slot indefinitely. |
| P1-3 | Local-first promise | During P1-1, run `lsof -p <mlx_whisper pid>`. | `TCP …:64447->[2600:9000:281d:a000:17:b174:6d00:93a1]:https (ESTABLISHED)`. The Whisper child holds an outbound HTTPS connection even though the model is already cached (`~/.cache/huggingface/hub/models--mlx-community--whisper-large-v3-turbo`). The destination is a CloudFront IP, probably the Hugging Face hub (unverified). | No network traffic for local analysis. Import copy says "The video stays on this machine." | `stt.py:238-254` launches `mlx_whisper` without `HF_HUB_OFFLINE=1` or `TRANSFORMERS_OFFLINE=1` in its environment. | Set `HF_HUB_OFFLINE=1` in the child environment once the model is present, and download only from the Setup/packs flow. A hung hub lookup is a plausible cause of P1-1 (unverified). |
| P1-4 | Missing source file | Import `no_audio.mp4` by path. Move the file away. Open the video in Studio and run Check (`POST /api/jobs/7bb71bfb1460/check` → 202). | Check finishes `status: ready`, and the rail shows **"Checked"** in green. The error is only a buried warning: `Text sampling failed: command failed: ffmpeg\n[in#0 @ 0xa99404000] Error opening input: No such file or directory…`. `/api/jobs` still says `source_deleted: false`. Find stories returns 0 stories with no reason. | Studio detects the missing source when the video is opened. It shows "The original file was moved or deleted: <path>. Locate it…" and blocks Check, Stories and render with that reason. | There is no source-existence check on job open or before Check. The `source_deleted` flag only covers app-initiated deletes. | On `GET /api/jobs/{id}` and before Check or render, `stat` the source and set `source_missing`. Lock rail steps with a relink action. |
| P1-5 | Edit text, final render | In Edit, go to Text → Hook card → type `QA hook test 🎬 ünïcode` → render 9:16 Final. | The exact frame (`/edits/…/frame?quality=final`) and the final `reel.mp4` both draw the emoji as a **□ tofu box**. The inspector shows Weight **800**, but the render is regular weight. The black outline is not visible. | Emoji render, or the field warns that they are not supported. Weight and outline are applied. | `render.py:531` maps `"sans"` to `Arial Unicode.ttf`, which has one weight and no colour-emoji glyphs. `style.weight` is validated in `overlays.py:388-395`, but no renderer code reads it (grep of `*.py` finds no other use). | Use a font stack with weights (SF Pro, Inter) plus Apple Color Emoji fallback, or strip emoji with an inline warning. Pass the weight through to drawtext/compose. |

## P2 — minor

| # | Area | Steps to reproduce | Actual | Expected | Root cause | Suggested fix |
|---|---|---|---|---|---|---|
| P2-1 | Rights / trust | Compare Studio Import, Classic `/?classic=1` and the API. | The Studio rights box is client-only. `import.js:10-11` says "The server has no import attestation field yet". `POST /api/jobs/path` and `/from-url` accept imports with no attestation, and Classic "Dissect video" has no rights box at all. There are also two separate rights boxes: Import (localStorage) and Check ("Sent with the next Check run"). | One rights record per video, stored on the server at import, and enforced the same way in Studio, Classic and the API. | `static/studio/import.js:10-31` (`ATTEST_PREFIX` in localStorage); `app.py:4588` `job_from_path` has no rights field. | Add `rights` to the import bodies and persist it to the job. Prefill Check from it. Add the gate to Classic. |
| P2-2 | Import errors | Path import of `qa-edge/fake.mp4` (not a video). | HTTP 400 `{"detail":"command failed: ffprobe\n[mov,mp4,m4a,3gp,3g2,mj2 @ 0xb85028000] moov atom not found\n…/fake.mp4: Invalid data found when processing input\n"}`. Studio shows `error.message` as-is. | "This file isn't a readable video. Try exporting it again as MP4 (H.264)." | `app.py:4593-4596` re-raises `pipeline.PipelineError` text verbatim. | Map probe failures to plain copy and log the raw stderr. |
| P2-3 | Progress copy | Import `two_sec_silent.mp4` and watch the top bar. | It shows "Reading the video · 68% · Tracking crop · 2 / 2" for 5 min while transcription is actually running. | "Transcribing speech…" during STT. | `stt.py:1494-1498` reports progress only after a chunk finishes. Nothing is emitted when STT starts, so the previous stage's message remains. | Emit `progress(0.70, "Transcribing speech · <engine>")` before the first chunk. |
| P2-4 | Check copy, edge: silent / no-audio | Run Check on `two_sec_silent` (STT ran for 5 min) or `no_audio.mp4` (no audio track). | `Speech coverage is unknown because transcription did not run. Captions and music decisions need it.` | For no-audio: "This video has no sound track." For STT that ran: "No speech found." | The `speech_unknown` warning is emitted whenever no transcript exists. | Branch on `source.has_audio` and on transcript attempted vs. not run. |
| P2-5 | Hook card placement | Edit → scrub to 0:14.5 → Text → Hook card → Add text. | The Hook card is created at **14.5–17.5 s** at the playhead. | A *hook* defaults to the story start (0–3 s). The playhead default suits titles and lower thirds. | Text add uses the current playhead for every kind (`static/studio/edit/layers/text.js`; exact line unverified). | Default `start = 0` for `kind: hook`. |
| P2-6 | Safe zones (retest #7) | Edit → Safe zones on (the default) at 1280-wide. | The dashed "Text safe area" outline shows. The shading over app-covered areas is barely visible (`rgba(5,5,6,0.46)` over dark footage). The "App buttons" region on the right is not visibly shaded. Labels are drawn at 42 px and 30 px on the 1080×1920 canvas, about 7 px and 5 px on screen, so they are unreadable. The "Text safe area" label overlaps the default Hook card. | Shaded areas are clearly visible and labels are readable at preview size. | `static/studio/edit/preview.js:190-224`. | Use a lighter or hatched tint, scale label size to the displayed canvas, and move labels outside text boxes. |
| P2-7 | Finish context | Edit story 02 → open Finish. | Finish selects story **01**. "Versions" and "Before you publish" describe 01 ("No render…", "Checks could not run for this story.") until the user clicks row 02. | Finish opens on the story just edited. | The selection is not carried from Edit (`finish.js`, exact line unverified). | Share the current story id through the shell context. |
| P2-8 | Preflight empty state | Finish → story not rendered yet. | `GET /preflight?story_id=st_0000000_0020880` → 404, shown as "Checks could not run for this story." | "Render this story first; checks run on the render." | A 404 is treated as a generic failure. | Special-case "no artifact" in `finish.js`. |

## P3 — polish

| # | Area | Steps to reproduce | Actual | Expected | Root cause | Suggested fix |
|---|---|---|---|---|---|---|
| P3-1 | Plain language (§10) | Finish → Versions. | Chip shows `v1 · Edit v3 · current`, and rows say "Version 1 · Edit Version 3". The Captions panel shows "style clean · version 1". | §10: no "v1/v2" in the primary UI. | Finish/version labels. | "Render 1 · from your 3rd edit". |
| P3-2 | Version counts | Render story 02 without a Captions layer. | The version row says "30 captions", but the artifact has `captions: false` (SRT sidecar only). | "Captions file (30 lines) · not burned in". | `caption_count` is read from the sidecar. | Clarify the label. |
| P3-3 | Grammar | Import any video, or open Edit history. | "1 moments · hook found"; "Oct 27 · 1 graphics". | Singular forms. | Pluralisation in job messages and Edit history. | Add a plural helper. |
| P3-4 | Stories, short source | Alice (11 s) → Find stories. | "Found 0 stories." in success green, plus "Try fewer stories or a source with more speech." The real reason is shown elsewhere: "Source is 11.0s; a story needs at least 20s." | One neutral message with the real reason, and the button disabled when the source is under 20 s. | `stories.js` result tone and copy. | Use the duration reason as the empty-state body. |
| P3-5 | Captions copy | Edit → Captions (empty). | "If the video has no transcript yet, build captions after Check finishes." | The transcript comes from Import (Speech), not Check. | Captions empty-state copy. | "…after the video finishes reading with Speech on." |
| P3-6 | Check screen | Open Check before it has run. | Two "Run Check" buttons (header and empty card). While running: "Sampling text every two seconds" appears twice. On the first run the rail said "Optional · not run" for about 2 s after starting. | One primary CTA, one status line, and the rail shows "Checking…" immediately. | `check.js`. | De-duplicate. |
| P3-7 | Check warnings | Video with no baked text, no rights. | "Clean is locked" plus "Own-footage attestation missing…" are shown even though "No old text needs cleaning". The Edit → Clean panel lists "Burned-in text crosses the middle…" twice. "Attestation" is jargon. | Hide the rights warning when there is nothing to clean, de-duplicate warnings, and use plain words ("You haven't confirmed you own this footage"). | `routes_check` warnings and `check.js`. | Filter and de-duplicate. |
| P3-8 | Import screen | Import via API or another tab, or while a video is reading. | "Recent videos" stays on "No videos yet" until Refresh is pressed. While reading, Import shows an empty form with no "reading <name>" panel. | Auto-refresh, plus a reading card with progress. | `import.js:386-460` loads once. | Subscribe to the shell job watcher. |
| P3-9 | Reload route | Reload `/` or `/?studio=1` with a video open. | Lands on **Import**, not the step where work stopped (the library pop-out does route correctly). `?studio=1` stays in the URL afterwards. | Resume at the job's step and drop the query. | `shell.js:629-631` defaults to `import`. | Reuse the library's "where you stopped" logic on boot. |
| P3-10 | Network chatter | Switch steps a few times. | 167 requests to `/api/jobs/7063d3690e17*`. `clip-sets` is fetched 3–5× per navigation, and `status`/`check` are duplicated. | One fetch per screen open. | Each panel plus the shell watcher fetch independently. | Cache per job in the shell context. |
| P3-11 | Misc | Any page. | `GET /favicon.ico` → 404 in every session. Error-dir path message: a directory path gives "File not found on this machine." | Favicon present; "That path is a folder; choose a video file." | `app.py:4591`. | Add a favicon and branch on `is_dir()`. |

---

## Verified as working (retest checklist `docs/testing/studio-fix-retest.md`)

- **#1 Video library pop-out:** thumbnail, length, date, status, search with a debounce, "No video matches that name.", **Import a new video** and Close all work. Esc first clears the search field (native `type=search` behaviour), and the second Esc closes the pop-out. Story count was not shown for jobs with 0 stories.
- **#2 Reopen where you stopped:** a ready video with stories opens on Stories or Edit; a video without a check opens on Check.
- **#3 Rail status:** "Video ready", "Checked" / "Optional · not run", "2 stories", "Needs stories" all show.
- **#4–#6 Edit preview:** shows a real frame, not black. ▶ gives "Fast preview" and "Playing a 540p copy with sound. Pause to see the exact frame." Pause plus scrub gives "Exact frame". Sound is not muted in code; actual audibility is **unverified**.
- **#8–#10 Reading progress:** the top bar shows "Reading the video · 68%"; the rail shows "Reading 68%" and "Waits for reading". Clicking Stories gives "Wait for the video to finish reading (68%)." The screen moved to Check on its own when reading finished.
- **#11 Locked Edit:** "Pick stories first. Open Stories and press Find stories." A deep link to `#/edit` shows a proper empty state.
- **#12 Edit this story:** opens the exact story (02).
- **#13 Switching steps:** no endless Loading. Back and forward through `#/edit → #/stories → #/finish` restore the right screen.
- **Double-clicks:** Run Check, Find stories and Queue 9:16 each sent a single POST (one queue, `sq_541cd2519234`).
- **Persistence:** the hook text and story selection survive a reload, and the header shows "Saved".
- **Render:** a 9:16 Final of story 02 finished: 25.63 s, 1080×1920 H.264 + AAC, mean −17.2 dB.
- **Bad URLs:** each gives a clear 400: `notaurl` / `ftp://` / `file:///etc/passwd` / `javascript:` → "URL must start with http:// or https://."; `http://` → "URL must include a host."; `http://127.0.0.1:1/x.mp4` → "URL ingest only accepts public internet links. Use a local path instead."
- **Missing path:** 404 "File not found on this machine."
- **Locked Clean:** the Edit → Clean panel shows "Check found no rights note. Clean is locked…" with **Record rights in Check**.
- **Width:** no horizontal overflow at 1024 or 1280 wide.
- **Keyboard:** focus rings are visible and the skip link is present. Classic DOM under Studio is `inert` (`shell.js:612-615`).
- **Server log:** no 5xx and no tracebacks during the session.

**Unverified:** actual audible sound in the preview; Audio, Music and Voice panels (cloud and keys were not exercised); 4:5 render; publish-kit build and review-link creation (off-screen per P0-1 and not exercised); caption timing ±80 ms.

---

## Release readiness: **Don't ship** (ship once the must-fix list is done)

Must fix before launch:
1. **P0-1:** the main pane cannot scroll on desktop widths. Finish's publish kit, review link and Apply to all, the Edit timeline, and the bottom of Check are unreachable with a mouse on a normal laptop window. The fix is a small CSS change, but nothing else on Finish can be used until it lands.
2. **P1-1 / P1-2:** a silent or short clip holds the single analysis slot for about 5 min and blocks every other import, and there is no cancel.
3. **P1-3:** the Whisper child opens an outbound HTTPS connection during "local" analysis. Set the hub offline.
4. **P1-4:** a missing source file reports "Checked" instead of a clear relink error.
5. **P1-5:** emoji render as □ and font weight is ignored in final renders. Creators will notice on the first hook.

Should fix in the Wave 5 bug bash: P2-1 (server-side rights record, and the Classic gate) and P2-2 through P2-8.
