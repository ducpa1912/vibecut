# Studio founder pass 1 — recorded founder pass

Every step below comes from the founder's own recording in
`~/vibecut-lanes/recordings/studio/2026-10-29-101659/` (`trace.zip`,
`network.har`, `storage.json`). The trace has the page snapshots and URLs; the
HAR has the requests, bodies and responses. Steps the recorder did not capture
say so. Nothing here is invented.

**Build:** `4734d35` (`studio`, and `main` at the same commit).

**Start the app** (Studio only, its own port and data):

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-studio
scripts/serve.sh
```

Open `http://127.0.0.1:8795`. Never use 8787. The data lives in
`~/vibecut-lanes/studio`.

Then, in your own Terminal, record the pass:

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-studio
scripts/record.sh
```

**Media** (name only, from `~/vibecut-lanes/media/studio/`):
`cn-1min29s-720x1280-voice-subtiltle.mp4` — 88.8 s, 720×1280, Chinese speech.
The recording used no other media file.

**Recording:** 10:17–10:53, job `77d072b8d44c`. The native file dialog was not
captured; the HAR shows `POST /api/jobs/upload 200` and the job id.

**How to read this:** Expected is what the recording shows, including waits
and the exact errors. The recording was made before the current UI:
- **Build your story** is now **Add story**.
- **Render this story / Render again** is now **+ Add to queue**.
- **Edit this story** is now **Start edit**.
- **Back to Stories** is now **Back to Moments**, and **All stories** is now
  **All moments**.
- Edit said **Step 4**; it now says **Step 3**.
- Finish said **Step 5**; it now says **Step 4**.
- Text, Captions, Effects and Colour were separate tabs; they are now inside
  **Texts & Effects**. Clean is still its own tab.
- Finish queued each story with **Queue 9:16 / Queue 4:5**; it now has a
  **Shape** picker and **Queue all stories · <shape>**.

Rows with a current control name carry
“UI changed since recording: …”. Leave Result empty unless you re-run the step.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1.1 | On **Import**, choose **File**, then choose `cn-1min29s-720x1280-voice-subtiltle.mp4` (the native file dialog is not captured; HAR: `POST /api/jobs/upload 200`) | Import the founder's Chinese clip | The file card shows `cn-1min29s-720x1280-voice-subtiltle.mp4` and `58 MB`; job `77d072b8d44c` is created. | |
| 1.2 | Tick **I own this footage or have the rights to it**, click **Import video** | Pass the rights gate | The button changes to **Importing…**, then the page says **Imported. Reading the video now…**. | |
| 1.3 | Wait on Import until **Reading** finishes | Record the real read | Reading reaches **98% · Transcribing speech · local Whisper**, with the ETA growing from about 1 min to about 5 min. The job becomes **ready** after 368.2 s with 25 scenes. Moments then shows **No moments yet** and **Read speech**; the recording does **not** click **Read speech**. | |
| 1.4 | In Moments, set **Length** to **Extended · 90–180 s**, click **Find moments** | Try a 90–180 s pick on an 88.8 s source | `POST /api/jobs/77d072b8d44c/clip-sets` with `min_s: 90, max_s: 180` returns `0` stories. The note reads **Source is 88.8s; a story needs at least 90s.** | |
| 1.5 | Set **Length** to **Short · 15–30 s**, click **Find moments again** | Get short moments | `POST …/clip-sets` with `min_s: 15, max_s: 30` returns 3 stories: 23.75 s, 19.625 s and 16.017 s. Moments says **3 moments ready**. | |
| 1.6 | On moment 01, click **+ Add to queue** (recording: **Render this story**) | Queue the first short moment in 9:16 | `POST …/stories/st_0010625_0034375/render` with `aspect: 9:16, quality: final`; the recording says **Render started in 9:16.** **UI changed since recording: Render this story is now + Add to queue.** | |
| 1.7 | On moment 02, click **+ Add to queue** (recording: **Render this story**) | Queue the second short moment in 9:16 | `POST …/stories/st_0049375_0069000/render` with `aspect: 9:16`; a second render starts. **UI changed since recording: Render this story is now + Add to queue.** | |
| 1.8 | On moment 03, click **+ Add to queue** (recording: **Render this story**) | Queue the third short moment in 9:16 | `POST …/stories/st_0072750_0088767/render` with `aspect: 9:16`; a third render starts. **UI changed since recording: Render this story is now + Add to queue.** | |
| 1.9 | Set **Shape** to **4:5 feed**, click **Queue all 3** | Queue the same three moments in 4:5 | `POST /api/story-queues` with three 4:5 items for set `cs_8d6be62ea6bd`; the page says **3 stories queued. They render one at a time.** | |
| 1.10 | Set **Length** to **Auto · 20–75 s**, click **Find moments again** | Try the automatic picks | `POST …/clip-sets` with `min_s: 20, max_s: 75` returns 2 stories: 31.875 s and 26.75 s. The note reads **Only 2 non-overlapping stories fit; requested 3.** | |
| 1.11 | Keep **Shape** at **4:5 feed**, click **Queue all 2** | Queue the two automatic picks | `POST /api/story-queues` with two 4:5 items for set `cs_25ffd12d9f00`; the page says **2 stories queued.** | |
| 1.12 | Click **Add story** (recording: **Build your story**) | Open the custom scene picker | The dialog opens on **Add a story** with the scene collage and **Build this moment**. The recording's dialog showed six scenes from 0:00 to 0:26, **Title (optional)**, **Cancel** and **Build this moment**, and **0 scenes · 0 s**. **UI changed since recording: Build your story is now Add story; checkboxes are now a click-to-pick collage.** | |
| 1.13 | Select the scenes at 0:00, 0:05, 0:11, 0:39, 0:41 and 1:20, click **Build this moment** (the recording submits this selection three times) | Try a custom story from spread-out scenes | Each `POST …/clip-sets` has `locks: [0, 1, 2, 9, 10, 22]` and `ban_scenes` for the rest; each returns **No non-overlapping story of 15-180s was found.**, and each empty set is deleted (`DELETE …/clip-sets/<id> 200`). **UI changed since recording: Build your story is now Add story; the current dialog logs the failure and deletes the empty set.** | |
| 1.14 | Select the scenes at 0:00, 0:05, 0:11 and 0:12, click **Build this moment** | Build one custom story from the opening | `POST …/clip-sets` with `locks: [0, 1, 2, 3]` returns one story, **谁懂啊终于把宫崎骏的动漫世界**, 0:00–0:16.25, 16.25 s. **UI changed since recording: Build your story is now Add story; the current builder adds the story to the open set.** | |
| 1.15 | On the new 16.25 s story, click **+ start**, then **− end**, then **+ end** | Try the sentence-edge controls | Three trim requests fail: `start_sentence: 1, end_sentence: 3` and `0/2` return **422 `too_short` — The trimmed story is 11.6s; the minimum is 15s.**; `0/4` returns **422 `range_invalid` — The trimmed range produced no story.** The card keeps its 16.25 s range. | |
| 1.16 | Set **Length** to **Custom range**, **From (s) 30**, **To (s) 90**, click **Find moments again** | Get longer moments | `POST …/clip-sets` with `min_s: 30, max_s: 90` returns 2 stories: **这个我心心念念的梦中庭院** 0:10.6–0:56.4 (45.75 s) and **它里面是科学配比好赤玉土** 0:56.4–1:28.8 (32.392 s). Moments says **2 moments ready**. | |
| 1.17 | On story 01 (45.75 s), click **Start edit** (recording: **Edit this story**) | Open the first moment in Edit | Edit opens with **Shape the story** (now **Shape the moment**), **9:16**, `0:46.8`, and the timeline. **UI changed since recording: Edit this story is now Start edit.** | |
| 1.18 | Click the **4:5** shape button | Create the 4:5 edit | A 4:5 edit is created (`POST /api/jobs/77d072b8d44c/edits` with `aspect: 4:5`); the header reads **Saved 0:46.8 · 4:5 feed**. | |
| 1.19 | Open **Clean**, choose **Cover plate**, click **Add box** | Cover the old subtitle by hand | A **Manual cover** layer appears at box 8 / 72 / 84 / 16 with **Cover plate**; `PATCH …/edits/ed_58010f01dedccdeb62a8667e7db60b5d` stores `kind: plate`. | |
| 1.20 | Change the layer's **Kind** to **Mask** | Try a mask instead of a plate | The same layer becomes **Mask**; `PATCH …/edits/ed_dad3dc3267bffaaa8a68e6332b439fba` stores `kind: mask`. | |
| 1.21 | Choose **Cover plate**, click **Add box** again | Add a second cover under the mask | **Clean layers · 2** shows **Mask** and **Cover plate**; the second `PATCH` stores a `plate` beside the `mask`. The preview shows a black cover over the old subtitle. | |
| 1.22 | Open **Texts & Effects → Text** (recording: the **Text** tab), choose **Lower third**, click **Add text** | Add a lower-third text layer | A text layer is added at 0:07.316–0:10.316 with **Name or detail**, **bottom-left**, box 64 / 14. `PATCH …/edits/ed_8c07b7aa4b03ccfe7eb130170571a607` stores a `lower_third` graphic. **UI changed since recording: Text, Captions, Effects and Colour are now inside Texts & Effects.** | |
| 1.23 | Change the text layer's **Kind** to **Hook card** | Make the text a hook card | The layer becomes **Hook card**, **top-center**, box 76 / 16; `PATCH …/edits/ed_f87fc8cfac45a7cf018b60e9074e6cc2` stores a `hook` graphic. | |
| 1.24 | Open **Texts & Effects → Colour**, choose **Warm film**, then **Vivid pop**, then **Teal and orange**, then **Vivid pop** again | Try the colour presets | Each choice saves a `color` object: `warm_film`, `vivid_pop`, `teal_orange`, then `vivid_pop` again. The recording ends on **Vivid pop**. **UI changed since recording: Colour is now inside Texts & Effects.** | |
| 1.25 | Open **Texts & Effects → Captions**, click **Build captions** | Build caption lines from the scene text | `POST /api/jobs/77d072b8d44c/captions` returns track `cap_e413d3e160d1413f` with 16 cues; the page says **Built 16 caption lines**. **UI changed since recording: Captions is now inside Texts & Effects.** | |
| 1.26 | Open **Audio**, set **Mode** to **Original with music** | Add a music bed under the source sound | `PATCH …/edits/ed_85c9f311b5e1003e08bc6c5271bf0ba8` stores `mode: original_bed` with duck `-12 dB`. | |
| 1.27 | Set **Mode** to **Voice-over** | Try a new voice over the story | `PATCH …/edits/ed_fa13766d44a8f0a0c2876f3b0be1e323` stores `mode: voice_over` with voice **Tingting**. | |
| 1.28 | Set **Mode** to **Music only** | Try music without the source sound | `PATCH …/edits/ed_8f6d6b6199320642b9ec25503a2b4ccb` stores `mode: music_only`. | |
| 1.29 | Click **Next: Finish** | Go to Finish | Finish opens on **Review**, with the render card and queue below it. | |
| 1.30 | In **Render**, set **Shape** to **4:5 feed**, click **Queue all stories · 4:5** | Queue both edited moments in 4:5 | The current UI queues both stories in 4:5 with `POST /api/story-queues`. In the recording this was two clicks, **Queue 4:5** on story 01 and then on story 02; the HAR records both 4:5 items. **UI changed since recording: per-story Queue 4:5 is now Shape + Queue all stories.** | |
| 1.31 | Set **Shape** to **9:16 vertical**, click **Queue all stories · 9:16** | Queue both edited moments in 9:16 | The current UI queues both stories in 9:16. In the recording this was two clicks, **Queue 9:16** on story 01 and then on story 02; the HAR records both 9:16 items. Four queue items are now in the queue. **UI changed since recording: per-story Queue 9:16 is now Shape + Queue all stories.** | |
| 1.32 | Wait for the renders, then play the cut in **Review** | Review the finished moment | The queue shows 4 items working. The Review card later shows **Version 2 · Edit version 2 · Final · Oct 29 · 9:16**, the player at **0:00 / 0:46**, and the banner **Render finished. New versions are ready.** | |

## How to finish the recording

Press Ctrl-C in the Terminal where `scripts/record.sh` is running, or close the
app tab. **Wait until it prints `Saved …`** before closing anything else. If a
recording is damaged, record it again.
