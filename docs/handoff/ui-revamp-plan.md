# Studio UI and UX revamp plan (2026-11-01)

The founder's report: "app is too hard to use, especially the editor, button
hiding under scrollbar and i don't know how and where the layer are added so
i can clean it."

This plan comes from a live walk-through of Studio on 8795 (job
`77d072b8d44c`, the Chinese subtitle video) at 1440x900, 1280x720 and
1024x680, plus a read of `static/studio/edit/**` and `edit.css`. Nothing was
changed during the review.

## 1. What is wrong today

### 1.1 The editor does not fit on one screen

- The editor is a long **scrolling page**. Preview, timeline and the
  settings panel are stacked in one document that scrolls inside `.st-main`.
- At **1280x720** the timeline starts at y = 810, below the screen. You cannot
  see the preview, the timeline and the settings at the same time.
- The settings panel (`.st-inspector-body`) scrolls **again** inside the page
  (`max-height: min(660px, calc(100vh - 250px))`). Two scroll areas, one inside
  the other. With "always show scrollbars" or a mouse, the inner scrollbar sits
  on top of right-aligned controls ("Remove all detected text", "Add box",
  "Add text"), which have only 12 px of right padding and no
  `scrollbar-gutter`.
- At **1040 px and below**, "Adjust moment" moves the whole settings panel
  **under the timeline**. You edit a layer with the preview scrolled off the
  top of the screen.

### 1.2 The sticky bar covers content

- "Back to Moments · Saved · Adjust moment · Next: Finish" is a sticky bar
  (`.st-edit-stepnav`, z-index 30) that sits **below** the page title. When you
  scroll, it floats over the middle of the preview and over timeline rows
  (seen hiding the Captions and Effects tracks at 1024x680).

### 1.3 Too many controls at the top, in three rows

The top of the editor has: step tabs, video name, Change video, Voice Room,
Menu; then the title; then Moment picker, five aspect buttons, All moments,
Undo trim, Undo; then Back to Moments, Saved, Adjust moment, Next: Finish.
About 20 controls before the picture. The settings tabs truncate
("Texts & Ef…").

### 1.4 Layers have no place you can see or touch

This is the core of "I don't know where the layers are added":

- **Clean boxes are not drawn on the preview.** `overlay.js` draws text,
  graphics and captions, but no Clean box. You cannot see where a box is, and
  you cannot drag or resize it.
- A box is placed with **four number fields** (x, y, width, height in percent
  of the original frame, "before the 9:16 crop").
- "Add box" adds a default box at the bottom (`x 0.08, y 0.72, w 0.84,
  h 0.16`) with no visual feedback on the picture.
- The timeline has a **Clean** track, but its empty state "No old text
  marked" has no add button, and clicking it does nothing useful.
- There is no single **Layers** list. Clean, Text, Effects, Captions, Colour
  and Audio each live in a different tab with different patterns.

### 1.5 The clean flow dead-ends

- On this job the text scan was **cancelled** earlier, so Check has 0 text
  regions. The panel says "The full text pass did not run" but offers no
  **Scan for text** button. "Remove all detected text" is still shown and does
  nothing useful.
- The copy is engineer language: "Remove interpolates nearby pixels… crop
  guard keeps the region out of the crop", "Rights", "Check region",
  "tracklet".
- The intro copy is now **wrong**: "Nothing invents missing pixels". AI fill
  does exactly that.
- AI fill is a third option buried in a kind dropdown, with no preview.

## 2. Principles for the revamp

1. **One screen, no page scroll in the editor.** A fixed app frame; only lists
   inside panels scroll, each with a stable scrollbar gutter.
2. **See it, touch it.** Every layer that has a place on the picture is drawn
   on the preview and can be selected, moved and resized there.
3. **One layer list.** Every layer of the moment, of every kind, in one list,
   in the same order as the timeline tracks.
4. **Task first, settings second.** The main tasks get one obvious button:
   remove on-screen text, add a title, captions on or off, music. Detail goes
   in the panel for the selected layer only.
5. **Plain words.** "Remove text", "Blur", "Cover", "AI fill". No internal
   terms.
6. **Never a dead end.** Every empty state says what to do and has the button
   to do it.

## 3. Target layout: the editor

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ VibeCut  Import · Moments · [Edit] · Finish     video.mp4 ●Ready     Menu ▾ │  48px app bar
├──────────────────────────────────────────────────────────────────────────────┤
│ ◀ Moments  Moment 01 ▾  [9:16|4:5|1:1|16:9]   ↶ ↷  Saved ✓        Finish ▶  │  44px toolbar
├────────────┬───────────────────────────────────────────────┬─────────────────┤
│ LAYERS   + │                                               │ SELECTED LAYER  │
│            │                                               │                 │
│ ▸ Text (1) │              PREVIEW (fits height)            │ Remove text     │
│ ▸ Remove   │        boxes drawn, drag / resize handles     │ ○ AI fill ●     │
│   text (3) │                                               │ ○ Blur          │
│ ▸ Captions │           [▶] 0:12.4 / 0:45.8   ⛶            │ ○ Cover         │
│ ▸ Effects  │                                               │ Time 0:10–0:14  │
│ ▸ Colour   │                                               │ [Delete]        │
│ ▸ Audio    │                                               │                 │
├────────────┴───────────────────────────────────────────────┴─────────────────┤
│ TIMELINE   sentences | remove text ▬▬ ▬ | text | captions | effects | audio  │  ~200px, resizable
└──────────────────────────────────────────────────────────────────────────────┘
```

- **App bar (48 px):** logo, the four steps, video name and status, one Menu.
  Change video and Voice Room move into Menu.
- **Toolbar (44 px), not sticky-over-content:** Back to Moments, moment
  picker, aspect, undo and redo (one pair: trim undo joins the same history),
  save state, Finish. "All moments" moves into the moment picker.
- **Left: Layers (240 px).** Groups in timeline order. Each group has a +
  button. Each row: icon, name, time, eye toggle (hide in preview), and a
  warning dot when the layer has a problem. Click selects; Delete key removes.
- **Centre: Preview.** Fits the available height. Draws every layer with a
  position: Clean boxes (dashed, coloured by method), text boxes, effects.
  Selected layer: solid outline, 8 handles, drag to move. Tools in a small
  floating bar on the preview: Select (V), Draw box (B), Safe zones, Exact
  frame.
- **Right: Selected layer (320 px).** Only the selected layer's settings. With
  nothing selected: the moment summary and the three main tasks (Remove text,
  Add title, Captions).
- **Bottom: Timeline (resizable, default 200 px).** Always visible. Track
  headers have + buttons. Clicking a bar selects that layer in all three
  places.

### Sizes

| Width | Layout |
|---|---|
| ≥ 1280 | Full layout above. |
| 1024–1279 | Layers panel becomes a 48 px icon rail that opens as an overlay; the settings panel stays on the right. Nothing moves under the timeline. |
| < 1024 | Edit shows a notice: "Editing needs a wider window (1024 px)". Preview and Finish still work. |

Height: at 720 px the timeline shrinks to 3 visible tracks with its own
scroll; the preview shrinks first, the timeline never leaves the screen.

## 4. Target flow: remove on-screen text

1. Open a moment in Edit. If the video has not been scanned for text, the
   Remove text group shows **"Find text on screen"** (runs the Check text
   pass, with progress and Cancel in the panel).
2. Found text appears as a list in the Remove text group: a thumbnail of the
   frame, the words read, the time, and a tick box. Boxes appear on the
   preview at the same time, dashed. Watermarks and screen UI show greyed with
   the reason ("Platform watermark: VibeCut does not remove these").
3. **"Remove all found text"** ticks all allowed rows. A method picker sits
   next to it: **AI fill** (default once the models are present), Blur, Cover.
4. Missed something? **Draw box** (B) on the preview, then drag the timeline
   bar edges to set when it shows. No number fields unless you open
   "Exact position".
5. **Preview this frame:** for AI fill, a button runs LaMa on the current
   frame only (a few seconds) and shows before and after with a slider.
   Blur and Cover preview live.
6. The render does the full fill, as now.

Copy for the group intro: "Remove text burned into the video. AI fill
rebuilds the background; Blur and Cover hide the text. Check the result
before you post."

## 5. Visual system

Studio already has a dark theme with tokens in `studio.css`. The revamp keeps
the look and tightens it:

- **Spacing scale** 4 / 8 / 12 / 16 / 24 / 32. Panels use 12 px inner padding
  and 16 px between groups. No ad hoc margins.
- **Type scale:** 12 (labels, mono times), 13 (body in panels), 15 (panel
  titles), 28 (page title, Import and Moments only). The editor drops the big
  "Shape the moment" title: the toolbar names the moment.
- **Controls:** one button height (32 px, 28 px in dense panels), one input
  height, icons from one set (Lucide, MIT, inline SVG), focus ring on every
  control.
- **Layer colours:** Remove text amber, Text blue, Captions green, Effects
  violet, Audio teal. Used on the layer row, the preview outline and the
  timeline bar.
- **Scroll areas:** `scrollbar-gutter: stable` and 4 px extra right padding on
  every scrolling panel; no nested vertical scroll inside a scrolling panel.
- **Keyboard:** Space play, J/K/L, ←/→ one frame, Shift+←/→ one second,
  V select, B draw box, Delete remove layer, ⌘Z / ⇧⌘Z, ? shows the list.

## 6. Other steps (light touch)

- **Import:** fine at desktop size. Move the rights tick next to the start
  button it gates; make the recent list the first thing when videos exist.
- **Moments:** keep the cards; show text-scan state per video and a "Scan for
  text" action there too.
- **Finish:** same app bar and toolbar pattern; long settings in panels with
  the same scroll rules.

## 7. Phases

Each phase is one shippable change on the studio lane, tested by the founder
by hand on their own videos with `scripts/record.sh`. Classic (`/classic`) and
Voice Room (`/voices`) must keep working; nothing here touches
`static/classic/**` or `static/voice/**`.

| Phase | What | Done when |
|---|---|---|
| **P0 · Fit and fix** | Fixed editor frame (no page scroll); toolbar replaces the sticky step bar; one scroll per panel with stable gutter; 1024–1279 keeps settings on the right; tab labels not truncated; fix the wrong clean copy; "Find text on screen" button when the scan is missing or cancelled. | At 1280x720 preview, timeline and settings are all visible with no page scroll; no control sits under a scrollbar; the founder can start a text scan from Edit. |
| **P1 · Layers you can see** | Layers panel; Clean boxes drawn on the preview with select, move, resize; Draw box tool; timeline bars select layers; + on track headers; Delete key. | The founder adds, moves and deletes a Remove-text box without typing a number. |
| **P2 · Remove text flow** | Found-text list with thumbnails and ticks; Remove all with method picker; AI fill single-frame preview with before/after slider. | The founder removes every subtitle in a moment and sees an AI fill preview before rendering. |
| **P3 · Polish** | Spacing and type scale across Edit; icon set; layer colours; keyboard shortcuts and the ? sheet; empty states for every group. | The founder's recorded run has no hesitation over where a control is. |
| **P4 · Other steps** | Import, Moments and Finish brought to the same frame and rules. | Same check on the other steps. |

P0 is small and removes most of the pain the founder named. P1 and P2 answer
"where are the layers". P3 and P4 make it feel finished.

## 8. Files

All inside the studio lane's own area:

- `static/studio/edit/index.js`, `inspector.js`, `timeline.js`, `preview.js`,
  `overlay.js`, `edit.css`, `layers/*.js`
- `static/studio/studio.css`, `shell.js` (app bar)
- New: `static/studio/edit/layers-panel.js`, `static/studio/edit/canvas-tools.js`
  (box select, move, resize, draw)
- Server: one route for the single-frame fill preview in `routes_studio.py`
  (P2), reusing `textfill`.

## 9. Risks

- **Preview geometry:** Clean boxes are in source coordinates, before the
  crop. Drawing them on a 9:16 preview needs the same crop maths as
  `compose_render._base_crop`. Boxes partly outside the crop must still be
  selectable (draw the part inside, with an edge marker).
- **Undo:** trim undo and layer undo are separate today; one history is a
  real change in `index.js`.
- **Speed of the single-frame fill preview:** LaMa took 16 s per frame on the
  swapping 8 GB Mac. P2 shows a spinner and allows cancel; if it stays slow,
  the preview uses STTN on a short window instead.
