# Studio B1b: cancel and time left in Check and Import (founder runs, Claude records)

**What changed:**
- Check has a **Cancel Check** button while it runs.
- Import shows the read's progress and time left, with **Cancel reading**, on the Import screen itself.
- A file upload shows time left and has a **Cancel upload** button.

**Start the app:** run `python3 app.py`, open `http://127.0.0.1:8787`, then press **Cmd+Shift+R** once.

**You need:** a long video (10 min or more), so there is time to press Cancel.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | **Import** → **File** → choose the long video → tick the rights note → **Import video** | Upload time left | Under the button, a bar and "N% · about N s left" (or "estimating" at first). A **Cancel upload** button is next to it. | |
| 2 | While it uploads, click **Cancel upload** | Upload stops | The bar goes away. The status says "Upload cancelled. Nothing was imported." The video is not in Recent videos. | |
| 3 | Import the same video again and let the upload finish | Read time left on Import | A second bar says "Reading the video · N% · (stage) · about N s left", with **Cancel reading** beside it. It moves about once a second. | |
| 4 | Click **Cancel reading** on the Import screen | Read stops | The rail says "Reading stopped" and the top strip offers **Read again**. Recent videos shows the video as Cancelled. | |
| 5 | Top strip → **Read again**, wait for it to finish | Back to normal | It opens **Check** by itself. | |
| 6 | **Check** → **Run Check**, then at once **Cancel Check** | Check stops | The card says "Check was cancelled" with a **Run Check** button. The rail says "Optional · not run". | |
| 7 | **Run Check** and let it finish | A full Check | The findings show, and the rail says "Checked". | |
| 8 | **Run Check** (top right) again, then at once **Cancel Check** | The last Check stays | After a moment the findings from step 7 are back. The rail still says "Checked". | |
