# Audio replacement plan (voice over, dub, music, VFX)

## Status: first version built

The render panel now has an **Audio** section with five modes:

| Mode | Pipeline |
|---|---|
| `keep` | Original audio, nothing changes |
| `full` | Original dropped, new voice + new music |
| `bed` | Demucs instrumental stem kept, new voice dubbed over it |
| `voice` | Original voice replaced, no new music |
| `music` | Original dropped, new music only |

Voice engines: Apple `say`, Piper medium, Kokoro int8, ElevenLabs (API key).
Music: own folder, CC0 folder, Stable Audio Open Small, Stable Audio Open 1.0,
all with auto mood from the cut's beats. Translation runs per render through
Apple Translation, Ollama, Marian/opus-mt or offline Argos, memoized in
`data/cache/translate` so repeat variants are free.

Renders share one cached video master per plan/quality/aspect/captions; each
language or voice mix is a small `-c:v copy` mux (~2 s). Voice lines are mono
FLAC and synthesized in parallel, Demucs stems are FLAC, and the Demucs scratch
folder is removed after each separation.

Still open: SFX auto-placement, voice cloning, per-clip mixer UI, beat-sync.

## Goal

For any plan, build an `AudioPlan` and a single mixed audio track:

```
mix = voice (optional) + music (optional) + sfx (optional)
original audio = 0% | ducked under voice | full
```

Output stays −14 LUFS, −1.5 dBTP, 48 kHz stereo.

## Data model

```json
{
  "mode": "keep | full | bed | voice | music",
  "translate": {"target": "en", "provider": "auto"} ,
  "voice": {
    "engine": "say | piper | kokoro | elevenlabs",
    "voice": "Tingting",
    "rate": 1.0,
    "gain_db": 0.0
  },
  "music": {
    "source": "none | library | cc0 | stable-small | stable-1.0",
    "track": "assets/music/cc0/calm-loop.mp3",
    "prompt": "auto",
    "gain_db": -18.0,
    "duck": true,
    "moods": ["calm", "warm"]
  },
  "sfx": {"enabled": false}
}
```

Rules:

- The script is built from Whisper speech first, on-screen text second. Fillers
  and stage directions are stripped, near-duplicate lines are dropped, and each
  line is cut to the room its beat has.
- Each line gets an emotion tag (energetic / calm / warm / punchy / neutral)
  that changes the speaking rate, so the read matches the beat.
- Lines are anchored to their beat and fitted into the slot: up to 1.35×
  `atempo` plus a trim with fades, so they never overlap the next line.
- Translation runs on the cleaned lines before fitting, because target-language
  length differs. Provider order: ready engines first (Argos pair, Apple
  Translation pack, Marian/opus-mt, Ollama), then first-use downloads.
- Music ducks under voice with ffmpeg `sidechaincompress`.
- SFX auto-place on hook (riser), every cut (whoosh, optional), payoff
  (impact). User can disable or move each one. Not built yet.
- `keep` is the default, so existing renders and jobs do not change.

## Pipeline stages

1. **Script** — collect plan clips → per-clip text (speech, OCR, or manual
   script). For dub, translate first.
2. **Voice render** — per line TTS to WAV, resample, trim/pad to the clip
   window, concatenate with silence for gaps.
3. **Bed** — music loop or generate, trim to total length, duck.
4. **FX** — place SFX samples at cut points with 5 ms fades.
5. **Mix** — `amix` voice + music + sfx, `loudnorm`, encode AAC 192 kbps.
6. **Mux** — replace the audio stream in the existing concat step.

Implementation sketch (all ffmpeg, no new runtime deps for the default path):

```bash
# per line
piper -m en_US-amy-medium.onnx -f line_00.wav
ffmpeg -i line_00.wav -af "aresample=48000,atempo=1.04,apad" -t 2.40 line_00_fit.wav

# voice bed
ffmpeg -f concat -i voice_list.txt -c copy voice.wav

# duck music under voice
ffmpeg -i music.mp3 -i voice.wav -filter_complex \
  "[0:a]volume=-18dB[m];[1:a]asplit=2[v][sc];\
   [m][sc]sidechaincompress=threshold=0.03:ratio=8:release=250[ducked];\
   [ducked][v]amix=inputs=2:duration=first" music_ducked.wav

# final mix
ffmpeg -i voice.wav -i music_ducked.wav -i sfx_list.wav \
  -filter_complex "[0:a][1:a][2:a]amix=inputs=3:normalize=0[mix]" \
  -map "[mix]" -af loudnorm=I=-14:TP=-1.5:LRA=11 mix.m4a
```

## Phases

| Phase | Scope | Notes |
|---|---|---|
| A1 | `AudioPlan` model + "Keep original / Mute original" toggle | No new deps |
| A2 | Upload or record a voice over, align to clips | Browser MediaRecorder |
| A3 | Local TTS voice over from transcript | Piper or Kokoro |
| A4 | Music bed + duck + SFX auto-placement | Local asset folder |
| A5 | Dub: translate transcript, per-language TTS | NLLB / M2M100 local |
| A6 | Voice cloning / matching | XTTS only with consent |
| A7 | Manual mixer UI: per-clip voice, music, FX gains | Preview before render |

## Where the audio assets live

```
assets/music/*.mp3      user-supplied, or generated locally
assets/sfx/*.wav        whoosh, riser, impact, pop
assets/voice/*.wav      per-line TTS or recordings
```

Keep all defaults local. Network TTS engines are opt-in and never the default.

## Voice options

### Free, on machine

| Tool | What it gives | License / note |
|---|---|---|
| **Piper** | Fast neural TTS, many languages, ONNX, CPU-friendly | MIT. Best default for local voice over |
| **Kokoro-82M** | Small, natural English + others | Apache-2.0 |
| **Coqui XTTS v2** | Multilingual, voice cloning from ~6 s sample | CPML, non-commercial |
| **Bark** | Expressive, laughs/emotion, slow | MIT weights, heavy |
| **espeak-ng** | Robotic fallback, tiny | GPL |
| **Whisper / faster-whisper** | Transcript for voice over and dub timing | MIT |
| **Demucs** | Split vocals vs music from the original | MIT |
| **RVC / so-vits-svc** | Voice conversion to a target voice | MIT code, model licenses vary |
| **ffmpeg + rubberband** | Retime and pitch-correct TTS | LGPL / GPL |
| **MusicGen / AudioCraft** | Generate music beds locally | Code MIT, weights CC-BY-NC |
| **Stable Audio Open** | Generate short music/SFX | Weights CC-BY-NC |
| **Freesound / Pixabay / Mixkit** | CC0 / royalty-free music and SFX libraries | Check per item |

### Free, online or hosted model

| Tool | What it gives | Caveat |
|---|---|---|
| **Edge TTS** (Microsoft) | Very natural multilingual TTS, no key | Unofficial endpoint, ToS risk |
| **Google Translate TTS** | Quick multilingual lines | Unofficial, rate-limited |
| **gTTS** | Simple Google TTS wrapper | Same caveat |
| **Hugging Face Inference API** | Free tier for many TTS models | Rate limits, models change |
| **Replicate / HF Spaces** | XTTS, Bark, MusicGen demos | Free credits, then paid |
| **ElevenLabs free tier** | ~10k chars/month, good quality | Attribution, quota |
| **Play.ht / Murf / Speechify trials** | Hosted voices | Time or character limited |
| **YouTube Audio Library** | Music and SFX | License varies per track |
| **Free Music Archive / Uppbeat** | Music beds | Attribution on some tracks |

### Paid

| Tool | Best for |
|---|---|
| **ElevenLabs** | Best voice quality, cloning, dubbing API |
| **OpenAI TTS** | Clean voices, simple API |
| **Azure / Google Cloud / Amazon Polly** | Production TTS, SSML, many languages |
| **PlayHT, Resemble AI, Murf, Speechify** | Hosted voice over and cloning |
| **Descript Overdub** | Fix words in an existing voice over |
| **Adobe Podcast Enhance** | Clean up recorded voice |
| **Suno, Udio** | Generated music beds |
| **Epidemic Sound, Artlist, Soundstripe, Musicbed** | Licensed music catalogs |
| **Envato Elements, AudioJungle** | Music and SFX packs |
| **HeyGen, Rask, Dubverse, Papercup, Deepdub** | Full video dubbing services |

## Dub flow

```
Whisper segments
  → translate (NLLB-200 local, or DeepL paid)
  → TTS per line in target language
  → retime each line to its clip (stretch/pad)
  → duck music under the new voice
  → mux over the untouched video
```

Keep the original transcript and the translated lines side by side in
`transcript/`, so a wrong line can be fixed without re-running Whisper.

## Consent and licensing

- Only clone a voice you own or have written permission to use.
- Non-commercial weights (XTTS, MusicGen, Stable Audio Open) must stay
  non-commercial unless the license is purchased.
- Record the source and license of every music/SFX asset in the job JSON.
- Add a `VIBECUT_AUDIO_LICENSE=strict` mode that blocks assets with missing
  license metadata.
