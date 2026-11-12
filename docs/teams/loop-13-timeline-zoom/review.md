# Loop 13 review — timeline zoom

**Verdict: pass.** Request REQ-20261112-03.

## Controls

`−`, the factor, `+` and **Fit** sit in the timeline head. Steps: 1, 1.5, 2, 3, 4, 6, 8, 12, 16.

## Measured

| Probe | 1440×900 | 1280×800 |
|---|---|---|
| 1× inner/client ratio | **1** | **1** |
| 6× ratio | **6** (7920 / 1320 px) | **6** (6960 / 1160 px) |
| 16× ratio | **16** (21120 px) | — |
| Ruler label gap at 6× | **109 px** | **86 px** |
| Ruler label gap at 16× | **108 px** | — |
| Page horizontal scroll | **none** | **none** |
| Click scene block 7 at 6× | selects **S07**, player seeks **00:31 / 02:40** | same |
| Fit | **1×**, scrollLeft **0** | same |

The ruler adds ticks with the zoom (`7 × zoom`, at least 7), so detail grows instead of one label
stretching. Lane labels are sticky at the left edge and stay visible while the tracks scroll.
Scene blocks keep their percentage geometry inside the wider inner track, so clicks and seeks work
unchanged.

## Layout

Bottoms **87.3–100 %**, layout overlaps **0**, clipped buttons **0**, no horizontal page scroll;
Edit bottoms **93.1 / 97.3 %**; pictures **99.8 %** (Edit). Captures `zoom-1440x900.jpg`,
`zoom-1280x800.jpg` at 6× looked at; six-screen captures at 1×.

**183 tests**, `node --check`, Xcode build.

## What got worse

- The timeline head is denser: zoom controls share the row with In/Out, split, slip and Script.
- At high zoom the ruler labels at the viewport edges clip, as in any scrolling ruler.
- Zoom is per session; it is not saved with the project.

## Not tested

- Wheel or trackpad pinch zoom (buttons only).
- Keyboard shortcuts.
- 1024×700 and browser zoom.
