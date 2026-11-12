# Founder test — the whole app in the new layout

Click-by-click on the built app (`build/DuckSuite-Xcode.app`). Do not run this as an agent. One
project is open: `人吃啥咪吃啥` (`prj_e95348a97316`). Have a second short video ready if you want to
try Import.

## 1. Welcome, 1440×900 and 1280×800

1. Open the app. Drag the window to 1440×900, then to 1280×800.
2. **Must see:** the dropzone and the latest-render card fill the middle column; the queue and engine
   panels run to the bottom of the window; no horizontal scroll bar.

## 2. Import

1. Click **Choose Video** and pick the short video. Choose “Use full video” or “Add scenes”.
2. **Must see:** the import finishes, the project opens, and the new clip appears in the timeline.
   (If you do not want to change this project, stop here and reopen `prj_e95348a97316`.)

## 3. Check

1. Open `人吃啥咪吃啥`, go to **Check**. If it is already done, click **Re-check** only if you want to
   move clean-layer ranges: **Check can change them** and the next render is cold for the spans it
   touches.
2. **Must see:** the stages list on the left, the player and the **Scenes** strip on the right of it,
   and a page that reaches the bottom of the window. No horizontal scroll.

## 4. Edit, Clean Focus

1. Open **Edit**, select a scene with text.
2. Look at the inspector’s layer list head and bottom edge.
3. **Must see:** `N of M layers`. If the list is longer than the box, a soft fade at the bottom while
   more rows are below; scroll to the end and the fade goes away.
4. Click the **moves** flag on a layer, then **Show all** if present. **Must see:** rows stay 32 px,
   nothing overlaps, and the count changes with the list.
5. Open **Clean** (Clean Focus). **Must see:** `Scenes · 35 shown / 35 total` above the list, the
   All/Yours filter, and a page that fills the window.
6. In the timeline, find the empty **Script**, **Voice & Music** and **SFX** lanes.
7. **Must see:** each empty lane is one short dashed row with a `+` (“Add a caption”, “Add an
   effect”). Add one caption (Script focus) and its lane opens to a normal row.

## 5. Preview

1. Open **Preview** at 1440×900 and 1280×800.
2. **Must see:** the player is as tall as the window allows and shows only a thin black edge
   (15 px) around the picture, not a wide black box; the **Scenes** strip sits in a narrow column
   beside it and runs to the bottom; no empty paper band under the player.
3. Switch to **Edit**: the video there also hugs the picture (no black bars at the sides). The
   **Filter** field has the same space on its left and right; the scene rows are hairlines with no
   dark edge.
4. Look at the player's controls.
5. **Must see:** one control bar only — play, time, scrub, mute, volume, full screen — and no
   browser controls. Click play: it plays; drag the scrub: the picture follows.
6. Click the speaker icon: the sound goes off; click again: it returns. Drag the volume: it
   changes. Click full screen: the player fills the screen; press Esc.
7. Repeat 5–6 on **Check** and on Preview’s **Play detection review** player: each has the same bar
   and the same six controls.
8. Find the transcript.
9. **Must see:** a **Transcript** panel in the paper beside the picture (portrait), dark text on the
   panel colour, one or two lines; it does not cover the picture. In a landscape project it sits
   under the picture.
10. **Must see:** a “Speaker” chip, the time, and a “⋯” button on the line. Click the line: the
    player seeks to it. Click “⋯”: **Seek to this line** and **Copy text**. Click **Hide**: the
    lines fold away and the button reads **Show**; click **Show**: they return.
6. Scroll the scenes list and the inspector: each shows a soft fade at the bottom while more is
   below, and the fade goes away at the end.
7. Rotate the window narrow (below ~1000 px) and widen it: the side panels stack, nothing overlaps.

## 6. Render, the estimate, the not-checked count

1. Open **Render**.
2. **Must see, left column:** settings, **Start render**, then the estimate block, then the ready
   facts. Nothing in that column scrolls at 1280×800.
3. Change one clean layer’s range in Edit, then return to Render.
4. **Must see:** **Measuring the fill… N %**, and the old figure marked **Old figure: the edit
   changed since it was measured.** When it finishes: one line with the whole-render time as a
   **range** (for example **≈ 7m 34s–10m 36s**), then the check cost.
5. Read the **Leftover** fact.
6. **Must see:** `Checked N frames · 0 found · 2 lines not checked` (the two short/unreadable lines
   stay visible; they are never counted as clean).
7. **Must see, right column:** the queue with 56 px rows, and **Finished renders** as cards below it,
   each with Play and Show.
8. Scroll the page: the left column stays put; the queue and cards scroll together.

## 7. The fill model folder (Settings)

1. **Settings → Models → Your fill model**.
2. **Must see:** it sits with the other model rows, same height, with **Choose**; the state is one
   line: **None**, **In use · model.onnx**, or **Not usable · reason**.
3. Choose a folder with a `model.onnx` or `model.pt`. **Must see:** **In use · model.onnx** and a
   **Clear** button. Choose a folder without one: a red toast says what is missing, the state does
   not change. Press **Clear**: the state returns to **None**.
4. Render a short span. **Must see:** the fill message says **Your fill model** and the Render screen
   still shows a range and the not-checked count.

## What to report back

- The window sizes you used and any screen where the page still ends early or runs past the window.
- Any text that sits on a picture or on other text.
- The exact words of the estimate line, the “not checked” line and every toast.
- Any scroll you did not expect.
