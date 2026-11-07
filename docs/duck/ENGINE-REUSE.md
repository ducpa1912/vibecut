# DuckSuite engine reuse

Date: 2026-11-07
Source reference: frozen VibeCut Studio at `510bee9` (last code commit before distribution docs).
Rule: **copy selected code into a new orphan DuckSuite branch. Do not merge Studio history.**

## Copy

| Module | Source | Launch decision |
|---|---|---|
| Apple Vision | `vision.py`, `tools/vision_probe.swift` | Copy. OCR, faces, saliency, smart crop. |
| Apple Speech | `stt.py`, `tools/apple_transcribe.swift` | Copy. Default transcription. |
| Text tracking / masks | `detect.py`, `textfill/mask.py` | Copy. One layer per real text; tracking and fill planning. |
| LaMa fill | `textfill/` | Copy **LaMa only**. No MI-GAN or STTN at launch. |
| Render baseline | `render.py` selected parts | Copy as a baseline. It is not “best”; optimize after launch. |
| Captions | `captions.py`, `caption_reflow.py` | Copy and simplify to one track. |
| Voice-over / dub | `audio.py`, `tts.py`, `voice_fit.py` | Copy local paths. Built-in local API lists installed voices/models in Settings. No cloud keys. |
| Cache lessons | cache keys, model stamps, saved fills | Copy the design. Compress fills; per-project cache. |
| Project/edit model | `edits.py`, `compose_render.py` | **Undecided.** Do not copy wholesale. Start with a new minimal project/manifest; borrow immutable-edit and hash ideas only. |
| Licenses | `LICENSE`, `LICENSES/`, `THIRD_PARTY_NOTICES.md` | Copy and update for DuckSuite. |

## Do not copy

- `app.py` 110-route monolith.
- Studio routers except tiny pieces DuckSuite needs.
- Studio UI.
- Stories, moments, clip sets, selection, packet, publish, review links.
- Admin, batches, shares, preflight.
- Voice cloning.
- URL/XHS ingest.
- Full Studio test suite. Keep a small release smoke/E2E suite instead.

## What those things are

- **`app.py` 110 routes**: the old monolithic FastAPI server. It exposes every Studio feature: import, jobs, check, edits, render, queue, packet, admin, shares, classic, voice and more. DuckSuite gets a small local API instead.
- **`routes_*`**: separate FastAPI modules for feature areas. DuckSuite copies only the engine calls it needs, or rewrites them into its small API.
- **Stories / moments / clip sets / selection**: Studio’s long-video-to-shorts story engine. DuckSuite keeps a simple Dissect (scenes, transcript, moments), not the full story selection system.
- **Packet / publish / review links**: publish bundle, cover/copy, client review URLs and version labels. Not DuckSuite v1.
- **Admin / batches / shares / preflight**: local admin console, batch jobs, review sharing and publish checks. Not a consumer app.
- **URL/XHS ingest**: downloading from platforms via yt-dlp or Xiaohongshu scrapers. Legal/ToS/copyright/App Review risk; local file import only.

## Tests

Do not copy the 2,400-test Studio suite. Keep a small release suite:

- local core token and project API
- import/copy/delete
- one 1080p render smoke
- LaMa fill smoke
- dub/voice smoke
- App Store sandbox and StoreKit checks

## Voice settings

The local core exposes installed local voices/models to Settings. No provider API keys in the app. A voice is listed only when its model is present and checksum-verified.
