# Classic beta pass 2 — founder test script

**Build:** `classic` at `c7032b8`. Nothing here is verified until you run it. An automated walk is not evidence; only your Result column counts.

**Recorded results.** No founder pass has been run at `c7032b8` yet. Write the hash you actually tested, the date and the outcome here, then fill the Result column. `scripts/release.sh` needs that same hash before a beta tag.

| Hash tested | Date | Outcome | Notes |
|---|---|---|---|
| `c7032b8` | — | not run | — |

**Start the app:** open Terminal and run these lines. Classic has its own port,
data folder and media folder. Use port **8796**, never 8787.

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic
eval "$(scripts/lane-env.sh classic)"
python3 app.py
```

Then open `http://127.0.0.1:8796` in your browser. The first run creates `~/vibecut-lanes/classic`; your normal VibeCut data is untouched.

**Videos to use.** Classic's media folder is `data/media/` in the Classic checkout (gitignored). Keep your clips there and pick them by role. Nothing in this pass generates media, and no clip is copied into the project.

| Role | What it must be | Used by |
|---|---|---|
| **A** | about 30–60 s, vertical 9:16, one person speaking | 2.1–2.4, 3.x, 5.x |
| **B** | 5 minutes or longer, spoken | 6.x (Clip Set) |
| **C** | about 1–2 min, speech in another language | 4.3 (translation) |
| **D** | vertical 9:16 talking head with burned-in subtitles | 3.6 (shape) |
| **E** | about 1 min, no speech, music bed only | 2.4.3 (speech off) |
| **Music** | any music track, 30 s or longer | 4.5, 4.7 |
| **Voice** | your own voice recording, 20 s or longer | 4.10 |
| **URL** | `https://www.youtube.com/watch?v=jNQXAC9IVRw` | 2.3 |

A cloud key is needed only when this machine has no native engine for the chosen capability. The platform row at the top-right says **On-device AI**, **Cloud AI** or **Mixed AI**; Setup shows which capability uses which route.

Send me pass or fail for each step, what you saw, any times you measured, and any error text exactly as shown. I fill in the Result column.

## 1. Start and first run

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1.1 | Run the commands above, then open `http://127.0.0.1:8796` | A clean Classic beta build | The Classic page opens with **Drop a video**, **Paste a video link**, **Creator** and **Setup**. No Studio view opens. | |
| 1.2 | Look at the top-right status | Capability check | It says **On-device AI**, **Cloud AI** or **Mixed AI** for this machine, and a health line such as **vision · whisper**. It does not promise **local only** on a machine that needs a cloud route. | |
| 1.2.1 | Open **Setup** → **Intelligence**, **Transcription** and **Voice over** | Route per capability | Each section names the active route or says it is not configured. The top pill matches whether any cloud route is active or a cloud key is saved. | |
| 1.2.2 | Switch the language to **VI** and back to **EN** | UI language is curated | Navigation and task labels change; product names, acronyms and provider names stay as designed. User job titles and transcript text never change. | |
| 1.3 | If this is the first run, read the banner at the top | First-run nudge | A one-line banner says **Optional: add keys and voices in Setup** with a button that opens Setup. | |
| 1.4 | Click **Open Setup** in the banner → **Save setup** → close Setup with **×** → reload the page | The nudge is not repeated after Setup was saved | The banner is gone. | |

## 2. Import

### 2.1 Choose a file (drag or click)

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.1.1 | Drag video **A** onto **Drop a video**, or click it and choose the file | File import | A file card shows the name, duration and size. The card has a **×** button. | |
| 2.1.2 | Read the line under **Drop a video** before a file is chosen | Local-only promise | It says **or click to choose · files stay on this machine**. The aside under **The cut** says **On-device AI on supported Macs; cloud AI where native engines are not available. No watermark.** | |
| 2.1.3 | Click **×** on the card, then drag **A** again | Removing and re-adding a file | The card clears, then the video returns with no error. | |

### 2.2 Local path

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.2.1 | Click **Use a local path instead**, paste the full path to video **A**, click **Load** | Path import reads in place | The file card appears and a toast says **Video loaded in place.** No file is copied. | |
| 2.2.2 | Click **Dissect video** | No attestation step | Analysis starts immediately. No rights dialog or own-footage tick appears. | |
| 2.2.3 | Read the line under the import controls | Responsibility notice | It says **You are responsible for having permission to edit this footage.** | |

### 2.3 URL

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.3.1 | Paste `https://www.youtube.com/watch?v=jNQXAC9IVRw` into **Paste a video link**, click **Get video** | URL import with yt-dlp | The provider label shows **yt-dlp**, then a download/progress view starts. No Docker is needed. | |
| 2.3.2 | Wait for the result view | URL import finishes | The job opens with the title **Me at the zoo**, about 19 seconds, 4 moments, and a hook. | |
| 2.3.3 | Click **Recent cuts** → the new URL job | The download is a normal job | The row shows the title and **ready**, and it opens again. | |

### 2.4 Speech

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.4.1 | Under the import card, check **Transcribe speech** (it ticks itself when the file has audio, Whisper is installed and the clip is short; otherwise tick it), then import video **A**. Dissect starts by itself; there is no separate speech step. | Speech analysis | The result meta line includes **whisper** or the local speech provider, and **CC · transcript** appears under the hook. | |
| 2.4.2 | Click **CC · transcript** | Transcript view | Timed lines appear. Clicking it again hides them. | |
| 2.4.3 | Import video **A** once more with **Transcribe speech** unticked | Speech off is distinct from speech failure | No transcript button appears, and no failure notice appears. | |
| 2.4.4 | If a speech-on job returns no transcript, read the result view | A speech failure is not silent | A notice says **Speech was on, but no transcript came back.**, names the engine that failed (for example **Local Whisper: No transcript returned.**), and offers **Retry speech**. Click **Retry speech**: the transcript arrives and the notice goes away. | |

## 3. Smart Cut: plan, render, hooks, edit

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 3.0 | Scroll to **Moments**, click **Show all N** (N is the moment count) | The strip becomes a vertical collage | The rail hides. Several moment cards fill each row, and **Show less** brings the strip back. No full-width scene cards. | |
| 3.1 | Open video **A**, then click **15s**, **30s**, **60s** in the **Smart Cut** section | Plan lengths | Each tab rebuilds the timeline and the button text changes to **Render 15s reel**, **Render 30s reel** or **Render 60s reel**. The total time is close to the target. | |
| 3.2 | Click **Render 30s reel** | A final render | A progress bar runs, then the player appears. The cut reaches **ready** with a poster. | |
| 3.3 | Click **Draft** next to Render | A fast draft | A second, shorter render finishes and the player shows the draft cut. | |
| 3.4 | Start another render, then click **Cancel** while it runs | Cancel is honest | The render stops, says **Cancelled**, and the earlier ready cut stays available. | |
| 3.5 | Open **Advanced**, tick **Captions**, render again | Burned-in captions | Captions are visible in the player and the render note includes **captions**. | |
| 3.6 | Open **Advanced** → **Platform preset** → choose **TikTok**, **Reels**, **Shorts**, **Square**, **Landscape** | Presets set shape | The **Aspect ratio** select changes to the matching shape (9:16, 9:16, 9:16, 1:1, 16:9). Render again and the player shape matches. | |
| 3.7 | Open **Advanced** → **All 15/30/60** | Render all three lengths | Three renders queue in order. Each finishes ready. History gains three rows. | |
| 3.8 | Open **Advanced** → **A/B hooks** | Hook variants for the same length | Up to three renders queue, one per top hook. Each finishes ready and gets its own **History** row; **Download reel** on each row plays that hook's cut. | |
| 3.9 | Click **Pick another hook →**, choose a different moment, then **Reset hook** | Hook override | The timeline and hook panel change to the chosen moment. **Reset hook** appears; clicking it restores the automatic hook. | |
| 3.10 | Click **Hook lab →**, look at the cards | Hook candidates | Up to eight cards show a thumbnail, a hook score badge, time, length and beats. Click one card; it becomes the hook. | |
| 3.11 | Click **Edit cut** (the button changes to **Editing…**). On a clip, click **−** (trim 0.25 s), **↑ / ↓** (move) or **✕** (remove). Keys also work: **← / →**, **Alt+← / →**, **− / +**, **Del** | Manual cut edit | The edit bar appears with the key hint. The timeline and the clip lengths change immediately. | |
| 3.12 | In edit mode, type a name in **Variant name**, click **Save variant**, then click **Done** | Saved variant | A toast says **Variant saved.** and a chip **name · length** appears next to **Save variant**. Click the chip to load it: the timeline returns to that cut and a toast says **Loaded “…”**. | |
| 3.13 | Click **✕** on a saved variant | Delete a variant | The chip disappears. The render stays. | |
| 3.14 | With an edited cut, click **Render 30s reel** | Render the cut on screen | The render uses the edited clips, not the automatic plan. | |
| 3.15 | Choose **New voice-over**, pick a cloud voice engine with no key (for example HeyGen) | A blocked render says why | A standing notice above **Render** names the engine, offers **Open Setup**, and Render, Draft, All and A/B are disabled. Hovering a disabled button shows the same reason. | |

## 4. Audio, voice and music

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 4.1 | Open the **Edit** section → **Copy, sound, text**. Leave **Mode** on **Original**, render | Original audio | The render note says **original audio** and the source speech is heard. | |
| 4.2 | Click **New voice-over**, then render | New voice over the original bed | The render note says **voice-over**, not **original audio**. The new voice is heard over the original audio. | |
| 4.3 | Click **Dub voice**, choose a **Language** in **Copy** (for example Vietnamese), then click **Story cut** | One full translation per language | The badge shows **Translating…** while the full translation runs, then **✓ Translation ready**. It stays on disk: the next job does not translate that language again. | |
| 4.3.1 | Click **Story cut** again with the same language, cut and style | The ready translation is reused | The script comes back far faster than the first run and no translation starts again. **Retry translation** is the only control that clears the cache. | |
| 4.3.2 | Change **Script style** to Viral, click **Story cut** | Only the script reruns | The note starts with **Translation reused ·**; the badge stays **✓ Translation ready** and no new translation runs. | |
| 4.3.3 | Click **Story cut** a second time with the same language and style | Reuse is real | The same script returns in about a second. | |
| 4.4 | Click **Music**, choose **Generate** with no MiniMax or OpenRouter key | An unavailable engine blocks the render | A warning says **Music generation needs a MiniMax or OpenRouter key. Add one in Setup, or choose Use my BGM.** Render, Draft, All and A/B are disabled. | |
| 4.5 | Click **Music** → **Use my BGM** → **Choose BGM**, pick your own music file, then render | Own music | The track name and length appear, the bed plays under the cut, and the render note says **music bed**. | |
| 4.6 | Click **Music** → **Generate** with a MiniMax or OpenRouter key saved in Setup | Generated music | The generate options are selectable, a bed is generated, and the render finishes with music. | |
| 4.7 | Click **New voice + music**, choose **Generate**, pick a voice, choose **Use my BGM**, render | New voice + new music | The render note says **new voice + music**. Both are heard. | |
| 4.8 | In **Copy**, click **Story cut** | Script write | A script appears under the audio panel. It is not spoken until you press play. | |
| 4.9 | Click **Generate voice sample**, then **▶** next to it | A voice sample, then play | The status line reads **Generating a short voice preview…**, then **Voice preview ready.** **▶** plays the sample and the render is unchanged. | |
| 4.10 | Click **Use my recording** → **Choose recording**, pick your own voice recording, then **Generate voice sample** and **▶** | Own recording | The status says **Your recording replaces the generated voice.**, the recording is fitted to the cut length, and **▶** plays it. | |
| 4.11 | In **New voice-over** or **New voice + music**, open **Automation mixer**, click a lane to add a node, drag it, double-click it | Mixer | The node moves and the readout changes. **Reset 100%** and **Flatten** restore the flat line. | |
| 4.12 | Click **Original** in **Mode** after using the mixer | Mixer hides in Original | The mixer panel is hidden or shows no automation for the Original mode. | |

## 5. Result view: history, export, review link, clean and delete

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 5.1 | Open **History** | History list | The header reads **N renders · M events**, not a raw attempt count. Rows for renders, script, translation and rewrite show a type, status, length, time and any problem. | |
| 5.2 | Click a **render** row → **Download reel** | The exact cut, not the newest cut | The file plays the cut from that row, even after A/B hooks or All 15/30/60 rendered newer files. | |
| 5.3 | Click a **script** row → **Restore script** | Restore a saved script | The fields return to that snapshot and a toast confirms the restore. | |
| 5.4 | Click **Delete** on a history row | Delete one attempt | The row disappears. Other history rows stay. | |
| 5.5 | With a ready cut, click **SRT**, then **VTT** | Caption export | Each button downloads a non-empty file with timed cues. | |
| 5.6 | Click **EDL**, then **XML** | Edit export | Each downloads a non-empty file. With an edited cut loaded, the file lists the edited clips. | |
| 5.7 | Open the video **A** job imported with **Transcribe speech** off (step 2.4.3), then click **SRT**, then **VTT** | No transcript is not an empty file | Each shows a toast: **This cut has no transcript, so there are no captions to export. …** No file downloads and no new tab opens. | |
| 5.8 | Click **Review link** next to a ready cut | Share the cut on screen | A review link is copied. It opens the same cut, with the right length and shape. | |
| 5.9 | Change the hook or render a newer cut, then make another **Review link** from the older cut | The link stays on the shown cut | The older link still plays the older cut, not the newest render for that length. | |
| 5.10 | Choose **Work files** in the Clean profile, click **Clean** | Clean asks for confirmation | A native confirmation names what Clean deletes and what it keeps. Confirm to continue; Cancel leaves everything. | |
| 5.11 | Confirm the Work files Clean | Clean work files | A toast lists what was removed. The source video and the ready renders stay. | |
| 5.12 | Choose **All but source** in the Clean profile, click **Clean**, confirm | Clean profile | The confirmation names the wider deletion, the job stays open, and no error appears. | |
| 5.13 | Click **Delete** on a throwaway job, confirm | Delete a job | The job leaves **Recent cuts** and its page returns to ingest. | |
| 5.14 | Go back to **Recent cuts** | Recent list | Each local job shows a thumbnail or scene count, duration, date and status. A live job cannot be deleted and says why. | |
| 5.15 | In Creator → **Queue**, open **Compatibility · source batches (15/30/60)**, paste two local paths, choose **Analyze only**, click **Create batch** | A batch without attestation | The batch starts. No rights tick or 409 appears. Each item gets a job id and a state. | |
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
| 8.1 | Click **Setup** at the top right | The Setup dialog opens | It shows **Cloud, optional** with **This machine**, Intelligence, **Video links · yt-dlp**, **RedNote · XHS**, Transcription, Voice over, **Voice fit**, Optional packs, Rights lock and **Save setup**. | |
| 8.1.1 | Read **This machine** at the top of Setup | The capability rows are visible from Classic | One row each for **STT / transcript**, **TTS / voice**, **Vision / text** and **Translation**, naming the route for this Mac. The badge matches the top-right pill. | |
| 8.2 | Intelligence → **Test OpenCode** | OpenCode login check | It says **OpenCode Go replied.** with a model name and seconds. | |
| 8.3 | Paste an OpenRouter key, click **Test OpenRouter**, then **Save setup** | OpenRouter key | The test says **OpenRouter replied.** After saving it says **Saved on this Mac.** The key is not shown again. | |
| 8.4 | Clear the OpenRouter key and click **Test OpenRouter** | An honest missing-key message | It says **OpenRouter model check failed. No OpenRouter key.** | |
| 8.5 | Video links → **Test yt-dlp** | Downloader check | The chip says **Ready · <version>** and the detail says no sidecar is needed. | |
| 8.7 | RedNote · XHS → **Test XHS** with no service running | An honest offline message | It says the XHS service is not reachable and suggests starting xhs-get. | |
| 8.8 | Transcription → choose a spoken language, click **Check local STT**, then **Live STT** | Local speech check | **Check local STT** says local STT is ready. **Live STT** generates a test clip and transcribes it. | |
| 8.9 | Voice over → paste a MiniMax key, click **Check TTS**, then **Live TTS** | Local/cloud voice check | **Check TTS** lists the ready engines. **Live TTS** plays a short sample. | |
| 8.10 | Voice engines list | Every voice engine and what it needs | Apple voices, Kokoro, HeyGen, Fish, Gemini, MiniMax and ElevenLabs each show **Ready** or **Needs setup**, with the missing key or pack named. No fake install button appears. | |
| 8.11 | Optional packs | Honest pack status | Speech, Voice and Separation each show **Installed**, **Ready** (the engine already works on this Mac, for example Whisper installed another way) or **Not installed** with its download size. Nothing downloads from Classic. | |
| 8.12 | Rights lock | The import gate | The toggle shows the current state. Turning it off removes the import dialog; turning it on restores it. | |
| 8.13 | Paste an ElevenLabs key, click **Save setup**, reopen Setup | A saved key round-trip | The key field is blank and a status says the key is saved. The key is never returned by the API or shown in the page. | |
| 8.14 | Fill the other key fields: **API key · optional** (OpenCode), **Service URL**, **Access token · friends mode** and **Cookie · one-shot handoff** (XHS), then **Save setup** | Every key field is real and saved | Each field accepts text, reopens with a configured/blank state, and no saved secret is echoed back into the page. | |

## 9. Trust checks (current)

These are the current T1–T6 checks. They replace the T1–T6 block in `classic-beta-pass-1.md`, which is historical at `1652c92`. Every quoted line below is the string this build shows; `tests/test_classic_trust_*.py` asserts it.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| T1.1 | Read the pill at the top right, then open **Setup** → **This machine** | The privacy claim matches the machine | The pill reads **On-device AI**, **Cloud AI**, **Mixed AI** or **AI** (before data loads). No screen says **Local by default** or **No cloud. No account. No watermark.** The aside under **The cut** reads **On-device AI on supported Macs; cloud AI where native engines are not available. No watermark.** | |
| T1.2 | Save any cloud key, or choose a cloud voice or music engine, then look at the pill | A cloud route is visible | The pill turns **Cloud AI** or **Mixed AI** and still names the capabilities nearby. | |
| T2.1 | Open **Edit** → **Copy, sound, text** → **Sound** → **Voice** and choose a cloud voice | A paid click is named before it | Under the actions: **<provider> · sends the preview line and script text · may cost credits.** Local engines such as Apple say or Kokoro show no cost line. | |
| T2.2 | **Sound** → **Music** → **Generate** → **AI · MiniMax Music**, then **AI · OpenRouter Lyria 3** | The provider name follows the engine | **MiniMax Music · sends a music prompt · may cost credits.**, then **OpenRouter (Lyria 3) · sends a music prompt · may cost credits.** | |
| T2.3 | Click **Generate music preview** twice with the prompt unchanged | A cache hit is named | The second status reads exactly **Cached · no new call**. | |
| T2.4 | Set **Language** to another language and wait 10 seconds without clicking **Story cut** | No automatic paid call | No **Translating…** badge starts and no script appears. The translation starts only after **Story cut**. | |
| T2.5 | With a cloud voice or generated music selected, read the note above **Render** | The render's own paid call is named | It ends with **Render calls <provider> · may cost credits.** With Apple say, Kokoro or your own files, no such line appears. | |
| T3.1 | **Sound** → **Voice** | The button names a sample | It reads **Generate voice sample**, with **▶** beside it. Under it: **The render uses the voice and settings above; this sample is only a preview.** | |
| T3.2 | Click **Use my recording** and choose a file | The render source changes | The note reads **The render uses your recording; the voice list and sample are not used.** | |
| T3.3 | **Sound** → **Music**, choose **Generate** then **Use my BGM** | Preview and final are distinct | **Generate music preview** with **The render generates its own music bed from this prompt.**, then **The render uses the BGM file you choose; this preview is only a listen.** | |
| T3.4 | Generate a sample or preview, then look at the buttons again | The busy label is temporary | The buttons return to **Generate voice sample** and **Generate music preview**. | |
| T4.1 | On a ready job at **9:16**, scroll to **Texts & Effects** | A supported shape is quiet | No shape warning appears. | |
| T4.2 | Change **Shape** to **16:9** before typing anything | The limit is early | Above the controls: **Text overlays and effects render on 9:16 and 4:5. Switch the shape to use them.** The text controls are disabled. | |
| T4.3 | Add a text overlay at 9:16, switch to **16:9**, read the render note | Existing layers are not dropped silently | The note ends with **Text layers are left out at this shape.** The render still runs. | |
| T5.1 | Render a cut and wait for the player | A fresh render is current | No stale line under the ready strip. | |
| T5.2 | Change a hook, a moment, the sound or a text layer | The shown render is now old | **Changed since this render — render again to see it.** appears under the ready strip; the player stays visible. | |
| T5.3 | Reload the page | The warning survives | The stale line is still shown. On a browser with no saved baseline it says **No render baseline on this browser.** | |
| T5.4 | Click the same Render button and wait for **ready** | Only a matching render clears it | The stale line disappears; it stays if you edit while that render runs. | |
| T6.1 | Open the profile menu beside **Clean** | The profiles are visible | The menu offers **Work files**, **Renders**, **All but source**. | |
| T6.2 | Keep **Work files**, click **Clean** | A plain confirmation | A native dialog titled **Clean work files?** says **Deletes: thumbnails, the transcript, extracted audio and deep-read scores.** and **Keeps: the source video, rendered reels and job details.** | |
| T6.3 | Click **Cancel** | Cancel is safe | Nothing is removed and the button still reads **Clean**. | |

## 10. Known issues

Open findings at the time of this script. Do not report these twice.

| # | Area | Issue | Status |
|---|---|---|---|
| F8 | Captions | Some cues split into one-word lines such as **It** or **dump.** This comes from a story clip that ends mid-sentence. | Open |
| — | Media | No test clips or audio files exist for this lane on this Mac. Steps 4.5, 4.7 and 4.10 wait for your own music and voice files. | Blocked on files |
| — | Story cut | The first script for a new language takes 1–3 minutes. Later scripts for the same cut and style are cached and take about a second. | Expected |

## 11. Evidence rule

Only your Result column counts. An API call, a script, or an automated walk is not a pass. If a step looks wrong, write the exact label, toast or console text; do not fix the sentence to match the screen.

**When you finish:** press **Ctrl+C** in the Terminal window to stop the app. Your test data stays in `~/vibecut-lanes/classic`; delete that folder when you no longer need it.
