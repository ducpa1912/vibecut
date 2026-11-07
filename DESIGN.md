# DuckSuite design

Direction: **Daylight Story Desk**.

A calm local Mac workbench. Warm paper around a dark video canvas. Amber is the work light. The product is one long video becoming a short, auditable list of stories, cleaned and rendered.

## Principles

- The work starts on Welcome, not a marketing page.
- Check cuts scenes first and opens Editor immediately; transcript, text detection, and stories continue in the background.
- Clean is a focus mode inside Edit, not a separate skin.
- Preview proves the clean with a before/after frame; blur is a processing placeholder, never a render fallback.
- Render is honest: real state, real progress, no fake ETA.
- Local is visible: “On this Mac,” model status, disk, cloud off.
- Mac-native where it matters: menus, Settings, file panels, keyboard, trackpad.

## Flow

```text
Welcome → Check → Edit ⇄ Clean Focus → Preview → Render → Welcome
```

Welcome is home. The project stepper is Check / Edit / Preview / Render. Clean Focus is the Edit step in focus mode.

## Colour

| Token | Value | Use |
|---|---|---|
| Paper | `#F7F4EE` | Window, page |
| Paper 2 | `#ECE6DC` | Sunken areas |
| Panel | `#FFFDF9` | Cards, rails |
| Panel 2 | `#FAF7F1` | Nested rows |
| Ink | `#29251F` | Main text |
| Muted | `#726B60` | Secondary text |
| Line | `#E2DBCF` | 1px borders |
| Amber | `#C46812` | Text/icon accent, active step |
| Amber fill | `#D97716` | Primary button |
| Amber soft | `#FDF0DF` | Selected row, focus mode |
| Success | `#2D7B59` | Ready, verified |
| Danger | `#B63A2C` | Error, failed, destructive |
| Video | `#0C0C0D` | Video canvas, always dark |

No gradients, glass, glow, or decorative texture.

## Type

- UI: SF Pro. No display serif.
- Title: 17–20 px semibold, tracking -0.02em.
- Body: 13–15 px.
- Label: 12 px minimum; uppercase labels 11–12 px with tracking.
- Timecode, hash, progress: SF Mono, tabular numerals, 10–12 px.
- Scene titles truncate with ellipsis; never hard-clip.
- Do not use 9 px text except chips inside dense rails; body copy never below 12 px.

## Space and shape

- 4/8/12/16/24/32/48 scale.
- Page gutters 24; card padding 14–20.
- Controls 30/34/46 high; primary 46.
- Radii: 999 chips, 6–8 inputs, 8 buttons, 10–12 cards.
- 1 px borders. Shadows only on dialogs and floating menus.
- One amber primary action per screen. Red only for destructive/error.

## Chrome

- Same top bar on every screen: duck mark + DuckSuite, project selector, facts, Local · ready, queue count, Settings, Back to Welcome.
- Same stepper for an open project: Check / Edit / Preview / Render.
- Same rail widths: left 220–284, right 320–342. Center flexes.
- Welcome has no active stepper.
- Clean Focus labels the Edit step “Clean focus”; no second selected pill.
- 1280×800 minimum; 1440×900 target. 200% zoom reflows rows to cards and rails to drawers.

## Screen contracts

### Welcome
Upload box, recent projects, active render queue, recent finished output, engine/disk. No marketing hero, no feature cards.

### Check
Source card, stage progress, player, scene strip, one Check panel. Stage 1 scenes complete; Editor opens. Stage 2 transcript, text detection, stories continue. Scene strip says “scroll →” when clipped.

### Edit
Proof Rows left, preview and transcript center, Clean/Captions/Voice inspector right, fine trim bottom. Clean tools: proof pair → Fill/Blur/Off → layer list. Clean focus entry lives here. Layer labels use product language, not raw OCR, e.g. “Screen text 01”; OCR sample stays in tooltip.

### Clean Focus
Same Edit frame. Only clean tools. Scene list with proof/layered status, before/after pair, Fill/Blur/Off, layer list, LaMa status, Preview clean, Clean all, Back to Edit. No captions, voice, story tools, or fine trim.

### Preview
Before / Compare / After player. After is the default full clean proof. Compare is the wipe. Current scene first; clean runs scene by scene. Unprocessed after side is a blurred text-region placeholder labeled Cleaning. Readiness counts proofs, not “clean”, until a human verifies.

### Render
Source-aspect 1080p output (1080×1080 for a square project). Queue with duration, resolution, state, progress, Play/Reveal. One queue control: Queue idle / Pause / Resume. Cancelled rows show a neutral dash, not a progress bar. Finished output returns to Welcome.

## Motion

- 120–180 ms controls; 220–240 ms sheets.
- Ease-out. No bounce. Respect Reduce Motion.
- Progress never moves backward.
- Scanning/proof states may pulse a small status dot; no confetti.

## Accessibility

- WCAG 2.2 AA.
- 4.5:1 body contrast; 3:1 large text and controls.
- 2 px amber focus ring at 3 px offset.
- Full keyboard path; no drag-only action.
- VoiceOver labels and live regions for render, queue, check, and proof states.
- 200% zoom; test at 1280×800, 1440×900.
- Colour never the only signal.

## Mac conventions

- Menu bar: File, Edit, View, Render, Help.
- Settings `⌘,`.
- `⌘N` new project, `⌘O` import, `⌘S` save, `⌘E` export, Space play/pause.
- `NSOpenPanel` / `NSSavePanel`; security-scoped bookmarks.
- Drag/drop, Quick Look, notifications, Dock badge for render completion.
- Autosave, window restoration, standard About panel.
- Native alerts for destructive actions.

## Product family

DuckSuite uses amber and medium density. DuckClean is white and calm. DuckClassic is dense and quick. DuckStudio is dark and full. Shared tokens, typography, grid, and states; product accents differ.

## Review records

UI reviews live in [docs/teams/README.md](docs/teams/README.md). Each block has a first review and a final review, with screenshots, verdict, good-to-go list, revision list, bug list, and failed items.
