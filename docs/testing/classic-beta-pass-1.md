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
| 1.23 | Choose **ElevenLabs** | Pick a cloud engine without a key | The list returns 0 voices. `[F8]` | |
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
| F4 | P2 | 2.8, 2.11 | Changing a setting mid-rewrite aborted the browser request (`-1`), but the server kept working and later wrote a 429 s script row. | `POST /audio/script` → **-1** (aborted), then a later script row with 429 s | Open: client abort does not stop the worker |
| F5 | P2 | 1.7, 2.13, 3.5 | **Expand** opened a second scene gallery under the strip, not a vertical collage. | none | Fixed in `582977c`; recordings show the old grid |
| F6 | P2 | 1.43, 1.54 | History called all worker rows "attempts": **3 attempts** then **8 attempts** for one render. | `GET /history` returned 8 rows: 1 render, 3 script, 2 translation, 2 rewrite | Fixed in `6f951be`; header now **N renders · M events** |
| F7 | P3 | 1.9, 3.6 | **Expand** was clicked twice while already expanded; the extra click changed nothing. | none | Cosmetic; no error |
| F8 | P3 | 1.23 | ElevenLabs had no key, and the voice list returned 0 voices with no reason in the list. | `GET /api/audio/voices?engine=elevenlabs` → 200, `voices: []` | Key/config; show "Needs a key" instead of an empty list |

No 4xx or 5xx responses appear in passes 2 and 3 other than the pass-1 items
above. The only aborted request is `-1` in pass 2.

## What this file does not cover

Pass 4 has only `server.log`, no `actions.spec.js` and no HAR, so it has no
steps here. File-dialog steps are marked where the recorder did not capture
them. `docs/testing/classic-beta-pass-2.md` describes behaviour added after
these recordings (translation badge, collage, history count); it is not evidence
from the recordings.
