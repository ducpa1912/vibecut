# UI/UX balance review 01

Date: 2026-11-11
Build: `build/DuckSuite-Xcode.app` at `7d6a70e`, local core
Screens: Welcome, Check, Edit, Clean Focus, Preview, Render
Size: 1440 × 900. Captures taken with headless Chrome against the local core, so the
numbers below are CSS pixels of the shipped layout.

## Verdict

**Not balanced.** The flows work; the page weight does not. Three of six screens
put their content in the top two thirds and leave paper below, and a portrait
project turns the main panel into a mostly empty field. Four defects fixed in
this pass; two need a layout decision, not a tweak.

## Fixed in this pass

| Screen | Issue | Fix |
|---|---|---|
| Edit, Clean Focus | Scene title painted over its thumbnail. Row grid column was 54 px while the thumb stayed 66 px, so 12 px of image sat under the text. Read as “cene 02”. | Thumb fills its column: `.proof-row.compact .proof-thumb { width: 100% }` |
| Preview | A 9:16 project rendered as a 300 px picture inside a 1050 px white panel. About 700 px of paper, no player edge. | Portrait stage is a dark player that hugs the frame: width `min(72vh × ratio + 36px)`, centred, media at `72vh` |
| Edit | A transcript placeholder bar sat over the video on a project with zero transcript lines. | Overlay only renders when the frame has cues |
| Welcome | Panels ended at y ≈ 640 of 900. | Workspace stretches to `calc(100vh - 150px)` |

## Measured imbalance, still open

1. **Render ends at 60% height.** Settings 600 px, queue 340 px, Ready 620 px in a
   900 px window. Stretching the queue only moved the void inside the panel, so it
   was reverted.
2. **Edit inspector clips its fifth layer row.** The rail is 342 px and each row
   carries name, a `moves` flag, `Fill` and the eye. The list scrolls with no hint
   that it does.
3. **Timeline gives 240 px to five lanes, three of them empty.** Script, Voice and
   SFX have nothing on this project, so the empty rows read as missing data.
4. **Portrait Preview still leaves ~300 px each side of the player.** The player is
   dark and framed now, but the column is wider than it needs to be.

## Proposals

### P1 · Render: two columns, not three

```text
┌─────────────┬──────────────────────────────────────────┐
│ Settings    │  Render queue (full width, top aligned)  │
│ (320 px)    │  rows 56 px                              │
│             │                                          │
│ Start       │  ── finished renders, thumbnails ──      │
└─────────────┴──────────────────────────────────────────┘
```

Move `Start render` under Settings so the primary action stays above the fold.
Give the queue the rest. Replace the empty lower half with the finished renders
as cards, which is the content the user actually returns for.

### P2 · Edit: collapse empty lanes

Timeline height follows what is in it: a lane with no cues renders one 32 px row
with a `+` affordance instead of a 48 px empty track. Saves ~110 px and removes
the “missing data” read.

### P3 · Inspector: show the count and the edge

Add `5 of 9 layers` to the list head and a 24 px fade at the bottom edge of the
scroll area. One line of CSS plus one span, and the clipped row reads as
“more below” instead of “broken”.

### P4 · Portrait Preview: stage plus strip side by side

At a portrait ratio, put the scene strip in a 300 px column to the right of the
player instead of under it. The player keeps its height; the strip uses the
paper. Needs a container query or a `portrait` class on the workspace.

## What was not changed

- Densities, type scale, palette. No token changes; the imbalance is layout.
- The Welcome dropzone stays the single import action.
- No screen gained a new mode or a new step.

## Acceptance for the next pass

- No screen ends above 85% of a 900 px window.
- No text overlaps an image in a list row.
- Every scrollable list shows either a count or a fade.
- A 9:16 project uses at least 60% of the main column width.
