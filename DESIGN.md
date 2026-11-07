# DuckSuite design

Direction: **Daylight Bench**.

A calm, warm Mac workspace. The video is the brightest object. Chrome is daylight; the canvas is dark.

## Principles

- One primary action per screen.
- The picture leads; controls recede.
- Local is visible: “On this Mac,” model status, disk, cloud off.
- Honest progress. No fake ETA, no silent fallback.
- Mac-native where it matters: menus, Settings, file panels, keyboard, trackpad.

## Colour

| Token | Value | Use |
|---|---|---|
| Canvas | `#0E0E10` | Video surround, always dark |
| Surface | `#F7F4EE` | Window |
| Surface raised | `#FFFFFF` | Cards, panels |
| Ink | `#1C1B19` | Main text |
| Muted | `#5F5B54` | Secondary text |
| Line | `#E4DED3` | Borders |
| Accent | `#A9540C` | Text/icon accent, focus |
| Accent fill | `#F0A45C` | Primary button |
| Success | `#2F7D5B` | Ready, verified |
| Warning | `#8A5A00` | Caution |
| Danger | `#B23A2E` | Error, destructive |
| Cloud | `#2F6FEB` | Cloud status only |

## Type

- Display: New York / system serif, 32–44 px, welcome and empty states.
- Title: SF Pro, 17–20 px semibold.
- Body: SF Pro, 15 px.
- Panel: SF Pro, 13 px.
- Label: SF Pro, 12 px.
- Timecode/hash: SF Mono, 11–12 px.
- Minimum 12 px labels. No 9–10 px text.

## Space and shape

- 4/8/12/16/24/32/48 scale.
- Page gutters 24; card padding 16–20.
- Controls 28/32/40 high; primary 40.
- Radii: 6 chips, 8 inputs, 10 buttons, 14 cards.
- 1 px borders. Shadows only for native popovers/sheets. No glass, gradients or glow.

## Motion

- 120–180 ms for controls; 220–240 ms for sheets.
- Ease-out. No bounce.
- Respect Reduce Motion.
- No confetti on export. No auto-playing sound.
- Progress never moves backward.

## Accessibility

- WCAG 2.2 AA.
- 4.5:1 body contrast; 3:1 large text and controls.
- Visible 2 px focus ring at 3 px offset.
- Full keyboard path; no drag-only action.
- VoiceOver labels and live regions for render, queue and model download.
- 200% zoom; test at 1024×700, 1280×800, 1440×900.
- Reduce Motion, Reduce Transparency, Increase Contrast.
- Colour never the only signal.

## Mac conventions

- Menu bar: File, Edit, View, Render, Help.
- Settings `⌘,`.
- `⌘N` new project, `⌘O` import, `⌘S` save, `⌘E` export, Space play/pause.
- `NSOpenPanel` / `NSSavePanel`; security-scoped bookmarks.
- Drag/drop, Quick Look, Share sheet, notifications, Dock badge for render completion.
- Autosave, window restoration, standard About panel.
- Native alerts for destructive actions; no custom web modal for system decisions.

## Product family

DuckSuite uses amber and medium density. DuckClean is white and calm. DuckClassic is dense and quick. DuckStudio is dark and full. Shared tokens, typography, grid and states; product accents differ.
