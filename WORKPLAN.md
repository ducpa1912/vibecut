# VibeCut Studio — Shared Workplan (OpenCode builds, Claude Code reviews)

**Source of truth for scope:** [`REVAMP_PLAN.md`](REVAMP_PLAN.md). This file covers only *who does what, in what order, and how work is accepted*.
**Baseline:** `main` at `0e0d0d7`.

## 1. Roles

| Role | Who | Does | Never does |
|---|---|---|---|
| **Builder lead** | OpenCode Go (main VibeCut session) | Spawns 4 coding sub-agents per wave. Gives each a worktree and branch. Collects their reports. Tells the founder when the wave is ready | Merges to `main`, pushes, edits another track's files, changes `REVAMP_PLAN.md` / `WORKPLAN.md` |
| **Coders T1–T4** | OpenCode sub-agents | Build one track per wave in its own worktree. Run the self-check (§4). Commit on the track branch | Touch files outside their ownership list (§3), merge, push, delete branches/worktrees |
| **Senior dev / merger** | Claude Code | Reviews every branch. Fixes small issues directly on the branch. Sends back larger ones. Merges in a fixed order. Runs the full suite on `main`. Opens the next wave | Builds whole tracks |
| **Founder** | you | Starts each wave. Supplies real fixture videos, Developer ID credentials and API keys. Final product calls | — |

## 2. Wave mechanics

1. **Wave start:**
   - Claude Code tags `main` as `wave-N-base`.
   - OpenCode creates 4 worktrees from that tag:

     ```text
     ../vibecut-wN-t1   branch rv/wN-t1-<slug>
     ../vibecut-wN-t2   branch rv/wN-t2-<slug>
     ../vibecut-wN-t3   branch rv/wN-t3-<slug>
     ../vibecut-wN-t4   branch rv/wN-t4-<slug>
     ```
2. **Build:**
   - Each coder works only in its worktree.
   - Commits are small, with Conventional Commit messages.
   - No rebases of `main` mid-wave.
3. **Report:** each coder writes `docs/handoff/wN-tK.md` on its branch. It covers:
   - what was built;
   - its files;
   - the endpoints/schemas touched;
   - tests added;
   - self-check output (§4);
   - known gaps.
4. **Hand-off:** OpenCode replies "Wave N ready", with the 4 branch names and their HEAD SHAs.
5. **Review** (Claude Code, per branch, in merge order T1 → T2 → T3 → T4). A branch is rejected or fixed if:
   - `git diff --name-only wave-N-base..branch` contains a file outside its ownership list;
   - the self-check fails;
   - the contract (§5) is broken;
   - it lacks tests for new behaviour;
   - it regresses a G1–G5 trust behaviour (lineage, packet bytes, queue recovery, auth, disk);
   - it reaches the network on the core path;
   - it introduces a removed engine or a "never" item.
6. **Fix or return:**
   - **Fix:** under about 50 lines; Claude Code commits on the branch as `review: …`.
   - **Return:** anything larger goes back to OpenCode with a numbered list of findings. The same coder fixes it on the same branch.
7. **Merge:**
   - Claude Code runs `git merge --no-ff` into `main` in order and resolves `app.py` include-line conflicts.
   - After each merge it runs the full suite.
   - When the wave is done, it tags `wave-N-done` and writes `docs/handoff/wN-review.md` with findings and fixes.
8. **Cleanup:** after the merge, Claude Code removes the wave worktrees and branches (`git worktree remove`, `git branch -d`). It also tags `wave-N-done`, so nothing is lost.

Nothing is pushed to GitHub until the founder asks.

## 3. Waves, tracks and file ownership

A coder may **create** new files only under its listed paths. It may **edit** only the files listed. `app.py` changes are limited to `import` and `app.include_router(...)` lines. Tests go in `tests/test_<module>.py` for the track's own modules only.

### Wave 1: Foundation

| Track | Build | Owns |
|---|---|---|
| **T1 Core model** | `Edit` model (versions, pointer, hash, history), `routes_edits.py` CRUD, pure `compose_render.py` compiling an Edit to per-segment filter strings + overlay layer list (golden-string tests; no ffmpeg calls) | `edits.py`, `routes_edits.py`, `compose_render.py`, `tests/test_edits.py`, `tests/test_compose_render.py` |
| **T2 Audio split + dead engines** | Pure move of `audio.py` into `stt.py` (cloud STT helpers only), `tts.py`, `music.py`, with re-exports kept in `audio.py` so callers don't change. Then remove dead code: Marian, Argos, Ollama, `local-mlx`, MusicGen, Stable Audio, `cc0` bucket, `tools/musicgen_generate.py`, `tools/music_generate.py`, `tools/rewrite_mlx.py`, `requirements-music.txt` | `audio.py`, `stt.py`, `tts.py`, `music.py`, the 4 tool/requirements files above, `tests/test_vibecut.py` (audio sections only), `tests/test_audio_split.py` |
| **T3 Check backend** | Keep OCR line boxes in `_apply_scene_read`; 0.5 fps sampled text pass; tracklet clustering; kind rules; speech/music/quality signals; `SourceReport`; `POST/GET /api/jobs/{id}/check` | `pipeline.py` (OCR/scene-read functions only), `detect.py`, `routes_check.py`, `tests/test_detect.py` |
| **T4 Studio shell** | `static/studio/` ES-module app: `shell.js` (5-step rail), `api.js`, `studio.css`, `import.js` + `stories.js` working on existing APIs; Classic toggle (Settings → "Use Classic editor", stored per viewer) | `static/studio/**`, `static/index.html` (entry point + toggle only) |

**Exit:**
- An Edit can be created, versioned and compiled.
- The full suite stays green after the `audio.py` split.
- `check` returns tracklets with real boxes.
- Studio opens, and Import and Stories work. Classic is still reachable.

### Wave 2: Engine

| Track | Build | Owns |
|---|---|---|
| **T1 Render hooks** | `_segment` `pre_filters` / `post_filters` (+ cache key), motion keyframes in crop path, `_burn_captions` → `_burn_layers` (static PNG + PNG sequences), frame endpoint, 540p story proxy, SSIM test frame vs final | `render.py`, `compose_render.py`, `routes_edits.py` (frame route), `tests/test_render_layers.py` |
| **T2 STT** | Move transcription out of `pipeline.py` into `stt.py`. Apple helper emits per-run word ranges. Whisper `--word-timestamps True`, large-v3-turbo default. Transcript v2 with chunk cache and resume. Vocabulary. Captions built from `words[]` (interpolation only for legacy). Remove OpenAI STT and the `auto` cloud ladder | `stt.py`, `pipeline.py` (transcription functions only), `tools/transcribe_apple.swift`, `captions.py` (cue building only), `tests/test_stt.py` |
| **T3 TTS + engine removal + packs** | TTS final set (MiniMax, ElevenLabs, OpenRouter, Kokoro, `say`); remove Piper/OpenAI/Groq/Deepgram/Cartesia TTS; one-voice-per-story fallback; per-sentence cache; settings migration table; `packs.py` (manifest, SHA-256 verify, install/remove under Application Support); admin pickers updated | `tts.py`, `packs.py`, `workflow_config.py`, `settings_store.py`, `admin/store.py`, `admin/routes.py`, `static/admin.js`, `tests/test_tts.py`, `tests/test_packs.py`, `tests/test_workflow_routes.py`, `tests/test_admin.py` |
| **T4 Studio Edit (base)** | `edit/preview.js` (canvas + safe zones + frame endpoint), `edit/timeline.js` (sentence track + layer tracks), `edit/layers/text.js`, `edit/layers/captions.js`, `edit/layers/color.js` against the T1-W1 Edit API | `static/studio/edit/**` |

**Exit:**
- One Edit with color, text, motion and a plate renders, and its frame matches the final within SSIM ≥ 0.98.
- Word timings are real.
- Removed TTS engines are gone, and old settings migrate.
- Packs install and verify.

### Wave 3: Flows

| Track | Build | Owns |
|---|---|---|
| **T1 Compose layers** | Text layers (from `overlays.py` validators), `fx.py` (punch-in, snap zoom, push, shake, arrow, circle, underline, progress bar, emoji/sticker), `color.py` + 8 `.cube` presets, sticker set, beat-snap | `overlays.py`, `fx.py`, `color.py`, `assets/luts/**`, `assets/stickers/**`, `compose_render.py`, tests for those |
| **T2 Clean (Flow 1)** | Tracklet → Clean layer; `crop_guard` / `blur` / `plate` / `mask`; kind policy (watermark refused; handle/logo needs attestation); residual-OCR quality report; rights attestation at import | `cleanup.py`, `routes_cleanup.py`, `tests/test_cleanup.py` |
| **T3 Music + mix + dub** | `music.py`: brief, 2 candidates, lock, cache, beat fit/loop/trim, licence metadata. `AudioPlan` modes. Ducking defaults, loudnorm −14. Dub slot fit 0.90–1.15× + Shorten | `music.py`, `audio.py` (mixer), `tts.py` (dub fit only), `tests/test_music.py`, `tests/test_mix.py` |
| **T4 Studio flows UI** | `check.js` (Source Check screen), `edit/layers/clean.js`, `edit/layers/effects.js`, `edit/layers/audio.js` (voice, music candidates, modes) | `static/studio/check.js`, `static/studio/edit/layers/{clean,effects,audio}.js` |

**Exit:**
- Flow 2 vertical slice works end to end.
- A Flow 1 baked-caption source is cleaned and recaptioned.
- Dub fits its slots.

### Wave 4: Finish

| Track | Build | Owns |
|---|---|---|
| **T1 Packet v2 + identity** | `edit.json`, `audio.json`, `music.json`, layer assets, cover from frame endpoint; artifact hash covers `edit.hash` / `transcript_id` / audio hashes; review links show the Edit version | `packet.py`, `artifacts.py`, `shares.py`, tests |
| **T2 Preflight inline** | Collision, face overlap, safe zone, residual text, caption density, loudness, voice-fit, missing music licence, 4:5-specific checks, as timeline markers API | `preflight.py`, tests |
| **T3 Migration + fallback** | Old jobs: caption track becomes an Edit with captions only; Classic reads/writes still work; render path for legacy targets intact | `migrations.py` (new), `app.py` (startup hook line only), tests |
| **T4 Studio Finish** | `finish.js` (render 9:16/4:5, queue, versions, packet, share), "Apply to all stories", `setup.js` (engines, keys, packs), plain-language sweep across `static/studio/**` | `static/studio/**` (except `edit/**`, which is frozen this wave) |

**Exit:** product complete in features. Feature freeze.

### Wave 5: Hardening

| Track | Build | Owns |
|---|---|---|
| **T1 Performance** | Proxy/cache/ETA; M1 16 GB budget runs; profile reports | profiling scripts, perf fixes routed to the owning file via review |
| **T2 Packaging (G1)** | `packaging/`: app bundle layout, bundled Python + ffmpeg build script, launchd plist, Application Support data path, diagnostics bundle, rollback build. Signing and notarization scripts **ready to run**. The founder runs them with their Developer ID | `packaging/**` |
| **T3 Acceptance harness** | Scripts that run REVAMP_PLAN §13 gates on the founder's fixture corpus and emit a report | `bench/**` |
| **T4 Bug bash** | Fix P0/P1 found in W5 review, one file owner at a time, as assigned by Claude Code | assigned per bug |

## 4. Coder self-check (paste output into the handoff file)

Run from the worktree root:

```bash
/opt/homebrew/bin/python3.11 -m pytest -q -p no:cacheprovider   # wave-1-base: 870 passed
/opt/homebrew/bin/python3.11 -m compileall -q .
node --check static/studio/*.js static/studio/**/*.js
git diff --name-only wave-N-base..HEAD
```

## 5. Contracts every track codes against

These are frozen at Wave 1 start. Changing one needs a note in the handoff file and Claude Code approval.

- **Edit, Transcript v2, AudioPlan, the layer catalogue and the never-list:** `REVAMP_PLAN.md` §3, §6.3, §7–§8.
- **SourceReport:** `REVAMP_PLAN.md` §5. Tracklet = `{id, kind, box{x,y,w,h} (source-normalized 0–1), ranges[{start,end}], text_sample, confidence}`.
- **Pointers:**
  - `job["story_edits"]["{set_id}:{story_id}:{aspect}"] -> edit_id`;
  - Edit versions under `jobs/<id>/edits/<edit_id>.json`, immutable;
  - transcripts under `jobs/<id>/transcript/transcript_v2*.json`.
- **Hashes:** sha256 over canonical JSON (sorted keys, no whitespace), the same as `overlays.overlay_hash`.
- **Feature flags:** none for new Studio code paths. The Classic UI is the fallback.
- **Network:** no new network calls outside `stt.py` / `tts.py` / `music.py` cloud routes and the existing text routes.
- **Tests:** never hit the network or require model packs. Fake every engine.

## 6. Founder inputs needed (and when)

| Input | Needed by |
|---|---|
| 10 short fixture clips with baked text + 10 clean, for Check tracklets | Wave 1 T3 (synthetic fixtures until then) |
| MiniMax / OpenRouter / ElevenLabs keys for manual music/voice checks | Wave 3 review |
| Full 30-source Check corpus, 60-clip cleanup set, 20-source story set | Wave 5 T3 |
| Apple Developer ID + notarization credentials (you run the scripts) | Wave 5 T2 |
| Confirm deletion of local caches (`REVAMP_PLAN.md` §9.4) | after Wave 2 merge |
