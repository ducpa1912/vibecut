# Studio B2: Finish shows render warnings (founder runs, Claude records)

**What changed:** Finish now shows the notes a render recorded, such as **Music bed skipped: …**, under its version row and once above the selected cut. Before, only Classic History showed them, so a cut could look clean in Finish while music was missing.

**Start the app:** run `python3 app.py`, open `http://127.0.0.1:8787`, then press **Cmd+Shift+R** once.

**You need:** one video with a render that shows a warning in Classic History (for example, music chosen but the bed was skipped), or any render whose Classic History row shows a warning.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | Open the video → **Finish** → pick the story and shape of the render that warns | Find the cut | The Versions list shows that render. | |
| 2 | Look under the version row | Warning on the row | A small amber line reads the same warning Classic History shows (for example, **Music bed skipped: …**). | |
| 3 | Look just under the **Versions** heading, above the player | Warning without scanning rows | The same warning appears once near the selected cut. | |
| 4 | Choose another version, then look under the heading again | Warning follows the cut | The line shows the chosen cut's warnings, or disappears when that cut has none. | |
| 5 | Open a failed render's row in the same list | Failure stays separate | The row still shows its failure reason, not a warning line. | |
| 6 | Open Classic History for the same video (`/?classic=1`) | Same note both views | Classic shows the same warning text. | |
