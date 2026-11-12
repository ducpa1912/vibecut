# Loop 16 brief — Preview plays a sequence

Request: **REQ-20261112-06**.

> "In Preview block, the preview panel can only preview one cut scenes at a time, it should either
> play all the scenes (if no story selected), or the scene in the story in the storytelling order."

## What must exist

1. A **Play all scenes** button when the full edit is open; **Play story order** when a story edit is
   open.
2. Playback crosses scene and clip boundaries without stopping, from the source file.
3. One bar shows sequence time, total, a scrubber and the current item (`2 of 35 · Scene 02`).
4. A seek lands on the right segment; closing returns to the proof view.
5. Story order follows the clip order, not source time.

## Acceptance

| Probe | Pass |
|---|---|
| Full edit | 35 segments; total 02:40; advances 01 → 02 at the boundary |
| Seek 50 % | lands on Scene 15 at 01:20 and keeps playing |
| Close | sequence player gone, proof steps back |
| Story edit built from scenes 6, 2, 4 | 3 segments, 15 s; first source 26.5 s, second 5.3 s |
