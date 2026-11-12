# Loop 12 brief — transcript opacity, nothing blocked

Request: **REQ-20261112-02**.

> "In edit: the transcript overlay did not have the tranparency slider. Player runtime being block
> by the transcript, volume is block by the transcript overlay."

## What must exist

1. An **Opacity** slider in the transcript panel, 30–100 %, applied to the panel, persisted per
   project, and restored on reload.
2. The transcript never covers the player **time**, **volume**, **scrub**, play or full screen; each
   control answers a hit test at its centre.
3. Text contrast stays at the panel's own level; only the panel background fades.
4. No layout regression on Edit, Preview or Clean.

## Acceptance

| Probe | Pass |
|---|---|
| Slider 100 → 50 | computed background alpha 0.5, label 50 %, stored value 50 |
| Reload the page | slider reads 50 and alpha 0.5 |
| Hit test on play, time, scrub, mute, volume, full screen | all true at 50 % |
| Transcript vs picture intersection | 0 px² |
| Layout overlaps, clipped buttons, horizontal scroll | 0 / 0 / 0 |

## Out of scope

Timeline zoom, Cut, safe zones, preview sequence, story.
