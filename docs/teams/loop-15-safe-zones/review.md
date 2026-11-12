# Loop 15 review — safe zones

**Verdict: pass.** Request REQ-20261112-05.

## Controls

A **Safe zones** button sits in the Preview actions. It opens seven chips: Off, TikTok, Reels,
Shorts, IG 4:5, IG 1:1, YouTube 16:9. The active platform is named on the button and the source line
under the chips names the document the margins came from.

## Probes

| Probe | 1440×900 | 1280×800 |
|---|---|---|
| Chips | **7** | **7** |
| TikTok on a 9:16 Cut: frame | **331 × 588**, ratio **0.563** | **280 × 498**, ratio **0.563** |
| Frame inside the picture | **yes** | **yes** |
| Bands + button block | **5 + 1** | **5 + 1** |
| Reels | **5** bands, Meta source line | **5** bands |
| Cut 9:16 → 1:1 in Edit, then Preview | frame ratio **1.000**, IG 4:5/1:1 draw **4** bands, no reload | same path |
| YouTube 16:9 on a 1:1 Cut | **no frame**, warning: “This guide is 16:9; the Cut is another shape.” | same |

The overlay is inside the picture, not the panel: the first implementation sat on the preview stage
and overflowed the picture (1440×540 frame against a 1046×588 picture). It was moved into the
split stage; the measured frame now sits inside the picture at both sizes.

Outside the output frame is dimmed (`box-shadow` mask) so the Cut frame reads as the frame.

## Numbers

`docs/duck/SAFE-ZONES.md`: TikTok 240/660/120/120 plus the x 780–960 button block; Reels 14/35/6 %;
Shorts 288/672/48/192; IG 4:5 and 1:1 10 % title-safe; YouTube 16:9 10 % title-safe labelled as a
convention.

## Layout

Bottoms **87.3–100 %**, layout overlaps **0**, clipped buttons **0**, no horizontal page scroll.
Captures `safe-tiktok-*`, `safe-reels-*`, `safe-ig11-*`, `safe-mismatch-*`, `safe-cut-9x16-*`.

**188 tests** unchanged (this loop changes UI only), `node --check`, Xcode build.

## What got worse

- The guide lives inside the source picture; a 1:1 Cut on a 16:9 source dims the sides but still
  shows the source pixels around the square rather than a true 1:1 player. A native player would
  show only the Cut frame.
- The panel takes three extra rows in the Preview sidebar when open.
- Guides are margins, not a guarantee; the platform UI moves.

## Not tested

- A guide combined with a crop that changes the output ratio (the ratio path is computed from crop,
  but no probe covered both together).
- Real device screenshots against the platforms.
- 1024×700, browser zoom, VoiceOver on the chips.
