# Studio B1c: "Load more" in Your videos (founder runs, Claude records)

**What changed:** "Your videos" shows the first 60 finished videos and the first 30 sources. A **Load more** button at the bottom adds the next page under the list.

**Start the app:** run `python3 app.py`, open `http://127.0.0.1:8787`, then press **Cmd+Shift+R** once.

**You need:** more than 30 imported videos, or more than 60 finished renders. With fewer, step 2 and step 5 expect no button.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | Top bar → **Change video** → **Sources** | First page | Up to 30 videos, newest first. | |
| 2 | Scroll to the bottom of the list | The button | A **Load more (N more)** button, where N is how many are left. | |
| 3 | Click **Load more** | Next page | More videos appear under the first ones. The list does not jump back to the top. No video shows twice. | |
| 4 | Keep clicking until the button is gone | The end | The last page shows and the button disappears. | |
| 5 | **Finished** tab, scroll to the bottom | Same for renders | With more than 60 renders, **Load more** works the same way. | |
| 6 | Type a word in the search box | Search restarts paging | The list shows only matches from the first page again, with its own **Load more** if needed. | |
