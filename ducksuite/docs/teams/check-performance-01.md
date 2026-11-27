# Check performance sprint 01

Date: 2026-11-08
Scope: Check handoff, stage truth, and wall time for dissect, read, transcript, text detect, stories.

## Findings

| # | Finding | Impact |
|---|---|---|
| 1 | The Editor waited for the whole Check, including stories, before a full edit could be created | Editor looked stuck at 90 % with transcript/text already done |
| 2 | Stage rows used the global `done` flag, so transcript and text at 100 % had no green check | User could not tell what was actually finished |
| 3 | Stories ran before the report was published | Every story second delayed the Editor |
| 4 | Smart crop and crop tracking ran during Check | Not used by Edit or Render in v1; wasted Vision passes |
| 5 | Edge OCR upscaled 1080p half-frames to 4K | Slowest part of text detection on HD video |
| 6 | Editor did not load clean layers when it created a full edit | Clean tab empty until Preview triggered from-check |

## Fixes

- Check now publishes an **editor-ready** report after transcript and text, before stories.
- `editor_ready` is in Check status; a partial `check.json` is saved.
- `create_full_edit`, story edits and `clean/from-check` accept the editor-ready report.
- Editor creates the full edit and applies clean layers at editor-ready.
- Editor reloads the transcript at editor-ready.
- Stage rows turn green independently:
  - Scenes: scenes done
  - Transcript: transcript 100 % or done
  - Text: text 100 % or done
  - Stories: done only
- Check copy: “Editor ready. Stories finish in the background.”
- Smart crop and crop tracking are off during DuckSuite Check.
- Edge OCR uses native 1080p crops and only frames with very large text or no text.
- Check status keeps a capped history of stage/time/progress for diagnostics.

## Measured

12 s clip, 1920 × 1080, cold transcript and text pass:

```text
check engine span       14.5 s
text pass               13.5 s
transcript               9.9 s (first run, overlapped work not counted separately)
story publish            3 ms after text on this fixture
```

The 46 s fixture text pass remains the long pole. The Editor no longer waits for it to finish stories; it opens as soon as text and transcript are published.

## Remaining

- Story candidates can be empty on a short clip; the Stories tab then stays empty.
- The text pass is still the largest single cost. Reducing the 4 fps sample needs a fixed-frame quality test.
- First-run Whisper model load can add seconds before the transcript starts.
- Engine span is measured from Check history, not shell wall time; shell timing is polluted by API polling.

## Acceptance

- Editor can open before stories finish.
- Transcript and text show green when their own work is done.
- Clean layers are present on first Editor open.
- Check report still finalizes with stories.
- 41 tests pass.
- Xcode build and unsigned archive pass.
