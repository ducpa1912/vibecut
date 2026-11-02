# Founder session 1: recorded run (2026-10-28)

**Build:** `main` at `5947af3` (R2 merged).
**Recorder:** `npx playwright codegen -o actions.js --save-har network.har`, about 25 minutes, 472 requests.

**Files in this folder:**
- `actions.js`: every click and field change, in order. Codegen output; it has no timestamps.
- `network-summary.md`: errors, slow calls, route counts, writes, and the progress timelines of Check and the render queue.

**Full HAR:** `~/vibecut-feedback/network.har` (39 MB), on the founder's Mac only. It is kept out of the repo because it holds frames and proxy media from third-party videos. Read it in place; never copy it or its media into the repo.

## Videos used

| Job | Video | Length | Size | Codec |
|---|---|---|---|---|
| `7610134fee5e` | A: JOYLO talking head with screen recordings | 52.9 s | 1440×2560 | AV1 |
| `25bb4aaa14e2` | C: "10 unsaturated print on demand products…" (Etsy tips) | 111.7 s | 1080×1920 | HEVC |
| `97a5fd3744c0` | B: rednote garden (Chinese subtitles + music) | 88.8 s | 720×1280 | H.264 |

## What the founder did (from `actions.js`)

The same flow was run once for each video:
1. **Import:** ticked the rights box, then Import video.
2. **Check:** Run Check. On A it was pressed again while waiting. The founder opened a tracklet and the recommendation.
3. **Stories:** Open Stories, Length = Short, Find stories, Shape = 4:5, then Render this story / Queue all.
4. **Edit:** Edit this story, then play/pause/scrub. Switched story from the Story dropdown. Color: Vivid pop, then Teal and orange. Effects: Add motion, then Add effect.
5. **Finish:** Queue 4:5 and 9:16 per story, then Queue all stories for each shape.
6. **Next video:** Change video, then the next one.

The session ended by opening and closing Settings and Setup.

## Founder's comments (verbatim)

> Checking the source take too long and the status run estimation is not correct, the interface is confusing, edit do not have the button to go back or fwd to next step, no media/library store all the completed video. Also … where is all the translation workflow & voice gen workflow.

## Evidence found so far (Claude Code)

1. **Check felt slow, and its progress froze. Root cause found and fixed in `3da8ac3`.**
   - **Measured:** the server finished Check in 23.4 s (A), 32.3 s (C) and 17.2 s (B), per `source_report.timings`. Studio showed it finished only after 147 s, 164 s and 135 s.
   - **What the founder saw:** the screen sat at 5% "Pulling frames to read text" the whole time. On A they ran Check a second time.
   - **Cause:** `fetch` treats a 202 "running" reply as a success, so the R1 read cache (`static/studio/api.js`) stored the first running snapshot. Every later poll was answered from that cache with no request sent, until the shell's 150 s job-stamp check cleared it.
   - **Fix:** running, queued and incomplete payloads are no longer cached. Test: `test_api_cache_never_freezes_a_running_check_poll`.
2. **Render queue estimates jump around.**
   - Progress sits at 0.333 and 0.667 (stage steps) while the ETA disappears or shows 0.0.
   - Example (`sq_e02b6`): ETA 21.8 → 30.6 → 11.5 → **0.0 at 33%** → gone → 26.6 → 5.2 → 8.8 → gone.
   - The renders themselves are fast: 5–40 s per story.
3. **"Before you publish" is broken on Finish.**
   - `GET /api/jobs/{id}/preflight?story_id=<clip-set story id>` returns 404 `story_not_found`.
   - It fails for every story tested.
4. **Scrubbing to the end of a story errors.**
   - `GET …/frame?t=20.800` returns 422 "t must be between 0 and the story duration (20.800s)".
   - The end time itself is refused, at the end of every story.
5. **The first preview is slow.** The Edit proxy took 16–18 s to load the first time.
6. **No way to move between steps from Edit.**
   - The founder reached Finish only through the rail.
   - Edit has no Back to Stories or Next: Finish control.
7. **No media library.**
   - Finished renders are only reachable per job, through Finish → Versions.
   - Nothing lists every finished video across jobs.
8. **Translation and voice generation are hard to find, or missing in Studio.**
   - **Where they are today:** Edit → Audio tab.
     - Mode has Voice-over and Dub, plus a voice picker with Preview voice (HeyGen is the default engine).
   - **What's missing in Studio:**
     - a target-language picker for Dub;
     - a voice-over script box;
     - translated captions;
     - the per-workflow engine order (Translate / Voice / Music routes).
   - **Where the missing parts live:**
     - the engine routes and translation mode are only in Classic (`?classic=1`) → Setup → model routes;
     - Classic's render panel has "No translation (same language)" and the language list.
     - Studio's Setup → Engines shows status only.
