# Loop 23 — phased implementation and evidence

Starting HEAD: `49e4a63`. No push. Each phase records incomplete acceptance explicitly.

## P1 — review leftovers

- #6 FAIL: long-scene story and synchronous batch latency remain unresolved; 0 new passing tests.
- #7 PARTIAL/FAIL: resident custom versions reduced from 2 to 1 in a failing-then-passing test. Estimate-time model loading remains unresolved.
- #9 FAIL: sequence overshoot remains unmeasured and unchanged; 0 frame-boundary proofs.
- #10 FAIL: unsupported ONNX slot remains unchanged; 0 new passing tests.
- #11 PARTIAL/FAIL: missing-output metadata and Render cards suppress Play; backend regression passes. Other home-card paths still need coverage.
- Dead SFX filter modal removed: 1 unreachable function deleted.
- Grade test now requires strokes at both contrasts: 2 passing cases.
- Stale aspect TODO corrected: aspect shipped; auto-frame remains open.

What got worse: no measured regression; missing-output checks add a filesystem stat per queue row.
Not tested: app screen, actual custom weights, story batch latency, sequence boundary timing.
Validation: 255 tests passed in 30.42 s; node syntax passed; 6 existing warnings.

## P2 — layout odds

1. FAIL: frame timecode available as player-time tooltip, not beside mm:ss; width not measured.
2. FAIL: 0 story/render playback captures; controls not exercised.
3. FAIL: 0 six-screen measurements at 1024×700/200% zoom; no layout claim.
4. PARTIAL/FAIL: real-clipboard hand step added; Node clipboard call not verified.

What got worse: no measured regression; tooltip adds information inaccessible on touch-only input.
Not tested: browser layout, clipboard, playback controls. Capture paths: none.
Validation: 255 tests pass; node syntax passes.

## P3 — local model slots

1. PARTIAL/FAIL: local Provider contract and Registry added; existing task routing is not migrated.
2. FAIL: 0 transcription slot flows implemented or measured.
3. PARTIAL/FAIL: 3 loopback URL cases accepted; 4 remote/credential/query cases refused. GET /v1/models and Settings integration remain absent.
4. FAIL: 0 voice slot flows implemented or measured.
Settings path/provider/flag persistence, valid/invalid/cleared slot cases remain untested.
What got worse: unused registry contract adds maintenance surface; no runtime behavior change claimed.
Not tested: real weights, endpoints, Settings rows, slot clearing. No model names added to UI.
Validation: 263 tests passed in 31.12 s; node syntax passed.

## P4 — readiness

1. FAIL: 0 publisher hashes verified; pack size rule unchanged. No guessed hashes introduced.
2. FAIL: 0 new LGPL source-offer documents or About integrations.
3. FAIL: 0 public Vietnamese samples benchmarked; no size/accuracy/speed recommendation or pack change.
4. PARTIAL/FAIL: repair instruction added to fill-status problem text; placement beside Reveal not verified.
5. FAIL: 0 new import error mappings or mapped-message tests.
6. PASS: 5-step clipboard/microphone hand-check sequence added in P2; microphone steps include permission, recording, playback and denial.
What got worse: longer fill-status text; layout not measured.
Not tested: downloads, checksum rejection, real microphone, Settings About or public speech models.
Validation: 263 tests pass; node syntax passes.
