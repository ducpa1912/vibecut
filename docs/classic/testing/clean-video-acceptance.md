# Clean video acceptance — founder gate

Status: **PENDING**. No founder pass is recorded on this tip. Automated tests
are engineering checks only; they are not acceptance. Only the human run on
real footage with the real model pack counts. No generated media or fake voice
is used in this document.

Tip for this pass: the current `classic` tip after Phase 5. The reviewer writes
the verdict in this file and in the phase notes; a green test run alone is not
acceptance.

## Terminal 1 — serve Classic

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic && scripts/serve-classic.sh
```

Expected: the script prints the local URL and the server stays in the
foreground. Do not close this tab. The Classic page is
`http://127.0.0.1:8796/`.

## Terminal 2 — record the pass

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic && npx -y playwright@1.65.0 codegen --viewport-size="1440,900" -o ~/vibecut-lanes/recordings/classic-test.spec.js http://127.0.0.1:8796/
```

Expected: Playwright records to
`~/vibecut-lanes/recordings/classic-test.spec.js` and the browser opens the
Classic page at 1440×900. If the recordings folder does not exist:

```bash
mkdir -p ~/vibecut-lanes/recordings
```

## Before the real run

- Use a real clip the founder owns. Record its name and duration here:
  - file: ______________________
  - duration / size: ____________
  - display size / fps: _________
- A LaMa model pack is installed (Setup shows AI fill ready). If it is absent,
  the pass still proves Blur and the missing-model copy, but AI fill quality is
  **not** accepted.
- Browser console is open with **Preserve log** on. No error line is allowed in
  a normal flow. A warning that names a missing model or a stopped analysis is
  acceptable and must stay out of the visible copy.

## Acceptance steps

### 1. Clean the whole video

1. Open Setup → **Clean review**. Confirm **Review first** is selected. It is the
   default. **One click** is opt-in and keeps the old scan-clean-render action.
2. On ingest, click **Clean video** and choose the real clip.
3. Wait for **Source ready**. Source Clean opens; Edit, moments and Smart Cut
   are absent.
4. Confirm the frame shows the source aspect, not a 9:16 crop. Confirm the
   compact header names the model state, and the timeline shows the total
   duration.
5. Click **Find text**. The scan runs and stops.
6. Confirm **no Clean layers were saved and no render started**. Detected text
   appears automatically as blue timeline bars.
7. Review the timeline. Click a bar to seek and show its tight box on the
   preview. Drag a bar to move its range; drag an edge to trim it. Double-click
   a bar to include or leave it out of Clean.
8. Confirm the model chip says **AI fill · Ready** or **Not ready**. Open it to
   choose a ready engine. GPU/CPU and Follow camera stay under **Fill options**.
9. Click **Clean N texts & render**.
10. Watch the stage line: **Finding text** → **Cleaning** → **Encoding**.
11. Wait for **Download**.

Expected:

- The scan is a review stop, not an automatic clean.
- No layer, no file and no render exists after the scan alone.
- Detected text is in the timeline immediately, one bar per tight line range.
- A subtitle area is one timeline row; its lines keep separate tight boxes and
  times. AI fill uses line boxes, not one large union box.
- A clear frame has no bar and no box.
- The model menu is anchored, 13px, and shows ready/not-ready per engine.
- Clean opens on the first timed text row when one exists. If the scan finds no
  timed row, the frame says **No text row at 0:00. Scrub the frame or scan
  again.** instead of claiming the frame is black.
- The result names output size, duration, file size and engine.
- **Download** saves a new file. The source is untouched.
- The downloaded file plays end to end at the source display size and frame
  rate, upright, with the source audio. Duration matches the source within one
  frame.

### 2. Timeline and detection review

1. Before cleaning, click the **Play** icon in the preview panel.
2. The real source video plays. Every found box and every drawn box is shown as
   an outline, ticked or not. There is no blur fill.
3. Watch for leftover text outside the boxes, two boxes on one line, a box on
   the wrong object, or a box that covers too much.
4. Click a timeline bar to seek to its start and show its tight box. Drag its
   body to move it; drag an edge to trim it.
5. Use **Add range** to start a manual box at the playhead.
6. Confirm the note says **Detection check · boxes outlined · not the final
   clean**.

Expected:

- Play starts immediately. It does not start AI fill, a clean render or a save.
- Outlines cover all found and manual boxes, including low-confidence and
  unticked rows. Text outside a box stays sharp.
- Overlap, wrong boxes and clear frames are visible, not hidden by blur.
- On a cut, Play uses a ready cut render. If no render exists, the workspace
  says **Render a draft once to play this cut.** and does not start one.

### 3. Before / After matches the file

1. On the frame, click **After**.
2. Compare the filled area with the same moment in the downloaded file.
3. Click **Before** and confirm the original text returns.
4. Click a timeline bar: the playhead moves to its start and the box is
   highlighted. Drag its edges to trim; `Escape` deselects.

Expected: After uses the same fill engine and layer data as the render. A
mismatch is a blocker. A missing filled frame must say so and fall back to the
source frame plus Clean boxes; it must not claim success.

### 4. Clean a cut

1. From the source result click **Make a reel**. Wait for the cut.
2. The result screen shows **Edit | Clean**. Click **Clean**.
3. Confirm the Edit columns are hidden, the frame and the timeline remain, and
   the scan affordance appears once.
4. Confirm the carried source Clean layers appear as timeline bars with no
   duplicate rows. A cut bar can be excluded or edited without changing the
   source copy.
5. Click **Find text**. The scan stops for review. Confirm no render started.
6. Review the timeline bars, then click **Clean N texts & render**.
7. Wait for the cut **Download**.

Expected:

- The primary action reads **Find text**, then **Clean N texts & render** (or
  **Render cut** when the cut has no found text).
- Rows outside the cut say **Not in this cut** and do not move the playhead.
- The render finishes into the normal render record; **Download** is live and
  saves `<source>-<target>s.mp4`.
- **Clean again** reruns honestly. A stale file is labelled **Download older
  file**; it is not presented as fresh.

### 5. Cancel and failure

1. Start a whole-video clean on a clip long enough to reach **Cleaning**.
2. Click **Cancel** while it runs.
3. Start a cut render and cancel it in **Rendering**.
4. Optionally remove the LaMa pack and retry AI fill.

Expected:

- Cancel stops the job and leaves no `.part` file. Check the job folder:
  no partial MP4 is offered as a result.
- The workspace says the clean or render was cancelled and offers a retry. No dead
  **Download** appears.
- A missing model disables AI fill only, keeps Blur available, and names the
  recovery. The raw model path is in the console, not in a tooltip.
- A failed render or clean names the problem and the retry. Raw ffmpeg text
  stays in the console.
- `ls <job folder>` shows no `.part`.

### 6. Full-length download and layer carry

1. Download the whole-video clean file. Play it fully.
2. Re-open the job from Recent cuts.
3. In Edit, confirm the carried source layers still exist.
4. Exclude one carried layer on the cut, render, then reload.

Expected:

- The full-length file plays past the reel length; audio stays in sync.
- Reload does not duplicate the carried rows.
- Editing the cut does not change the source Clean record.
- A source row that is excluded in the cut still shows **Excluded**, never
  **Already cleaned** beside it.

### 7. Responsive and keyboard

1. Record at 1440×900 and repeat the key clicks at 1280×800.
2. Resize to 1050×800 and 900×800 in Source Clean and Cut Clean.

Expected:

- No horizontal scrollbar at any of the four sizes.
- At 1440×900 and 1280×800 the frame sits above the timeline; the primary and
  **Download** stay above the fold.
- Under 1100 px the timeline stays below the frame and the action bar stays
  visible; scrolling the timeline never hides the primary.
- Tab reaches the primary, timeline bars, model menu, scrubber and expand
  control with a visible focus ring. `Escape` closes the job menu and menus.
- With **Reduce motion** enabled in the OS, page scrolls jump and transitions
  and animations do not play.

## Real-use Playwright script

The script drives the real server and the real video. It does not start the
server, generate media, fake voice, or stub a route.

Terminal 2:

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic
CLASSIC_REAL_VIDEO="/absolute/path/to/your-real-video.mp4" \
  node scripts/classic-real-acceptance.mjs
```

Add the cut pass:

```bash
CLASSIC_REAL_VIDEO="/absolute/path/to/your-real-video.mp4" \
CLASSIC_REAL_CUT=1 \
  node scripts/classic-real-acceptance.mjs
```

Optional:

```bash
CLASSIC_URL="http://127.0.0.1:8796/" \
CLASSIC_OUT_DIR="$HOME/vibecut-lanes/real-acceptance/run-1" \
CLASSIC_VIEWPORT="1280x800" \
CLASSIC_REAL_VIDEO="/absolute/path/to/your-real-video.mp4" \
  node scripts/classic-real-acceptance.mjs
```

The script writes screenshots, a JSON report, and the downloaded files under
`CLASSIC_OUT_DIR` (default `~/vibecut-lanes/real-acceptance/<timestamp>`). It
stops for human review when the scan finds only low-confidence rows; it never
auto-ticks those.

## Result

| Item | Result | Notes / evidence |
| --- | --- | --- |
| Whole-video clean on real footage | PENDING | |
| Before/After matches preview and render | PENDING | |
| Cut Clean with carried layers | PENDING | |
| Cancel leaves no `.part` | PENDING | |
| Full-length download plays with audio | PENDING | |
| 1440 / 1280 / 1050 / 900 layout | PENDING | |
| Keyboard and reduced motion | PENDING | |
| Vietnamese copy spot check | PENDING | |

Founder signature / date: ______________________

Do not mark this pass complete from a synthetic-clip run. The gate needs the
founder's real media and a real model pack.
