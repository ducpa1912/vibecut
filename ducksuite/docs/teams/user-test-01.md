# User Test 01 — Solo creator, first look

**Session:** user-test-01  
**Date:** 2026-11-07  
**Environment:** Local DuckSuite dev build at `http://127.0.0.1:8797`, 1440 × 1000 Chromium viewport, macOS. Project `check-smoke` (`prj_9542d62ce105`): 45.833 s, 1080 × 1080, 24 fps, existing full edit with 80 clean layers and 35 caption cues, Check done at start. The in-app browser was disconnected, so I drove the same build in headless Chromium and used the local API for timings, caption data, proof frames, and render output. I also reviewed the supplied screenshots in `/tmp/duck-shots/`.

## What I did, in order

1. Opened Welcome at 1440 × 1000. Read the screen cold, without reading any other screen first.
2. Clicked `check-smoke`. It opened directly into Edit, not Check. Clicked the Check tab and pressed Re-check.
3. Timed the re-check from the UI and from the API. Then opened Edit and inspected scene 01, the transcript, Clean / Captions / Voice, and Fine trim.
4. Opened Clean Focus. Selected scene 07 (“The rooms that actually changed…”, the `obviously` proof), then scene 01 (the large stylised title). Toggled Fill / Blur / Off and compared frames.
5. Opened Preview. Switched Before / Compare / After on scene 01 and scene 07.
6. Opened Render. Inspected the queue, started a 2 s render, watched it complete, and played the output. Also extracted frames from an existing 5 s export to compare with the proof.
7. Returned to Welcome and re-read the queue / recent state.

### Observed timings

| Event | Observed |
|---|---|
| Project opens from Welcome | under 1 s |
| Scene detection | 12 scenes ready by 3.2 s after Re-check |
| Automatic Editor handoff | 4.4 s after Re-check |
| Transcript / text detect / stories at handoff | 0% / 0% / 0% |
| Check complete | 36.3 s wall on the first run; 26.5 s engine time on the second run |
| Text detection | 183 frames, 80 text tracklets, 100% before Stories |
| Stories | 1 story; still pending at 78% overall |
| Fresh Clean proof render | 12.5 s for one scene-01 frame; 14 s for scene 07 after a layer change; 31 s and 46 s for back-to-back further frames |
| 2 s render | 1.18 s |
| 5 s render | 1.55 s |
| 2 s output file | 2.023 s, 730 KB, H.264 1080 × 1080 at 24 fps + AAC |
| 46 s full render | not run; the existing full-render queue row was cancelled after ~98 s |

## First-five-seconds read

This is a local video cleaner/editor: “One long video in. We find the scenes, clean the old text, and cut the clips.” The first action is unambiguous: **Choose Video**. The sample project is listed on the left and can be opened. Nothing is actively queued; two recent renders are marked done, and the latest render is playable. That is clear enough. But “Queue: 0” is ambiguous because the Render screen later shows nine historical jobs, and the sample names (“check-smoke”, “Render smoke”) read like QA artifacts, not a real creator’s project.

## What worked

- The visual system is coherent and calm: warm paper, dark video canvas, one amber primary action, readable type, no visual noise.
- Welcome says what the product does and gives one obvious action. It does not make me hunt for the import.
- Check is fast for a 46 s clip. Scenes, transcript, text tracks, and one story are real data, not placeholders.
- The Edit frame is the best screen: scene list, video, transcript, Clean / Captions / Voice tabs, and a compact queue rail in one view. Selecting a scene and reading its transcript is immediate.
- Clean **Fill** on scene 07 is believable at normal viewing size. It removes “obviously” / “rooms” without a grade jump; there is only a faint smudge on the mountain where the word was.
- The 2 s render completed quickly, produced a correct 1080 × 1080 H.264/AAC file, and played in the in-app modal without a broken state.
- The exported frame at 0.8 s is genuinely clean. The final-output clean is the strongest part of the product.

## What confused me

- Check showed a green completed icon and the Editor opened at 4.4 s, while the new Check was still at 78% with transcript, text detection, and stories at 0%. The Editor showed the previous transcript and previous clean layers, so the app looked finished while it was still working.
- Clean Focus says **12/12 clean**, **Text detect 100%**, and gives every scene a green “Proof” chip. Scene 01’s proof shows large black blobs and a smeared sky. I could not tell whether the clean failed or the proof was wrong.
- “Fine trim” looks like an editing control — timecode, filmstrip, playhead — but nothing moves. It is a picture, not a trimmer.
- The layer list stops at six. “+ 2 more layers in this scene” is plain text, not a control. Seven layers in scene 06 are unreachable.
- Choosing **Blur** made the whole preview go soft while it re-cleaned. The copy “Blur is a temporary placeholder” made me think the Blur method itself was a placeholder. The actual local blur is a hard, obvious rectangle around the word.
- One layer change cleared all 12 proofs and started a serial re-clean. After 15 s the UI still said “Cleaning 0/12” while the scene strip still said “12/12 clean”.
- Render says the output folder is `/Users/happynghia/vibecut-lanes/ducksuite/exports`; that directory does not exist. Actual renders live under `projects/prj_9542d62ce105/renders/`.
- The queue has nine historical jobs with truncated names (“check-smo…”), no archive/clear, and “Queue: 0” in the header. I could not tell what was current work and what was test history.
- The Voice list is an unsorted dump of macOS voices, including “Bad News”, “Bells”, “Boing”, “Bubbles”, “Cellos”, “Jester”, “Organ”, “Trinoids”, “Whisper”, and “Zarvox”. There is no sample before generating.

## Bugs

| Severity | Screen | Bug |
|---|---|---|
| **P0** | Preview / Clean Focus | **The proof and the export disagree.** A freshly generated scene-01 proof at 0.83 s and 1.47 s shows black blobs and smeared sky where the large title was. An exported 0.8 s frame from the same source and the same 80-layer clean set is clean. The product’s “12/12 clean” approval step shows damage the render does not have, so the proof cannot be trusted. |
| **P1** | Check | **Editor opens far too early.** Re-check auto-opened Edit at 4.4 s while transcript, text detection, and stories were all 0%. The Check step showed a green completed icon while the check was still running at 78%. The Editor showed the previous transcript and previous clean layers; the sample only looked complete because it already had an old edit. |
| **P1** | Edit / Captions | **Every caption line is duplicated.** 35 cues, only 22 unique; 13 duplicated cues; 12 cues shorter than 0.5 s; one cue is 5 ms (`10.120 → 10.125`). The SRT repeats lines, and burning the captions would flash each sentence twice. |
| **P1** | Edit / Fine trim | **Fine trim does not trim.** It has a filmstrip and a playhead but no in/out handles, no range inputs, and no click/drag handlers. It also shows all 12 scene thumbnails, not the selected scene. The advertised trim control is decorative. |
| **P1** | Edit / Clean | **Most clean layers are unreachable.** The inspector renders only the first six layers per scene; “+ N more layers” is not clickable. Scene 06 has 13 layers (7 hidden), and scene 01 has 8 layers (2 hidden). Users cannot inspect or change the layers that actually ship. |
| **P1** | Clean Focus / Preview | **One tweak invalidates every proof.** Changing one layer’s method clears all 12 cached proofs and serially re-renders them. The selected scene took ~14 s; after 15 s the UI still showed “Cleaning 0/12”. A 46 s video becomes a multi-minute wait after every Fill/Blur/Off decision. |
| **P2** | Preview | **Compare hides left-side artifacts.** Scene 01’s black blobs are in the top-left, which is the Before half of the split, so Compare looks clean. Only the full After view exposes the damage. A split wipe cannot prove the whole frame. |
| **P2** | Clean Focus / Preview | **Cleaning blur looks like a clean method.** The whole frame is blurred while a proof is regenerating, and the status copy says “Blur is a temporary placeholder.” The real Blur method is a large hard-edged blurred rectangle. The two meanings collide. |
| **P2** | Render | **The displayed output folder is wrong.** The UI says `/Users/happynghia/vibecut-lanes/ducksuite/exports`; that path does not exist. Renders are written to `projects/prj_9542d62ce105/renders/`. |
| **P2** | Render | **Queue is unmanaged history.** Nine jobs, truncated project names, no archive/clear, and “Queue: 0” in the header while nine rows exist. Done and cancelled test jobs are mixed with the current edit. |
| **P2** | Clean Focus / Proof | **Rapid edits can reuse a stale proof.** Toggling Blur/Off/Fill within one second returned the same cached proof image three times because the cache accepts a preview one second older than the edit. The displayed proof may not reflect the current method. |
| **P3** | Edit / Voice | Novelty macOS voices are mixed into the production voice list with no sorting, preview, or recommendation. |
| **P3** | Preview | “Current scene first” is a checked, disabled checkbox. It looks like a control but cannot be changed. |
| **P3** | Clean Focus | The top pipeline replaces “Edit” with “Clean focus”, so Clean Focus reads as a fifth step rather than a mode inside Edit. |
| **P3** | Multiple | Terminology drifts: “Proof rows” vs “Scenes”, “12/12 clean” vs “12/12 proofs”, “Clean” chips vs “Proof” chips, and “Queue: 0” vs nine jobs. |

## Trust scores

| Area | Score | Reason |
|---|---:|---|
| **Check handoff** | **4 / 10** | Check data is fast and useful, but the app declares Check done and opens Edit at 4.4 s with transcript, text detection, and stories at 0%. The handoff shows the old edit, not the new check. |
| **Edit** | **5 / 10** | The scene/transcript workspace is good. Fine trim is fake, most layers are hidden, and captions are duplicated. |
| **Clean proof** | **2 / 10** | Scene 07 Fill is credible. Scene 01’s proof shows black blobs that the export does not have, and a single midpoint frame cannot prove a moving text track. |
| **Preview** | **3 / 10** | Before/Compare/After is the right control set, but the proof disagrees with the render and Compare can hide the artifact. |
| **Render** | **8 / 10** | Short renders are fast and correct; the 2 s file played at 1080 × 1080 H.264/AAC. Queue clutter and the wrong output-folder label keep it from 9–10. |

## Would I pay $29?

**No —** the exported clean is genuinely useful, but I would not pay for an approval screen that shows damage the render does not have and captions that repeat every line.

## Would I recommend it?

**No —** wait for proof/render parity and fixed captions; the automatic clean is promising, but the review flow is not shippable.

## The one thing to fix before launch

**Make the proof an actual render frame.** Generate Clean Focus and Preview proofs with the same all-layer pipeline as the export, sample more than the scene midpoint, and never label 12/12 clean until the proof matches the file the user will download. A proof that shows black blobs on a frame the exporter renders clean is worse than no proof.

## Verdict

**FAIL**
