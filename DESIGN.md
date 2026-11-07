---
name: VibeCut Studio (legacy visual system)
description: Legacy dim workbench; DuckSuite replaces it with the Daylight Bench direction
colors:
  amber-work-light: "#e8a266"
  amber-work-light-hover: "#f0b27c"
  amber-ink: "#1a1209"
  bench-black: "#0b0b0c"
  panel: "#121214"
  panel-raised: "#17171a"
  panel-top: "#1d1d21"
  line: "#2a2a2f"
  line-strong: "#3a3a40"
  paper-white: "#f1efe9"
  muted: "#a3a1a6"
  dim: "#8a888f"
  ok-green: "#8ec9a3"
  bad-coral: "#e28a7c"
typography:
  display:
    fontFamily: "ui-serif, Iowan Old Style, Palatino Linotype, Palatino, Georgia, serif"
    fontSize: "clamp(30px, 3.2vw, 44px)"
    fontWeight: 500
    lineHeight: 1.06
    letterSpacing: "-0.025em"
  title:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 580
  body:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    lineHeight: 1.45
  body-editor:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: "13px"
  label:
    fontFamily: "ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif"
    fontSize: "12px"
  timecode:
    fontFamily: "SF Mono, ui-monospace, Menlo, Consolas, monospace"
    fontSize: "11px"
rounded:
  sm: "4px"
  md: "8px"
  control: "10px"
  card: "14px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "24px"
  "6": "32px"
components:
  button-primary:
    backgroundColor: "{colors.amber-work-light}"
    textColor: "{colors.amber-ink}"
    rounded: "{rounded.control}"
    padding: "9px 17px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "{colors.amber-work-light-hover}"
  button-ghost:
    textColor: "{colors.paper-white}"
    rounded: "{rounded.control}"
    padding: "9px 17px"
    height: "40px"
  button-ghost-hover:
    backgroundColor: "{colors.panel-raised}"
  button-quiet:
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "9px 17px"
    height: "40px"
  button-small:
    padding: "6px 12px"
    height: "32px"
  icon-button:
    size: "30px"
---

# Design System: VibeCut Studio

Recorded 2026-11-06 from `static/studio/studio.css` and `static/studio/edit/edit.css`. Classic and the Voice Room keep their own styles and are not covered here.

## Overview

**Creative North Star: "The Darkroom Bench"**

A dim, warm working room for long sessions. The picture is the lit object on the bench, the tools stay quiet around it, and amber marks what is active, like a safelight. Nothing competes with the video, because judging the video is the job.

Studio is an Operate surface. Its density is high in Edit: one fixed screen that never scrolls as a page, with panels and a timeline that scroll inside themselves, and small labels that assume a creator who is there for an hour. The other steps breathe a little more and open with a serif heading. A faint amber glow in the page corner is the one atmospheric touch.

**Key Characteristics:**

- Near-black, slightly warm tonal layers instead of shadows.
- One accent: amber, on the primary action, the selected item and the keyboard focus.
- Serif for step and stage headings, system sans for every control, mono for time.
- Plain, literal labels with a line of honest detail beside them.

## Colors

A warm near-black ramp, warm off-white text, one amber accent and two muted state colours.

### Primary

- **Amber Work Light** (#e8a266): the primary button, selection, focus ring and active timeline edge. A 13% tint (`rgba(232, 162, 102, 0.13)`) marks selected rows. Hover lifts to #f0b27c.
- **Amber Ink** (#1a1209): text on Amber Work Light.

### Neutral

- **Bench Black** (#0b0b0c): the page behind everything.
- **Panel** (#121214), **Panel Raised** (#17171a), **Panel Top** (#1d1d21): three steps of surface, each one closer to the creator.
- **Line** (#2a2a2f), **Line Strong** (#3a3a40): dividers and the ghost button border.
- **Paper White** (#f1efe9): main text.
- **Muted** (#a3a1a6), **Dim** (#8a888f): secondary and tertiary text.

### State

- **OK Green** (#8ec9a3) and **Bad Coral** (#e28a7c), each with a 12% tint for backgrounds. They report status and never decorate.

### Named Rules

**The Safelight Rule.** Amber means active or next. If two things on a screen are amber and neither is selected or primary, one is wrong.

**The Blue and Orange Rule.** On the Clean lane and preview, a box you drew is blue (#7fb7e8) and a box the scan found is orange. These are data colours and keep their meaning everywhere boxes appear. A dashed bar is found text with no layer yet.

## Typography

**Display Font:** the system serif (Iowan Old Style, Palatino, Georgia)
**Body Font:** the system sans (`-apple-system`, Segoe UI, Helvetica)
**Label/Mono Font:** SF Mono (`ui-monospace`, Menlo) for time and technical values

**Character:** an editorial serif gives each step a calm title, while native system fonts keep controls familiar and fast. Text is a loaded system stack, so nothing is downloaded and it works offline.

### Hierarchy

- **Display** (500, `clamp(30px, 3.2vw, 44px)`, line height 1.06, -0.025em): step headings and Finish stage headings.
- **Title** (580, 15px): panel titles in Edit.
- **Body** (400, 15px, line height 1.45): the shell. Prose keeps to about 620px.
- **Body Editor** (13px): Edit panels, whose small scale is `--edit-text-small` 12px, `--edit-text-body` 13px and `--edit-title` 15px.
- **Label** (11–12px): the most common size in the CSS, for rows, hints and timeline text.

### Named Rules

**The One Serif Rule.** The serif is for headings that name where you are. No control, row or timeline label uses it.

## Layout

Edit is a fixed frame: Elements on the left, the preview in the middle, layers and inspector on the right, and a full-width timeline below. The page itself never scrolls, and timeline widths are percentages, so 1280 and 1440 wide both fit with no sideways scroll. The other steps are a bounded grid that scrolls inside `.st-main`.

Spacing is a 4px-based scale (4, 8, 12, 16, 24, 32), exposed in Edit as `--edit-space-1` to `--edit-space-6`. Page gutters use `clamp(12px, 1.7vw, 24px)`.

The main breakpoints are 1366, 1100, 1023, 900 and 767 wide, plus 780 tall for short screens. Below 1023 the Edit inspector becomes a drawer or sheet.

## Elevation & Depth

The system is flat. Depth comes from the tonal steps of Panel, Panel Raised and Panel Top. Box shadows act as hairlines, not lift: `0 0 0 1px` in amber for selection, `inset 0 0 0 1px` for an inner edge, and `inset 2px 0 0` in amber for an active row.

**The No Lift Rule.** Do not float a surface with a soft drop shadow. A dialog or drawer is separated by its tone and its line.

## Shapes

Corners are gently curved and scale with the object: 3–5px on small chips and timeline bars, 8px on inputs and rows, 10px on buttons, 14px (`--st-radius`) on large cards. Borders are 1px.

## Components

Component variables are scoped to `#studio-root` and `.st-edit-panel`, so other pages keep their own rules.

### Buttons

- **Shape:** 10px radius, 40px tall, 9px 17px padding, 13.5px at weight 580. Small buttons are 32px tall at 12px text.
- **Primary:** Amber Work Light with Amber Ink. There is one per view.
- **Ghost:** transparent with a Line Strong border. Hover fills Panel Raised.
- **Quiet:** transparent, Muted text, for low-priority actions.
- **States:** focus is a 2px amber outline at 3px offset. Press moves down 1px over 140ms. Disabled is 42% opacity.

### Icon buttons

30px square with a transparent border, using one Lucide-derived icon set from `static/studio/edit/icons.js`. Every icon has a label and tooltip.

### Clean boxes and timeline bars

A box on the preview and its timeline bar are one object: select, move or resize either. The orange and blue colours follow the Blue and Orange Rule, and the bars stack in rows when they overlap so each stays clickable.

### Queue drawer

A slide-over from the Finish step with Queue and History tabs. The render card keeps a compact status strip with the real time left.

## Do's and Don'ts

### Do:

- **Do** keep the video the brightest thing on screen.
- **Do** use tokens from `#studio-root` rather than new hex values.
- **Do** put state in words as well as colour.
- **Do** keep Edit one fixed screen, with scrolling inside its panels.
- **Do** bump the `?v=` asset version in `static/index.html`, `static/studio/shell.js`, `static/studio/edit.js` and `static/studio/edit/index.js` when Studio's JavaScript changes.

### Don't:

- **Don't** add a second accent colour, or use amber for decoration.
- **Don't** use the serif on controls.
- **Don't** use soft drop shadows for depth.
- **Don't** add web fonts or remote assets. The app must work with the network off.
- **Don't** reuse blue or orange for anything other than drawn and found boxes on the Clean surfaces.
