# Refactor pass, no behaviour change — REQ-20261125-01 (2026-11-25)

Founder: "Do a code refractor for DuckSuite, rebuild & launch it for user test".
Read as a cleanup pass that changes no behaviour: remove what nothing reaches. Built by the
sub-leader. Fill output unchanged: `VERSION` stays 17, no cold render.

**Verdict: pass. 1,920 lines and one module removed, 0 lines added to code; 373 tests pass.**

## Method

- A reference count over `duckcore/`, `tests/`, `scripts/`, `static/duck/` and `mac/`: a top-level
  Python function or class, or a top-level JS function, whose name appears only at its own
  definition was removed. Repeated until none were left, because each removal can strand helpers.
- Decorated functions (FastAPI routes) were skipped. No `getattr`, `importlib` or `window[...]`
  lookup by a stored name exists in `duckcore/` or `app.js`, so a name count is complete.
- Unused imports removed by hand; the probe import `import onnxruntime  # noqa` in `custom.py`
  stays (it checks that the package exists).

## Removed

| Area | What |
|---|---|
| Python, round 1 (27) | VibeCut leftovers: `clipset.build_full_video_set`, `apply_edits`; `pipeline._transcribe_workflow`, `llm_rank_hooks`, `arc_order`, `read_scene`; `captions.apply_margin`, `merge_style_settings`, `parse_srt`, `list_tracks`, `edit_track`, `safe_zone_rects`; `selection.rank_stories`; `detect.CheckError`, `state_report`; `stt.whisper_model_cached`, `speech_language_for`; `settings_store.save_settings`, `get_secret`; `workflow_config.default_workflows`; `rights.may_import`; `preview.render_clean_preview`; `script._array_from_text`; `sttn.chunk_spans`; `textfill.render_options`, `model_signature`; `coreml_fill.package_ready` |
| Python, rounds 2–3 (29) | helpers only those used: `story_to_plan`, `validate_track` and its error class, `hook_candidates` and the story-evidence helpers, `transcribe_routes`, `fill_frame`, `release_fillers`, `package_path`, and others |
| Module | `duckcore/engine/usage_store.py` (cloud usage ledger; imported, never called) |
| Imports | 24 unused imports in 13 files |
| UI (9) | `checkStage`, `segmentsForScene`, `transcriptRow`, `focusShell`, `waveformBars`, `scriptDrawer`, `inspectorCaptions`, `openAudioModal`, `setCaptionSrt` |

## Acceptance

| # | Check | Result |
|---|---|---|
| 1 | Only deletions in code (`git diff --stat`: 0 code insertions) | pass |
| 2 | Every module imports; `node --check static/duck/app.js` | pass |
| 3 | The JS function list differs from `HEAD` by exactly the 9 names | pass |
| 4 | Full suite | 373 passed |
| 5 | Rebuilt app opens and its core listens on 127.0.0.1 only | see commit notes below |

## Revision 2026-11-25: the "Write .srt file" switch

Founder asked what the removed story and caption code did; checking it showed the **Write .srt
file** switch (Script inspector and Render) drew `data-action="caption-srt"` with no handler, before
and after this pass, so renders never wrote a `.srt`. Its helper `setCaptionSrt` was the orphan this
pass removed. Fixed: the change handler now sends `{ srt }` through `patchCaptions`, as the burn
switch does. New guards: `tests/test_ui_actions.py` (all 123 drawn actions have a handler) and the
captions route test now switches `srt` on and off. 375 tests pass. Not clicked in a real window (needs
a project).

## Not done (bigger refactors, need a brief)

- `static/duck/app.js` is still one 5,800-line file; `pipeline.py` 3,000 lines. Splitting them is a
  real refactor with UI risk, not this pass.
- Module-level constants only the removed code read, and CSS rules only the removed UI drew, were
  not hunted.
- `workflow_config.py` and `settings_store.py` still back the local speech ladder; not removed.

## Report row

- `docs/reports/ducksuite-product-progress.html`: not added; the insert anchor is not named.
