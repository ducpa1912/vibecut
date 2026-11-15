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
