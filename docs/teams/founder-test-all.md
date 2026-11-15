# Founder test — everything waiting, in one sitting

Written 2026-11-15 by the sub-leader (REQ-20261115-01 · E). It replaces the separate founder
scripts of loop 10, loops 11–19, fix-02 and fix-04, and adds the hand checks of loops 21–22. Each
step names the loop it proves in `[brackets]`. The old scripts stay in their folders as history.

**Before you start**

- Build and open the app yourself: `./scripts/build-xcode-dev.sh`, then
  `open build/DuckSuite-Xcode.app`. Agents do not click in this window.
- Project: `人吃啥咪吃啥` (`prj_e95348a97316`), edit `ed_38a4c36a3aae`. **Do not press Re-check**:
  it can move clean-layer ranges.
- **The first render after loop 21 is cold** (fill clips were re-keyed): about 10–14 min on this
  Mac for the whole edit. Part 8 needs no new render; part 9 asks for one, and you may skip it.
- Part 5 changes the Cut of this edit. Part 5's last step puts it back; do it before Render.
- Time: about 45 min without part 9.
- Removed as stale: the “Play detection review” player (gone since loop 11), the old example
  estimate figure, and loop 19's need for a 360p project (the half crop in part 5 shows the same
  Enhance controls on this project).

## 1. Window and Welcome  [loop 10]

1. Open the app; size the window to 1440×900, later to 1280×800.
2. **Must see:** the drop zone and the latest-render card fill the middle column; the queue and
   engine panels run to the bottom; no horizontal scroll bar.

## 2. Check  [loop 10]

1. Open `人吃啥咪吃啥` → **Check** (do not re-check).
2. **Must see:** the stages list on the left, the player and the **Scenes** strip beside it, the
   page reaching the bottom of the window, no horizontal scroll.
3. On the Check player: play, time, scrub, mute, volume, full screen each work (Esc leaves full
   screen).  [loop 10, loop 12]

## 3. Edit — player, transcript, timeline  [loops 10, 12, 13]

1. **Edit**. **Must see:** the video hugs the picture (no black bars at the sides); the **Filter**
   field has equal space left and right; scene rows are hairlines.  [10]
2. One control bar only: play, time, scrub, mute, volume, full screen — each works.  [10, 12]
3. **Transcript** panel: beside the picture (portrait), dark text, one or two lines, not over the
   picture or the controls. Speaker chip, time, “⋯”. Click a line → the player seeks. “⋯” →
   **Seek to this line**, **Copy text** (paste it somewhere: is it the line?). **Hide** / **Show**
   fold and return the lines.  [10]
4. Drag the transcript **Opacity** to 50 %: the panel fades, words still readable. Reload the window:
   still 50 %. The player controls still all answer with the transcript showing.  [12]
5. Timeline head: press **+** a few times → beats and scenes widen, the ruler shows more labels, the
   page does not scroll sideways. Click a scene far from the playhead → it is selected, the player
   jumps, the playhead stays in view. **−** and **Fit** → whole video at 1×.  [13]
6. Empty **Script**, **Voice & Music**, **SFX** lanes are short dashed rows with a `+`. Add one
   caption (Script focus): its lane opens to a normal row.  [10]
7. Narrow the window below ~1000 px and widen it: side panels stack, nothing overlaps.  [10]

## 4. Clean  [loops 10, 11]

1. Select a scene with text. Inspector shows `N of M layers`; a soft fade at the bottom while more
   rows are below, gone at the end. Click a **moves** flag, then **Show all**: rows stay 32 px,
   nothing overlaps, the count follows the list.  [10]
2. Open **Clean** (Clean Focus): `Scenes · 35 shown / 35 total`, the All/Yours filter, page fills
   the window.  [10]
3. Change one layer's **X / Y / W / H**, press **Apply box**, then **Prove this scene**: the box and
   the blur move together.  [11]
4. Press **Re-check & re-apply**: the box you set is kept.  [11]

## 5. Cut — aspect, crop, look, grade, enhance  [loops 14, 15, 18, 19, fix-02, fix-04]

1. **Edit → Cut**. Press **9:16**: a tall 1080×1920 frame, Fill selected. **1:1**, **4:5**: the
   output label and the picture follow.  [14]
2. Set Crop H to 0.6, **Apply crop**: only that band stays. **Reset crop**, **Fit**: the whole source
   is back.  [14]
3. **Cut → Look**: Warm / Cool / B&W / Vivid are here, not in SFX. Exposure, Contrast, Saturation,
   Temperature sliders. Exposure +80 brightens while dragging; reload → still +80. Saturation −100
   → grey. Temperature +100 → warm. **Reset grade** → all 0, picture neutral.  [14, 18]
4. With no crop at Source size, **Enhance** shows no controls and says no upscale is added.  [19]
   Crop to half (W 0.5, H 0.5), **Apply crop**. **Enhance** shows `540×960 → 1080×1920` with a
   **Lanczos upscale** switch and **Sharpen**; the output label reads 1080 × 1920. Switch on, Sharpen
   60: “No new detail: upscaling cannot recover what the source never captured.” Reload: both stay.
   [19, fix-02]
5. Choose **16:9**, **Fit**, Contrast −50, then **Prove this scene** in Preview: the bars above and
   below stay black.  [fix-02]
6. While a proof is showing, change any Cut value: the proof clears (it is no longer for this Cut).
   [fix-04]
7. **Put it back:** Reset crop, Reset grade, Enhance off, **Source**. The picture is the original
   aspect.  [14]

## 6. Preview — proofs, safe zones, sequence  [loops 10, 11, 15, 16]

1. **Preview** at 1440×900 and 1280×800: the player as tall as the window allows, a thin black edge
   (≈15 px), the Scenes strip in a narrow column to the bottom, no empty band under the player. [10]
2. Nothing starts on its own; the card says **No proof yet**. Press **Prove this scene · blur**: in
   about a second the text is blurred, not rebuilt. Strip reads **1 · Detect / 2 · Compare /
   3 · Review** (boxes, split slider, blurred frame).  [11]
3. Change **Fill / Blur / Off** on a layer in Edit: no proof starts by itself. **Re-clean this
   scene** opens Clean Focus on that scene.  [11]
4. **Safe zones** → **TikTok**: the 9:16 frame, top/bottom bands, side margins, the button block on
   the right, outside dimmed. **Reels**, **Shorts**: bands change, the source line names the
   document. Set Edit → Cut **1:1**, back to Preview: the 1:1 frame and IG guide without reload.
   **YouTube 16:9** with Cut 1:1: no guide; the panel says the shapes differ. **Off**: clean picture.
   Set the Cut back to **Source**.  [15]
5. **Play all scenes**: keeps playing across cuts, bar says `All scenes · n of 35`. Drag the
   scrubber to the middle: lands on a later scene, keeps playing. **×**: proof steps return.  [16]

## 7. Story  [loops 16, 17]

1. **Edit → Stories → Write a story**: a thesis bar (**No model · basic story** unless Apple
   Intelligence is on), beat count, runtime, one source line per beat.
2. Read the beats: **every line is something actually said in the video.** Note any that is not.
3. **Preview → Play story order**: beats play in story order, not source order.  [16, 17]
4. **Write again**: a new story; the old one stays in the edit menu. Switch back to the main edit.

## 8. Render — no new render needed  [loops 10, 21, 22, fix-04]

1. **Render**. Left column: settings, **Start render**, the estimate, the ready facts; nothing in it
   scrolls at 1280×800. Right column: the queue (56 px rows) and **Finished renders** as cards with
   Play and Show. The left column stays put while the right scrolls.  [10]
2. **Frame rate** line reads `30 fps · set from the source (… fps)` or `24 fps …` for this project.
   If you have any clip at 25, 50 or 60 fps, open it once: the line must say what changes, e.g.
   `Source 60 fps → 30 fps: about 30 frames per second are dropped`.  [22]
3. The Cut size shows on Render (1080 × 1920 here).  [fix-04]
4. Change one layer's range in Edit, back to Render: **Measuring the fill… N %** and **Old figure:
   the edit changed since it was measured.** Then one line with a time **range**, then the check
   cost. Write down the exact words.  [10]
5. **Leftover** fact: `Checked N frames · 0 found · 2 lines not checked` (never counted as clean).
   Put the layer's range back.  [10, fix-04]
6. On an **older** finished card press **Play**: it plays that render, not the newest. The player's
   timer moves, play/pause works, scrub moves.  [fix-04]
7. While a render is queued, put focus on a card's button (Tab) and wait for the queue to refresh:
   focus stays on the same card's button.  [fix-04]

## 9. Optional — one real render  [loops 21, 22]

Only if you have 15 min. Set Cut crop to the top half (H 0.5), Start render.
- **Must see:** lines below the crop listed as “not checked · the Cut leaves this line out of the
  frame”; the render finishes; a second Start of the same edit is much faster than the first (fill
  and ink reused). Reset the crop afterwards.

## 10. Settings — your fill model  [loop 10]

1. **Settings → Models → Your fill model**: same row height as the others, **Choose**, state is one
   line: **None**, **In use · model.onnx**, or **Not usable · reason**.
2. Choose a folder with `model.onnx` or `model.pt` (if you have one): **In use · …** and **Clear**.
   A folder without one: a red toast says what is missing, state unchanged. **Clear** → **None**.

## 11. Optional — Import, last  [loop 10]

It changes the project you import into. **Choose Video** → a short clip → “Use full video” or
“Add scenes”: the import finishes and the clip appears in the timeline.

## What to send back

- For each part: pass, or the step number and what you saw instead.
- The exact words of: the estimate line, the frame-rate line, the “not checked” line, any toast.
- Window sizes used; any page that ends early, runs past the window, or scrolls sideways.
- Any story beat that is not in the video.
# Loop 23 hand checks

1. Open a scratch project with a transcript. Open a line's menu and choose Copy text.
2. Paste into TextEdit. Confirm the pasted text exactly matches that line.
3. Open the voice recording control. Grant microphone permission when macOS asks.
4. Record five seconds of speech, stop, then play it back. Confirm sound and duration.
5. Deny microphone permission in System Settings, retry recording, and confirm an actionable error.
