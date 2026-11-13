# QA repair brief — 2026-11-13

Source: `docs/reviews/independent-qa-2026-11-13.md` (0 P0, 0 P1, 7 P2, 2 P3).

Fix every finding without widening scope:

1. Cut changes must drop proofs drawn through the old Cut.
2. Crop offsets at 0 must stay 0.
3. Estimate unit keys must include geometry, mask, method, device and source.
4. Enqueue must be one atomic lookup+insert.
5. Queue refreshes must not drop keyboard focus.
6. A failed sidecar handshake must stop the core.
7. The proof key must include the source generation.
8. Layers with no ranges are always on in proofs too.
9. Reconcile the documents with shipped behaviour and the 219-test baseline.

No new features. No full render. No founder-project writes.
