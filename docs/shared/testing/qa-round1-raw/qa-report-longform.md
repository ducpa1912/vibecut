# VibeCut QA: long-form creator persona (24-min talking video)

Server :8802 (isolated data dir `.../scratchpad/qa2-data`), browser tab-4. Source: `What I Learned About AI Is Changing My Plans.mp4` (24:02, 640×360, 0.3 Mbps). I ticked the rights box because Import requires it ("Required."). The 13-min second video was not tested.

## Timing

| Step | Time | Notes |
|---|---|---|
| Import → Ready | ~195 s (3m15s) | Stayed at 68% "Tracking crop · 534 / 534" for ~70 s with no change |
| Check | 290.8 s (the app's own figure) | Stayed at 5% "Sampling text every two seconds" for ~270 s, then jumped to 70% and finished |
| Find stories (6) | ~11 s | "6 stories from 252 sentences" |
| First Edit frame | ≤9 s after opening Edit | Later frames 0.45–0.73 s (curl) |
| Scrub → exact frame | <2 s | |
| Preview proxy, first build | 8.1 s for a 34 s story (9.4 MB) | Cached: 0.05 s |
| Render, final 9:16 1080×1920 | 6.2 s (22 s story), 6.2 s (21 s), 7.7 s (24 s), 7.7 s (28 s), 11.9 s (34 s); 8.3 s for v2 with a hook | Story 6 (the only one with captions) **failed** after 6.8 s |
| Queue all 6 | ~50 s in total | |

## P0: blockers

| # | Where (screen + control) | What I did | What happened | What I expected | Likely cause |
|---|---|---|---|---|---|
| 1 | Edit → Captions → Build captions; Finish → Queue | Built Bold captions on story 6, set the colour to #ffd400, clicked Apply style, then queued the render | The preview badge changed to **"Preview failed"**. Frame request returned `GET .../frame?t=20.060 → 500`. The render failed with only "Render failed." in the UI. Server log: `ValueError: can't measure length of multiline text` | Captions show in the preview and are burned into the export | `render.py:588` `_wrap_caption` calls `draw.textlength()` on cue text that already holds `\n` (cues like `"THAT DOESN'T MEAN THAT\nYOUR RESPONSE HAS TO"`). Called from `render.py:808` → `render.py:932`. Fails in both `routes_edits.py:676` (frame) and `app.py:1852` (`run_render`) |
| 2 | Finish: exported files | Queued all 6 stories in 9:16 | The 5 renders that succeeded have **no burned-in captions**. The manifest has `"captions": False`, and a frame at 5 s shows no text. Only an SRT/VTT sidecar is written. Result: no path gives a short with on-screen captions (default = none, building them = crash #1) | Captions on by default, burned into every short | Render path skips captions when the edit has no caption track. The only way to get a track triggers #1 |
| 3 | Edit → Captions | Played the story with captions built | No captions appear during playback either ("Playing a 540p copy with sound"). The creator never sees captions anywhere | A live caption overlay in the preview | Proxy/overlay does not draw the caption track; the exact frame is blocked by #1 |

## P1: major

| # | Where | What I did | What happened | What I expected | Likely cause |
|---|---|---|---|---|---|
| 4 | Stories → "How many" | Tried to ask for 8–10 stories | The select only offers 3,4,5,6. The API rejects higher values with "count must be an integer from 3 to 6." | 8–10+ shorts from a 24-min video | `clipset.MAX_STORIES`; `app.py:6250`, `app.py:6295` |
| 5 | Stories: pick quality | Read all 6 stories | 3 of 6 are not shorts material. #3 (18:38) is a giveaway/CTA: "congrats to Shelly von Huten, who won a free one-year city prepping membership… tell me in the comments". It names a private viewer. #2 opens with a CTA: "Your answers are going to help us decide whether to make a separate video…". #4 opens with "The 1st is… which we actually did 3 years ago" (references other videos) | Sponsor, CTA and housekeeping segments are filtered out | Selection scoring has no CTA/sponsor penalty (`selection.py`/`clipset.py`) |
| 6 | Stories: completeness | Compared story 6 to the transcript | Story 6 ends at 23:09.8 on "Maybe it's one online account or your income." The list continues: "It could be how you communicate…". The real payoff, "Find one of those weak points and make it a little less fragile.", is at 23:18–23:21 and is cut. Stories 1 and 6 also open on dangling references ("And that is like…", "Now, that doesn't mean…") | The story ends on a complete thought and does not open mid-argument | The 20–75 s window plus the sentence-boundary picker does not check the discourse ("And/Now/that" openers, list continuation) |
| 7 | Stories: coverage | Looked at the time ranges | Nothing was picked from 0:00–7:10. That part holds the video's strongest hook: 1:10–1:25 "During an open AI cyber security test, AI agents found ways around their controls…". 4 of 6 picks are in 18:38–23:10 | Picks spread across the video, best hooks first | Ranking/coverage logic |
| 8 | Stories / Edit: adjust the range | Looked for start/end trim on story cards and the Edit timeline | **No control exists** to extend or trim a story. The Edit timeline only seeks. The backend accepts `stories` patches (`ClipSetPatchBody.stories`, `app.py:5731`), but no UI uses them | Drag handles or ± sentence to fix #6 | UI missing in `static/studio/stories.js` and `edit/timeline.js` |
| 9 | Finish → Apply to all stories | Ticked Caption style + Text + Colour + Music + Voice, clicked "Apply to 5 other stories" | It reported **"Applied to 5 stories."**, but the other edits still show `captions: {track_id: None, style_id: None}` and `layer_counts.captions: 0`. My yellow brand style reached no other story | Every story gets the same captions and style | Applying a style copies nothing when the target has no caption track. It should build the track or at least warn instead of reporting success (`finish.js` `applyToAll`) |
| 10 | Edit → Captions: accuracy | Read the built cue track (`/captions/cap_6f3a1789b99a9aa5`) | The first word of each sentence is dropped: "Now," → `THAT DOESN'T MEAN…`, "You may" → `MAY NOT HAVE LAND`, "But I would" → `I WOULD ASK`, "I would encourage" → `WOULD ENCOURAGE`, "Where am I" → `AM I COMPLETELY`, "Maybe it's" → `IT'S ONE ONLINE`. Words also repeat at cue boundaries: `…HAS TO` / `TO LOOK…`, `AND` / `AND ASK THIS.`, `…ACCOUNT` / `ACCOUNT OR YOUR`. Nothing is shown for 0–1.26 s | Exact words, no drops or repeats | Word-to-cue chunking in `captions.py` (off-by-one at sentence/cue boundaries) |
| 11 | Finish: SRT sidecar | Opened `artifacts/art_14aa…/captions.srt` for story 1 | Cue 1 at 00:00 is "It is that a system still being tested, can reach beyond its", which is speech from **before** the story starts. The last cue ends mid-word: "…have products, va". There are 39 cues at a uniform ~0.98/0.43 s each, with text running past the story's end | SRT matches the cut's speech and timing | Sidecar built from a fixed text window with synthetic timing, not from the clip's words |
| 12 | Check: progress | Ran Check | Stayed at 5% "Sampling text every two seconds" for 4.5 min, then jumped to 70% | Progress that moves (frame N / M) | `routes_check.py` `run_check_job` reports no progress during OCR sampling |

## P2: minor

| # | Where | What I did | What happened | What I expected | Likely cause |
|---|---|---|---|---|---|
| 13 | Edit → Text → Hook card | Clicked Add text | Placeholder "Your hook" (not pre-filled from the story hook). The preview shows **two copies**: a small one at the top-left edge and one in the selection box. Render: size 44, thin white text, no box or outline over the forehead; weak as a hook | WYSIWYG preview; hook pre-filled from the story's hook; a bold readable default card | Client overlay vs server frame position mismatch (`edit/preview.js` vs `render.py` text layer) |
| 14 | Finish → Publish kit | Opened the kit for story 1 | Titles are templates around a truncated sentence: "Watch this: And that is like discovering that the concept car has somehow m…". Description cut mid-word ("…safety systems a"). Hashtags: `#shorts #story #video` | Real titles and topic hashtags (#AI, #AIsafety) | Template-only kit, ellipsized title reused |
| 15 | Stories cards | Tried to judge picks | No play/preview on a story card and no transcript excerpt beyond hook/payoff. Story 5's hook and payoff are the same single 20 s sentence. The list is sorted by source time, not strength | Watch a pick before editing; sort by strength | `stories.js` |
| 16 | Import: while processing | Watched the Import screen | "Recent videos" still said "No videos yet. Import one to begin." while the job was reading. The "Import video" button became enabled again (double import is possible) | List shows the running job; button disabled | `import.js` |
| 17 | Check results | Read the Text-on-screen list | 160 OCR regions, mostly noise ("^9UM.", "OII8C", "4HIH}"). Told "30 baked-in text regions need cleaning" on a talking-head video where the text is B-roll screenshots | Filter low-confidence junk; less alarm | OCR threshold ~36–50% shown |
| 18 | Edit timeline | Opened story 6 | The last sentence "Maybe it's one online account or your income." is listed twice in Sentences | Listed once | Payoff sentence appended twice in timeline rows |
| 19 | Finish → "Before you publish" | Viewed story 1 before editing | "Checks could not run for this story." with no reason given | A reason, or an auto-created edit | `finish.js` |
| 20 | Edit: first caption build | Build captions | First `PATCH /edits/ed_c9cd… → 409 Conflict`, then it recovered on a new edit id | No conflict on the first action | Edit version race after `POST /edits` |
| 21 | Network | Sat idle on Edit and Finish | 472+ requests. `status`, `check` and `clip-sets` are polled together every few seconds even after everything is Ready | Stop polling once idle | `shell.js` poller |

## P3: polish

| # | Where | What I did | What happened | What I expected | Likely cause |
|---|---|---|---|---|---|
| 22 | Reload | Reloaded the page on Edit/Finish | Always lands on `#/import` (data does persist: rail, edits, captions v2) | Return to the last step and story | `shell.js` route restore |
| 23 | Page load | Navigated to any step | A dimmed/overlay state lasts ~1–3 s before content shows | Instant or a skeleton | Transition overlay |
| 24 | Edit → Story select | Opened the select | Titles are the first ~60 characters of the hook ("01 · And that is like discovering…"). Hard to tell stories apart | Short generated titles | `edit/index.js:67` |
| 25 | Hidden DOM | Ran find for comboboxes | ~18 hidden legacy controls (minimax-music, lyria-clip, analyze_render…) sit in the DOM | Removed | Legacy page markup |
| 26 | Render filenames | Looked at `renders/` | Files are named by duration (`reel_22.mp4` for both story 2 at 21.8 s and story 6 at 22.4 s). Artifacts keep their own `reel.mp4`, so the v1 file survived the v2 render (checked), but `renders/` collides | Unique names | `render.py` output naming |

## What worked
- Reloading mid-import keeps the job, and the rail shows "Reading 63%". Check and later steps are locked with "Wait for the video to finish reading (63%)".
- Import of a 24-min file in ~3 min. Renders are very fast (6–12 s per short, 1080×1920 h264+aac, VideoToolbox).
- Versions: re-rendering story 1 made v2 and kept the v1 file.
- Preview plays with sound (540p proxy). Scrubbing returns an exact frame in under 2 s.
- The Change video library dialog lists the video with duration, story count and search.

## Persona verdict
Not weekly yet. Import and render speed are good. But I cannot ship a single captioned short: building captions breaks the preview and fails the render, and default renders have no captions. Half the AI picks are sponsor or CTA segments, or end mid-list, and I can't extend a story to fix that. "Apply to all" says it worked but my brand style didn't carry over.

Top 3 asks:
1. Fix captions end to end: on by default, burned in, word-accurate (no dropped first words or repeats), live in the preview, with the same brand style applied to every story.
2. Better picks, and more of them: 8–10+ stories, skip CTA/sponsor/giveaway segments, end on the real payoff, cover the whole video.
3. Let me trim or extend a story's start and end by sentence in Stories or Edit (the backend already accepts `stories` patches).
