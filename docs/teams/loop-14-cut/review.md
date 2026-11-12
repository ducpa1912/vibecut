# Loop 14 review — Cut Focus, phase 1

**Verdict: pass for phase 1.** Request REQ-20261112-04.

## The block

A new **Cut** tab in the Edit inspector and **Cut Focus**, laid out like the other focus blocks.

| Section | Controls |
|---|---|
| Output | Aspect `Source · 9:16 · 1:1 · 4:5 · 16:9`, Framing `Fit · Fill`, Crop `X · Y · W · H`, Apply crop, Reset crop, the output size |
| Look | Warm, Cool, B&W, Vivid — moved out of SFX |
| Enhance | planned (loop 19), stated as planned |

The SFX filter buttons and the filter modal entry point are gone; `sfx-filter-add` is used only from
Cut.

## Probes

| Probe | 1440×900 | 1280×800 |
|---|---|---|
| Cut tab / Cut Focus present | yes | yes |
| Tabs | Cut, Clean, Script, Audio, SFX | same |
| Presets in Cut | Warm, Cool, B&W, Vivid | same |
| Choose 9:16 | player ratio **0.5625** (1080×1920), Fill → `object-fit: cover` | same |
| Crop H = 0.6 | player ratio **2.963**, crop vars applied | same |
| Proof frame through the render path after the cut | **1080 × 1920** JPEG | same |

The proof cache key now includes `edit.cut`; without it a stale 1920×1080 proof was served after a
Cut change (found in this loop and fixed).

`test_no_cut_keeps_the_old_source_chain` proves the render chain for a project without a Cut is
byte-for-byte the old `scale … pad … setsar … fps` string.

## Layout

Bottoms **87.3–100 %**, layout overlaps **0**, clipped buttons **0**, no horizontal page scroll;
pictures 99.8 % (16:9), 95.8 / 95.2 % (9:16 Preview), 99.8 % (Edit). Captures `cut-9x16-*` and
`cut-crop-*` at both sizes looked at.

**188 tests**, `node --check`, Xcode build.

## What got worse

- A 9:16 Cut on a 16:9 source makes the Edit player a narrow 250 px strip; the preview column keeps
  its paper. It is correct framing, not a comfortable view.
- The Cut inspector is dense at 320 px (five aspect buttons, four crop fields, two action rows).
- The player preview is CSS crop; the render uses ffmpeg crop. The numbers match, the pixels were not
  compared side by side.
- Cut applies to video scenes. An inserted story image keeps its own framing.

## Not tested

- A full render with a Cut (only a proof frame through the render path).
- Rotation metadata and non-16:9/9:16 sources.
- Safe zones on the Cut output (loop 15), grading (18), enhance (19).
- 1024×700, browser zoom, real clicks in the app window.
