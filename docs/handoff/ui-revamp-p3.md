# Studio UI revamp — P3 polish (2026-11-02)

Base: `38a0c84` (P2 found text and fill preview). Branch: `studio`.

## Summary

P3 makes the editor feel like one product rather than several panels. The
Edit chrome now uses one spacing and type scale, one inline icon set, and one
layer palette. Keyboard shortcuts cover playback, stepping, tools, undo/redo
and the shortcut sheet. Every empty group has an action instead of a dead
message.

It also fixes a real undo bug: Undo checked for a parent version before it
flushed the pending autosave, so Undo immediately after a change did nothing.
It now saves first and undoes the new version.

## What changed

### Tokens and type

- `static/studio/edit/edit.css` defines the editor's 4/8/12/16/24/32 spacing
  scale, 12/13/15 type scale and one 32 px control height.
- Toolbar, Layers, Preview, Timeline and inspector padding use the tokens.
- Panel titles are 15 px; layer/found rows use 12 px names and 10 px meta.
- Focus rings still come from the shell's global `:focus-visible` rule.

### One icon set

- New `static/studio/edit/icons.js`: inline SVG paths adapted from Lucide
  (MIT), inheriting `currentColor`.
- Used by Layers group icons, empty actions, eye toggles, preview Select /
  Draw box, and toolbar Undo / Redo / keyboard help.
- No icon font, external request or image sprite.

### One layer palette

- `LAYER_COLOURS` in `model.js`: Remove text amber, Text blue, Captions
  green, Effects violet, Colour gold, Audio teal.
- The same colours drive Layers rows, preview Clean/Text/Caption outlines and
  timeline bars.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Space` | Play / pause |
| `J` / `K` / `L` | Back 1 s / pause / play |
| `←` / `→` | One frame |
| `Shift` + `←` / `→` | One second |
| `Home` / `End` | Start / end of the moment |
| `V` / `B` | Select tool / Draw box |
| `Delete` | Remove the selected layer |
| `⌘Z` / `⇧⌘Z` | Undo / redo |
| `?` | Keyboard shortcut sheet |
| `Esc` | Close a tool or panel |

The `?` sheet is a real modal dialog with the full list. Timeline focus keeps
its own arrow handling and stops the event so a step is never applied twice.

Undo/redo now has a visible pair in the toolbar. Redo uses the existing
`POST …/edits/{id}/restore` route with a session-local stack; any new change
clears it.

### Empty states

- Layers: every empty group has a button with its own icon and verb — Add a
  text box, Add text, Open captions, Add an effect, Choose a colour, Add
  music.
- Timeline: empty tracks show an Add action that opens the same panel/action
  as the track header +.
- Inspector text/captions/effects already had their build/add controls; those
  remain the next action.

## Verified

- New source/Node tests: palette, icon set, tokens, shortcuts, help dialog,
  restore request, empty actions.
- Mounted Chromium at 1280×720 and 1024×680:
  - `?` opens the sheet and Escape closes it;
  - `B` / `V` switch preview tools;
  - one frame step is 1/30 s, Shift+arrow is one second;
  - Add text from Layers, then `⌘Z` removes it and `⇧⌘Z` restores it;
  - the three-column layout, box editing and fill flow still pass.
- Full suite: **2018 passed, 12 skipped, 1 deselected** on the P3 tree; the
  deselected Voice Room browser test fails identically on `88eeab9`.

## Known limits

- Redo is a session-local stack, not persisted across reloads.
- `J` means back one second; real reverse playback is not implemented.
- The shortcut sheet lists `Delete`, but deleting a caption cue still goes
  through the Captions panel because cues are not Edit layers.

## Next

P4 brings Import, Moments and Finish onto the same app bar, toolbar, panel
scroll and type rules.
