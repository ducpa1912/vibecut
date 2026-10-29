# Voice Room founder pass 1 (recorded 2026-10-29 09:22)

**Build:** the `voice-room` lane.

**Start:** from the Voice Room worktree:

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room
scripts/voice-serve.sh
```

Then open `http://127.0.0.1:8797/voices`.

**Data:** `~/vibecut-lanes/voice`. **Media folder:** `~/vibecut-lanes/media/voiceroom/`. This recording did not select a media file; it used the two clones already in the Voice data, `Andy-VN` and `Andy-EN`.

**What this recording covers:** `/voices`, the Setup panel, the OpenRouter key save, the voice catalog, and three previews of the same clone. The run took 2m25s. The first and third previews took 14.0 s and 14.9 s; the second was cached and answered in 36 ms.

Send pass or fail for each step, what you saw, and any error text exactly as shown. The Result column stays empty here.

## 1. OpenRouter key for this app

The Setup panel is open on load because the OpenRouter key comes from the environment. If it is collapsed, press **Setup** in the top bar.

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1.1 | Open `http://127.0.0.1:8797/voices` | Reach the page and its own Setup | The page opens with **Setup** visible. **OpenRouter** says **From environment**. The **OpenRouter API key** field is empty. | |
| 1.2 | Top bar → **Refresh**, twice about 5 s apart | Reload the page data | The page re-reads settings, voices and videos. **Setup** stays open. | |
| 1.3 | **OpenRouter API key** → paste your key → **Save key** | Use a key for this app only | The chip changes to **Saved on this Mac**. The status reads **OpenRouter key saved for this app. The auth quarantine is cleared.** The clones stay listed. | |

## 2. Play a cloned voice

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 2.1 | Scroll to **01 your voices** → **Andy-VN** → **Play** | Preview in your own voice | The status says **Speaking the test line as Andy-VN…**, then **Playing Andy-VN.** The button reads **Stop** while it speaks. Observed: 14.0 s. | |
| 2.2 | Press **Play** on **Andy-VN** again | The same line should reuse the cached sample | The request answers almost at once (observed: 36 ms). The status behaves the same. | |

## 3. Change the test line and rate

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 3.1 | Scroll to **03 stock voices** → **Test line** → type a different line | Speak a different line | The field accepts the new line. The recording used a Vietnamese line. | |
| 3.2 | **Rate** → set to **1.15×** | The rate is used by the next preview | The rate reads **1.15×**. | |

## 4. Play the clone with the new line

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 4.1 | Scroll back to **01 your voices** → **Andy-VN** → **Play** | The clone speaks the new line at the new rate | The status says **Speaking the test line as Andy-VN…**, then **Playing Andy-VN.** Observed: 14.9 s. | |

## 5. Finish the recording

Only while recording with `scripts/voice-record.sh`: press the floating **Finish recording** button after the last preview. Wait for the terminal to print `Saved …/trace.zip` before closing anything.

## Live OpenRouter check (not part of this recording)

First the dry run. It sends nothing:

```bash
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-voice-room
VIBECUT_DATA="$HOME/vibecut-lanes/voice" python3 scripts/voice_live_check.py
```

Expected: exit `2` and **Dry run: nothing was sent.** with the voice name, a sample near 10 s, and one request line.

The real run sends one request and is allowed only with the founder's explicit OK:

```bash
VIBECUT_DATA="$HOME/vibecut-lanes/voice" python3 scripts/voice_live_check.py --yes-send-to-openrouter
```

## Not covered by this recording

- Cloning from a recording or an upload.
- The clip finder: video search, fast search, clean search, and Cancel.
- Rename and Delete on a clone.
- Cancel on a clone request or a clip search.
- Stock, non-clone voices; the search and language filters.
- OpenCode key save, **Test key**, **Save model**, engine **Refresh**, removing a saved key, and the auth-error/quarantine path.
- Studio → Setup → **My voice**, and Studio → Edit → Audio → **Clone the video's voice**.
- The live OpenRouter check above.
