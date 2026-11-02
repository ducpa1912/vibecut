# Panel report — Client editor, paid delivery

**Build:** `b07ebcc` · **Run:** 2026-10-28 17:01–17:32 · **Port:** 8811 · one server, one Chromium. Scratch: `…/T/panel6-seq-client-editor-r2`. Continuation after the server restart at 17:15:52. Job A (`e2bea262e70e`) was lost with that restart; A's re-import hit the disk reserve, so Edit/Audio was completed on the ready C job (`951b70f7394a`), then B (`57cfebdcd51d`) was imported fresh.

## Verdict

Studio can shape a story and render a cut. It cannot run paid client delivery end to end. Dub is selectable but cannot render: no target, no script, no queue action. Finished cuts have no library; they live only inside one job's Finish screen. Import/Check give long silences with percent-only progress, and disk preflight can refuse a 64 MB import while 4.3 GB is free. Versions, publish kits, and pinned/expiring review links are strong foundations — but there is no approval state, feedback, or delivery log. A paying client would see a demo, not a service.

## Timeline

| Time | Event |
|---|---|
| 17:01–17:02 | A import 48.4 s; Check 54.8 s for 0:53 source |
| 17:04 | Stories 2.7 s, 2 stories |
| 17:06 | Edit opens in ~3 s (run.log's 65 s is a harness regex miss on uppercase "STEP 4", not app latency) |
| 17:08 | Finish; 4:5 + 9:16 queued; at 16% the queue showed **"3 min 48 s left"** |
| 17:11:46 | First 21 s story rendered — ~3.8 min per short |
| 17:12–17:16 | B import timed out at 240 s; server restarted, losing A and B |
| 17:16–17:24:25 | C (HEVC 1080×1920) import **505.4 s**; scan 252.9 s |
| 17:22–17:30 | A 404; A re-import 412 disk; C Edit/Audio; B import **24.9 s** |
| 17:32 | Server stopped |

## Ranked issues

### P0 — Dub is a dead end

`audio4-dub-C.png`: selecting **Dub** changes the help text to "Replace the spoken lines with a translated voice" but adds no target language, no script, no translated-line preview, and no queue action. The panel still says **"Saved."** Saved edit: `audio.mode = "dub"`, `voice.engine = "say"`, `voice.voice = "Karen"`, and **no `translate` object**.

Root cause: `static/studio/edit/layers/audio.js:259-274` (`buildPlan`) writes mode/voice/music and never writes `translate`; `audio.js:44` promises translation. The mixer correctly refuses it at `audio.py:2811-2813`: `Dub needs a target language.` The user only discovers this after queueing a render.

Fix: target language, source confirmation, editable translated script, translated-caption toggle, and a preflight that disables Queue until a target exists. Show the server reason in the row, not "Render failed."

### P0 — No finished-video library

`library4.txt` — "Your videos" contains: `source.mp4 1:52 · Oct 28 Ready`. It is a source-job list (`shell.js:538`, `shell.js:553-575`), not a deliverable list. Renders live only under Finish → Versions for one story and one shape. Three sources named `source.mp4` are indistinguishable.

Fix: one artifact library: thumbnail, story, shape, quality, version, date, review state, download. Sources get a separate tab. This is the biggest client-delivery gap.

### P1 — Import and Check are slow, silent, and have no ETA

C took **505.4 s**; B took **24.9 s**. C's scan was 252.9 s versus B's 2.8 s. C is HEVC 1080×1920, B H.264 720×1280; the per-frame gap needs profiling. Both showed only stage text and percent. C's `Tracking crop · 50 / 50` at 68% reads like completion while the job still works.

Check: 54.8 s for a 0:53 source, with 1% → 5% → 35% → done. The UI held 35% for ~36 s with no heartbeat, no ETA, and no cancel (`check.js:551-560`). Copy says "takes a few minutes on a long video" (`check.js:578`), then finishes a one-minute video in 55 s.

Fix: time-weighted progress, elapsed + "about N s left" after 10%, stage heartbeat, cancel. Reuse import OCR instead of resampling at 0.5 fps (`detect.py:1668`), and show a pre-run estimate.

### P1 — Disk preflight blocks work and reports "0 bytes available"

With 4.3 GB free, a 64 MB A import returned 412: **"only 0 bytes are available above the 5,368,709,120-byte reserve."** Deleting a 218 MB scratch image unblocked the next import. The reserve is hard-capped at 5 GB (`disk.py:116-121`); the message quotes available-above-reserve as if the disk were empty.

Fix: show free, reserve, and shortfall in GB; offer cleanup or an external target; do not require the full reserve for an in-place path import that copies nothing.

### P1 — No Back/Next in Edit

The Edit header has Story, shape, All stories, Undo (`static/studio/edit/index.js:172`); the only route to Finish is the left rail. Autosave says "Saved", but there is no "Save and next" or "Back to Stories." On a paid job the editor cannot tell whether leaving is safe.

Fix: footer **Back to Stories** / **Next: Finish**, with "Saved" pinned beside them.

### P2 — Review links are good; approvals and feedback are absent

Review links are pinned to one artifact and support expiry and labels (`finish.js:1653-1700`; `shares.py:1`). That is the right trust model. But there is no **Approved / Changes requested** state, no comments, no per-client link list, and no record that a client saw version 3. A studio cannot close a job on "I sent a link."

Fix: approval state + comment thread, plus a delivery log per artifact (sent, viewed, approved, expires). Rights attestation should also appear on the artifact, not only at import.

## Feature asks

| Ask | Call |
|---|---|
| Finished-video library with versions and review state | **Greenlight now** |
| Dub: target language + editable script + preflight | **Greenlight now** |
| Client approval/comments on review links | **Greenlight now** |
| Time estimates + cancel for Import/Check | **Greenlight now** |
| Per-client workspaces, roles, delivery ledger | **Defer** — after the artifact library |
| Auto-publish to social platforms | **Reject** — approval and rights must gate it |
| Watermark removal | **Reject** — already refused; keep it that way |

## Explicit answers

**(a) Check speed/progress/ETA honesty.** 54.8 s for 0:53. Four visible states, no ETA, no cancel, 36 s frozen at 35%. Percent is accurate but not honest about waiting. The copy overpromises speed on long video and underexplains the 0.5 fps resample.

**(b) Confusing interface.** Audio is one long scroll mixing sound mode, music brief, generation, library, upload, voice, mix, and status. Dub and Voice-over differ by one sentence with no visible workflow difference. Music generation sits above voice, so "generate music" reads before "choose the voice that defines Dub."

**(c) No back/next in Edit.** Rail only. No explicit save-and-continue.

**(d) No finished-video library.** Confirmed. "Your videos" lists sources; cuts exist only under Finish → Versions. Clients cannot be handed a link to "their video."

**(e) Translation / voice generation.** Translation exists only in **Classic** Edit → Audio → Rewrite → Language. Studio Audio has no language or script control. Studio Voice (engine, voice, rate, Preview) makes a sample only; the real voice is generated during Finish render. Gaps: no target, no script review, no translated captions, no queue-time validation.

**Evidence:** `shots/audio4-dub-C.png`, `audio4-voiceover-C.png`, `library4-open.png`, `finish4-C.png`, `check-A.png`, `finish-queued-A.png`; texts `audio4-dub.txt`, `library4.txt`, `finish4-C.txt`; timings `run.log`, `run4.log`, `server2.log`. Full-page shots show Classic below the fixed Studio overlay; at 1440×960 it is covered, not a user bug.
