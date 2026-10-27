# Wave 3 live checklist (founder runs, Claude records)

**Before you start:**
- Start the app with Clean enabled: `VIBECUT_ENABLE_CLEANUP=1 python3 app.py`.
- Close other heavy apps, so the timings mean something.

**Videos:**
- A: `~/Downloads/Comment JOYLO and Ill send you the link!  … See more.mp4`
- B: `~/Downloads/天呐我把童话书里的花园搬进了现实太美了 - rednote.mp4`

Run every step on both A and B unless the step says otherwise.

| # | Action: where to click | Intent: what it proves | Expected | Result A | Result B |
|---|---|---|---|---|---|
| 1 | Studio **Import**: choose the file. Leave the rights box unticked. | The rights gate starts locked. | Import works. | | |
| 2 | **Check**: wait for the report. | Detection. | A: the word-pop captions are listed as subtitles, the UI text as "screen text" with no action, and the watermark is refused. B: the Chinese subtitle line is in the lower band. | | |
| 3 | **Check**: tick the rights note, then **Run Check** again. | Rights are stored on the server. | The note shows as recorded. | | |
| 4 | **Stories** → first story → **Edit → Clean**. | Clean auto-fill. | The covers are filled. A: no cover on the screen-recording UI text. B: a plate over the subtitle. | | |
| 5 | Scrub the preview at 1 s, 5 s and 15 s. | Visual quality. | The old text is gone. The covers don't hide faces. Note any visible patch. | | |
| 6 | **Effects**: add punch-in, an arrow and a colour preset. | Compose. | The preview updates. | | |
| 7 | **Audio**: upload a music file, set the mode to "original + bed", then go back to **Effects** and click **Snap selected**. | Beat snap on an uploaded bed (fixed in review). | It shows the BPM and the effect moves. | | |
| 8 | Render the story (9:16, final). Note the story length, and time it from click to ready. | Render speed, target ≤ 2× story length. | The video plays and has every layer. | | |
| 9 | Open the rendered video and check the cleaned area. | Residual old text. | No old text is readable. | | |
| 10 | B only: in the browser, open `/_ductator` or ask Claude to call `POST /api/jobs/<id>/cleanup/residual` with 60 frames. | Re-check the 500 seen in review. | 200 with `residual_pct` ≤ 0.5. If you get 500, copy the terminal error. | — | |

Tell Claude for each step: pass or fail, what you saw, any time you measured, and any error text exactly as shown.
