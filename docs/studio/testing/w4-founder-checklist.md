# Wave 4 founder checklist (founder runs, Claude records)

**Build:** `main` after the Wave 4 merge.

**Start the app:** run `python3 app.py` with no flags, then open `http://127.0.0.1:8787`. Clean should be on by default.

**Videos:**
- **A:** JOYLO (`~/Downloads/Comment JOYLO and Ill send you the link!  … See more.mp4`)
- **B:** rednote (`~/Downloads/天呐我把童话书里的花园搬进了现实太美了 - rednote.mp4`)

**Old jobs:** if you have jobs from before Wave 4, open one in part 1. It proves the startup migration.

Send me pass or fail for each step, what you saw, any times you measured, and any error text exactly as shown. I fill in the Result column.

## 1. Old jobs, migration and Classic fallback

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 1.1 | Studio → **Import** → **Recent videos** → open an old job (from before Wave 4) | Old jobs open after the startup migration | The job opens with no error. Its 9:16 stories carry a captions-only Edit. | |
| 1.2 | Same job → **Stories** → pick a story, shape 9:16 → **Render this story** | A migrated story renders with its old captions | The render reaches Ready and the captions match the old track. | |
| 1.3 | Gear → **Use Classic editor** → Creator → **Captions** → edit one cue → **Save cues**. Then go back to Studio and render the same story (9:16). | A Classic caption edit carries into the Edit (fixed in review) | The new render shows the **edited** cue. | |
| 1.4 | Same story → shape **4:5** → **Render this story** | 4:5 with no Edit stays on the legacy path | It renders with no 409 error. | |

## 2. Import, Check and Clean (A and B)

| # | Action: where to click | Intent | Expected | Result A | Result B |
|---|---|---|---|---|---|
| 2.1 | **Import** → choose the video → **Check** → **Run Check** → record the own-footage rights note | Setup and detection | A: text is found, the watermark is refused, and UI text shows as "Never". B: the Chinese subtitle and titles are found. | | |
| 2.2 | **Stories** → story 1 → **Edit** → **Clean** (first open) | Auto-fill comes from the server policy | Covers fill, at most 32, and refused regions stay refused. B: the lower-band subtitle becomes a plate. | | |
| 2.3 | A: in **Clean**, try **Add from Check** on a screen-text row such as `Search` or `Home` | Screen text can never be cleaned | The chip says **Never** and Add is disabled. | | — |
| 2.4 | Scrub the preview at 1 s, 5 s and 15 s | Visual quality | The old text is gone and no faces are covered. Note any visible patch. | | |

## 3. Effects, Audio and Voice

| # | Action: where to click | Intent | Expected | Result A | Result B |
|---|---|---|---|---|---|
| 3.1 | **Effects**: add punch-in, an arrow and a colour preset | Compose | The preview updates. | | |
| 3.2 | **Audio** → **Music bed** → **Generate two candidates** | Cloud music, or the honest no-key message | Two candidates appear, or exactly: "Cloud generation needs a MiniMax or OpenRouter key." | | |
| 3.3 | **Preview A**, then **Preview B**, then **Use A** (or upload a bed if there's no key) | A/B preview and lock | Both play. Use A locks the bed and the save succeeds. | | |
| 3.4 | **Audio** → **Voice** → choose **HeyGen Voice Turbo** → **Nadine** → **Preview voice** | The HeyGen route | The hint says "free until 30 Nov 2026". A clean sample plays within about 2 s with normal pitch and speed. | | |
| 3.5 | Set mode **Original + bed** (A) or **Dub** to Vietnamese (B), save, then **Render this story** | Edit audio is mixed into the story render (fixed in review) | A: music sits under the speech. B: the dubbed voice is heard. Loudness is even, with no clipping. | | |
| 3.6 | Beat snap: with a bed locked, go to **Effects** → **Snap selected** | Beat snap works on an uploaded or locked bed | It shows the BPM and the effect moves. | | |

## 4. Preflight markers

`$JOB` and `$EDIT` are the ids in the Studio URL.

| # | Action: where to click | Intent | Expected | Result A | Result B |
|---|---|---|---|---|---|
| 4.1 | **Finish** → **Before you publish** → **Check again** | Inline markers | Markers show times and suggestions, with no crash. | | |
| 4.2 | **Clean** → remove the cover over a caption → save → **Check again** | Uncovered old text is caught | A `residual_text` (or uncovered-text) marker names that caption, and the result is not a pass. | | |
| 4.3 | **Effects**: add two text layers at the same anchor with overlapping times → **Check again** | Collision | A collision marker covers the overlap window. | | |
| 4.4 | **Audio** → **Voice** → **Rate** `1.40` → save → **Check again** | Voice fit | The marker says the rate is outside 0.90–1.15×. | | |
| 4.5 | **Audio**: a bed showing **No licence note** → save → **Check again** | Licence | A `missing_music_license` marker appears. | | |
| 4.6 | Terminal: run the two probes below | A watermark or screen-text box can't be smuggled in | Both return `409` and no new version is created. | | |

```bash
BASE=http://127.0.0.1:8787
curl -s -w '\n%{http_code}\n' -X PATCH "$BASE/api/jobs/$JOB/edits/$EDIT" -H 'Content-Type: application/json' \
  -d '{"clean":[{"kind":"plate","box":{"x":0.8,"y":0.05,"w":0.15,"h":0.06},"tracklet_id":"probe_water","tracklet_kind":"watermark"}]}'
curl -s -w '\n%{http_code}\n' -X PATCH "$BASE/api/jobs/$JOB/edits/$EDIT" -H 'Content-Type: application/json' \
  -d '{"clean":[{"kind":"blur","box":{"x":0.05,"y":0.03,"w":0.2,"h":0.05},"tracklet_id":"probe_ui","tracklet_kind":"screen_text"}]}'
```

## 5. Finish: render, versions, packet, review link

| # | Action: where to click | Intent | Expected | Result A | Result B |
|---|---|---|---|---|---|
| 5.1 | **Finish** → **Render** → Shape **9:16** → **Queue all stories · 9:16**. Time one story from start to Ready. | Queue and speed (target ≤ 2× story length) | Stories run one at a time and versions appear. Note the time and the story length. | | |
| 5.2 | Same, with Shape **4:5** | 4:5 queue | A separate 4:5 queue runs, and its versions are grouped under 4:5. | | |
| 5.3 | **Queue** → **Pause**, then **Resume** | Durable queue | It pauses after the current story and resumes with no duplicate. | | |
| 5.4 | **Versions** → pick two ready cuts, A/B | Side-by-side versions | Both play, labelled "Version N". | | |
| 5.5 | **Publish kit** → fill title and hashtags (B: Chinese text) → **Build publish kit** → **Download** | Packet v2 | The ZIP has `packet.json` (schema `vibecut.publish_packet/2`), `edit.json`, `audio.json`, `music.json` and 2 covers. Chinese text is intact. | | |
| 5.6 | Open `packet.json` in the ZIP | Identity | `covers[].source` is `"frame"`. `media[].edit.version` matches the Versions panel. `edit.json` has no absolute paths. | | |
| 5.7 | **Review link** → **30 days** → **Make review link** → **Copy** → open it | Review link pinned to the exact cut | It plays that cut, and the banner shows `Edit vN · current`. | | |
| 5.8 | **Apply to all stories** → tick Caption style, Text style, Colour, Music brief and Voice → **Apply** | One-click style pass | Other stories get the styles. Text, timing and Clean stay per story. | | |

## 6. Setup

| # | Action: where to click | Intent | Expected | Result |
|---|---|---|---|---|
| 6.1 | Rail → **Setup** → **Keys** → save the OpenRouter key | Saving a key | It shows "Saved on this Mac", and the key is never shown again. | |
| 6.2 | **Setup** → **Engines** → OpenRouter voices | HeyGen is listed | HeyGen Voice Turbo is listed with the free-until hint. | |
| 6.3 | **Setup** → **Packs** → **Refresh** | Honest pack status | Speech, Voice and Separation show Installed or Not installed with their size. No fake download is offered. | |
