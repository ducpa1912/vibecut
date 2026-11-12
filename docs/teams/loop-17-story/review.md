# Loop 17 review — Story v1

**Verdict: pass for v1.** Request REQ-20261112-07.

## What ships

- `duckcore/story.py`: scene context from the transcript (one line per scene, verbatim cue),
  batching at 20 scenes when the summary would not fit the prompt, on-device `story_apple` call,
  validation, and a deterministic fallback.
- `POST /edits/story/write`: builds the story, creates a story edit from the chosen scene ids in the
  chosen order, stores `edit.story` with the thesis, beats and model.
- Edit: **Write a story** in the Stories tab, a thesis bar with the model chip, beat count, runtime
  and each beat's source line.

## Probes

| Probe | Result |
|---|---|
| Fallback on this Mac (`appleIntelligenceNotEnabled`) | HTTP **200** in **0.08 s**; model **none**; **4** beats; runtime **18.5 s**; scene ids **17, 18, 20, 23** |
| Thesis | strongest opening cue, verbatim |
| Beat cues | every cue is in the transcript; no invented line |
| UI after writing | chip **No model · basic story**, 4 beats · 18 s, four beat lines in the bar |
| Model order (fake) | `[2, 0, 5]` kept exactly; thesis kept |
| Bad model answer | falls back with a reason |
| 200-scene source (fake) | every call ≤ **20** scenes; reduce keeps 3 beats, 15 s |

Apple Intelligence is not enabled on this Mac, so the real model path is **unproven**; the helper
reports `appleIntelligenceNotEnabled`. The order, validation and batching paths are covered with a
fake model.

## Limit, stated plainly

v1 **focuses** the story; it does not rewrite the spoken words. The thesis is the model's line, or in
the fallback the strongest source line. Captions are not regenerated around the thesis.

## What got worse

- A beat is a whole scene, not a sentence or a shot; a 5 s beat can carry more than the chosen line.
- The fixture transcript repeats one line for every segment, so the fallback shows the same cue four
  times. That is the data, not the picker; a real transcript reads differently.
- The thesis bar takes one row above the Edit workspace.

## Not tested

- Real Apple Intelligence output, including prompt quality and the 4,096-token boundary on device.
- Non-English transcripts.
- Media beats inside a written story.
- 1280×800 capture of the thesis bar; the bar is one flex row and wraps.
