# P-D · Timeline editing and waveform

## Audit before implementation

**Split.** The route already walks output durations, but recreates both halves with the clip constructor, losing additional clip properties. The main timeline renders scenes independently of clips and the split action never selects the new half. Only the brush has undo.

**Reorder.** Story movement already pops and inserts by index. The main timeline uses source seconds directly, and the story helper neither remaps timed attachments nor handles a general edit.

**Remove silence.** Check supplies scene-level information. The timeline has no preview or cut command. Track waveforms currently decode whole files with Web Audio, sample sparse peaks and paint DOM bars. The core needs a shared source-level envelope for highlighting, cuts and drawing.

## Implementation and evidence

- Split retains each clip's properties and advances the file offset of an inserted video. The selected right half begins at the output playhead. Alt+Left/Right and drag both move clip occurrences, including repeats of the same source scene. The edit stores the resulting order.
- Captions, voice, dub, music and sound effects follow the retained output intervals. A row crossing a cut becomes independently selectable fragments with distinct IDs and original sample offsets. Clean ranges stay in absolute source time. The fill-cache test checks that a pure reorder retains both keys and that splitting one clip changes only its keys.
- Both the FFmpeg mixer and browser audition use the original audio fade position. For the synthetic 48 kHz signal, FFmpeg produced exactly 2,400 samples for each of two 50 ms fragments taken inside attack and release. Each sample matched the corresponding part of the unsplit fade.
- Remove silence reads the same cached mono RMS as the waveform. The threshold applies to a conservative sum of audible track envelopes with gain, fades, mute, solo and voice replacement. This can leave time in the edit where overlapping sources cancel in the actual mix. Word times protect speech, and a transcript containing only segments protects the whole segment. The protected interval follows the clip when its output time changes.
- Silence preview, cancel, subset acceptance and stale preview rejection are covered. An edit that changes while a cut is being prepared rejects the older write. Each new asset gets one on-disk envelope keyed by path, size and modification time. Split rows sharing an asset reuse the same browser level request within a saved edit.

## Measurements

The input was 160 s of synthetic mono 48 kHz PCM alternating one second of 440 Hz tone with one second of digital silence. At −40 dBFS, 0.60 s minimum and 0.12 s retained at each edge, the preview found 80 spans totaling 60.80 s. The final cold preview took 211 ms. Median of eleven cached previews was 0.82 ms. An earlier cold run took 452 ms.

Headless Chrome, same 640 px lane and audio file, measured the old decode-and-bars path and the new levels-and-canvas path in separate documents. Retained memory is the increase in JS heap plus backing storage after garbage collection, not whole-process RSS. Warm draw is the median of eleven batches of fifty draws including a synchronous layout read.

| Waveform path | First fetch through first draw | Warm draw | Retained JS and backing storage |
|---|---:|---:|---:|
| Decode and 64 bars | 95 ms | 0.104 ms | 30,829,437 bytes |
| Cold core levels and canvas | 173 ms | 0.044 ms | 191,858 bytes |

The first draw cost 78 ms more while creating the levels cache. Warm draw time fell by 58% and retained browser memory fell by 99.4%. Drawing and detection use 16,000 levels for this signal. Playback still decodes audio on demand.

The scratch browser selected the right half after split, reordered it by keyboard, cancelled a preview, and removed just one of 80 proposed spans. Final duration was 159.24 s. A separate drag moved the last clip to the first position, and the canvas contained the selected-span highlight.

## Founder hand test

1. In Edit, pick a project with a caption, an active Clean range and a voice or music row with a fade. Note the duration and choose a point inside the fade.
2. Split. Check the selection begins on the right half, then play across the seam and listen for a repeated fade. Split again at the seam and confirm the app asks for a position inside a clip. The timeline has no general undo.
3. Drag the right half past another clip, then use Alt+Left or Alt+Right on the focused clip. Play the sequence. Check the picture, caption, Clean location and audible word still belong together.
4. Compare speech, music and pauses on the waveform. Change a row's gain and check its height. Open Remove silence, find spans, change a checkbox and check its highlight. Cancel and verify that duration and clip count hold.
5. Preview again. Keep one span checked and accept. Compare the reported removal with the change in duration. Repeat on another working copy with all spans selected. Listen for clipped words.
6. Render the edited copy. Check the first frame after each moved clip and both sides of a silence cut, including a Clean range and voice fade. Visual alignment on real video and native WKWebView interaction remain founder checks.

## Verification and PO handoff

The suite passed 448 tests. The existing bundled-helper test skipped because this worktree has no DuckSuite-Xcode.app. Both edited JavaScript modules passed Node syntax checks. The 1024×700 Edit measurement on six clip fragments had zero clipped buttons or labels, zero control overlaps and no horizontal page scroll. The only reported overlap was the existing “Not cleaned yet” overlay on the After image.

One existing renderer defect still affects visual acceptance. With a Blur layer active from source 1–2 s, rendering a subsequent clip beginning at source 8 s generates an enable interval of 0–0 s. That can apply blur to the first frame of the wrong picture. The regression was reproduced by inspecting the actual FFmpeg filter. Renderer ownership for this loop currently covers the audio mixer. PO sign-off on Blur alignment is pending.
