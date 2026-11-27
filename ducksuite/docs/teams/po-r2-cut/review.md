# R2 product-owner review — Cut Focus

**Verdict: PASS** for the founder acceptance test after one fix loop.

## PO findings and fixes

| Finding | Fix |
|---|---|
| P0: Warm/Cool/B&W/Vivid added an SFX filter, not a grade | Presets now set the four grade sliders; the SFX lane stays at 0 effects. Probe: grade 0/6/8/35, effects 0. |
| P1: 16:9 player clipped 126 px, play button off-screen, badge said source size | Landscape card follows width (772×434 at x299 in a 774 px block), no horizontal overflow, badge reads 1920×1080. |
| P1: Cut Focus duplicated the inspector and pushed the page past the window | The inspector is hidden while a focus dock is open; three cards, dock 508–848 at 1440, document 900. Kicker removed. |
| P1: aspect change silently switched Fit to Fill | A toast states “Fill crops to cover the frame. Choose Fit to keep the whole picture.” |
| P1: active segmented text was 3.17:1 | Active segments use `#9a5310` with white. |
| P1/P2: Cut tab showed the empty transcript, taking the centre | Transcript is hidden on the Cut tab; card 772×434 at 1440, 422×237 at 1024. |
| P2: crop is normalized numbers only | Not fixed; founder decision, noted. |

## Measured

| Viewport | Card | Document / viewport | Inspector body |
|---|---|---|---|
| 1440×900 | 772×434 | 900 / 900 | 437 / 997 (scrolls) |
| 1024×700 | 422×237 | 700 / 700 | 337 / 997 |
| 800×600 | 198×140 | 600 / 600 | 237 / 997 |
| 200 % (720×450) | 118×140 | 580 / 450 (90 px page scroll) | 237 / 997 |

Clean tag still **Source · no proof yet**; 346 tests, `node --check`.

## What got worse

- The inspector still scrolls for Look/Enhance at 1440; no explicit “more below” cue beyond the fade.
- At 800/200 % the card is 198/118 px wide, so overlay labels and the grade are hard to read.
- 200 % still has a 90 px page scroll.

## Not tested

- Real founder click-through; VoiceOver; a render with the changed Cut; crop-drag gesture (not built).
