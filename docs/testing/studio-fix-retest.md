Superseded by studio-founder-pass-1.md for the full flow.

# Studio fix retest (founder runs, Claude records)

**Build:** commit `f40de21`.

**Start the app:** run `python3 app.py`, open `http://127.0.0.1:8787`, then press **Cmd+Shift+R** once. Your browser still holds the old Studio files. After this fix it always checks for new ones.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | Top bar → **Change video** | Video library pop-out | A pop-out lists your videos with thumbnail, length, date, story count and status, plus a search box and **Import a new video**. | |
| 2 | In the pop-out, click a video that already has stories | Reopen where you stopped | It opens straight into **Edit**. | |
| 3 | Look at the left rail | Step status | Import: "Video ready". Check: "Checked" or "Optional · not run". Stories: "N stories". | |
| 4 | **Edit** → wait about 1 s | Preview shows the video | A real frame, not black. | |
| 5 | **Edit** → press **▶** | Sound and smooth playback | Plays with sound. The label says "Fast preview" and the note says "Playing a 540p copy with sound". If you press it right after opening, it first says "Preparing playback…", then plays. | |
| 6 | Pause, then scrub | Exact frame | The frame refreshes. The label says "Exact frame". | |
| 7 | **Safe zones** toggle on | A readable safe-zone overlay | The area the app covers is shaded, the text area has one dashed outline, and the "App buttons" area is shaded on the right. | |
| 8 | **Change video** → **Import a new video** → import a file (Speech is ticked by default) | Progress while reading | The top bar shows "Reading the video · N%" with a bar. The rail shows Import "Reading N%" and the other steps "Waits for reading", greyed out. | |
| 9 | While it reads, click **Stories** in the rail | Locked step explains itself | It doesn't navigate. A note says "Wait for the video to finish reading (N%)". | |
| 10 | Wait for reading to finish | Moves on by itself | It opens **Check**, and the rail updates. No screen stays on "still being read". | |
| 11 | On a video with no stories, click **Edit** | Locked until stories exist | A note says "Pick stories first…". | |
| 12 | **Stories** → **Find stories** → on a card, **Edit this story** | Direct path into Edit | Edit opens on that exact story. | |
| 13 | Switch between steps a few times | Nothing hangs | Each screen opens with its content, not an endless "Loading". | |
