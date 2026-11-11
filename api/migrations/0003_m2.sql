-- DuckClean — M2 schema additions.
--
-- 1. `detection_runs.effective_fps_milli`. A run reports the temporal density it
--    actually scanned. It is separate from the source fps because a truncated
--    run reads fewer frames than the source has, and that difference is product
--    truth, not a derived detail.
--
-- 2. `detection_runs.beat_manifest_hash_snapshot` is not added: the run already
--    points at a revision that hashes the manifest, and a second copy would let
--    the two disagree.

begin;

alter table detection_runs
  add column effective_fps_milli integer
  check (effective_fps_milli is null or effective_fps_milli >= 0);

commit;
