# Loop 12 review — transcript opacity, no blocked controls

**Verdict: pass.** Request REQ-20261112-02.

## Opacity

A slider in the transcript head. It changes a CSS variable, stores the value under
`duck.transcriptAlpha.<project>` and restores it when the project opens. Only the panel background
fades; the text keeps its colour.

| Probe | 1440×900 | 1280×800 |
|---|---|---|
| Slider 100 → 50 | alpha **0.50**, label **50 %**, stored **50** | same |
| After reload | slider **50**, alpha **0.50** | same |
| Range | **30–100 %**, step 5 | same |

## Nothing blocked

Every player control answers `elementFromPoint` at its centre, with the transcript at 50 %.

| Control | Edit 1440 | Edit 1280 | Portrait Edit |
|---|---|---|---|
| play / time / scrub / volume / full screen | **all true** | **all true** | **all true** |
| Blocked interactive controls, whole screen | **0** | **0** | **0** |

The hit test also found a real fault on Preview and Clean: the before/after image was painted over
`.media-overlay`, so the overlay play button and its timecode could not be hit. The image layer now
sits under the overlay (`z-index: 4`). Blocked controls on Preview and Clean: **1 → 0** at both sizes.

Transcript vs picture: **0 px²**. Text contrast **14.99 : 1**. Lines: **1** (16:9), **2** (9:16).

## Layout

Bottoms **87.3–100 %**, layout overlaps **0**, step/control overlaps **0**, clipped buttons **0**, no
horizontal scroll; pictures **99.8 %** (16:9), **95.8 / 95.2 %** (9:16 Preview), **99.8 %** (Edit).
Captures `after-*`, `portrait-*`, `opacity-50-*` looked at.

**183 tests**, `node --check`, Xcode build.

## What got worse

- The transcript panel gains one 16 px row for the slider, so the portrait panel is a little taller.
- The slider is 3 px tall; it is usable with a mouse but small for touch (no touch target on macOS).

## Not tested

- Browser zoom and 1024×700.
- VoiceOver on the slider; it has an `aria-label` and a visible value, not exercised.
- Real clicks in the app window.
