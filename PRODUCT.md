# DuckClean — product truth

DuckClean removes text, logos and burnt-in images that are baked into a video,
then returns the **full-length** clip with the original audio, duration, display
size and frame rate.

Source of truth for scope: `HANDOFF.md`, `docs/duckclean/plan.md`,
`docs/duckclean/contract.md`. Where this file and `HANDOFF.md` disagree,
`HANDOFF.md` wins and this file is corrected.

## Who it is for

People who must repost a video they did not shoot or cannot re-edit: social
editors, small agencies, creators reposting clips, someone cleaning a screen
recording before publishing. They have the file on their phone or laptop, they
are not video engineers, and they are often in a hurry.

Inferred, not yet confirmed with users: most sessions start on a phone with a
clip already in the camera roll, and the decision to pay happens only after they
have seen one real result.

## The mechanism worth showing

Every beat of the video is checked for text; only beats with a selected target
are processed. Everything else is passed through untouched. The output keeps the
source's duration, display size, frame rate and audio, so it is the same video
with the marks gone — not a shortened edit.

That mechanism is the product's evidence: frame ranges, coverage, confidence,
revision, compute time. None of it may be invented on screen.

## What M1 is

Accounts and library. Sign in, upload a real file straight to storage, see it in
a library, and play a proxy of what was uploaded. M1 proves the upload and
playback path end to end. Detection and cleaning begin at M2.

## Non-negotiables

- Cloud only. No local runner, desktop install or LAN renderer.
- Video bytes never pass through the web host or the API Worker. The browser
  uploads directly to object storage with a short-lived presigned PUT.
- A phone must be able to complete upload → review → render → download.
- No fake progress, fake frames, fake voices, fake success. A status is either
  measured or absent.
- Real media only for acceptance. No stock clip, no generated demo file.
- No hidden spend: estimate before work, actual usage after, balance visible.
- `range_mode` is `ranges` or `whole_source`; an empty range list never means
  "the whole video".
- Every query is scoped to the signed-in user. Cross-user access is a 404.

## Standing brand commitments

None yet. The visual world is recorded in
`docs/duckclean/m1-surface-brief.md` and becomes durable in `DESIGN.md` when M1
is finished and reviewed.
