# Founder hand test · 2026-11-26 build

**App:** `build/DuckSuite-Xcode.app`, built from `ducksuite` after the G1 core merge.

**Before you start:**
- Work on a **copy** of an edit: duplicate it, or use a new full edit. Split, reorder and
  remove-silence change the edit, and the timeline has no general undo yet.
- Note anything that fails as "step number · what you saw". I file it.
- Use only your own footage.

## A · Speech inside the app (P-B)
1. Open **Settings**. If an older speech pack is installed, it says it needs an update.
2. Download the speech pack (1.62 GB). Settings shows it installed.
3. Turn off Wi-Fi.
4. Import your Vietnamese clip, choose Vietnamese, and run **Check**.
5. Compare the transcript with what's said. Note:
   - the clip's length;
   - how long Check took;
   - wrong words;
   - word timings that are off around pauses;
   - any made-up line over music or silence.
6. Dub a short section and listen for alignment. Turn Wi-Fi back on.

## B · Split, reorder, remove silence, waveform (P-D)
7. On the Edit screen, pick an edit with a caption, an active Clean range, and a voice or music
   track with a fade. Note the total duration.
8. Put the playhead inside the fade and press **Split**.
   - The selection lands on the right half.
   - Play across the seam: no repeated fade.
9. Drag the right half past another clip. Then focus a clip and press **Alt+Left** or
   **Alt+Right**. Play it: the picture, caption, Clean box and spoken word still go together.
10. **Waveform.** Speech, music and pauses should look different. Change a track's level, and the
    waveform height follows.
11. **Remove silence.**
    - Open it and look at the spans it found. Untick one, then press **Cancel**: the duration
      and clip count don't change.
    - Open it again, keep one span ticked, and accept. The duration drops by the amount it reports.
    - Listen for clipped words.
12. Render this copy. Check the first frame after each moved clip, and both sides of each silence
    cut.

## C · Remove a Clean layer, pick a layer by its box (P-E)
13. On **Clean**, select a detected layer and press **Remove layer**. Confirm.
    - The row and its box disappear.
    - Prove the scene: the text is back, and the other layers still apply.
14. Paint a brush mask, select it, and remove it the same way.
15. Run **Re-check & re-apply** on that scene. The removed box must not come back. A genuinely new
    text block may appear.
16. Start the source review so boxes show on the video. Click inside a box: its layer is selected.
    - Where a small box overlaps a big one, the small one wins.
    - Clicking outside every box does nothing new.

## D · The timeline shows the picture (T1)
17. On the Edit timeline, each clip shows pictures and a dark `S0n · duration` tag. Zoom with
    **+**, **−** and **Fit**: pictures stay in place, with no blank tiles when you scroll.
18. The left column reads V (eye), S, T, A1… (M, S, dB) and FX.
    - Press the eye: the preview shows "Picture hidden in preview only".
    - Press it again.
19. Press **B**, then click the middle of a clip. It splits, and the tool stays on blade.
    - **Escape** goes back to select.
    - **V** also goes back to select, and dragging a clip works again.
20. On **Check**, press the grid button. Type a word spoken in one scene: only matching scenes
    stay. Use the arrow keys, then Enter.
21. At a small window (about 1024×700), nothing in the timeline is cut off.

## E · Colour: render only in this build (G1 core)
The preview still uses the **old** CSS colour. The new preview, the look menu and the LUT picker
come in the next loop. Here, check only the **render**:

22. On a copy, set exposure +50 and temperature +50, and render.
23. Expect the render to differ a little from earlier renders of the same grade. Warm grades now
    really warm the picture: grey turns orange-ish. Before, temperature barely moved it.
24. The first render of a graded edit is slow once (cold).

## Already on the list from before
`docs/teams/founder-test-all.md` (loops 10–26) and the R2 voice fallback message: a saved Kokoro
voice now says it uses the macOS voice.
