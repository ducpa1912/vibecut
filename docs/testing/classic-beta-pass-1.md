# Classic beta pass 1 — founder test script

**Build:** `classic` at `e1057fa` (the build this pass walked; later fixes are noted in §12).

**Start the app:** open Terminal and run these two lines. Use port **8793**, never 8787.

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic
VIBECUT_EDITION=classic VIBECUT_DATA=~/vibecut-beta-test VIBECUT_PORT=8793 python3 app.py
```

Then open `http://127.0.0.1:8793` in your browser. The first run creates `~/vibecut-beta-test`; your normal VibeCut data is untouched.

**Videos to use:**
- **A:** one short own video with speech, under 1 minute.
- **B:** one 2–3 minute own video with speech.
- **URL:** `https://www.youtube.com/watch?v=jNQXAC9IVRw` (Me at the zoo).
- Optional: one voice recording (`voice.m4a`) and one music file (`music.m4a`).

No cloud key is needed. Setup is optional; the flows below say where a key changes the result.

Send me pass or fail for each step, what you saw, any times you measured, and any error text exactly as shown. I fill in the Result column.

## 1. Start and first run

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1.1 | Run the two commands above, then open `http://127.0.0.1:8793` | A clean Classic beta build | The Classic page opens with **Drop a video**, **Paste a video link**, **Creator** and **Setup**. No Studio view opens. | |
| 1.2 | Look at the top-right status | Engine check | It says **local only** and a health line such as **vision · whisper**. It does not say **engine offline**. | |
| 1.3 | If this is the first run, read the banner at the top | First-run nudge | A one-line banner says **Optional: add keys and voices in Setup** with a button that opens Setup. | |
| 1.4 | Reload the page | The nudge is not repeated after Setup was saved | The banner is gone after **Save setup** was used once. | |

## 2. Import

### 2.1 Choose a file (drag or click)

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.1.1 | Drag video **A** onto **Drop a video**, or click it and choose the file | File import | A file card shows the name, duration and size. The card has a **×** button. | |
| 2.1.2 | Read the note under the card | Local-only promise | It says **Read in place · no copy.** or the file stays on this machine. | |
| 2.1.3 | Click **×** on the card, then drag **A** again | Removing and re-adding a file | The card clears, then the video returns with no error. | |

### 2.2 Local path

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.2.1 | Click **Use a local path instead**, paste the full path to video **A**, click **Load** | Path import reads in place | The file card appears and a toast says **Video loaded in place.** No file is copied. | |
| 2.2.2 | Click **Dissect video** | The rights dialog | A native OK/Cancel dialog says **The rights lock is on.** and **I own this footage or have the rights to it.** Click **OK**. | |
| 2.2.3 | Click **Dissect video** again on a fresh path, then click **Cancel** in the rights dialog | Cancel is honest | The import stops and an error says **Import cancelled. Confirm you own this footage or have the rights to it.** | |

### 2.3 URL

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.3.1 | Paste `https://www.youtube.com/watch?v=jNQXAC9IVRw` into **Paste a video link**, click **Get video** | URL import with yt-dlp | The provider label shows **yt-dlp**, then a download/progress view starts. No Cobalt or Docker is needed. | |
| 2.3.2 | Wait for the result view | URL import finishes | The job opens with the title **Me at the zoo**, about 19 seconds, 4 moments, and a hook. | |
| 2.3.3 | Click **Recent cuts** → the new URL job | The download is a normal job | The row shows the title and **ready**, and it opens again. | |

### 2.4 Speech

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.4.1 | On video **A**, tick **Transcribe speech** (it is on by default for speech videos under 15 minutes) | Speech analysis | The result meta line includes **whisper** or the local speech provider, and **CC · transcript** appears under the hook. | |
| 2.4.2 | Click **CC · transcript** | Transcript view | Timed lines appear. Clicking it again hides them. | |
| 2.4.3 | Import video **A** once more with **Transcribe speech** off | Speech off is distinct from speech failure | No transcript button appears, and no failure notice appears. | |
| 2.4.4 | If a speech-on job returns no transcript, read the result view | A speech failure is not silent | A notice says **Speech was on, but no transcript came back.**, shows the last engine error, and offers **Retry speech** with a **Setup → Transcription** hint. | |

## 3. Smart Cut: plan, render, hooks, edit

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 3.1 | Open video **A**, then click **15s**, **30s**, **60s** under **Reel length** | Plan lengths | Each tab rebuilds the timeline and the button text changes to **Render 15s reel**, **Render 30s reel** or **Render 60s reel**. The total time is close to the target. | |
| 3.2 | Click **Render 30s reel** | A final render | A progress bar runs, then the player appears. The cut reaches **ready** with a poster. | |
| 3.3 | Click **Draft** next to Render | A fast draft | A second, shorter render finishes and the player shows the draft cut. | |
| 3.4 | Start another render, then click **Cancel** while it runs | Cancel is honest | The render stops, says **Cancelled**, and the earlier ready cut stays available. | |
| 3.5 | Open **Advanced**, tick **Captions**, render again | Burned-in captions | Captions are visible in the player and the render note includes **captions**. | |
| 3.6 | Open **Advanced** → **Platform preset** → choose **TikTok**, **Reels**, **Shorts**, **Square**, **Landscape** | Presets set shape | The **Aspect ratio** select changes to the matching shape (9:16, 9:16, 9:16, 1:1, 16:9). Render again and the player shape matches. | |
| 3.7 | Open **Advanced** → **All 15/30/60** | Render all three lengths | Three renders queue in order. Each finishes ready. History gains three rows. | |
| 3.8 | Open **Advanced** → **A/B hooks** | Two hook variants for the same length | Two renders are queued with different hooks. Both appear in the player/variant area. | |
| 3.9 | Click **Pick another hook →**, choose a different moment, then **Reset hook** | Hook override | The timeline and hook panel change to the chosen moment. **Reset hook** appears; clicking it restores the automatic hook. | |
| 3.10 | Click **Hook lab →**, look at the cards | Hook candidates | Up to eight cards show a thumbnail, a hook score badge, time, length and beats. Click one card; it becomes the hook. | |
| 3.11 | Click **Edit cut**, select a clip and use **← / →**, **Alt+← / →**, **− / +**, **Del** | Manual cut edit | The timeline changes immediately. The plan badge says **manual** or the note says **Manual edit**. | |
| 3.12 | In edit mode, type a name in **Variant name**, click **Save variant**, then click **Done** | Saved variant | The variant chip appears under **Advanced**. Click the chip to load it: the timeline returns to that cut and a toast says **Loaded “…”**. | |
| 3.13 | Click **✕** on a saved variant | Delete a variant | The chip disappears. The render stays. | |
| 3.14 | With an edited cut, click **Render 30s reel** | Render the cut on screen | The render uses the edited clips, not the automatic plan. | |

## 4. Audio, voice and music

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 4.1 | Open **Audio · rewrite, voice, music**. Leave **Mode** on **Original**, render | Original audio | The render note says **original audio** and the source speech is heard. | |
| 4.2 | Click **Voice-over**, then render | New voice over the original bed | The render note says **voice-over**, not **original audio**. The new voice is heard over the original audio. | |
| 4.3 | Click **Dub**, then render | Replace only the voice | The render note says **dubbed voice**. The original music/effects remain under the new voice. | |
| 4.4 | Click **Music**, choose **Generate** with no MiniMax or OpenRouter key | An unavailable engine blocks the render | A warning says **Music generation needs a MiniMax or OpenRouter key. Add one in Setup, or choose Use my sound.** Render, Draft, All and A/B are disabled. | |
| 4.5 | Click **Music** → **Use my sound** → **Choose sound**, pick `music.m4a`, then render | Own music | The track name and length appear, the bed plays under the cut, and the render note says **music bed**. | |
| 4.6 | Click **Music** → **Generate** with a MiniMax or OpenRouter key saved in Setup | Generated music | The generate options are selectable, a bed is generated, and the render finishes with music. | |
| 4.7 | Click **Full Replace**, choose **Generate**, pick a voice, choose **Use my sound**, render | New voice + new music | The render note says **new voice + music**. Both are heard. | |
| 4.8 | In **Voice**, click **▶ Rewrite** | Script rewrite | A script appears under the audio panel. It is not spoken until you press play/test. | |
| 4.9 | Click **Test voice** | A voice sample | A short sample plays. The status line names the engine and voice. | |
| 4.10 | Click **Use my recording** → **Choose recording**, pick `voice.m4a`, then **Test voice** | Own recording | The recording is fitted to the cut length and plays. | |
| 4.11 | In Voice-over or Full Replace, open **Automation mixer**, click a lane to add a node, drag it, double-click it | Mixer | The node moves and the readout changes. **Reset 100%** and **Flatten** restore the flat line. | |
| 4.12 | Click **Original** after using the mixer | Mixer hides in Original | The mixer panel is hidden or shows no automation for the Original mode. | |

## 5. Result view: history, export, review link, clean and delete

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 5.1 | Open **History** | History list | Rows for renders, script attempts and uploads show a type, status, length, time and any problem. | |
| 5.2 | Click a **render** row → **Download reel** | The exact cut, not the newest cut | The file plays the cut from that row, even after A/B hooks or All 15/30/60 rendered newer files. | |
| 5.3 | Click a **script** row → **Restore script** | Restore a saved script | The fields return to that snapshot and a toast confirms the restore. | |
| 5.4 | Click **Delete** on a history row | Delete one attempt | The row disappears. Other history rows stay. | |
| 5.5 | With a ready cut, click **SRT**, then **VTT** | Caption export | Each button downloads a non-empty file with timed cues. | |
| 5.6 | Click **EDL**, then **XML** | Edit export | Each downloads a non-empty file. With an edited cut loaded, the file lists the edited clips. | |
| 5.7 | Open video **A** once with **Transcribe speech** off, then click **SRT** | No transcript is not an empty file | An error says there is no transcript for this video and suggests importing with **Transcribe speech** on. No empty download starts. | |
| 5.8 | Click **Review link** next to a ready cut | Share the cut on screen | A review link is copied. It opens the same cut, with the right length and shape. | |
| 5.9 | Change the hook or render a newer cut, then make another **Review link** from the older cut | The link stays on the shown cut | The older link still plays the older cut, not the newest render for that length. | |
| 5.10 | Click **Clean** once | Clean asks for confirmation | The button changes to **Click to confirm**. | |
| 5.11 | Click **Click to confirm** | Clean work files | A toast lists what was removed. The source video and the ready renders stay unless **Renders** or **All but source** was chosen. | |
| 5.12 | Choose **All but source** in the clean menu, then **Clean** twice | Clean profile | The confirmation runs and the job stays open with no error. | |
| 5.13 | Click **Delete** on a throwaway job, confirm | Delete a job | The job leaves **Recent cuts** and its page returns to ingest. | |
| 5.14 | Go back to **Recent cuts** | Recent list | Each local job shows a thumbnail or scene count, duration, date and status. A live job cannot be deleted and says why. | |
| 5.15 | In Creator → **Queue**, open **Compatibility · source batches (15/30/60)**, paste two local paths, choose **Analyze only**, tick **I own these videos or have the rights to them**, click **Create batch** | A batch with the rights lock on | The batch starts. It does not return **409 Confirm you own this footage or have the rights to it.** Each item gets a job id and a state. | |
| 5.16 | Click **Pause**, **Resume**, then **Cancel** on that batch | Batch controls | Pause stops after the current item, Resume continues, Cancel asks for confirmation and then cancels the rest. | |

## 6. Creator: Clip Set and stories

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 6.1 | Click **Creator** at the top right, choose video **B** in **Recent job** | The Creator workspace | The job loads with **Clip Set**, **Captions**, **Preflight**, **Packet**, **Artifacts & Shares** and **Queue** tabs. | |
| 6.2 | Click **Auto Select** with **Stories** set to **3** | Build a Clip Set | Story cards appear with hook, payoff, sentence rows and beat chips. The meta line shows available stories, order and sentence count. | |
| 6.3 | Click **Read Analysis** | Read the evidence | The **Read Analysis** panel opens on **Original analysis** with one card per story, its duration, time range, hook and payoff. | |
| 6.4 | Click the **Beta read** tab, type `no politics` in **Optional read prompt · exclusions only**, click **Run beta read** | Optional ranking | Ranked story cards appear with a rank score, duration and why. Excluded stories are tagged **excluded**. | |
| 6.5 | Click **Tighten first story** with **30s** selected | Tighten a story | A new plan appears under **Filler / silence / punch-ins**. The source cut is not overwritten. | |
| 6.6 | Click **Render story** on a story card | A story render | The card shows a render state and then a ready artifact. The artifact also appears under **Artifacts & Shares**. | |
| 6.7 | Click **Open in Smart Cut** on a story | Story to Classic | The Classic result view opens with the story's clips on the timeline and a manual-cut note. | |
| 6.8 | Edit a sentence order or exclude a sentence, then click **Save edits** | Save Clip Set changes | The card keeps the new order and the meta line updates. | |
| 6.9 | Click **Queue stories** with a 3-story set | Queue three stories | **Queue stories** opens the Queue tab and a toast says **3 stories queued.** The queue runs one story at a time. | |
| 6.10 | On a fresh queue, click **Pause**, then **Resume** | Queue pause and resume | Pause says the current story keeps rendering; Resume continues with no duplicate artifact. | |
| 6.11 | On a fresh queue, click **Cancel** | Queue cancel | The queue says **Cancelled**; waiting items are cancelled and the running render stops. | |
| 6.12 | Click **Queue stories** twice quickly on the same set | No duplicate queue | The second click attaches to the active queue. No failed row and no Version 2 appear. | |

## 7. Creator: captions, preflight, packet and artifacts

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 7.1 | **Captions** → **Target** 30 → **Build caption track** | Caption cues | Timed cues appear in **Cue list**. The meta line shows the cue count and style. | |
| 7.2 | Edit one cue's text, click **Save cues** | Save caption edits | A toast confirms the save. Reloading the track shows the edited text. | |
| 7.3 | Click **Caption preview** | Preview without a render | The poster shows the cue at the chosen **Cue time** in the safe zone. No full render starts. | |
| 7.4 | Click **Download SRT** | Caption export | A non-empty SRT downloads with the edited cue. | |
| 7.5 | **Preflight** → choose a story or artifact → **Run preflight** | Preflight on a clip-set story | The five checks and suggestions show, with no **Render this story first** dead end for a story id. | |
| 7.6 | **Packet** → choose a story with a ready artifact → **Suggest copy** | Local copy fallback | Three titles, a description, 3–8 hashtags, and a pin comment fill blank fields. Titles do not end mid-word. Hashtags are meaningful words, not `#today #want #show`. | |
| 7.7 | Fill or adjust **Title 1**, choose **Cover 1 · seconds** and **Cover 2 · seconds**, click **Build packet** | Build a packet | A packet card appears with titles, description, hashtags and **Download ZIP**. | |
| 7.8 | Click **Download ZIP** | Packet ZIP | The ZIP contains `packet.json`, `copy.txt`, two covers, an SRT and the media file. `packet.json` opens as valid JSON. | |
| 7.9 | Look at **Packets for this job** | Packet history | The packet is listed with its date and a **Download ZIP** button. | |
| 7.10 | **Artifacts & Shares** → **Refresh artifacts & shares** | Artifact list | Ready story renders appear with title, id, status, length, shape and cue count. | |
| 7.11 | Click **Pin** on an artifact, then **Unpin** | Pinning | The tag changes to **pinned** and back. | |
| 7.12 | On an artifact, type a **Review label**, set expiry days, click **Create review link** | Artifact-pinned share | The link is copied and a **review link** tag appears on that artifact. Open it: it plays that artifact. | |
| 7.13 | **Shares** → **Revoke** → **Confirm revoke** | Revoke a link | The link stops working and the tag changes to **revoked**. | |

## 8. Setup from Classic

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 8.1 | Click **Setup** at the top right | The Setup dialog opens | It shows **Cloud, optional** with Intelligence, Video links, Transcription, Voice over and **Save setup**. | |
| 8.2 | Intelligence → **Test OpenCode** | OpenCode login check | It says **OpenCode Go replied.** with a model name and seconds. | |
| 8.3 | Paste an OpenRouter key, click **Test OpenRouter**, then **Save setup** | OpenRouter key | The test says **OpenRouter replied.** After saving it says **Saved on this Mac.** The key is not shown again. | |
| 8.4 | Clear the OpenRouter key and click **Test OpenRouter** | An honest missing-key message | It says **OpenRouter model check failed. No OpenRouter key.** | |
| 8.5 | Video links → **Test yt-dlp** | Downloader check | The chip says **Ready · <version>** and the detail says no sidecar is needed. | |
| 8.6 | Video links · Cobalt → **Test Cobalt** with no service running | An honest offline message | It says Cobalt is not reachable at the configured URL and suggests checking the service or URL. | |
| 8.7 | RedNote · XHS → **Test XHS** with no service running | An honest offline message | It says the XHS service is not reachable and suggests starting xhs-get. | |
| 8.8 | Transcription → choose a spoken language, click **Check local STT**, then **Live STT** | Local speech check | **Check local STT** says local STT is ready. **Live STT** generates a test clip and transcribes it. | |
| 8.9 | Voice over → paste a MiniMax key, click **Check TTS**, then **Live TTS** | Local/cloud voice check | **Check TTS** lists the ready engines. **Live TTS** plays a short sample. | |
| 8.10 | Voice engines list | Every voice engine and what it needs | Apple voices, Kokoro, HeyGen, Fish, Gemini, MiniMax and ElevenLabs each show **Ready** or **Needs setup**, with the missing key or pack named. No fake install button appears. | |
| 8.11 | Optional packs | Honest pack status | Speech, Voice and Separation show **Installed** or **Not installed** with their size. Nothing downloads unless a real install is offered. | |
| 8.12 | Rights lock | The import gate | The toggle shows the current state. Turning it off removes the import dialog; turning it on restores it. | |
| 8.13 | Paste an ElevenLabs key, click **Save setup**, reopen Setup | A saved key round-trip | The key field is blank and a status says the key is saved. The key is never returned by the API or shown in the page. | |

## 9. Known issues

Open findings at the time of this script. Do not report these twice.

| # | Area | Issue | Status |
|---|---|---|---|
| F6 | Hook lab | The badge rounds a half score up while the text rounds it down (for example 33 vs 32). | Open |
| F8 | Captions | Some cues split into one-word lines such as **It** or **dump.** | Open |
| F9 | Packet | No-key copy truncates a title mid-word and uses stop words as hashtags. | Open |


## 10. What was walked by automation

These flows were exercised against a local beta build on port 8793 with scratch data and no cloud keys: URL import (Me at the zoo), path import, plan/render/history/export, batches with the rights tick, queue pause/resume/cancel, packet ZIP, Clean, Delete, Recent cuts, every Setup Test button, Creator Debug **Load job**, **Read Analysis**, **Run beta read**, and preflight on a clip-set story id.

File drop and the native file chooser cannot be driven by automation. Those steps are written for you above.
