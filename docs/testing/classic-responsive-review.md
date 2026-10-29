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
cd /Users/happynghia/Public/Project/Code/drop_eval/vibecut-classic
eval "$(scripts/lane-env.sh classic)"
python3 app.py
```

Terminal 2:

```bash
~/vibecut-lanes/recorder/record.sh classic-ui-pass
```

A browser opens at `http://127.0.0.1:8796/`. Stop with **Ctrl-C** in Terminal 2,
or just close the browser. Either way the recorder saves:

- `~/vibecut-lanes/recordings/classic-ui-pass/trace.zip`
- `~/vibecut-lanes/recordings/classic-ui-pass/video/*.webm`
- `~/vibecut-lanes/recordings/classic-ui-pass/session.log` (clicks, changes, console errors)

The recorder masks password/key/token/cookie values. Do not paste a key while
recording unless you accept it in the video.

## Open UI/UX items (not fixed here)

- Setup, Creator and caption selects still use native popups, which macOS draws
  at system size. Only the four audio selects use the 15 px list.
- No safe-area inset handling for notched phones in landscape.
- The desktop top bar hides "Open Studio" in the Classic edition by design; the
  phone bar keeps the same rule.
- Founder confirmation is still needed for R1–R10; this file is not evidence.
