# Clean retest after round 1 (founder runs, Claude records)

**Why:** the first run in `studio-clean-fill-real-video.md` failed most steps. This checks those fixes, using one of your own videos.

**Start:** open `http://127.0.0.1:8795` and press **Cmd+Shift+R** once.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

## What the controls do

- **White line around the preview:** the frame, at the render's exact size. Its size is written top left. Anything past it is cut in the render.
- **Network list and phone button, left of Play:** the safe area for that network. It never shows in the render.
- **Zoom buttons above the preview:** only change your view, from 25% to 300%. The render does not change.
- **Framing** (crop icon on the right rail; it replaces Video zoom): the zoom and place of the scene under the playhead, in the render too. 1× fills the frame. **Fit scene** shows the whole picture, with black around it.
- **Move button on the preview toolbar:** drag the scene inside the frame. **Area focus:** draw a box, and that part fills the frame.
- **Add motion** (Elements → Effects): a timed zoom. Punch in eases in, Snap zoom jumps, and Push grows slowly.
- **Blue box or bar:** one you drew. **Orange:** one the scan found. **Dashed bar:** found text with no layer yet.

## Steps

| # | Action: where to click | Expected | Result |
|---|---|---|---|
| 1 | Open Clean, draw a box with **Draw box** on a subtitle | The box and its timeline bar are blue, at the current time | |
| 2 | Drag the bar's right edge, then drag its middle | It gets shorter, then moves in time. The box only shows in that time | |
| 3 | **Scan video**, then **Check this scene** | The scene button only filters the list, at once, with no new scan. Other scenes' text comes back when you pick the video again | |
| 4 | Look at the Clean lane where layers overlap | Overlapping bars stack in rows, and each can be clicked | |
| 5 | Add found text to layers, then look at the list | Added text folds into one "already added" line, and the list holds what is left | |
| 6 | Drag the timeline's top edge up | Lanes and text get bigger, not only the empty space | |
| 7 | Select a scanned layer while the playhead is elsewhere, then **Test 1 second** | The playhead jumps to that layer, then Before/After and a moving clip appear after a few minutes | |
| 8 | Do step 7 with a painted layer | Same. If it refuses, send me the message exactly | |
| 9 | Look at the clip from step 7 or 8 | Text is gone, with no ghost and no halo, and objects do not smear | |
| 10 | Find the bold line under **Add box** in Clean | It says about how long AI fill adds | |
| 11 | Elements → Text: add a Hook card, then drag it on the preview | It moves, and stays on that spot of the video. A plain click does not move it | |
| 12 | Drag the Hook card's bar edge on the timeline, then type a new End in its panel | Its time changes both ways | |
| 13 | **Framing**: raise to 1.5×, then press Play | The video and the Hook card grow together, playing and paused | |
| 14 | Elements → Effects: **Add motion** → Punch in, then Play across it | The video zooms in with the text, playing and paused | |
| 15 | Moments: **Delete moment** (click twice), then **Clear all moments** (click twice) on a test set | They go. Find moments that finds nothing leaves your moments alone | |
| 16 | Finish, on a moment with no render: **Add this moment to queue**, on a 10 to 20 second moment | It joins the queue. Note the estimate and the real time | |
| 17 | Watch the result | AI fill and Blur boxes each got their own method, and the Hook card stays locked to the video during zoom. **This decides option A or B** | |
| 18 | Look at the preview, then change the shape to 16:9 and back | A white line marks the frame, with its size written top left. The size follows the shape | |
| 19 | Pick each network in the list left of Play | The safe area changes and names the network. Instagram Reels is there | |
| 20 | Press the shrink button above the preview, then click the percent to go back | The frame gets smaller on screen, then returns. The video does not change | |
| 21 | **Framing** → **Fit scene** on a wide video in 9:16 | The whole picture shows, centred, with black above and below. Paused it is exact within a few seconds | |
| 22 | Press Play on that scene | It takes a moment the first time, then plays with the same framing and normal sound | |
| 23 | Move button on the preview: drag the scene past the frame edge | It moves as you drag. The part past the white line is gone | |
| 24 | **Area focus**: draw a box on a face | That part fills the frame | |
| 25 | Go to another scene | Framing names that scene, at its own zoom. **Use on all** copies a framing to every scene | |
| 26 | Render a 10 to 20 second moment with a zoomed-out and a moved scene | The render matches the preview: same place, black in the empty frame, the cut part gone, and sound unchanged | |
| 27 | Look at every toolbar: preview, timeline, right rail | One icon style. Each icon's tooltip matches what it does. Tell me any icon you cannot read | |

## Tell me too

- What "super buggy" looked like in Check and Scan, if it still happens: hang, lost results, wrong text or repeats.
- Which project you used, if you want me to open it and run `scripts/fill_audit.py` on its clips.

## Results

Not run yet.
