# P-D · Split, reorder, remove silence, and the loudness waveform (REQ-20261125-03, REQ-20261126-01 W1)

Owner: **Codex**. Folder `drop_eval/ducksuite-codex`, branch `cx/pd-split-reorder-silence`.
**D8 decided 2026-11-26: split, reorder and remove-silence are all in v1** (founder: "Include
remove-silence"). Plan: `docs/plans/2026-11-25-app-store-readiness.md` (D8, section F).
**W1 folded in 2026-11-26** (founder: "Yes, fold W1 in"). Plan: `docs/plans/2026-11-26-editroom-adoption.md` (W1).

**Queued.** Start after the PO merges your P-B (`cx/pb-whisper-in-app`). Base on `ducksuite` at
that merge or later. The PO will switch your folder to the new branch.

## Why
`TODO.md` says "Trim works, the rest does not." Pieces already exist, but none of the three is a
working creator tool today:
- `edits.split_at`, the `clips/split` route, and a "Split at playhead" button in the timeline
  (`app.js`, about line 2559);
- `edits.move_story_clip`, for story clips only.

Silence data exists only per scene, in Check (`pipeline.py` about lines 1290–1350 and
`stt.has_speech_energy`).

## You own, for this loop
- `static/duck/app.js` and `static/duck/app.css`: the Edit timeline only. You are the only owner
  of `app.js` until the PO merges this loop. After that, OpenCode's P-E starts on the Clean layer
  code, so stay out of Clean (`layerListMarkup`, `inspectorClean`, `cleanAction`, the detection
  overlay).
- `duckcore/edits.py`, and `duckcore/main.py` (the clip and edit routes only)
- `duckcore/silence.py` (new) or an equivalent small module
- `duckcore/levels.py` (new), and `static/duck/audio-tools.js` (the waveform drawing)
- `tests/test_timeline_split_reorder.py`, `tests/test_remove_silence.py`, `tests/test_levels.py` (new)
- `docs/teams/pd-split-reorder-silence/review.md`

## Done looks like
First, audit what exists for each of the three tools. Write one paragraph per tool in the review
before you change code.

1. **Split.** Split at the playhead makes two clips with no gap and no overlap.
   - Both halves keep their look, crop, volume and fades.
   - The playhead and the selection land on the right half.
   - Undo works if the timeline has undo. If there is none, say so in the review.
2. **Reorder.** Clips in the main edit move by drag and by keyboard; reuse the pattern from
   `move_story_clip`. Output time is recomputed.
3. **Follow the clips.** On split, reorder and silence cuts, these follow their source time:
   - caption cues;
   - Clean layer ranges;
   - the voice or dub track;
   - audio tracks.

   Nothing is filled or captioned over the wrong picture. Test this on built-in edit data.
4. **Remove silence.** Runs on the edit's own audio, local only.
   - It finds quiet spans longer than a minimum length, with a loudness threshold, and pads each
     cut so words aren't clipped.
   - It shows the spans it found, with their total length, **before** cutting. The creator can
     accept all, accept some, or cancel.
   - It reports, in words, the threshold and minimum it used, and how much time was removed.
   - It never cuts inside a transcript word.
   - Measure the time it takes on a 160 s audio file that you generate yourself as **silent and
     tone test audio**, which is synthetic signal, not media. Put the number in the review.
5. **Loudness levels and the waveform (W1).**
   - **Levels.** The core computes RMS levels once per source: 100 per second, mono, from FFmpeg
     into NumPy. It caches them in the project and serves them as JSON on one route. It does the
     same for every audio track the creator adds.
   - **Remove-silence uses them.** Remove-silence (item 4) reads these levels, not its own pass.
     The quiet spans the creator sees are then exactly the spans it cuts.
   - **Drawing.** The timeline draws each audio lane on a `<canvas>`, in Editroom's chosen style:
     - RMS, averaged over five samples;
     - lifted ×2, with 8% headroom, and the clip or track gain applied;
     - a filled shape, with quiet stretches as a thin line.

     Read Editroom's method in the plan. Don't copy its Swift.
   - **No browser decode.** The browser no longer decodes whole audio files to draw the waveform:
     `decodeAudioData` stays only where playback needs it. Measure the page's memory and the
     draw time on synthetic test audio before and after, and put both in the review.
   - **Highlight.** Quiet spans found by remove-silence are highlighted on the same canvas.
6. **Render.** Render still matches the timeline after each tool. Write this down: the render
   cache key changes for edited clips only. Don't change `textfill` output.
7. **Tests.** Cover split edges (at a clip edge, inside a fade), reorder mapping, silence spans
   (threshold, minimum, padding, word guard), and the follow rules from item 3, and the levels (length, rate, cache reuse, gain, empty audio). Use built-in data
   and synthetic arrays.
   - Run the full suite and `node --check static/duck/app.js`.
   - Run `scripts/measure-layout.mjs` at 1024×700 on the Edit screen if the timeline layout changes.
8. **Hand test.** Numbered founder hand-test steps for all three tools and the waveform on the project under work.
   **Do not open the app.** Don't open founder projects or make any media besides the synthetic
   audio in item 4.

## Notes
- Commit on `cx/pd-split-reorder-silence` with `git -c commit.gpgsign=false commit`. Don't push.
  Don't edit `MEMORY.md`, `TODO.md`, `PLAN.md` or `PRODUCT.md`.
- If you check anything by hand, use port 8831 and `build/scratch-root` only.
