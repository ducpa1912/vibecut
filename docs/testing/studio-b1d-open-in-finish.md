Superseded by studio-founder-pass-1.md for the full flow.

# Studio B1d: Open in Finish lands on the right cut (founder runs, Claude records)

**What changed:** **Open in Finish** in "Your videos" now opens Finish on that video's story set, story and shape, with that cut selected. Before, it always opened on the first story in 9:16.

**Start the app:** run `python3 app.py`, open `http://127.0.0.1:8787`, then press **Cmd+Shift+R** once.

**You need:** one video with at least two stories, and a render of the **second** story in **4:5**.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | Open a **different** video first (Change video → Sources → any other video) | Start somewhere else | The top bar shows the other video's name. | |
| 2 | **Change video** → **Finished** → on the 4:5 render of the second story, click **Open in Finish** | Jump to that cut | Finish opens on the right video. The top bar shows its name. | |
| 3 | Look at the story list and the shape picker | Story and shape | The second story is selected, and the shape is **4:5 feed**. | |
| 4 | Look at **Versions** | The cut | The render you clicked is marked **Selected**. | |
| 5 | Look at **Publish kit** and **Review link** | Same cut everywhere | Both pickers show that same render. | |
| 6 | Click **Open in Finish** on a render whose story set you deleted or rebuilt | Safe fallback | Finish opens on the video's first story. No error. | |
