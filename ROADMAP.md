# VibeCut Roadmap

Version history, checklist and build plan. `[x]` shipped, `[~]` in progress,
`[ ]` planned, `[!]` parked on purpose.

## Version control

| Version | Date | Theme | Key changes |
|---|---|---|---|
| 0.9.0 | 2026-10-24 | P1/P2 | usage/cost readout, live STT/TTS tests, Cartesia, smoothed crop paths, review links, keyboard editor, Whisper model manager |
| 0.8.0 | 2026-10-24 | Bilateral crop | per-aspect attention crops for 9:16/4:5/1:1/16:9, true aspect reframe, direct OpenCode Go project key mode |
| 0.7.2 | 2026-10-24 | OpenCode translation | OpenCode Go becomes a translation provider, on by default; provider-scoped translation memo; line-end facts preserved through fit |
| 0.7.1 | 2026-10-24 | OpenCode Go | Intelligence switched from OpenRouter to local OpenCode Go / DeepSeek V4.1 Flash, `low` variant, session-per-call, no key copy |
| 0.7.0 | 2026-10-24 | Cloud config | Setup drawer, cloud STT (Groq/OpenAI/Deepgram), cloud TTS (OpenAI/Groq/Deepgram), secret store 0600 |
| 0.1.0 | 2026-10-23 | Core cut | probe, scene scan, stills, scoring, plans, 9:16 render |
| 0.2.0 | 2026-10-23 | Deep read | lazy scene read, why notes, hook lab, variants, transcript CC |
| 0.3.0 | 2026-10-23 | Render speed | parallel segments, segment cache, draft/final, VideoToolbox, cancel, ETA, render-all, aspects, captions, timeline edit |
| 0.4.0 | 2026-10-23 | Audio replacement | voice engines (say/piper/kokoro/elevenlabs), music (own/CC0/Stable Audio), modes keep/full/bed/voice/music, translation, script builder |
| 0.5.0 | 2026-10-23 | Storage & speed | video masters + audio mux, FLAC caches, 360px thumbs, cache caps, render retention, job clean, install audit |
| 0.6.3 | 2026-10-23 | Mixer v2 | click-to-add nodes, drag anywhere, cosine ramps, 100% scale, Flatten |
| 0.6.2 | 2026-10-23 | Mixer & small models | ruler automation mixer with draggable envelopes, original/music stem waveforms, MLX + Ollama small-model rewrite with story brief and retrieval |
| 0.6.1 | 2026-10-23 | Context rewrite | rewrite reads the full transcript, one complete sentence per beat, word-boundary fitting, memo keyed by context |
| 0.6.0 | 2026-10-23 | Script & delivery | rewrite styles, per-clip mixer, beat sync, line editor, SpeechAnalyzer, CAS source store, SRT/VTT/EDL/XML, presets, A/B, license registry, story arc, music library |

Versioning: SemVer-ish per feature batch. Every batch bumps the minor, updates
this table, and gets one commit. Patch bumps for fixes only.

## Checklist

### Audio script and language
- [x] Clean, de-duplicate and time-fit voice lines
- [x] Literal translation with provider ladder (OpenCode / Apple / Ollama / Marian / Argos)
- [x] Translation memo keyed by provider
- [x] Global translation memo cache
- [x] Rewrite styles: faithful, smooth, viral (fit to short duration)
- [x] Full-transcript context for the rewrite (whole story before writing the cut)
- [x] Complete-sentence per-beat source lines instead of trimmed fragments
- [x] Fact and budget validation for rewrites (no invented numbers)
- [x] Rules-only rewrite fallback when no LLM is available
- [x] Local small models: MLX worker, Ollama presets, provider select
- [x] Target-language transcript context + story brief + BM25-lite retrieval
- [x] Brief and rewrite caches keyed by model and context
- [x] Per-line script editor with instant re-TTS (line cache)
- [x] Rewrite variant compare in the Voice script panel

### Cloud setup (optional)
- [x] Local secret store (`data/secrets.json`, 0600) with env override
- [x] Setup drawer: keys, provider selects, masked values, test buttons
- [x] OpenCode Go rewrite + story brief; model `deepseek-v4.1-flash`, variant `low`
- [x] Direct OpenCode Go project API key mode (project-local secret, no shared login)
- [x] OpenCode Go translation
- [x] OpenCode Go optional translation
- [x] Cloud STT: Groq Whisper turbo, OpenAI Whisper, Deepgram Nova-3
- [x] Cloud TTS: OpenAI gpt-4o-mini-tts, Groq Orpheus, Deepgram Aura
- [x] Cloud STT/TTS fall back to local on any error
- [x] Cost table + recommendations in [docs/cloud-speech.md](docs/cloud-speech.md)
- [x] Per-job cloud usage/cost readout
- [x] Cartesia TTS adapter

### Audio mixing
- [x] Ruler automation mixer: draggable dB envelopes, ramps between points, clip sections
- [x] Original audio and music-stem waveforms for loud/mute/dip monitoring
- [x] Per-clip voice and music gain, mute
- [x] Beat sync: BPM detection, cut snapping, beat-aligned music start
- [!] SFX auto-placement (riser / whoosh / impact) — parked
- [!] Voice cloning (Apple Personal, RVC, ElevenLabs) — parked, consent gated
- [x] Music asset library (generated beds saved as reusable tracks)
- [x] License registry + strict mode for music and voice assets

### Analysis
- [x] SpeechAnalyzer transcription engine (macOS 26, 0 MB) with whisper fallback
- [x] Smart crop bilateral: vertical source to horizontal 16:9 / 4:5 / 1:1 and the opposite, attention stored per aspect
- [x] Per-frame crop path: 3 attention samples per beat, smoothed, rendered with dynamic crop expressions
- [ ] Story-arc reorder (setup → proof → payoff) for the beat order
- [ ] Local-LLM scene notes feeding hook and payoff explanations

### Delivery
- [x] SRT and VTT caption export
- [x] EDL (CMX3600) and FCP7 XML export for Resolve / Premiere
- [x] Platform presets (TikTok, Reels, Shorts, Square, Landscape)
- [x] Safe-zone caption margin per preset
- [x] A/B package: top 3 hooks rendered in one batch
- [x] Read-only review links with token, MP4 and SRT
- [x] Keyboard-first editor: select, reorder, trim, remove, save, draft, play

### Storage and speed
- [x] Content-addressed source store with hardlinks and GC
- [x] Cache caps, age prune, master reuse, FLAC caches
- [x] Job clean (work files / renders / all but source)
- [x] Install audit CLI
- [x] Whisper q4/model manager in Setup: cached marker and model picker

### Parked on purpose
- [!] SFX auto-placement: wait until music assets exist for most users
- [!] Voice cloning: legal risk, needs consent UX and license registry first
- [!] Beat-sync for AI-generated beds: generation is one-shot, no stable grid yet

## Build order

| Phase | Content | Status |
|---|---|---|
| 9 | Rewrite styles, script editor, variant compare | shipped 0.6.0 |
| 10 | Per-clip mixer, beat sync, music library, license registry | shipped 0.6.0 |
| 11 | SpeechAnalyzer, SRT/VTT, EDL/XML, presets, A/B | shipped 0.6.0 |
| 12 | CAS source store, story arc | shipped 0.6.0 |
| 12.5 | Cloud setup: OpenCode Go + cloud STT/TTS | shipped 0.7.1 |
| 13 | Smart crop bilateral, crop tracking, review links, keyboard editor | shipped 0.9.0 |
| 14 | SFX, cloning (consent gated), whisper q4 manager | parked |

## Acceptance checks

- Rewrite: hook line ≤ 2.2 s at 1.0x, every line fits its slot, entity/number
  drift is zero, rules fallback works with no LLM installed.
- Mixer: muting one clip removes voice only in that window; preview under 2 s warm.
- Beat sync: synthetic 120 BPM click track detected within ±2 BPM; cuts land
  within 250 ms of a beat; drift guard skips when snapping would move > 0.4 s total.
- SpeechAnalyzer: zh sample transcript comparable to whisper-small, no HF download.
- Cloud: Direct OpenCode Go payload uses `deepseek-v4.1-flash`, variant `low`,
  and the project key; a missing key/service falls back without failing the job;
  Groq/Deepgram segments parse; TTS payloads match provider contracts.
- Crop: portrait→16:9 follows the subject vertically; landscape→9:16 follows it
  horizontally; 4:5 and 1:1 use their own crop; segment cache keys change by crop.
  Tracked paths use three samples per beat, smoothed, and per-frame crop
  expressions; a trimmed clip offsets the path correctly.
- Usage: one OpenCode rewrite records tokens and estimated cost on the job.
- Review: token page serves the MP4 and SRT without exposing the editor.
- CAS: ingesting the same file twice yields one store entry; GC keeps referenced copies.
- Exports: EDL imports in Resolve with correct in/out frames at 30 fps.

## Smart crop bilateral (planned, phase 13)

Today the attention crop targets 9:16 only, because `crop_center()` clamps
against `TARGET_AR` and the face/salient boxes are dropped after scoring.
Plan:

1. Keep a compact `attention` block per scene: best face box, best salient box
   (x, y, w, h, confidence), rounded to 3 decimals.
2. `crop_center(scene, source_w, source_h, target_ar)` takes the aspect as a
   parameter and clamps against it, so a portrait source cropped to 16:9 uses the
   face's vertical position and vice versa.
3. `render._crop_filter` already handles both directions; pass the per-aspect
   crop computed from `attention` at render time instead of the stored 9:16 crop.
4. Aspect switch in the UI becomes a true reframe: no re-analysis, no re-scan of
   frames; only the crop math and the segment cache key change.
5. Tests: portrait + 16:9 clamps on the vertical axis and keeps the face in
   frame; landscape + 9:16 is unchanged from today's output; square is centred
   on the attention point.
