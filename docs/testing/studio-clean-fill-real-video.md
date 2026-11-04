# Clean, AI fill and sticking text on a real video (founder runs, Claude records)

**Build:** commit `1170aba`, on `http://127.0.0.1:8795`.

**Why this test:** R0, R1, R2, R3 and the R5 spike have only had code tests. Shipping `studio` to `main` waits for this run.

**Video:** one of your own, with burned-in subtitles and a busy background behind them. A 16:9 video cut to 9:16 tests the most, because the crop moves. Use a moment of about 10 to 20 seconds with at least one scene cut, so AI fill stays short.

**Record the run** (optional, and it gives me the exact clicks):

```bash
scripts/record.sh
```

Or open `http://127.0.0.1:8795` and press **Cmd+Shift+R** once.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column. Steps come from the plan's test gates and the code's labels, so if a label or a click is wrong, that is my error and worth telling me.

## A. Clean: AI fill or Blur, per box

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | Open your video in **Edit**. In the right panel, open **Clean** | Lane in view (R3) | The timeline scrolls to the Clean lane without you scrolling. Text in the panel is easy to read | |
| 2 | **Scan video**, and wait for it to finish | Scan works, one row per text (R0, R3) | One row per found text, with its times folded inside. Layers outside this moment fold into one line | |
| 3 | **Scan video** again | No duplicates (R0) | No new rows for the same text in the same area | |
| 4 | Under the preview, pick **Draw box** and draw a box on some subtitles. Draw a second box elsewhere | New boxes | Each box has its own **AI fill** / **Blur** switch. Each starts on the current beat | |
| 5 | Set one box to **AI fill** and the other to **Blur** | Per-box method (R0) | Each switch keeps its own choice. There is no Cover option anywhere | |
| 6 | Pick **Paint mask**, paint over a subtitle, then click its row's brush again | Brush reuses its layer (R0) | No extra layer appears, and the painted stroke is smooth with no gaps | |
| 7 | Select a found row and press **Delete** | Remove without scrolling (R3 gate) | The row goes, and you did not need to scroll the timeline | |
| 8 | Drag the top edge of the timeline, then double-click it | Resizable timeline (R3) | It resizes, then resets | |

## B. Test before waiting

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 9 | Read the time estimate in Clean | Honest cost (R2) | It says about how long AI fill adds. Note the number here | |
| 10 | Select an AI fill layer with subtitles at the playhead, then **Test 1 second** | Real engine preview (R1, R2) | After a few minutes, Before/After and a moving clip appear. Nothing is saved | |
| 11 | Look closely at the clip | The picture (R1) | Text is gone, with no ghost and no halo. Objects in the band do not smear | |

## C. Text sticks to the video (R5 spike)

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 12 | Add a Text layer with **Add text** in the timeline toolbar. Stretch it across the scene cut, then tick **Stick to the video** in its panel | Option A | The text stays where it was on the first frame | |
| 13 | Under Layers, open the zoom layer and raise **Zoom** to about 1.5× | Text scales with zoom | The text grows with the video and stays on the same part of the picture | |
| 14 | Use **Area focus** to move the crop so the text sits at the edge | Hides at the crop edge | The text moves with the video and is cut off only by the frame. It does not rewrap, shrink or move back | |
| 15 | Play across the scene cut | Known effect of this rule | With auto reframe the text may jump at the cut, because it follows the video. Say whether this is acceptable | |
| 16 | In **Effects**, use **Add motion** to add a Punch in on the same beat, then pause mid-zoom | Motion match on the exact frame | The text and the video zoom together | |

## D. The render

Pick **Render** in Finish, with the shortest quality you are happy to judge.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 17 | Before rendering, read the estimate on the Render card | R2 test gate | Note the estimate here | |
| 18 | Render, and note the real time taken | Estimate accuracy (R2 gate) | Real time within about 30% of the estimate | |
| 19 | Watch the result: the AI fill box and the Blur box | Each method applied (R0 gate) | Each box got its own method. Objects do not smear, and text does not flicker back at beat edges | |
| 20 | Watch the zoomed and moving text | **Decides option A or B** | The text stays locked to the video during the Punch in, with no drift or wobble. Note how soft it looks at full zoom | |
| 21 | Compare with the paused preview at the same moment | Preview matches render | Text sits in the same place in both | |

## E. Afterwards

Tell me which project this was. With your OK I open only that project and run `scripts/fill_audit.py` on its fill clips, which reads them and writes nothing. That also gives its thresholds their first real reading.

## Results

Founder run, 2026-11-04, by hand in a normal browser, with no recording. Words are the founder's, shortened.

| # | Result | Founder's note |
|---|---|---|
| 1 | Pass | Text is easy to read. Overlapping layers need better selection in the timeline |
| 2 | Pass | |
| 3 | Pass | |
| 4 | Fail | Cannot see the box on the timeline or shorten it there. Drawn boxes need another colour from scanned ones |
| 5 | Pass | |
| 6 | Hard | The list of found text is too crowded |
| 7 | Fail | There is no delete button, only Remove, and Remove can mislead in a feature that removes text |
| 8 | Fail | The timeline grows but its elements do not get bigger. Its icons and buttons need a revamp |
| 9 | Fail | Not sure where to look |
| 10 | Fail | A painted layer gave no AI fill. A scanned text in a box did not run |
| 11 | Fail | Cannot see a thing |
| 12 | Fail | Cannot move text or a hook card on the video. Cannot change a text's duration in settings or on the timeline |
| 13 | Fail | Is Zoom only inside the preview? How to zoom the video to fit the border, and where is the border |
| 14 | Unclear | Not sure what it does |
| 15 | Pass | Normal |
| 16 | Fail | Not sure what it is. It does nothing |
| 17 | Fail | No button to add to the queue at Render. The time estimate does show, on an older queued clip |
| 18 | Not run | Saw the seconds count, and the estimate may be wrong |
| 19 | Not run | Could not finish the new test media |
| 20 | Not run | No zoom or moving text to judge, so option A or B is still open |
| 21 | Not run | |

Also reported:

- Check this scene and Scan video are very buggy.
- Moments has no button to clear one story or all of them. Find moments replaces what is there, or adds nothing.

**From the server log and code, not yet fixed:**

- Test 1 second: 1 of 6 runs returned a result, and 5 were refused with a 422. The log does not say why. It runs at the playhead, not at the selected layer's time, which is the likely cause.
- The fast preview is built once from the story range and shows no crop, zoom or motion. Only the paused exact frame does, which is why steps 13 and 16 seem to do nothing.
- Canvas dragging of text and timeline dragging of Text and Clean durations do not exist.

**Verdict:** not ready to ship.
