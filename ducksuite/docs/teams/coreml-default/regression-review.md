# bc89a5a regression repair — 2026-11-17

The pack-status path again checks exact size only. Publisher digests remain
verified once during download. A test patches verification to fail if status
tries to hash installed files. This intentionally does not detect later
same-size corruption; explicit verification remains a separate operation.

Import UI preserves creator sentences from the core, including wait/format/
copy instructions, and only maps recognizable technical browser/native errors.
Both tests failed before repair. Whole working tree passed 338 tests before
the subsequent Core ML fixes; JavaScript syntax passed. No real pack downloads.

The Core ML development files are excluded from this regression commit.
