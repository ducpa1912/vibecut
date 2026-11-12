# Loop 15 brief — safe zones on the Preview panel

Request: **REQ-20261112-05**.

> "No safezone for each social media, this is a button on the preview panel, and it should refresh
> if the cut edit chose to crop or make the original video to different dimension, like from 16:9 to
> 9:16 or 1:1."

## What must exist

1. A **Safe zones** button on the Preview panel with guides for TikTok, Reels, Shorts, IG 4:5,
   IG 1:1 and YouTube 16:9, plus Off.
2. Guides drawn on the **Cut output frame**, with the outside dimmed so the output frame is visible.
3. The guide refreshes when the Cut aspect or crop changes, without a page reload.
4. A guide is not drawn on the wrong shape; a warning says so instead.
5. Every number comes from a cited source in `docs/duck/SAFE-ZONES.md`.

## Acceptance

| Probe | Pass |
|---|---|
| Chips | Off + 6 platforms |
| TikTok on a 9:16 Cut | frame ratio 0.563, inside the picture, 5 bands + button block |
| Reels | 5 bands, Meta margins |
| IG 4:5 / 1:1 | 4 bands, 10 % title-safe |
| YouTube on a 1:1 Cut | no frame drawn, warning shown |
| Change Cut 9:16 → 1:1 in Edit, open Preview | guide frame ratio 1.0 without reload |
