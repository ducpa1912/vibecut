# VibeCut Roadmap

Version history, shipped checklist, current plan and future proposal.
`[x]` shipped, `[~]` in progress, `[ ]` planned, `[!]` parked on purpose.

Full compressed plan: `~/.opencode/plan/vibecut-plan.md`.

## Version control

| Version | Date | Theme | Key changes |
|---|---|---|---|
| 0.10.0 | 2026-10-24 | Speech/Music/Upload | OpenCode→OpenRouter→Apple translation, AI rewrite fallback, MiniMax TTS/music, OpenRouter TTS/Lyria fallbacks, uploaded voice fit for Voice-over/Dub/Full Replace, audio tabs |
| 0.9.2 | 2026-10-24 | AI music fix | Stable Audio preflight + gated-weight guidance; ungated MusicGen Small fallback with worker |
| 0.9.1 | 2026-10-24 | Script prompt v2 | full target voice script + aesthetic + char/word budgets, complete-sentence rules, condense repair pass |
| 0.9.0 | 2026-10-24 | P1/P2 | usage/cost readout, live STT/TTS tests, Cartesia, smoothed crop paths, review links, keyboard editor, Whisper model manager |
| 0.8.0 | 2026-10-24 | Bilateral crop | per-aspect attention crops for 9:16/4:5/1:1/16:9, true aspect reframe, direct OpenCode Go project key mode |
| 0.7.2 | 2026-10-24 | OpenCode translation | OpenCode Go becomes a translation provider, on by default; provider-scoped translation memo; line-end facts preserved through fit |
| 0.7.1 | 2026-10-24 | OpenCode Go | Intelligence switched from OpenRouter to local OpenCode Go / DeepSeek V4.1 Flash, `low` variant, session-per-call, no key copy |
| 0.7.0 | 2026-10-24 | Cloud config | Setup drawer, cloud STT (Groq/OpenAI/Deepgram), cloud TTS (OpenAI/Groq/Deepgram), secret store 0600 |
| 0.6.3 | 2026-10-23 | Mixer v2 | click-to-add nodes, drag anywhere, cosine ramps, 100% scale, Flatten |
| 0.6.2 | 2026-10-23 | Mixer & small models | ruler automation mixer with draggable envelopes, original/music stem waveforms, MLX + Ollama small-model rewrite with story brief and retrieval |
| 0.6.1 | 2026-10-23 | Context rewrite | rewrite reads the full transcript, one complete sentence per beat, word-boundary fitting, memo keyed by context |
| 0.6.0 | 2026-10-23 | Script & delivery | rewrite styles, per-clip mixer, beat sync, line editor, SpeechAnalyzer, CAS source store, SRT/VTT/EDL/XML, presets, A/B, license registry, story arc, music library |
| 0.5.0 | 2026-10-23 | Storage & speed | video masters + audio mux, FLAC caches, 360px thumbs, cache caps, render retention, job clean, install audit |
| 0.4.0 | 2026-10-23 | Audio replacement | voice engines (say/piper/kokoro/elevenlabs), music (own/CC0/Stable Audio), modes keep/full/bed/voice/music, translation, script builder |
| 0.3.0 | 2026-10-23 | Render speed | parallel segments, segment cache, draft/final, VideoToolbox, cancel, ETA, render-all, aspects, captions, timeline edit |
| 0.2.0 | 2026-10-23 | Deep read | lazy scene read, why notes, hook lab, variants, transcript CC |
| 0.1.0 | 2026-10-23 | Core cut | probe, scene scan, stills, scoring, plans, 9:16 render |

Versioning: SemVer-ish per feature batch. Every batch bumps the minor, updates
this table, and gets one commit. Patch bumps for fixes only.

## Current state

- Local-first FastAPI + vanilla UI, no build step.
- Analysis: scan, shortlist, deep read, bilateral crops, smoothed crop paths.
- Smart cut plans 15/30/60, hook lab, variants, A/B, review links, keyboard editor.
- Audio: Voice-over/Dub/Music/Full Replace tabs; uploaded voice fit; mixer.
- Translation: OpenCode Go DeepSeek V4.1 Flash → OpenRouter DeepSeek V4.1 Flash → Apple Translation.
- Rewrite: OpenCode → OpenRouter → MLX/Ollama → rules.
- TTS: MiniMax Speech 2.8 Turbo → OpenRouter Fish S2.1 Pro Free → Gemini 3.8 Flash-Lite TTS → local.
- Music: MiniMax Music → OpenRouter Lyria 3 → library/CC0.
- STT: cloud → Apple SpeechAnalyzer → mlx-whisper.
- Setup: keys in `data/secrets.json` 0600, env overrides, masked API.
- 100 tests pass. Commit `02c0fc2`.

## Shipped checklist

### Audio script and language

- [x] Clean, de-duplicate and time-fit voice lines
- [x] Fixed translation ladder: OpenCode → OpenRouter → Apple
- [x] One local translation fallback in normal UI: Apple; batches split and retried
- [x] Translation memo keyed by provider; global translation cache
- [x] Rewrite styles: faithful, smooth, viral; full-transcript context
- [x] AI rewrite ladder: OpenCode → OpenRouter → MLX/Ollama → rules
- [x] Complete-sentence per-beat lines; fact/budget validation; no invented numbers
- [x] Target-language transcript context + story brief + BM25-lite retrieval
- [x] Brief/rewrite caches keyed by model and context
- [x] Per-line script editor with instant re-TTS; rewrite variant compare
- [x] Uploaded voice fit for Voice-over/Dub/Full Replace

### Cloud setup (optional)

- [x] Local secret store (`data/secrets.json`, 0600) with env override
- [x] Setup drawer: keys, provider selects, masked values, test buttons
- [x] OpenCode Go rewrite + story brief; model `deepseek-v4.1-flash`, variant `low`
- [x] Direct OpenCode Go project API key mode (project-local secret, no shared login)
- [x] OpenRouter DeepSeek translation/rewrite fallback
- [x] MiniMax Speech 2.8 Turbo + OpenRouter Fish/Gemini TTS fallback
- [x] MiniMax Music + OpenRouter Lyria 3 fallback
- [x] Audio mode tabs and upload-only-in-supported-modes UI
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
- [x] Music asset library (generated beds saved as reusable tracks)
- [x] License registry + strict mode for music and voice assets
- [x] Legacy AI music: Stable Audio preflight, MusicGen Small fallback (hidden from normal UI)

### Analysis

- [x] SpeechAnalyzer transcription engine (macOS 26, 0 MB) with whisper fallback
- [x] Smart crop bilateral: vertical source to horizontal 16:9 / 4:5 / 1:1 and the opposite, attention stored per aspect
- [x] Per-frame crop path: 3 attention samples per beat, smoothed, rendered with dynamic crop expressions
- [x] Story-arc reorder (setup → proof → payoff) for the beat order
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

## Outstanding now

1. **Verify cloud keys.** MiniMax TTS/music and OpenRouter Lyria/TTS are
   mock-tested only. `OPENROUTER_API_KEY` returns 401; unset or replace it.
   Add a MiniMax key, then live-test TTS and music.
2. **MiniMax music access.** Hosted music API is only for existing paying
   accounts. Confirm account access; otherwise use MiniMax Audio web or open
   Music 3 weights locally.
3. **Music latency.** First generation still blocks render. Cache exists, but
   there is no async prefetch/background job. This is the main remaining speed
   problem.
4. **UI revamp not shipped.** Moments rail above Smart Cut, compact horizontal
   strip, expandable collage, drag/drop cut editing, auto-hook orange, payoff
   neon green, and Smart Cut rename are absent from the current UI.
5. **Uploaded audio is whole-file fit.** It time-stretches/pads the recording to
   cut length. Per-line sentence alignment and manual line mapping are future.
6. **Apple Translation reliability.** Batches of 20 with one retry now; still
   needs a live stress test on large transcripts and missing language packs.
7. **Legacy cleanup.** Stable Audio, MusicGen, Argos/Marian/Ollama are hidden
   from normal UI but remain in code/docs. Decide keep as Advanced or remove.
8. **Translation glossary.** Brand/product names are not yet extracted or
   editable. Add glossary per job, cache keyed by glossary version.

## Future proposal

### Audio and voice

- **Async music:** generate in background on Smart Cut change, debounce, cache
  by prompt+mood+duration, use library placeholder, swap when ready, timeout +
  fallback.
- **Music candidates:** generate 2 short beds, score speech masking, beat
  alignment, energy match, spectral balance; keep best, A/B other.
- **Stem buses:** voice, original SFX, original music, generated
  drums/bass/harmony/melody, SFX. Dynamic EQ carve and sidechain duck.
- **Mastering:** platform LUFS targets, true peak limiting, dialogue leveling,
  de-ess, room match.
- **Uploaded voice v2:** forced alignment per line, sentence split, manual
  mapping, high-quality time-stretch. Optional voice-reference cloning later
  with consent.
- **SFX:** riser/whoosh/impact/ambience from MiniMax/Stable/ACE-Step or CC0;
  auto-place at cuts/beats. Parked until music library is stable.
- **Voice cloning:** parked; consent, provenance, license registry required.

### Smart Cut UI

- Move Moments directly below intro + video rating, above Smart Cut.
- Compact horizontal filmstrip + scrub slider; expand to full collage.
- Auto hook orange border; payoff neon green; selected clips check badge.
- Drag moment into Smart Cut; drag clip to reorder; drag edge to trim; drag out
  to remove.
- Rename Build to Smart Cut.
- One primary Render + Draft; Advanced collapses aspect, captions, arc, A/B,
  variants, render-all.
- Audio tabs below Smart Cut; only mode-relevant controls visible.

### Translation

- Keep fixed ladder: OpenCode → OpenRouter → Apple.
- One local option only. Apple recommended for macOS; Marian only if
  Linux/Docker becomes a target.
- Full-script translation prompt with line IDs, target language, aesthetic/tone,
  glossary, complete sentences, JSON array, one repair pass.
- Cache per provider + glossary version.
- Add glossary extractor and editor; do-not-translate list.

### Music provider strategy

- Normal path: MiniMax Music → OpenRouter Lyria 3 (Clip for ≤32 s, Pro for
  longer).
- Keep library/CC0 as instant fallback.
- Hide Stable Audio/MusicGen from normal UI; keep legacy code only if needed.
- OpenRouter Lyria image-to-music: pass hook/hero frame for visual vibe; test.
- Local ACE-Step 1.5 optional future Advanced path: MIT, fast on Mac,
  reference/repaint/cover. Do not make it required setup.
- Music Director: transcript + aesthetic + clip energy → structured brief
  (genre, BPM, key, instruments, sections, reference, negative prompt).
- Cost controls: per-job usage, provider caps, cache reuse across variants.

### Cloud and publishing

- Open-core: AGPL/Apache core + proprietary cloud control plane.
- Cloud needs cross-platform models: faster-whisper, PaddleOCR/Florence,
  Demucs, Kokoro/Piper, MiniMax/OpenRouter APIs.
- Per-tenant buckets, signed URLs, queue workers, quota/metering, Stripe,
  retention, moderation, voice-clone consent.
- Portable job bundle between local and cloud.
- Cost model: ~$0.01–0.03 compute per 10-min job before margin; storage/CDN on
  top; price 3–5×.

### Provider/cost notes

- MiniMax Speech 2.8 Turbo: ~$60/M chars; 10-min VO ~$0.54.
- Gemini 3.8 Flash-Lite TTS: ~$0.009/min; ~$0.09 per 10 min.
- MiniMax Music: $0.15 per up-to-5-min track (existing accounts).
- Lyria 3 Clip: $0.04 per 30 s; Pro: $0.08 per song.
- OpenCode Go/OpenRouter DeepSeek: negligible per script; OpenRouter invalid
  key must be fixed.
- Apple Translation: free, on-device, macOS-only.
- MusicGen: slow, non-commercial weights; do not ship in cloud.
- Stable Audio Open: gated; optional legacy.

## Priorities

1. Fix OpenRouter env key; add MiniMax key; live-test TTS/music.
2. Async music prefetch/cache so render does not block.
3. Smart Cut + Moments rail UI revamp.
4. Per-line uploaded voice alignment.
5. Translation glossary + Apple stress test.
6. Music Director + candidates + stem buses/mastering.
7. SFX and cloning remain parked.

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
| 15 | OpenRouter fallback, MiniMax TTS/music, upload fit, audio tabs | shipped 0.10.0 |
| 16 | Async music, Smart Cut/Moments UI, per-line upload, glossary | next |
| 17 | Music Director, candidates, stem buses, mastering | future |
| 18 | Cloud/open-core packaging | future |

## Acceptance checks

- Translation: OpenCode→OpenRouter→Apple works; Apple large batch does not
  crash; one local provider in UI; glossary and provider cache stay separate.
- Rewrite: smooth/viral uses AI; complete sentences; no fragments; fallback does
  not cache literal; entity/number drift is zero.
- TTS: uploaded recording fits cut; no translation/voice-engine prompts;
  MiniMax → Fish → Gemini fallback order works.
- Audio tabs: Original/Voice-over/Dub/Music/Full Replace behave as defined;
  Voice-over keeps original audio under the voice; Dub keeps music/SFX.
- Music: MiniMax→Lyria fallback; first generation async/cached; render never
  stalls at 90% without status.
- UI: Moments rail + Smart Cut drag/drop works; hook orange, payoff neon green.
- Mixer: muting one clip removes voice only in that window; preview under 2 s
  warm.
- Beat sync: synthetic 120 BPM click track detected within ±2 BPM; cuts land
  within 250 ms of a beat; drift guard skips when snapping would move > 0.4 s.
- SpeechAnalyzer: zh sample transcript comparable to whisper-small, no HF
  download.
- Cloud: direct OpenCode Go payload uses `deepseek-v4.1-flash`, variant `low`,
  and the project key; a missing key/service falls back without failing the job;
  Groq/Deepgram segments parse; TTS payloads match provider contracts.
- Crop: portrait→16:9 follows the subject vertically; landscape→9:16 follows it
  horizontally; 4:5 and 1:1 use their own crop; segment cache keys change by
  crop. Tracked paths use three samples per beat, smoothed, and per-frame crop
  expressions; a trimmed clip offsets the path correctly.
- Usage: one OpenCode rewrite records tokens and estimated cost on the job;
  MiniMax/Lyria music records a call/cost.
- Review: token page serves the MP4 and SRT without exposing the editor.
- CAS: ingesting the same file twice yields one store entry; GC keeps referenced
  copies.
- Exports: EDL imports in Resolve with correct in/out frames at 30 fps.

## Parked on purpose

- [!] SFX auto-placement: wait until music assets exist for most users.
- [!] Voice cloning: legal risk, needs consent UX and license registry first.
- [!] Beat-sync for AI-generated beds: generation is one-shot, no stable grid yet.
