# Classic UI/UX and responsive review

**Build:** `classic` with the narrow-screen rules in `static/classic/style.css`.
**Method:** founder recordings (`classic-pass-1`, `-2`, `-3`) plus a CSS/DOM
audit. No automated browser pass, no generated media, no claim that a width was
seen working. The founder tests by hand.

## Findings and fixes

| # | Area | Finding | Fix |
|---|---|---|---|
| R1 | Top bar | At phone width the bar kept a fixed 64 px height and 20 px gaps. Creator, Setup and the local pill could crowd or overflow. | The bar now wraps, keeps a minimum height, and drops the health line at 680 px and the local pill at 480 px. |
| R2 | Actions | Action rows, render buttons and result actions stayed inline on phones. | They stack and go full width under 680 px. |
| R3 | Creator tabs | Six tabs wrapped into three rows and pushed the screen down. | One horizontal scroll row under 680 px. |
| R4 | Forms | iOS Safari zooms the page when a control under 16 px receives focus. | Form controls are 16 px under 680 px. |
| R5 | Touch | Small ghost buttons and tabs were under the 44 px touch target. | Coarse pointers get a 44 px minimum and larger padding. |
| R6 | Dropdown | The 15 px custom list could be wider than a narrow screen and start off-screen. | Width is clamped to the screen minus 24 px; left is clamped to 12 px. |
| R7 | History | The four-column row was tight at 320–390 px. | 46/52 px columns under 680 px; status column hides under 480 px; problem text wraps. |
| R8 | Setup | The modal kept desktop padding and height on a phone. | 16 px side margin, 92–94 vh, smaller header padding. |
| R9 | Moments | A 96 px collage cell was too wide at 320 px. | 84 px cells under 680 px, 76 px under 480 px. |
| R10 | Ingest | The pipeline stage pair stayed two columns on a phone. | One column under 480 px. |

## What the founder should check

Widths: **1440**, **1024**, **768**, **390**. On the 390 run, rotate once to
landscape. Check:

- No horizontal scrollbar on the page itself; the timeline and Moments rail may
  scroll inside their own box.
- Top bar: brand, Creator, Setup visible; nothing clipped.
- Import card, path field, URL field stack and stay usable.
- Smart Cut target tabs, Render/Draft/Cancel, and the render notice stack.
- Audio mode tabs wrap; Language, Script style, Voice list and Voice open the
  custom list inside the screen and scroll when long.
- Moments collage scrolls vertically; cards are not cut off.
- Creator tabs scroll sideways; Clip Set, Captions, Packet stay one column.
- Setup modal fits, scrolls, and its footer Save button is reachable.
- History rows do not overlap; problem text wraps.

## How to record it

Terminal 1, only if `http://127.0.0.1:8796/` does not already answer:

```bash
cd /Users/ducpa/code/vibecut-classic
eval "$(scripts/lane-env.sh classic)"
python3 app.py
```

Terminal 2:

```bash
~/vibecut-lanes/recorder/classic-record.sh classic-ui-pass
```

A browser opens at `http://127.0.0.1:8796/`. Stop with **Ctrl-C** in Terminal 2,
or just close the browser. Either way the recorder saves:

- `data/recordings/<timestamp>-classic-ui-pass/trace.zip`
- `data/recordings/<timestamp>-classic-ui-pass/video/*.webm`
- `data/recordings/<timestamp>-classic-ui-pass/session.log` (clicks, changes, console errors)

The recorder masks password/key/token/cookie values. Do not paste a key while
recording unless you accept it in the video.

## Open UI/UX items (not fixed here)

- Setup, Creator and caption selects still use native popups, which macOS draws
  at system size. Only the four audio selects use the 15 px list.
- No safe-area inset handling for notched phones in landscape.
- The desktop top bar hides "Open Studio" in the Classic edition by design; the
  phone bar keeps the same rule.
- Founder confirmation is still needed for R1–R10; this file is not evidence.


## Second pass (tightening)

| # | Finding | Fix |
|---|---|---|
| T1 | Smart Cut was below the full Moments rail, so a render result sat far down the page. | Smart Cut (plan, render, player) now comes before Moments. |
| T2 | A finished render appeared off-screen; the founder had to scroll to find it. | When a render moves from running to ready, the player scrolls into view once. |
| T3 | The expanded collage used 96 px cells, giving twelve tiny cards in one row. | 132 px cells on desktop, 104 px at 680 px, 88 px at 480 px. |
| T4 | The plan explanation ran five or more lines. | Clamped to three lines; the full text stays in **Why this cut**. |
| T5 | History said **1 events**. | Singular **event** when the count is one. |
| T6 | The four result actions stacked into four full-width rows on a phone. | Two-column grid under 680 px. |
| T7 | The audio summary could clip on narrow screens. | It wraps and breaks long words. |
| T8 | The phone collage and history rows were tight. | Smaller cells/columns from the responsive pass remain. |

Still needs the founder's hand: the second pass changed layout order and
scrolling, which a screenshot cannot fully judge.

## Third pass (founder's UI brief)

| # | Change |
|---|---|
| U1 | Moments is above Smart Cut again. The scrub slider is gone. |
| U2 | Every moment card has a round select control: click adds it to Smart Cut, click again removes it. The drawer has **Add to Smart Cut** / **Remove from Smart Cut**. |
| U3 | Clicking a clip's **hook / beat / payoff** label, or right-clicking the clip, opens the role menu. Choosing a role moves the clip into Hook → Beat → Payoff order. |
| U4 | The **Clean** profile dropdown is gone; Clean always removes work files. |
| U5 | Shapes now include **1:1**, **16:9** and **16:10**. |
| U6 | The audio panel is **Edit**: mode tags on top, then three cards: **Copy**, **Sound**, **Texts & Effects**. The Script sits full width at the bottom. |
| U7 | Copy replaces Rewrite. Its action is **Story cut**. It shows **Translating…**, **✓ Translation ready**, **Rewriting…**. Unavailable models are disabled, dimmed and blurred. |
| U8 | Sound has **Voice** and **Music** tabs. **Generate** is the primary action, with a small play button and **Use my recording** / **Use my BGM**. **Mixer** sits at the top right. |
| U9 | Render and Draft sit at the bottom right of Edit, below the full-width Script. |
| U10 | Texts & Effects sits directly below Copy; Sound spans the right column. |
| U10 | Quick-scan hooks and clips no longer request a missing thumbnail. |

### Still open

- **Texts & Effects** carries text overlays and effects on 9:16 and 4:5.
  Other shapes show the shape limit instead of silently dropping layers.
- The mixer still opens as a panel under Smart Cut; the button scrolls to it.

## Fourth pass (expert review fixes)

Checked live at 1440×900 and 390×844 against job `b3207be73257`, plus a
headless sweep at 1024, 768, 320. No media was generated.

| # | Review item | Fixed in this pass |
|---|---|---|
| 1 | Finished player buried under Edit | The player now sits directly under the hook. `#audio-panel` starts closed, and a compact **Final 30s reel ready · Download** strip sits under the result title. |
| 2 | Ingest primary action below the fold | Hero top padding 78→34 px, `h1` capped at 56 px, dropzone 330→196 px, four options in one row. `#analyze` is at y=790 on 1440×900; with a file card it is at 678. |
| 3 | Raw filename at 56 px | Result title is the hook line (fallback “30s cut”), capped at 40 px/2 lines. The full filename stays in `title` and `#result-meta`. |
| 4 | 24 near-identical recent cards | Recent cuts group by source (`24 cuts · 5 sources`), show a resume card plus five groups with “Opened …”, and **View all cuts** opens the full list. Delete moved into that list; no jobs are removed by the grouping. |
| 5 | Hook panel dead space | Frame 286×508→240×427; `.hook-info` is vertically centred. |
| 6 | Mobile hook image before data | At ≤680 px `.hook-info` is `order:-1`, then a 200 px-wide frame. |
| 7 | Dead Copy form | Original/Music/recording modes show one dashed note and **Rewrite this cut →**; the form only renders when a generated voice mode needs it. |
| 8 | Mode tabs too short and unexplained | Five modes in one segmented control, 44 px high, a 2×2 + full-width grid on mobile, and one description below. |
| 9 | Tiny moment controls, lime payoff | Check target 32 px, moment time 10.5 px, clip role 11 px with ▾ and a **Change role** heading. Payoff uses a neutral dashed border plus a two-item legend. |
| 10 | Dim microtype | `--dim` is `#9a999f` in Classic and Creator; labels are at least 11 px and hints 12 px. |
| 11 | Smart Cut repetition and nesting | Default `#plan-why` removed; a one-line hook→payoff route remains. Smart Cut and Edit are separate bands; the Edit disclosure starts closed, nested panel/script borders are gone, and Render/Draft stay at the bottom right of Edit. |
| 12 | Music mode repeated warning | One inline message under the music source with **Use my BGM** / **Generate**. Generate is disabled while the source is **No music**; `#render-block` is gone and `#render-note` no longer repeats the reason. |
| 13 | Orphan Delete | Result actions are three equal columns at ≤680 px. |
| 14 | Mobile Moments triple count | One short line “12 moments · best first”; sort and **Show all/Show less** share one toolbar row. |
| 15 | History strip | Renamed **Activity**, one event count, latest event inline while collapsed, 12 px rows, chevron, 48 px summary, 320 px list. |

### Verification

- `node --check static/classic/app.js`: pass.
- Classic tests (`tests/test_classic*.py`): 75 passed.
- Full suite: 1,790 passed, 10 skipped, 1 failed. The only failure is the
  Voice Room token-parity test described below.

### Open items

- `tests/test_voice_room_page.py` compares Voice Room tokens with Classic
  `:root`. Raising Classic `--dim` to `#9a999f` makes that cross-lane parity
  test fail (`Voice Room` still has `#6c6b70`). Voice Room was not touched, per
  the lane rules; report it to the Voice Room owner.
- The recent drawer shows version rows by creation date, not a named variant;
  older renders still have no user label.
- The hook frame keeps a 9:16 thumbnail on mobile; a “View full frame” action
  is still not built because no lightbox exists yet.
- The founder still needs to judge the new order, the copy note, and the
  music-source actions by hand.

### Screenshots used

Captured with Playwright from `~/vibecut-lanes/recorder` (no media generated):

- `.../opencode/ui-after/result-1440.png`, `result-390.png`, `result-390-full.png`
- `.../opencode/ui-after/ingest-1440.png`, `ingest-390.png`
- `.../opencode/ui-after/edit-original-1440.png`, `edit-music-1440.png`, `edit-music-390.png`
- `.../opencode/ui-after/recent-all-1440.png`, `history-open-1440.png`
- `.../opencode/ui-sweep/result-320.png`, `result-768.png`, `result-1024.png`
- `.../opencode/ui-sweep/moments-expanded-390.png`, `activity-390.png`
