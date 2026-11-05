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

## Tell me too

- What "super buggy" looked like in Check and Scan, if it still happens: hang, lost results, wrong text or repeats.
- Which project you used, if you want me to open it and run `scripts/fill_audit.py` on its clips.

## Results

Not run yet.
