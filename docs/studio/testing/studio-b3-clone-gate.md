# Studio B3: voice cloning shows only when voice_room is on (founder runs, Claude records)

**What changed:** Edit → Audio shows **Clone the video's voice** only in a build with the `voice_room` feature on. With the feature off, nothing about cloning appears and no clone search starts. The default development build has it on; the Classic beta build has it off.

**Start the app:** ask Claude to start each build for you. For the on build: `python3 app.py`. For the off build: `VIBECUT_EDITION=all VIBECUT_FEATURES= python3 app.py`. Open `http://127.0.0.1:8787`, then press **Cmd+Shift+R** once after each start.

**You need:** one video with at least one story, opened in Studio for both builds.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1 | On the **on** build, open a video → **Edit** → **Audio** | Button is visible | A **Clone the video's voice** button sits under the voice controls. | |
| 2 | Click **Clone the video's voice** | Open the block | The block opens with a name field and **Find the best voice clips**. | |
| 3 | Stop the on build, then start the **off** build (`VIBECUT_EDITION=all VIBECUT_FEATURES=`), reopen the video | Different build | Studio still opens, and `/api/settings` reports an empty feature list. | |
| 4 | In the off build, open the same video → **Edit** → **Audio** | Button is hidden | No **Clone the video's voice** button and no clone text anywhere in Audio. | |
| 5 | Stay in Audio for a minute, then look at the server window | No clone request | No voice-candidate request is made while the feature is off. | |
| 6 | In the on build, open **Setup** → **My voice** | Known follow-up | The panel still appears; gating it is a separate follow-up, not part of this test. | |
