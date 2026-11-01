# Classic beta pass 1 — recorded founder passes

This file replaces the earlier draft. Every step below comes from the founder's
own recordings in `~/vibecut-lanes/recordings/classic-pass-1`, `-2` and `-3`
(`actions.spec.js` for the clicks, `session.har` for the requests and results).
A step that the recorder did not capture says so. Nothing here is invented.

**Start the app** (Classic only, its own port and data):

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic
eval "$(scripts/lane-env.sh classic)"
python3 app.py
```

Open `http://127.0.0.1:8796`. Never use 8787.

**Media** (names only, from `~/vibecut-lanes/media/classic/`):
`cn-1min29s-720x1280-voice-subtiltle.mp4`,
`en-53s-1080x1920-subtitle.mp4`,
`en-5mins-640x360-voice-text-overlay.mp4`.
The recordings also used a YouTube Short, `https://www.youtube.com/shorts/GEHJwh9vcaY`.

**How to read this**: Expected is what the recording shows, including errors and
dead ends. `[F#]` points to the Findings section. Leave Result empty unless you
re-run the step.

## Pass 1 — 08:31–08:50, job `c9047febb2b9`

Source: `cn-1min29s-720x1280-voice-subtiltle.mp4` (88.8 s, 25 scenes, Chinese
speech). The recorder did not capture the file dialog; the HAR shows
`POST /api/jobs/upload 200`.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1.1 | Click **Dissect video ↗** (the file choice before it was not captured; the HAR shows `POST /api/jobs/upload 200`) | Import with the rights lock | A native dialog asks **The rights lock is on. I own this footage…**; job `c9047febb2b9` reaches **ready** in 50.2 s with 25 scenes, Chinese speech, **whisper**. | |
| 1.2 | Open `http://127.0.0.1:8796/#job=c9047febb2b9` | Open the finished job | The result view loads with the 30 s plan: 29.7 s, 9 beats. | |
| 1.3 | Click the opening-beat line **Opening beat 0:16.2 – 0:20.8 · 4.6s 养花种菜之所以轻松 Scene 4 is the strongest opening** | Open a moment | The scene drawer opens with the beat detail. | |
| 1.4 | Click **:00 ✓** in the drawer | Use this moment as the hook | The hook moves to that moment and the drawer closes. | |
| 1.5 | Click the drawer backdrop | Close the drawer | The drawer closes with no error. | |
| 1.6 | Click **:00 ✓** again, then the drawer backdrop | Repeat the hook choice | Same result as 1.4–1.5; no error. | |
| 1.7 | Click **Expand** | Expand the moments strip | A second grid of scene thumbnails appears under the horizontal strip. `[F5]` | |
| 1.8 | Click **Collapse** | Close the grid | The grid hides; the strip stays. | |
| 1.9 | Click **Expand** again, then **Expand** once more | Toggle behaviour | The first click opens the grid; the extra click is recorded but changes nothing visible. `[F7]` | |
| 1.10 | Click **Timeline**, then **Timeline** again | Sort moments by time | The list re-sorts; the second click is a no-op. | |
| 1.11 | Click **Best** | Sort by hook score | The strip re-sorts by score. | |
| 1.12 | Drag the **Scrub moments** slider to the start | Move along the strip | The rail scrolls to the first moment. | |
| 1.13 | Click **Edit cut** | Enter manual edit | Clip controls appear on the timeline. | |
| 1.14 | Drag **Scrub moments** to about 21 | Move along the strip while editing | The rail scrolls; the edit state stays. | |
| 1.15 | Click **Voice-over** | Pick a voice mode | The Rewrite/Voice/Music steps show. | |
| 1.16 | Click **Dub** | Replace only the voice | Dub is selected; the rewrite step stays. | |
| 1.17 | Click **Full Replace** | New voice and new music | Full Replace is selected. | |
| 1.18 | In **Language**, choose **Vietnamese** | Set the target language | The select shows `vi`; a translation-status request starts. | |
| 1.19 | Click **▶ Rewrite** | Translate and rewrite the cut | A script arrives after 43 s; History gains script, translation and rewrite rows, all **ok**. | |
| 1.20 | Click the **Music** block (Use your own track, or generate a bed · None / Use my sound / Generate) | Open music choices | The music controls expand; no request yet. | |
| 1.21 | Click empty page space | Dismiss focus | Nothing changes. | |
| 1.22 | In **Voice list**, choose **Kokoro** | Pick a local voice engine | The voice list reloads with 31 Kokoro voices. | |
| 1.23 | Choose **ElevenLabs** | Pick a cloud engine without a key | The list returns 0 voices and the Voice box reads **Add the key in Setup**. `[F8]` | |
| 1.24 | Choose **HeyGen** | Pick the OpenRouter voice engine | The list returns 10 voices (Nadine, Tabitha, Bram, Gareth, Noelle, Meredith…). | |
| 1.25 | Click **Test voice** | Hear the HeyGen voice | `POST /voice/sample` returns **400**: `OpenRouter heygen voice failed: HTTP Error 401: Unauthorized`. `[F2]` | |
| 1.26 | Click **Test voice** again | Retry | **400**: `OpenRouter is quarantined after an auth error; retry in 292.4s.` `[F2]` | |
| 1.27 | Click **Test voice** a third time | Retry sooner | **400**: `OpenRouter is quarantined after an auth error; retry in 289.3s.` `[F2]` | |
| 1.28 | Click **Setup** | Open Setup | Setup opens on **Cloud, optional**. | |
| 1.29 | Click the **Intelligence / OpenCode Go** area | Inspect keys | The OpenCode and OpenRouter key fields show. | |
| 1.30 | Click **Open admin console ↗** | Open the admin console | A new tab opens the admin console with a password form. | |
| 1.31 | Type the admin password and confirmation, click **Create admin** | First admin login | The console opens on **Overview**. Do not write the password in this file. | |
| 1.32 | Click **Keys**, click **Test** twice, click **Models**, click **Refresh catalogs** | Check providers | The console stays responsive; the keys page reports the OpenRouter test result. | |
| 1.33 | Click **VibeCut ADMIN** to return to Classic | Back to Classic | The Classic Setup is still open. | |
| 1.34 | Paste the OpenRouter key into **OpenRouter key · translation/TTS/music fallback**, click **Save setup** | Fix the 401 | `POST /api/settings 200`; no key is echoed back. Do not write the key in this file. | |
| 1.35 | Click the Setup backdrop, then **Test voice** | Retry the voice sample | `POST /voice/sample 200`; a sample plays. | |
| 1.36 | Click the script panel line **Click ▶ Rewrite to translate** | Select the script panel | No request. | |
| 1.37 | Click **▶ Rewrite** | Rewrite again after the key fix | `POST /audio/script` returns **500** after 290.8 s; History adds `script failed`. Exact error: `cannot access local variable 'OPENCODE_LAST_ERROR' where it is not associated with a value`. `[F1]` | |
| 1.38 | Click empty page space twice | Dismiss focus | Nothing changes. | |
| 1.39 | Click **Generate / Use my recording** | Switch voice source | The source choice updates; no request. | |
| 1.40 | Set **Script style** to **Creative** | Change rewrite style | The select shows `Creative · vivid and surprising`. | |
| 1.41 | Set **Language** to **Portuguese**, then **Vietnamese** | Change target twice | Two translation-status requests; no script request. | |
| 1.42 | Click the **Generate / Use my recording / Voice list** area | Focus the voice panel | No request. | |
| 1.43 | Open **History** (header **3 attempts**) | Read history | Three rows: rewrite **ok**, translation **ok**, script **ok**. The header counts worker rows. `[F6]` | |
| 1.44 | Click the **rewrite ok 30s · smooth** row | Inspect a rewrite | The history detail opens for that rewrite. | |
| 1.45 | Click **Voice-over** | Switch mode | The audio mode changes. | |
| 1.46 | Set **Script style** to **Fun**, then **Language** to **English** | Change style and language | No script request while the panel is reset. | |
| 1.47 | Reload `http://127.0.0.1:8796/#job=c9047febb2b9` | Restart the result view | The job reloads **ready** with its ready 30 s render. | |
| 1.48 | Click **Voice-over** | Switch mode again | The audio mode changes. | |
| 1.49 | Set **Language** to **Vietnamese** | Target Vietnamese again | A translation-status request; no script request yet. | |
| 1.50 | In **Voice list**, choose **HeyGen**, then in **Voice**, choose **Weston** | Pick a HeyGen voice | The voice select shows `Weston`. | |
| 1.51 | Click **▶ Rewrite** | Rewrite with HeyGen | `POST /audio/script 200` after 95.9 s; script and history rows appear. | |
| 1.52 | Click empty page space | Dismiss focus | Nothing changes. | |
| 1.53 | Click **Render 30s reel ↗** | Render the cut | `POST /render 200`; the render reaches **ready** in 15.9 s with an artifact and poster. | |
| 1.54 | Click empty page space, then open **History** (header **8 attempts**) | Read the final history | Eight rows: one render, plus three script/translation/rewrite groups (one failed). The header calls all rows attempts. `[F6]` | |

## Pass 2 — 09:07–09:24, jobs `c9047febb2b9` and `a6e2d0a82c9d`

Source: first the existing `c9047febb2b9`, then
`en-53s-1080x1920-subtitle.mp4` (52.9 s, 16 scenes, English speech).

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.1 | Open `http://127.0.0.1:8796/`, click the recent card **cn-1min29s-720x1280-voice-subtiltle.mp4 · 1m 29s · Oct 29 · 25 scenes · ready** | Reopen a finished job | Job `c9047febb2b9` opens ready with its 30 s render. | |
| 2.2 | Click the **VibeCut** brand | Return to ingest | The ingest view shows. | |
| 2.3 | Click **Dissect video ↗**; the native dialog is dismissed by the recorder (the file choice before it was not captured) | Import a new file | `POST /api/jobs/upload 200`; job `a6e2d0a82c9d` is created. The dismissed dialog is recorded as a cancel. | |
| 2.4 | Open `http://127.0.0.1:8796/#job=a6e2d0a82c9d` | Open the new job | **ready** in 49.3 s; 16 scenes, English speech, 30 s plan = 30.0 s, 11 beats. | |
| 2.5 | Click the moment line **Opening beat 0:07.5 – 0:10.0 · 2.5s trading class ships, Scene 2 is the…** | Open a moment | The drawer opens. | |
| 2.6 | Click **Dub** | Replace only the voice | Dub is selected. | |
| 2.7 | Set **Language** to **Vietnamese** | Target Vietnamese | Translation-status request; no script yet. | |
| 2.8 | Click **▶ Rewrite**, then change a setting while it works | Cancel a slow rewrite | The first `POST /audio/script` is recorded as **-1** (aborted in the browser). The server keeps working and later writes a script row. `[F4]` | |
| 2.9 | Click the **Smart Cut** line, the rewrite step, then the result view, then the **Smart Cut** line again | Move around the page | The page stays responsive; no request. | |
| 2.10 | Set **Script style** to **Chill** | Change the style | The select shows `Chill · calm and understated`. | |
| 2.11 | Click **▶ Rewrite** | Rewrite again | `POST /audio/script 200`; History gets a script, translation and rewrite row. The first (aborted) script took 429 s and still appears. `[F3]` `[F4]` | |
| 2.12 | Click the line **Translating the full script,** | Select the working note | No request. | |
| 2.13 | Click **Expand** | Expand moments | The scene gallery opens under the strip. `[F5]` | |
| 2.14 | Click the **Voice / Generate / Use my recording** area | Focus the voice panel | No request. | |
| 2.15 | Click the **Rate** spinbutton | Focus the rate field | No change. | |
| 2.16 | Click **Render 30s reel ↗** | Render the cut | `POST /render 200`; **ready** in 30.2 s with an artifact. | |
| 2.17 | Click the **Test voice** area | Dismiss focus | No request. | |
| 2.18 | Open **History** (header **1 render · 4 events**) | Read history | Four rows: render, rewrite, translation, script. The header separates renders from events. | |
| 2.19 | Open **Advanced** | Inspect advanced settings | The advanced panel opens. | |

## Pass 3 — 09:26–09:33, URL job `1fd96e13474d`

Source: `https://www.youtube.com/shorts/GEHJwh9vcaY`, imported with
**Transcribe speech** ticked. Result: title **Own Your Links Now!**, 39.3 s,
7 scenes, English speech, ready in 25.3 s.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 3.1 | Paste `https://www.youtube.com/shorts/GEHJwh9vcaY` into **Paste a video link**, click **Get video** | URL import | `POST /api/url/inspect 200`, then `POST /api/jobs/from-url 200`; job `1fd96e13474d` starts **downloading**. | |
| 3.2 | Click the **Transcribe speech** check box, tick **Transcribe speech Apple / …** | Speech on | The checkbox is ticked before the job is opened. | |
| 3.3 | Open `http://127.0.0.1:8796/#job=1fd96e13474d` | Open the URL job | **ready** in 25.3 s; 7 scenes, English, 30 s plan = 26.9 s, 6 beats. | |
| 3.4 | Click the scene line **Store Visits · 306 7 20% · 300 visitors** | Open a moment | The drawer opens. | |
| 3.5 | Click **Expand** | Expand moments | The scene gallery opens. `[F5]` | |
| 3.6 | Double-click **Expand**, then click **Collapse** | Toggle twice | The second Expand is a no-op; Collapse closes the gallery. `[F7]` | |
| 3.7 | Click the result view | Dismiss focus | Nothing changes. | |
| 3.8 | Click **Dub** | Replace only the voice | Dub is selected. | |
| 3.9 | Open **Language** and choose **Vietnamese** | Target Vietnamese | The custom list opens; Vietnamese is selected. | |
| 3.10 | Open **Script style** and choose **Viral · punchy hook** | Set the style | The custom list closes; Viral is selected. | |
| 3.11 | Click **▶ Rewrite** | Translate and rewrite | `POST /audio/script 200` after 208.4 s; History gets script, translation and rewrite rows. `[F3]` | |
| 3.12 | Open **Voice list** and choose **OpenRouter HeyGen Voice Turbo** | Pick HeyGen through OpenRouter | The custom list shows the engine; 10 voices load. | |
| 3.13 | Open **Voice** and choose **Sabrina · multi**, then **Gareth · multi** | Pick voices | The select ends on Gareth; no request. | |
| 3.14 | Click **Test voice** | Hear the voice | `POST /voice/sample 200`; a sample plays. | |
| 3.15 | Click empty page space, then **Render 30s reel ↗** | Render the cut | `POST /render 200`; **ready** in 26.9 s with an artifact and poster. | |

## Findings from the recordings

Ranked by severity. "Fixed" means a later Classic commit covers it; the
recording still shows the old behaviour.

| ID | Sev | Pass / step | What happened | Request / exact text | Status |
|---|---|---|---|---|---|
| F1 | P1 | 1.37 | Rewrite returned a server error after 290.8 s and wrote a failed script row. | `POST /api/jobs/c9047febb2b9/audio/script` → **500**; `cannot access local variable 'OPENCODE_LAST_ERROR' where it is not associated with a value` | Fixed in `6ea61c0`; regression test `tests/test_classic_rewrite_error.py` |
| F2 | P1 | 1.25–1.27 | HeyGen voice failed with a 401, then OpenRouter was locked for 5 minutes. Test voice was retried three times. | `POST /voice/sample` → **400**; `OpenRouter heygen voice failed: HTTP Error 401: Unauthorized`; then `OpenRouter is quarantined after an auth error; retry in 292.4s.` and `…289.3s.` | Key problem, not code. Reminder below |
| F3 | P1 | 1.19, 1.51, 2.11, 3.11 | Rewrite sat in **working…** for minutes with no progress or ETA. | `POST /audio/script` latencies: 43.4 s, 95.9 s, 290.8 s (500), 429.0 s, 112.6 s, 208.4 s | Improved after the recordings: 20-line translation batches, ready badge, cache. `1a727db` |
| F4 | P2 | 2.8, 2.11 | Changing a setting mid-rewrite aborted the browser request (`-1`), but the server kept working and later wrote a 429 s script row. | `POST /audio/script` → **-1** (aborted), then a later script row with 429 s | Open, P2: stopping the server-side rewrite needs cancel support in shared `audio.py`; the translation warm-up (`1a727db`) now does the slow part once, so an abandoned rewrite costs one model call |
| F5 | P2 | 1.7, 2.13, 3.5 | **Expand** opened a second scene gallery under the strip, not a vertical collage. | none | Fixed in `582977c`; recordings show the old grid |
| F6 | P2 | 1.43, 1.54 | History called all worker rows "attempts": **3 attempts** then **8 attempts** for one render. | `GET /history` returned 8 rows: 1 render, 3 script, 2 translation, 2 rewrite | Fixed in `6f951be`; header now **N renders · M events** |
| F7 | P3 | 1.9, 3.6 | **Expand** was clicked twice while already expanded; the extra click changed nothing. | none | No change needed: in the current build the button reads **Collapse** once open, and a second click closes the list |
| F8 | P3 | 1.23 | ElevenLabs had no key, and the voice list returned 0 voices with no reason in the list. | `GET /api/audio/voices?engine=elevenlabs` → 200, `voices: []` | No change needed: with no ElevenLabs key the Voice list already reads **Add the key in Setup**; the empty `voices: []` is that case |

No 4xx or 5xx responses appear in passes 2 and 3 other than the pass-1 items
above. The only aborted request is `-1` in pass 2.

## What this file does not cover

Pass 4 has only `server.log`, no `actions.spec.js` and no HAR, so it has no
steps here. File-dialog steps are marked where the recorder did not capture
them. `docs/testing/classic-beta-pass-2.md` describes behaviour added after
these recordings (translation badge, collage, history count); it is not evidence
from the recordings.

## Trust fixes T1–T6

Founder checks for `classic` at `1652c92`. Run them by hand on 8796 with your
own media. The labels and sentences below are exact. T2 checks that reach a
provider may cost credits; read the notice and only click if you accept the
cost. Do not paste keys into this file.

### T1 — honest privacy copy

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| T1.1 | Open the ingest screen, read the note under **The cut** | The promise matches the product | The note reads **Local processing by default. Optional AI features may send data to external providers. No watermark.** | |
| T1.2 | Read the top bar pill | Local state is visible | With no cloud key and a local voice engine the pill reads **Local by default**. | |
| T1.3 | Save any cloud key in Setup, or choose ElevenLabs / MiniMax / HeyGen / Fish / Gemini as the voice engine | Online state is visible | The top pill reads **Online features on**. | |
| T1.4 | Open Creator → **Compatibility · source batches** | The old promise is gone | The chip reads **Local by default**. No screen says **No cloud. No account.** | |

### T2 — cost and data notice before paid calls

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| T2.1 | Choose a voice mode, open **Sound → Voice**, choose **ElevenLabs** (or another cloud voice) | Cloud voice notice | Under the actions: **ElevenLabs · sends the preview line and script text · may cost credits.** The provider name follows the chosen engine. | |
| T2.2 | Choose **Apple say** or **Kokoro** | Local voice has no cost notice | No cost line appears. | |
| T2.3 | Open **Sound → Music**, choose **Generate** as the source and **AI · MiniMax Music** | Cloud music notice | Under the actions: **MiniMax Music · sends a music prompt · may cost credits.** | |
| T2.4 | Choose **AI · OpenRouter Lyria 3** | Provider name follows the engine | The line reads **OpenRouter (Lyria 3) · sends a music prompt · may cost credits.** | |
| T2.5 | Choose **Use my BGM** | Own music has no cost notice | No cost line appears. | |
| T2.6 | Choose a voice mode with a cloud key, set **Language** to a language other than the source | Translation notice before the click | The Copy card shows **OpenCode Go or OpenRouter · sends the transcript text and the cut script · may cost credits.** No **Translating…** badge starts on its own. | |
| T2.7 | Wait 10 seconds after T2.6 | No automatic paid call | No translating badge and no script starts. The paid call begins only after **Story cut**. | |
| T2.8 | With the music prompt unchanged, click **Generate music preview** twice (optional, paid on the first click) | A cache hit is named | The first status is a preview message. The second status reads exactly **Cached · no new call**. | |

### T3 — sample versus final

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| T3.1 | Open **Sound → Voice** | The button names a sample | The primary button reads **Generate voice sample**. Under it: **The render uses the voice and settings above; this sample is only a preview.** | |
| T3.2 | Click **Use my recording**, choose a file | The render source changes | Under the actions: **The render uses your recording; the voice list and sample are not used.** | |
| T3.3 | Switch back to **Generate** | The sample promise returns | The line returns to the T3.1 sentence. | |
| T3.4 | Open **Sound → Music**, choose **Generate** | The button names a preview | The primary button reads **Generate music preview**. Under it: **The render generates its own music bed from this prompt.** | |
| T3.5 | Choose **Use my BGM** | The own-track promise | The line reads **The render uses the BGM file you choose; this preview is only a listen.** | |
| T3.6 | Generate a voice sample, then a music preview (optional, paid) | Buttons restore | The busy label is temporary; the buttons return to **Generate voice sample** and **Generate music preview**. | |

### T4 — shape limit early and at render time

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| T4.1 | Open a ready job at **9:16** | Supported shape is quiet | The Texts & Effects card shows no shape warning. | |
| T4.2 | Change the shape to **16:9**, before typing anything | The limit is early | Above the controls: **Text overlays and effects render on 9:16 and 4:5. Switch the shape to use them.** The text controls are disabled. | |
| T4.3 | Switch back to **9:16**, add a text overlay, then switch to **16:9** | Existing layers are not dropped silently | The render note above the buttons ends with **Text layers are left out at this shape.** | |
| T4.4 | With the T4.3 note visible, click **Render 30s reel** | Render still runs | The render queues and finishes normally. It does not refuse because layers exist. | |

### T5 — changed since this render

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| T5.1 | Render a cut and wait until the player appears | A fresh render is current | Under the ready strip there is no stale line. | |
| T5.2 | Add a text overlay or an effect, or change the music source | The shown render is now old | The line appears under the ready strip: **Changed since this render — render again to see it.** The player stays visible. | |
| T5.3 | Change the hook, a moment, sound or captions | Every edit is covered | The same stale line appears. The player keeps the last finished reel. | |
| T5.4 | Click **Render 30s again** and wait for **ready** | The line clears only for the current state | The stale line disappears when the new render is ready. It stays if you edit while that render runs. | |
| T5.5 | Reload the page after T5.2 | The warning survives a reload | The stale line is still shown for the changed state in the same browser. | |

### T6 — plain Clean confirmation

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| T6.1 | Open the clean menu beside **Clean** | The profile is visible | The menu offers **Work files**, **Renders**, **All but source**. | |
| T6.2 | Keep **Work files**, click **Clean** | Plain confirmation | A native dialog titled **Clean work files?** says **Deletes: thumbnails, the transcript, extracted audio and deep-read scores.** and **Keeps: the source video, rendered reels and job details.** and **Analysis work files can be rebuilt by analyzing again.** | |
| T6.3 | Click **Cancel** | Cancel is safe | Nothing is removed. The button still reads **Clean**. | |
| T6.4 | Choose **Renders**, click **Clean** | Render confirmation | The dialog is titled **Clean rendered reels?** and names **rendered reels, render masters and legacy render files** as deleted, with the source, transcript, thumbnails and job details kept. | |
| T6.5 | Choose **All but source**, click **Clean** | Everything-but-source confirmation | The dialog is titled **Clean everything except the source?** and says the source video and job details stay. | |
| T6.6 | Confirm **Work files** on a throwaway job | The action matches the words | The toast lists what was removed. The source video and ready reels stay. | |

### Not covered here

- T2.8 and T3.6 need one paid preview; skip them if you do not accept the cost.
- The native Clean dialogs are browser dialogs; screenshots of the page do not
  show them. Record the dialog text or leave Result empty.
