# Loop 17 brief — Story v1: one thesis, beats from anywhere

Request: **REQ-20261112-07**.

> "The story should be to understand the whole context of the video then select several beat and
> scene that fit together and no need to be in the same consequence or timely order, and to rewrite
> or focus on 1 specific narrative or bold statement."

## Constraints in force

- Local only. The on-device model is text-only and 4,096 tokens on macOS 26; it cannot watch the
  video. Context is the transcript, one line per scene, batched when the source is long.
- No model means a deterministic fallback, labelled **No model · basic story**.
- Every beat keeps a verbatim cue from the transcript, so it can be traced back.

## What must exist

1. **Write a story** in the Stories tab, with the full edit open.
2. The server builds a story: one thesis, 3–6 beats, 15–90 s, ordered by narrative, not source time.
3. A story edit is created from those scene ids; non-contiguous beats are allowed.
4. The thesis, model chip and each beat's source line are visible in Edit.
5. A bad or missing model answer falls back, never fails silently.

## Acceptance

| Probe | Pass |
|---|---|
| No model (this Mac) | story created, chip says No model, thesis and 4 beats shown |
| Model order [2,0,5] (fake) | beats stay in that order |
| Bad model ids | fallback |
| Cue traceability | every cue appears in the transcript |
| Long source | batched, no call carries more than 20 scenes |
