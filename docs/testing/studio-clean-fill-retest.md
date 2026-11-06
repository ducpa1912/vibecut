# Clean retest after round 1 (founder runs, Claude records)

**Why:** the first run in `studio-clean-fill-real-video.md` failed most steps. This checks those fixes, using one of your own videos.

**Start:** open `http://127.0.0.1:8795` and press **Cmd+Shift+R** once.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

## What the controls do

- **White line around the preview:** the frame, at the render's exact size. Its size is written top left. Anything past it is cut in the render.
- **Network list and phone button, left of Play:** the safe area for that network. It never shows in the render.
- **Zoom buttons above the preview:** only change your view, from 25% to 300%. The render does not change.
- **Framing** (crop icon on the right rail; it replaces Video zoom): the zoom and place of the scene under the playhead, in the render too. 1× fills the frame. **Fit scene** shows the whole picture, with black around it.
- **Move button on the preview toolbar:** an orange outline with corners appears. Drag a corner to zoom the scene in or out, drag the middle to move it, or scroll. **Area focus:** draw a box, and that part fills the frame.
- **Add motion** (Elements → Effects): a timed zoom. Punch in eases in, Snap zoom jumps, and Push grows slowly.
- **Blue box or bar:** one you drew. **Orange:** one the scan found. **Dashed bar:** found text with no layer yet.

## Steps

| # | Action: where to click | Expected | Result |
|---|---|---|---|
| 1 | Open Clean, draw a box with **Draw box** on a subtitle | The box and its timeline bar are blue, at the current time | |
| 2 | Drag the bar's right edge, then drag its middle | It gets shorter, then moves in time. The box only shows in that time | |
| 3 | **Scan video**, then **This scene** in Found on screen | The scene button only filters the list, at once, with no new scan. **Whole video** brings the rest back | |
| 4 | Look at the Clean lane where layers overlap | Overlapping bars stack in rows, and each can be clicked | |
| 5 | Add found text to layers, then look at the list | Added text folds into one "already added" line, and the list holds what is left | |
| 6 | Drag the timeline's top edge up | Lanes and text get bigger, not only the empty space | |
| 7 | Select a scanned layer while the playhead is elsewhere, then **Test 1 second** | The playhead jumps to that layer, then Before/After and a moving clip appear after a few minutes | |
| 8 | Do step 7 with a painted layer | Same. If it refuses, send me the message exactly | |
| 9 | Look at the clip from step 7 or 8 | Text is gone, with no ghost and no halo, and objects do not smear | |
| 10 | Find the line under Clean layers | It says about how long AI fill adds | |
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
| 28 | **Scan video** on a video with subtitles, then read the found list | All subtitle lines are one row, "Subtitles · N lines". The same words show once | |
| 29 | **Clean N**, then read Clean layers and the Clean lane | Subtitles are one group with a count, and open to one row per line. Each line has its own bar, with its words on it | |
| 30 | Move the playhead through the moment | The preview shows only the boxes and brush marks on at that time. Selecting a layer in the list moves the playhead to it | |
| 31 | Delete a group with its bin icon, then **Delete all** (click twice), then Undo | The group goes, then all layers go, then Undo brings them back | |
| 32 | Open a project that had repeated layers | A message says how many repeated layers were removed. The Clean lane and list show each text once | |
| 33 | Drag a found text bar on the Clean lane, then a drawn box's bar | Both move and resize | |
| 34 | **Framing** on the right rail, then drag a corner of the orange outline on the preview in and out | The scene shrinks and grows, with black in the empty frame | |
| 35 | Scroll on the preview, then drag the middle of the scene past the white line | Scrolling zooms. The scene moves, and the part past the line is cut | |
| 36 | Elements → Effects: **Zoom out over time** and **Zoom in over time**, **Add motion**, stretch the bar, Play | The scene zooms over the bar's length, and it runs across cuts | |
| 37 | Moments → **Edit full video** | Edit opens with every scene in time order, on a wide shape for a wide video. Its total time matches the whole video | |
| 38 | In it, press Play across several cuts, listen, and split then delete a scene on the timeline | Sound runs with no tick at the cuts. The scene goes and the rest closes up | |
| 39 | Back to Moments, press **Edit full video** again | The same edit opens with your changes. Your found moments are untouched | |
| 40 | Finish → pick Full video in the list, add to queue, and render a short video | The whole video renders and downloads. Tell me how long it took and how long the video was | |
| 41 | Pick a network, then shrink and magnify the view, change the shape, press Play, go to Finish and back | The safe area and frame size stay on the white line throughout, and the network stays chosen | |
| 42 | Press the top right **Finish** in Edit | It saves and opens Finish on this moment | |
| 43 | Import: press the bin on an old video, then **Cancel**. Press it again, then **Delete**. Then **All videos** and do the same there | Cancel keeps it. Delete removes it from both lists | |
| 44 | Start **Scan video** or a render, then press the bin on that video | The prompt names what is running. **Cancel** lets it carry on. **Delete** stops it, the video leaves the list at once, and the app stays responsive | |
| 45 | Clean: add a new box and read its engine, then render a 10 to 20 second moment with AI fill | The engine is LaMa, and layers you saved before keep their own engine. Tell me the real time, and whether the filled area flickers or looks soft | |
| 46 | **Scan again**, then look at the boxes while you play | Each box fits its own line, not all lines together. It appears when the text appears and goes when it goes, within about a quarter second. Tell me how long the scan took | |
| 47 | Click a box on the video, drag it, drag a corner, then drag its bar. Do this for a found text and a drawn box, also right after using **Framing** | The box moves and resizes on the video, and its time changes on the timeline | |
| 48 | Pause on some text, then **Add box**, or **Paint** | The new layer starts at the playhead and lasts three seconds. Nothing is added before the playhead | |
| 49 | Read the Clean panel from the top | One **Remove with** choice, **Add box** and **Paint**, the found list with one **Clean N** button, then the layers. Tell me anything you miss or cannot find | |
| 50 | Find text labelled watermark, screen UI, title or card | Every row can be ticked and cleaned with AI fill or Blur | |
| 51 | New video: press **Edit full video** without finding moments, then **Finish** | Finish opens on the full video, and it can be queued and rendered | |
| 52 | **Scan again**, then read Found on screen and look at the boxes | Each line has its own box, with no second box over the same words. Logos on objects, like a cup, are listed but start unticked. Tell me any repeat or any box bigger than its text | |
| 53 | Render a 10 to 20 second moment with AI fill, on a still shot and a moving shot | It is much faster than one frame at a time. Tell me the time for each, and if the filled area smears on the moving shot | |
| 54 | Clean → **AI model** → Telea, then Navier-Stokes. For each: **Before / After** on a found line, then render a 10 to 20 second moment | The result takes about a fifth of a second per frame. Tell me which shots look acceptable; expect smears on detail like wood or leaves | |
| 55 | **Before / After** on small text over a busy background | No letters are left behind | |
| 56 | Scan again, then watch two stacked lines and a drawn box over a found line | Boxes of stacked lines touch and do not overlap. Render a moment and tell me its time per frame | |
| 57 | **Scan again** on a mostly still video and on a moving one, then render each | Each line gets its own plan: one fill when still, more when moving. The estimate is close to the real time on both. Tell me the times, and any smear on moving shots | |
| 58 | Restart the server. Queue a full video with AI fill, wait for several percent, press **Pause**, then **Resume** | Pause stops within seconds and the queue says Paused. Resume climbs fast back to where it was, the message counts saved fills reused, then the time left appears. Tell me the time to catch up, and whether the join shows in the result | |
| 59 | During a fill, stop the server with Ctrl+C. Start it again, then **Resume** | Same as step 58: the work is not lost, and the Mac did not sleep during the render unless the lid was closed | |
| 60 | Draw one box on a moving shot, AI fill, then render. The box must be new or moved, so the old clip is not reused | It takes about one model run per 4 frames at 25 fps, not one per frame. The estimate under Clean layers is close to the real time. Tell me both, and any smear | |
| 61 | Finish → **AI fill on GPU**, then render a video with AI fill. Compare with a CPU render of the same Edit | It renders much faster, the two results look the same, and the first render asks for no new choices. Tell me both times, and if the Mac slowed or swapped | |
| 62 | Clean → **AI model** → MI-GAN, then render on CPU and on GPU | Text is gone. Tell me the times, and any flicker or smear compared with LaMa | |
| 63 | Finish → tick **Follow camera motion**, then render a shot with a camera move and a shot with something crossing the text | The camera move keeps a steady fill with fewer model runs. The crossing falls back with no jump. Tell me the times, and where it looks wrong | |
| 64 | Draw a box over several lines of found text and select it, then press **Clean only the N lines inside** | The panel says what the box costs. The box becomes tight line boxes, on screen only with their lines, inside the box's time | |
| 65 | While a render runs, pick another quality, GPU or **Follow camera motion**, then **Queue**. Change the model in Clean and queue again | The button is open for any new choice, and shows Queued only for the same choice. The renders run one after another, and the review video does not reload | |
| 66 | **Scan again**, render with AI fill, then check 7 s, 9 to 12 s | Every word is found, including short ones. The text turns into picture, not a dark patch | |
| 67 | Click a dashed bar on the Clean lane | The playhead moves to it, and it becomes a solid bar you can edit | |
| 68 | Open Finish, let a render end, and open History | The page opens at once and the review video fills in after. The render joins Finished without a reload. History says how long it took | |

## Tell me too

- What "super buggy" looked like in Check and Scan, if it still happens: hang, lost results, wrong text or repeats.
- Which project you used, if you want me to open it and run `scripts/fill_audit.py` on its clips.

## Results

**2026-11-05, founder, full video, 59.6 s, AI fill with LaMa: 6.5/10.** The render took about 2 hours and started before the speed and box changes (`ef61c18` onward), so it used LaMa on every frame, one large crop, block boxes and a 1 s time margin.

| Time | Founder saw | Likely cause, from frames and layers | Status |
|---|---|---|---|
| 22 to 23 s | Something rendered there | The second line of text was left behind | Fixed in `9e55079`, not re-rendered |
| 24 to 25 s | Many overlapping boxes, then one removed | Blocks of text missed letters; a stale box ran 1 s past its line | Fixed in `dd21cd0`, `9e55079`, `5b552f6`, not re-rendered |
| 28 to 31 s | Distortion: moving background in one scene | Each frame is filled alone, with a hand moving through the box | Open |
| 32 s | Logo on the black cup removed cleanly | Steady dark surface | Good |
| 49 to 51 s | Distortion on a mostly steady background | The cat crosses a full-width box; 30% of the last fill was kept | Open; the blend is gone from the keyed path, not re-rendered |
