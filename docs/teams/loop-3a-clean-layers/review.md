# Loop 3A review — Clean layer list collapsed to 0 px

**Verdict: pass.** Founder-visible bug: the six layer rows existed in the DOM but the list had height 0, so no layer could be selected or turned off.

## Cause

`.inspector-body` is a CSS grid with a fixed height and `overflow: auto`; `.layer-list` has `max-height: 232px; overflow-y: auto`. Its automatic minimum size in the grid track was 0, so the track collapsed. At 800×600 the rows sat below the viewport (first row top 794).

## Fix

- `.inspector-body { grid-auto-rows: max-content; }` gives the scroll child its content height.
- The layer head and list are the first two controls in the Clean inspector (`order: -2/-1`). At 800×600 the list starts at y 253 and all six rows are visible; the proof and Fill/Blur/Off controls follow below the fold.
- No other scroll child collapsed: the audit found **0** elements with `overflow-y:auto`, `clientHeight 0` and `scrollHeight > 10` on Edit, Clean, Preview and Render at 800×600.

## Measured

Script: `NODE_PATH="$(npm root -g)" node scripts/check-clean-layout.cjs --base "http://127.0.0.1:8813/?t=scratch-3a" --project prj_e95348a97316 --out build/opencode-3a`

| Viewport | List height | Rows | Visible rows | Row selects | Off reaches the layer |
|---|---:|---:|---:|---|---|
| 800×600 | **207 px** | 6 | **6** | Title 01 / `cl_7b144258ac` | **yes**, kind **Off** |
| 1024×700 | **207 px** | 6 | **6** | same | yes |
| 1280×800 | **207 px** | 6 | **6** | same | yes |
| 1440×900 | **207 px** | 6 | **6** | same | yes |
| 200 % (720×450 CSS) | **207 px** | 6 | **5** | same | yes |

Before the fix, the same script/measurement gave list **0 px**, visible rows **0**, first row top **794** at 800×600. Screenshots: `build/opencode-3a/clean-800x600.png`, `clean-200%.png` (gitignored).

## The founder's "remove" wish

Today a layer has **Fill / Blur / Off** only. **Off** keeps the layer, greyed, so Clean all can still leave the line alone. Clicking a box on the video does not select a layer. Neither is built here; both are proposals in `TODO.md` under REQ-20261118-01.

## What got worse

- At 800×600 and 200 % the layer list is first, so the before/after pair and the Fill/Blur/Off buttons are below the fold and need a scroll. Choosing the line first is the intent; the controls remain reachable.
- At 200 % one row (the sixth) is just below the viewport; five of six are visible.

## Not tested

- Real clicks in the founder's app window; the dev server on a scratch copy was used.
- VoiceOver and keyboard order; the rows are buttons and the controls follow.
- The story media inspector and render player (not part of this tab).
