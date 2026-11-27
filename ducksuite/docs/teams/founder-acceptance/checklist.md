# Founder acceptance test — Edit surfaces

All five Edit review rounds passed the product-owner gate. This sheet is the script for the
founder's own pass, with what to look at and what should be true.

## Before you start

```bash
./scripts/build-xcode-dev.sh
open build/DuckSuite-Xcode.app
```

Use a copy of a real project. The review rounds ran on a scratch copy; nothing was written to a
founder project. Minimum window to test: 1024×700, then 800×600, then 200 % zoom
(View → Zoom In, or ⌘+ twice).

## Round 1 — Edit desk + Clean

1. Open a project → Edit. Select a layer in the Clean tab.
2. **Expect** Fill / Blur / Off directly under the layer list, no scrolling. With the fill engine
   absent, an amber line beside the choice says Fill will not run.
3. Pick Blur, look at the proof pair: the right image says **Not cleaned yet**, and Clean Focus
   labels the unproved side **Source · no proof yet**, never a bare After.
4. Press Paint a mask: the toolbar (Kind, Size, Undo, Clear, Apply, Cancel) must be inside the
   window at 1440×900 and 1024×700.
5. Shrink to 800×600: the page must not scroll as one document; the timeline scrolls inside its
   own panel.

## Round 2 — Cut Focus

1. Edit → Cut. Click Warm under Look: the four grade sliders move, the SFX lane stays at 0 effects.
2. Set 16:9: the frame keeps its shape, no clipping, the badge reads the Cut output (1920 × 1080).
3. Change aspect with Fit active: a toast says Fill crops and Fit keeps the picture.
4. Open Cut Focus: three cards in a dock, the inspector does not duplicate, Back to timeline is
   visible.

## Round 3 — Script Focus

1. Edit → Script → Open Script Focus with a project that has cues.
2. **Expect** one script list (no duplicate Cues column), a summary line with line count,
   coverage and **SRT only / Burned into video**, and exactly one current row that follows a seek.
3. Click any timecode: the player seeks and that row scrolls into view.
4. Translate or Rewrite: a confirm states how many lines are replaced; inputs and the three bulk
   controls disable while it runs.
5. Resize to 1024×700, 800×600, 200 %: the page equals the window, the preview strip never covers
   the editor, the tools rail stays beside the list.

## Round 4 — Audio Focus

1. Edit → Audio → Open Audio Focus (with at least one music and one voice row).
2. **Expect** Add music / Add sound / Preview mix in the card header, a placement strip with scene
   ticks, and a readout: Source bed, Voice or dub, Music with levels from the rows.
3. The source chip must state the render rule: **22 % under voice**, **100 %** with no voice row,
   **Removed · 0 %** when soloed or voice-only.
4. Press Mute original audio: chip becomes Muted here, and the render drops the bed (a toast says
   so). Unmute returns to 22 % under voice.
5. Preview mix: a toast reports what it mixed, e.g. `Preview mix · source 22% · 2 rows`.

## Round 5 — SFX Focus

1. Edit → SFX. Add a text block: it appears in the list with its start–end timecode and in the
   player as an approximate overlay (chip: Effect preview · approximate).
2. Click the row: an editor opens with Start/End, a timecode, and the look controls for that kind.
   Change Start, Save: the list timecode follows.
3. Add a Colour filter (Warm / Cool / B&W / Vivid): the frame tints in the player and the row
   appears as `filter`.
4. Timeline: the SFX lane shows every effect in collision-free rows with readable labels.
5. Buttons keep their names at 800×600 and 200 %; the dock never pushes the page.

## Decisions the founder should confirm

- **Clean placeholder**: unproved Clean shows the source labelled Source. Confirm this is the v1
  answer instead of a blurred placeholder.
- **Focus docks at 200 %**: Script, Audio and SFX hide the preview workspace to fit the editor.
  Confirm that trade.
- **Source bed**: 22 % under voice is a fixed rule, shown but not settable. Confirm fixed for v1.
- **Audio shape**: Audio Focus is a dock, not a full surface; the voice panel scrolls inside it.
- **SFX text position**: default bottom-centre (y = 0.84) with X/Y numbers, no drag on the frame.
- **Cut crop**: normalized numbers only; no drag crop box.

## What is proven, and how

| Check | Command | Result |
|---|---|---|
| Python core | `python3 -m pytest -q tests` | 353 pass |
| Clean layout | `scripts/check-clean-layout.cjs` | pass |
| Script Focus layout | `scripts/check-script-focus-layout.cjs` | exit 0 at 7 sizes |
| Audio Focus layout | `scripts/check-audio-focus-layout.cjs` | exit 0 at 8 sizes |
| SFX Focus layout | `scripts/check-sfx-focus-layout.cjs` | exit 0 at 8 sizes |
| Text renders at preview size | `tests/test_text_effect_size.py` | 2 pass (real ffmpeg) |
| Source mute reaches the render | `tests/test_audio_source_mute.py` | 2 pass (real ffmpeg) |
| Effect edits persist | `tests/test_effects_update.py` | 3 pass |

The layout guards need a running dev shell and `NODE_PATH="$(npm root -g)"`; each says so and exits
2 if puppeteer-core is missing.

## Known limits, in the open

- Focus docks cap their body and scroll inside at small heights; at 200 % the preview is hidden.
- At 800×600 the SFX add grid's last row sits below the dock-body fold, and the Audio cards below
  the fold need one internal scroll.
- The effect preview is approximate: badge text shows as bold text, not the rendered dark pill.
- Empty-state and populated states were reviewed on a scratch copy; the founder's real project was
  never written to.
- No VoiceOver pass and no full render were run inside these rounds.

## Evidence

- `docs/teams/po-r1-edit-clean/review.md`
- `docs/teams/po-r2-cut/review.md`
- `docs/teams/po-r3-script/review.md`
- `docs/teams/po-r4-audio/review.md`
- `docs/teams/po-r5-sfx/review.md`
