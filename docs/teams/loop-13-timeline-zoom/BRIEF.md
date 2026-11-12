# Loop 13 brief — timeline zoom

Request: **REQ-20261112-03**.

> "Timeline should be zoom in & out to go into mini detailed of each beat/scene."

## What must exist

1. Zoom controls on the timeline: out, in, Fit, and the current factor.
2. A range from Fit (1×) to 16×.
3. The tracks scroll inside the timeline, never the page.
4. Ruler labels stay apart at every zoom and get denser as the zoom grows.
5. Lane labels stay visible while the tracks scroll.
6. Scene blocks stay clickable and seek at any zoom.

## Acceptance

| Probe | Pass |
|---|---|
| 1× | inner/client ratio 1 |
| 6× | ratio 6; ruler label gap > 40 px |
| 16× | ratio 16; page has no horizontal scroll |
| Click a scene block at zoom | that scene is selected and the player seeks |
| Fit | back to 1×, scroll left 0 |
