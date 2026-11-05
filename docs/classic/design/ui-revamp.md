# Classic UI/UX review and revamp

Status: **proposal**, not implemented. Fifth UI pass after
`classic-responsive-review.md` (passes 1–4). Screens were captured at
`classic` `e56471c`; the current build is `c7032b8`, so this is a design
proposal, not a screenshot of the shipped UI.

Method: Node Playwright against a real fixture job
(`tests/classic_browser_harness.py`) at 1440×900, 1024×680 and 390×844, with the
text scan stubbed and the AI-fill status served in both its locked and ready
shapes. Screens read: home, cut frame, found text ticked, fill status, Finish,
narrow window. Plus a CSS/DOM audit of `static/classic/style.css` (3,643 lines)
and `static/classic/index.html` (1,438 lines).

The visual study of the proposed frame is
[`ui-revamp-study.html`](ui-revamp-study.html) (open it in a browser; no build
step, no network). Toggle **Cut / Finish** in its top bar; the link under Review
switches between a rendered reel and the empty state that the shipped screen is
missing.

## Where it stands

Classic is an **Operate** surface: the founder is mid-task and success is a
finished reel, not a feeling. The warm charcoal + amber identity, the serif
spoken line and the mono timecodes are worth keeping — they make the tool feel
like a cutting table rather than a SaaS form. What is missing is not taste, it
is system: too many type sizes, too many equally loud controls, one screen with
no content at all, and an inspector that has become the whole app.

| Heuristic | Score | Note |
|---|---|---|
| Visual hierarchy | 3/5 | The frame leads, but three serif headings inside the tool compete with it. |
| Consistency | 2/5 | 21 font sizes, 19 radii, four button weights, three naming systems for the same action. |
| Legibility | 3/5 | 11 px is used 140 times; 9–10 px microcopy exists; mono caps for labels. |
| Feedback | 3/5 | Status lines and `aria-live` are good; the AI-fill card leaks absolute paths. |
| Workflow clarity | 2/5 | No visible path from "cut" to "rendered"; Render sits at the bottom of a long scroll. |
| Dead ends | 1/5 | Finish with no render is an empty page. |
| Responsive | 2/5 | The frame layout is 1000 px+; 1024 cramps, tool labels vanish, 390 is a dead column. |
| Accessibility | 3/5 | Focus rings and reduced motion are handled; hit targets and micro type are not. |

## Findings

### P0 — Finish is blank

`body.editor-frame.finish-frame` hides `.clean-stage`, `.hook-panel` and
`.result-ready`, hides the timeline and settings panes, and shows the preview
pane — whose only child, `#player-wrap`, is `hidden` until a render exists. A
founder who presses **Finish** before rendering gets an empty screen with a
**Back to edit** button and no explanation. Evidence: `05-finish-1440.png`.

There is also no visible route from Finish to the action that fixes it: Render
lives inside `#audio-panel` in the settings pane, which Finish has just hidden.

### P0 — the bulk Clean bar breaks the moment AI fill is ready

With both engines installed, the found-text card's action row is
`Select all · Clear · [AI fill] · [STTN · vid…] · Remove ticked`. In a 400 px
inspector the two selects clip at the card edge and the primary button wraps
underneath, right-aligned. The promised engine label
("STTN · video, best on subtitles") can never fit a select of that width.
Evidence: `08-fill-ready.png`, `09-fill-ready-ticked.png`.

### P1 — the inspector is the app

`#audio-panel` (open by default) holds Copy, Sound, Texts & Effects and Script,
then Render/Draft — after Clean, Find text and the optional mixer. Two sections
say the same thing: the Clean card tells you to scan, and a separate
"Find text on screen" card scans. At 1440×900 the inspector's first screen is
Clean + the AI-fill card + a bare sentence; Render is several scrolls below.
Evidence: `02-editor-1440.png`, `04-fill-status.png` (the section title has
scrolled away, so the column has no header).

### P1 — two things named Clean, and Delete next to it

The result bar carries `Work files ▾ · Clean · Delete`. **Clean** there means
"delete job files", and **Clean** in the inspector means "cover text". Delete,
an irreversible action, sits one careless click from the file-cleanup control.
Evidence: all cut screenshots.

### P1 — the work is not visible as a path

The top bar says `03 cut`, the button says `Finish`, the render button says
`Render 30s reel`, the output appears in `#player-wrap`, and the timestamps and
formats live under it. Nothing on screen expresses **cut → render → download**
as one sequence, so Finish reads as "done" when it is actually "review".

### P1 — 1024 px is the awkward size

The frame layout starts at 1000 px. At 1024 the three columns are ~300/340/310
px: tool labels disappear (`body.editor-frame .clean-tool-label {display: none}`
under 1180 px), the Moments rail clips its fifth card, "TEXT ON SCREEN · 2 found
· tick the ones to remove" wraps to three lines and **Remove ticked** is cut off
at the card edge. Everything still *works*; nothing is comfortable.
Evidence: `06-editor-1024.png`.

### P1 — type and shape sprawl

- 21 distinct font sizes across 274 `font-size` declarations; 9, 10, 10.5, 11,
  11.5, 12, 12.5, 13, 13.5 all appear as UI text.
- 19 distinct `border-radius` values (2, 3, 4, 5, 6, 10, 12, 14, 16, 18, 20, 26,
  999, `50%`, …).
- 46 `text-transform: uppercase` rules, most of them 10–11 px mono labels
  (`FRAME`, `MOMENTS`, `EDIT`, `TEXT ON SCREEN`, `MISSING`, `READY`).
- Serif headings appear inside the tool four times (Moments, Smart Cut, Edit,
  Clean), which is a landing-page device used in an operational panel.

### P2 — smaller, real

- `#clean-empty` ("No boxes yet. Scan for text on screen, or draw a box on the
  frame.") is an unstyled sentence floating between two cards.
- The found-text row draws a checkbox and a second square (the crop thumbnail)
  that is empty for a fixture and reads as a duplicated control.
- The AI-fill locked state prints the full model path
  (`/private/tmp/vc/review/data/models/fill`) into the panel; the ready state
  prints "About 5 s per frame on this Mac…" inside a 44 px row.
- The "Optional: add keys and voices in Setup" banner is a full-width attention
  strip on every screen, including a cut that needs no setup.
- Home: `Dissect video` sits at y≈890 on a 1440×900 window — pass 4 fixed this
  at y=790; the hero and banner have grown back since.
- Primary buttons are white; the accent amber is only decorative (brand dot,
  eyebrow numbers, score rings). Selection state uses a different visual
  language again (white fill on segmented controls).

## The revamp

**Direction: keep the cutting table, build the system around it.** Not a new
visual world — the identity is good. A revamp here means one type scale, one
control system, one clear path from cut to file, and an inspector that fits in
a column.

### 1. Frame

- **Top bar, 52 px:** brand, `Cut 03`, the cut's spoken line (13 px, one line,
  ellipsis), meta line; right side a single segmented **Cut · Finish** switch,
  then `⋯` (New video, Work files…, Clean job files…, Delete cut…).
- **Three columns with a minimum, not a ratio:** `minmax(360px, 0.95fr)
  minmax(420px, 1.15fr) minmax(360px, 0.95fr)`. Below 1180 px the layout drops
  to **two columns** (frame + story), and the inspector becomes a right drawer
  opened by its tab — never a squeezed third column.
- **Preview pane:** the frame keeps the pane's height; the tool rail moves to a
  36 px vertical strip beside it (Box, Undo, Redo, Refresh — icon over a 10 px
  label, labels *always* visible). Under the frame, one transport row: play,
  `0:01.2 / 0:23.0`, clip ticks, and the box hint on the right.
- **Finish** is a state of the same frame, not a new page: the player takes the
  left two-thirds, the right third becomes **Review** (file size, duration,
  Download, SRT/VTT/EDL/XML, Review link). With no render it is an empty state
  with one action: **Render this cut →**. Finish never shows nothing.

### 2. Inspector

- A tab bar — **Clean · Text · Sound** — with the count of items in each
  (`Clean 2`). Tabs replace eight stacked cards.
- Sticky footer inside the inspector: `Draft` (secondary) and
  `Render 30s reel` (primary). Always reachable, never scrolled away.
- Clean absorbs the scan: one card with the found list, a scan button in its
  header (`Scan text`), and the layers below it. The second "Find text on
  screen" card is deleted.
- AI fill becomes two engine chips with a state dot (`STTN ● ready`,
  `LaMa ● not installed`) and a `Details` disclosure for paths, per-frame cost
  and the preview. No absolute path in the default view.

### 3. Type scale — 21 sizes to 6

| Token | Size / weight | Used for |
|---|---|---|
| `--fs-display` | 44 px serif | Home hero only |
| `--fs-quote` | 22 px serif | The cut's spoken line, hook copy |
| `--fs-title` | 15 px / 600 sans | Panel and card titles (Clean, Story, Review) |
| `--fs-body` | 13 px / 1.5 | Body copy, rows, controls |
| `--fs-label` | 12 px / 500 | Field labels, chips, buttons |
| `--fs-meta` | 11 px mono, tabular | Timecodes, scores, versions, file paths |

Rules: serif never appears inside a card; uppercase only for 1–2 word state
chips at 12 px; no text below 11 px, and 11 px only when it is mono data.

### 4. Controls

- **Primary:** amber `#e8a266` fill with `#1a1206` ink (9.5:1) — one per
  screen (Render, or Download on Finish). White is retired as a fill so the
  loudest thing on screen is always the next action.
- **Secondary:** 1 px `--line-2`, transparent, text at `--text`.
- **Tertiary:** text button, `--text-2`, underline on hover.
- **Destructive:** only inside `⋯`, with a confirm that names the cut.
- Heights: 32 px dense, 36 px toolbar, 44 px under 980 px and for coarse
  pointers. Radii collapse to three: 8 (controls), 12 (cards), 16 (stage and
  modals).
- Segmented controls are the only "selected" pattern (Cut/Finish, tabs, target
  length); no red/white fill for selection.

### 5. Clean card, concretely

```
Clean                                    2 found · Scan text
┌──────────────────────────────────────────────────────────┐
│ ☑ Subtitle      Burned into the caption zone      ⌄      │
│ ☐ Watermark     Locked · use your original file          │
└──────────────────────────────────────────────────────────┘
[ Blur | Cover | AI fill ]              Remove 1
AI fill  ● STTN ready   ○ LaMa not installed        Details ⌄
```

- Row = checkbox (16 px) + kind chip + label 13 px + reason 12 px, one line,
  `title` for the full text. No second empty square: the thumbnail only renders
  when a crop actually exists.
- The bulk bar is sticky inside the card while anything is ticked, so the action
  never wraps under the controls. The method is a segmented control (three
  options), and the engine select appears only when **AI fill** is chosen, with
  short labels (`STTN`, `LaMa`) and the long description beneath.
- Layers rows: 40 px, method chip + eye + `⋯`. "No boxes yet" becomes a real
  empty state with two inline actions (Draw a box, Scan text).

### 6. Tokens to add

```css
:root {
  --fs-display: 44px; --fs-quote: 22px; --fs-title: 15px;
  --fs-body: 13px; --fs-label: 12px; --fs-meta: 11px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px;
  --space-4: 16px; --space-5: 24px; --space-6: 32px;
  --radius-sm: 8px; --radius: 12px; --radius-lg: 16px;
  --text-2: #b9b6ae; --text-3: #8f8d86;   /* 5.0:1 on --bg */
  --ok: #8fbc8b; --warn: #e0b070;
}
```

`--dim` is `#6c6b70` in `:root` (3.72:1) and then re-declared as `#9a999f`
inside `body`. That patch works but leaves a token that lies; fold the real
value into `:root` and keep Voice Room's parity check in mind
(`tests/test_voice_room_page.py` compares the lanes).

### 7. Motion

120 ms ease-out for hover and press, 140 ms cross-fade when switching inspector
tabs, 180 ms fade for a frame arriving. No entrance animations on panels, no
shimmer in progress bars. `prefers-reduced-motion` already disables the rest —
keep that.

## Roadmap

| Phase | Work | Risk |
|---|---|---|
| **R0** (½ day) | Finish empty state + Render route back; delete the duplicate scan card; 11 px labels → 12 px; icon labels back at 1024; Delete and Clean job files into `⋯`; `--dim` folded into `:root` | Low. Docs copy and additive markup; three browser specs must be re-run. |
| **R1** (1–2 days) | Inspector tabs + sticky render footer; tool rail; top bar cut title and Cut/Finish switch | Medium: DOM moves; keep every `id` the specs use. |
| **R2** (2–3 days) | Type scale and control system migration; Clean card restructure; engine chips; spacing tokens | Medium-high: touches much of `style.css`. Do it file-wide, in one pass, with screenshots at 1440/1024/390. |
| **R3** | Finish review screen, home fold, found-row thumbnails, AI-fill details disclosure | Low. |

## Acceptance

- 1440×900, 1024×680 and 390×844 screenshots for: home, cut, Clean with a tick,
  AI fill ready, Finish with no render, Finish with a render.
- No text below 11 px; no more than 6 font sizes; 3 radii; one primary per
  screen.
- Finish is never empty: render present → player + Download; render absent →
  one action that starts a render.
- Every row in Clean is operable at 1024 px without wrapping, with both engines
  installed.
- Keyboard: `?` sheet, `B` box, `⌘Z`, `Tab` order through tabs → list → actions.
- Tests: `tests/test_classic_clean_browser.py`,
  `tests/test_classic_fill_browser.py`, `tests/test_classic_frame_browser.py`
  and `node --check static/classic/app.js` stay green.

## What the revamp does not change

Product truth and the contract the suite relies on: `body.editor-frame`,
`.editor-pane-preview|timeline|settings`, `#clean-*`, `#result-view`,
`#result-top`, `#player-wrap`, `#finish-cut`, the Clean box storage rules, the
AI-fill engines and their costs, the platform capability copy, and Vietnamese
string coverage. This revamp is visual and structural, not behavioural.

## Open questions for the founder

1. **Amber primary or white primary?** Amber is warmer and more distinctive;
   white is neutral and familiar. The study uses amber.
2. **Inspector tabs vs one long scroll?** Tabs save the Render button; a scroll
   keeps everything visible at once.
3. **Two columns under 1180 px (inspector as a drawer) or three cramped?**
   The study shows three at 1440 only.
