# Voice Room founder pass 1 (founder runs, Claude records)

**Build:** the `voice-room` lane, with voice extraction included.

**Start the app** from the Voice Room worktree on its own port and data folder:

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room && scripts/voice-serve.sh
```

Then open `http://127.0.0.1:8797/voices`. Data lives in `~/vibecut-lanes/voice`; media lives in `~/vibecut-lanes/media/voiceroom`. Port 8787 and the founder's data are not used.

**You need:**
- An OpenRouter key saved in Setup. Without it the page shows "Add an OpenRouter key in Setup to clone a voice."
- One finished video with clear speech in Recent videos. Some music under it is fine; the clip finder should remove it.
- A microphone, and one voice recording file (WAV, MP3 or M4A, 30 s to 3 min).

**What goes to the cloud:** cloning itself stays on this Mac. Only **Play** on a cloned voice, and Play on a cloud stock voice, send a request to OpenRouter. A cloned voice's Play sends its sample with the line.

Send me pass or fail for each step, what you saw, and any error text exactly as shown. I fill in the Result column.

## 0. This app's Setup

The Voice Room has its own Setup, and its own config files. Nothing here changes Studio or Classic.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 0.1 | Top bar → **Setup** | The Voice Room has its own keys and model pickers | The Setup section opens. It shows **OpenRouter**, **OpenCode**, **On this Mac**, and **This app's config**. | |
| 0.2 | OpenRouter → paste your key → **Save key** | A key just for this app | The chip changes to **Saved on this Mac**. The environment key no longer wins. Paths at the bottom point into `~/vibecut-lanes/voice/`. | |
| 0.3 | OpenRouter → **Test key** | Check the key with one cloud call | **OpenRouter replied.** If it fails, the exact OpenRouter error shows here, including a rejected key or a management key. | |
| 0.4 | Text model → pick a model → **Save model** | The model picker works | The chosen model stays after **Refresh**. | |
| 0.5 | OpenCode → **Test key**, or leave the local login | OpenCode API and local login | **Local login** means the OpenCode already signed in on this Mac. A saved key shows **Direct API key**. | |
| 0.6 | **On this Mac** | Local engines are visible | Apple say is **Ready**. Each other engine says **Ready** or **Needs setup** with the install or key hint. | |

## 1. Getting there, and the switch

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1.1 | Classic top bar → **Voice Room** | The page is reached from Classic | `/voices` opens. Top bar: **VibeCut**, a **VOICE ROOM** pill, **Back to VibeCut**, **Refresh**. | |
| 1.2 | Look at the whole page | The Classic look, not Studio's | Same dark background, orange accent and serif headline as Classic. Three numbered sections: **01 your voices**, **02 clone a voice**, **03 stock voices**. | |
| 1.3 | **Back to VibeCut** | The way back | Classic opens. | |
| 1.4 | Stop the app. Start it again **without** `VIBECUT_FEATURES=voice_room` (empty value), same `VIBECUT_DATA`, `VIBECUT_PORT=8797` and `VIBECUT_EDITION=classic`. Open Classic, then type `http://127.0.0.1:8797/voices` | The switch hides the feature | Classic shows no **Voice Room** link. `/voices` says Not Found. Restart with the switch on before part 2. | |

## 2. Stock voices (section 03)

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.1 | Read the line under **Voices on this machine** | The catalog loads | "N voices across M engines". **Apple say** is folded; the other engines are open. | |
| 2.2 | Open **Apple say** → **Play** on any English voice | Offline voice | The test line plays within about 2 s. | |
| 2.3 | Change the **Test line**, set **Rate** to about 1.2×, then **Play** again | Line and rate are used | Your new line plays, a little faster. | |
| 2.4 | HeyGen Voice Turbo → **Play** on **Nadine**, then press the same button (now **Stop**) before it starts | Stop cancels a sample still being made | The status says **Stopped.** and nothing plays. | |
| 2.5 | Type `nadine` in **Search voices**, then pick a language in **All languages** | Filters | Only matching voices show. Clearing them brings all back. | |
| 2.6 | Open **Not set up on this machine** (if shown) | Missing engines explain themselves | Each row says what to install or which key to add. | |

## 3. Clone from a recording or a file (section 02, left card)

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 3.1 | **Record my voice** → allow the microphone → read the lines for 30 to 60 s → **Stop recording** | Recording | A clock counts up to 3:00; the reading lines show. After Stop, a player lets you listen back. | |
| 3.2 | Name `My voice test`, tick the consent box, **Clone my voice** | Clone from a recording | "Your voice is ready." The voice appears in **01 your voices** as **My voice · N s sample**. | |
| 3.3 | **Choose File** → your recording file → tick consent → **Clone my voice**, then at once press **Cancel** | Cancel a clone | The status says **Cancelled. No voice was cloned.** and no new voice appears. (A short file can finish first; then it is cloned. Say which happened.) | |
| 3.4 | Same file → tick consent → **Clone my voice**, and wait | Clone from a file | A second voice appears in **01 your voices**. | |

## 4. Your voices (section 01)

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 4.0 | With a bad or quarantined OpenRouter key, open `/voices` | Local clones stay visible | **01 your voices** still lists every clone on this Mac. A hint says OpenRouter is not ready; **Setup** shows the exact auth error and retry time. | |
| 4.1 | **Play** on `My voice test` | The clone speaks (sends one OpenRouter request) | Within a few seconds the test line plays **in your voice**. Note how close it sounds, 1 to 5. | |
| 4.2 | **Rename** → type `Founder voice` → press Enter | Rename | The row now says **Founder voice**. **Refresh** keeps the new name. | |
| 4.3 | **Rename** again → press Escape | Rename can be left | The old name stays. | |
| 4.4 | Section 03 → HeyGen Voice Turbo | Clones show in the voice pickers | **★ Founder voice · my voice** is listed first. | |
| 4.5 | **Delete** on the second clone (from 3.4) → OK in the dialog | Delete | It disappears from 01 and from the HeyGen list. | |

## 5. Clean-clip finder (section 02, right card)

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 5.1 | **From a video** → **Video** → pick your video | Videos are listed | Your finished videos show with their length. | |
| 5.2 | **Find clean clips**, then press **Cancel** while it says "Finding the speech and removing music…" | Cancel the search | It says **Search cancelled.** and **Find clean clips** is available again. | |
| 5.3 | **Find clean clips** again and wait. Time it. | The real search | **Fast search** is ticked by default: it skips music separation and returns in seconds. Uncheck it for a clean search with the separation model, which is slower. By default it searches the first **2:00** only; tick **Search the whole video** to scan all of it. Up to 5 clips appear, each with a time range, length, clarity and % speech. Note the time it took. | |
| 5.4 | **Play** on each clip (the button turns to **Stop**) | Clips are clean speech | Each clip is the speaker's voice with the music gone or much quieter. Note the best clip number. | |
| 5.5 | **Use this clip** on the best one → name `Video voice test` → tick the speaker consent → **Clone this clip** | Clone from a found clip | The status names the clip, e.g. "Cloned "Video voice test" from clip 2 (0:48–0:58)". It appears in 01 as **From a video**. | |
| 5.6 | **Play** on `Video voice test` in 01 | The clip clone speaks | The line plays in the video speaker's voice. Note 1 to 5. | |
| 5.7 | **Use a time range instead** → From `0`, To `60` → tick consent → **Clone this range** → press **Cancel** at once | Cancel a long clone | **Cancelled. No voice was cloned.** No new voice appears. | |
| 5.8 | Reload the page and pick the same video | Results are kept | The clips from 5.3 show again without a new search. | |

## 6. Studio still uses the same voice code

Run this part on the Studio lane, port `8795`, after Studio merges this Voice Room lane. Voice-only checks stay on port `8797`.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 6.1 | Studio → Setup → **My voice** | The shared record panel still works there | Your clones are listed with Play and Delete. | |
| 6.2 | Studio → Edit → Audio → **Clone the video's voice** → **Find the best voice clips** | The Edit picker still works | Clips appear as before. | |

## 7. Live OpenRouter check of one cloned voice (only with your OK)

This sends **one** request to OpenRouter with about **10 s** of a cloned voice's sample, using your key. Claude never runs it without your explicit OK.

First a dry run. It sends nothing, and shows which voice, how long a sample, and the one request it would make:

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room && VIBECUT_DATA="$HOME/vibecut-lanes/voice" python3 scripts/voice_live_check.py
```

Then, only if you agree, the real request:

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room && VIBECUT_DATA="$HOME/vibecut-lanes/voice" python3 scripts/voice_live_check.py --yes-send-to-openrouter
```

Pick a voice with `--voice clone_…` (the newest clone is used otherwise). It cuts the first 10 s of that clone into a temporary clone, sends one request, deletes the temporary clone, and writes the reply to `~/vibecut-lanes/voice/cache/voice-live-check.wav`.

| # | Action | Intent | Expected | Result |
|---|---|---|---|---|
| 7.1 | Dry run | Nothing is sent | "Dry run: nothing was sent." with the voice name, `Sample: ~10.0 s` and `Request: 1 x POST …` | |
| 7.2 | Real run (with your OK) | HeyGen Voice Turbo clones from a 10 s sample | `OK: 1 request, N s of speech written to …`. | |
| 7.3 | Open the WAV from 7.2 and listen | The clone is real | It sounds like the cloned voice, not a stock voice. Note 1 to 5. | |
| 7.4 | Voice Room → 01 your voices | No leftovers | No "(live check)" voice is listed. | |
