# Clean video acceptance — founder gate

Status: **PENDING**. No founder pass is recorded on this tip. The automated
suites prove the stubbed pipeline and the UI states; they do not prove image
quality on real footage, a real LaMa model pack, or the full-length file on
disk.

Tip for this pass: `classic` at the commit that adds Phase 5 polish. The
reviewer writes the verdict in this file and in the phase notes; a green test
run alone is not acceptance.

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

1. On ingest, click **Clean video** and choose the real clip.
2. Wait for **Source ready**. Source Clean opens; Edit, moments and Smart Cut
   are absent.
3. Confirm the frame shows the source aspect, not a 9:16 crop. Confirm the rail
   names the file, duration, size, frame count and engine.
4. Click **Find text & clean** once for a clip under three minutes, or twice for
   a clip of three minutes or more (first click scans and shows the estimate).
5. Watch the stage line: **Finding text** → **Cleaning** → **Encoding**.
6. Wait for **Download**.

Expected:

- One primary action owns the screen before the run.
- The row list ticks only high-confidence text by default; low-confidence rows
  stay visible behind **Review N more**.
- Clean opens on the first timed text row when one exists. If the scan finds no
  timed row, the frame says **No text row at 0:00. Scrub the frame or scan
  again.** instead of claiming the frame is black.
- The result names output size, duration, file size and engine.
- **Download** saves a new file. The source is untouched.
- The downloaded file plays end to end at the source display size and frame
  rate, upright, with the source audio. Duration matches the source within one
  frame.

### 2. Before / After matches the file

1. On the frame, click **After**.
2. Compare the filled area with the same moment in the downloaded file.
3. Click **Before** and confirm the original text returns.
4. Click a row: the playhead moves to its start minus 0.5 s and the box is
   highlighted. Double-click opens the detail strip; `Escape` closes it.

Expected: After uses the same fill engine and layer data as the render. A
mismatch is a blocker. A missing filled frame must say so and fall back to the
source frame plus Clean boxes; it must not claim success.

### 3. Clean a cut

1. From the source result click **Make a reel**. Wait for the cut.
2. The result screen shows **Edit | Clean**. Click **Clean**.
3. Confirm the Edit columns are hidden, the frame and one rail remain, and the
   scan affordance appears once.
4. Confirm the carried source Clean layers are present with no duplicate rows.
   A cut row can be excluded or edited without changing the source copy.
5. Click **Clean N texts & render** once.
6. Wait for the cut **Download**.

Expected:

- The primary action reads **Clean N texts & render** (or **Render cut** when
  the cut has no found text).
- Rows outside the cut say **Not in this cut** and do not move the playhead.
- The render finishes into the normal render record; **Download** is live and
  saves `<source>-<target>s.mp4`.
- **Clean again** reruns honestly. A stale file is labelled **Download older
  file**; it is not presented as fresh.

### 4. Cancel and failure

1. Start a whole-video clean on a clip long enough to reach **Cleaning**.
2. Click **Cancel** while it runs.
3. Start a cut render and cancel it in **Rendering**.
4. Optionally remove the LaMa pack and retry AI fill.

Expected:

- Cancel stops the job and leaves no `.part` file. Check the job folder:
  no partial MP4 is offered as a result.
- The rail says the clean or render was cancelled and offers a retry. No dead
  **Download** appears.
- A missing model disables AI fill only, keeps Blur available, and names the
  recovery. The raw model path is in the console, not in a tooltip.
- A failed render or clean names the problem and the retry. Raw ffmpeg text
  stays in the console.
- `ls <job folder>` shows no `.part`.

### 5. Full-length download and layer carry

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

### 6. Responsive and keyboard

1. Record at 1440×900 and repeat the key clicks at 1280×800.
2. Resize to 1050×800 and 900×800 in Source Clean and Cut Clean.

Expected:

- No horizontal scrollbar at any of the four sizes.
- At 1440×900 and 1280×800 the frame and rail sit side by side; the primary and
  **Download** stay above the fold.
- Under 1100 px the rail becomes a bottom sheet below the frame, with rounded
  top corners and the primary pinned to the sheet's bottom edge. Scrolling the
  rail never hides the primary.
- Tab reaches the primary, rows, checkboxes, selects and the scrubber with a
  visible focus ring. `Escape` closes the job menu and the row detail.
- With **Reduce motion** enabled in the OS, page scrolls jump and transitions
  and animations do not play.

## Automated evidence

Run without starting the real server:

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic
python3 -m pytest tests/test_classic_phase5.py -q
python3 -m pytest tests/test_classic_phase5_browser.py -q
python3 -m pytest tests/test_classic_source_clean_browser.py tests/test_classic_cut_clean_browser.py tests/test_classic_source_clean_gates.py -q
```

Expected: all pass. The browser specs start their own private loopback uvicorn
and stop it when the spec ends. They skip (exit 2) when Node Playwright is not
installed, which is not a pass.

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
