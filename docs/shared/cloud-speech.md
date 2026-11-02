> **Scope:** Setup exposes OpenCode, OpenRouter, MiniMax and local engines. The
> admin console manages all eight AI keys and the ordered route lists for
> intelligence, speech, music, and transcription. Cloud STT/TTS are optional;
> local engines remain the default. OpenRouter project keys override env.

# Cloud speech: optional providers behind ordered admin routes

VibeCut is local-first. The admin console adds optional cloud providers for the
stages where local models cost the most time or quality: intelligence,
transcription and voice over. Setup keeps the spoken language and optional key
entry; route order lives in the admin console.

Keys are stored in the configured data directory (`secrets.json`, default `data/secrets.json`) with mode `0600`. Environment variables
win, so Docker and CI can inject keys without writing a file. If a key comes from
the environment, Setup shows that field read-only; change or unset the env var to
replace it.

```
OPENCODE_GO_API_KEY   OPENROUTER_API_KEY   MINIMAX_API_KEY
GROQ_API_KEY          OPENAI_API_KEY       DEEPGRAM_API_KEY
ELEVENLABS_API_KEY    CARTESIA_API_KEY
```

The API only returns `configured: true/false`; it never returns a key.

## Transcription

Prices checked October 2026, pay-as-you-go.

| Provider / model | Price | 10-min job | Notes |
|---|---|---|---|
| Groq `whisper-large-v3-turbo` | $0.04/hour | $0.007 | Best default. Fast, word segments, multilingual. |
| Groq `whisper-large-v3` | $0.111/hour | $0.019 | Highest Whisper accuracy. |
| Deepgram Nova-3 | ~$0.0043/min promo, ~$0.0077/min list | $0.043–0.077 | Good on noise; diarization and smart formatting. |
| OpenAI `whisper-1` | $0.36/hour | $0.060 | Older model; use only if the key already exists. |
| Apple SpeechAnalyzer | free | $0 | macOS 26, strong zh/en, private, 0 MB. |
| mlx-whisper | free | $0 | Local fallback, model download on first use. |

Recommendation: **Groq turbo** for normal use. If the local pipeline already
runs Whisper large-v3-turbo, cloud buys speed rather than accuracy; use Groq
large-v3 or Deepgram for hard audio.

The ladder is whatever the admin console transcription routes list, top to
bottom. The default is local:

```
Apple SpeechAnalyzer → mlx-whisper
```

Add Groq, OpenAI, or Deepgram routes to opt into cloud STT. Audio is uploaded
as mono 16 kHz mp3 to stay under provider limits. Segments come back as verbose
JSON.

## Voice over

A 10-minute voice over is roughly 9,000 characters.

| Provider / model | Price | 9k chars | Notes |
|---|---|---|---|
| Kokoro local | free | $0 | Elo ~1064; already very good. Keep as default. |
| OpenAI `gpt-4o-mini-tts` | ~$15/M chars | ~$0.14 | Steerable; one public comparison puts it near or below Kokoro. |
| Groq Orpheus v1 English | $22/M chars | ~$0.20 | Expressive, six English voices, English only. |
| Deepgram Aura-1 / Aura-2 | $15 / $30 per M | $0.14 / $0.27 | Fast; business voices; Kokoro-tier quality. |
| ElevenLabs Flash v2.5 | ~$40/M chars | ~$0.36 | Clear naturalness and multilingual upgrade. |
| Cartesia Sonic 3.6 | ~$49/M chars | ~$0.44 | Top quality and latency. Implemented. |

Recommendation: **keep Kokoro default**. Add ElevenLabs Flash for multilingual
naturalness, Groq Orpheus for cheap expressive English, or Cartesia when quality
matters more than cost. OpenAI mini and Deepgram Aura are sidegrades, not
upgrades.

Cloud voice runs only when its route is in the admin voice-over list; the
route order is the fallback order. Every line is cached by provider, model,
voice, rate, and text; only changed lines are regenerated.

## Intelligence

VibeCut uses **OpenCode Go / DeepSeek V4.1 Flash** through a project API key or
the local OpenCode service.

A key entered in **Setup → Intelligence** is stored only in this project's
`data/secrets.json` (0600, gitignored). It is never returned by the API, never
logged, and never committed. When a key exists, VibeCut calls the direct
endpoint exclusively:

```
https://opencode.ai/inference/go/openai/v1/chat/completions
```

and does not borrow the shared local login. Leave the key blank to use the
OpenCode CLI login instead.

```bash
opencode auth login          # connect OpenCode Go
opencode models | grep opencode-go/deepseek-v4.1-flash
```

Direct API requests use:

```json
{
  "model": "deepseek-v4.1-flash",
  "reasoning_effort": "low"
}
```

Local-service requests create a session pinned to the same model and the `low`
variant, generate once, then delete the session. A failure falls back to MLX,
Ollama, then rules. The first rewrite of a job can take tens of seconds; lines
are cached by context afterwards, so repeated renders are instant.

DeepSeek V4.1 Flash on OpenCode Go:

- Included in the Go plan; monthly usage limit $80 (Go) / $160 (Go Plus).
- Token price: $0.15 input / $0.60 output per 1M off-peak;
  $0.30 / $1.20 at peak.
- A full-context rewrite (~3k input + 1k output) costs about $0.001–0.002.
- Not used for training; 0-day retention per OpenCode Go docs.

### Translation

OpenCode Go also translates subtitle lines, one batch per render. **Setup →
Intelligence → Translation** is on by default; the audio panel's **Translate
engine** list also offers OpenCode Go explicitly. The provider ladder is:

```
OpenCode Go → Argos → Apple Translation → Marian → Ollama
```

Translation cache entries are keyed by provider, so switching from Argos to
OpenCode does not reuse the old engine's output. If every provider fails, VibeCut
shows the install hints and keeps the literal script.

OpenCode Go is optional. Local MLX, Ollama, and the rules fallback stay active
without it.


## Usage and tests

- The result header shows per-job calls, OpenCode tokens, STT minutes, TTS
  characters and an estimated cost.
- **Live STT** in Setup synthesizes a local test clip and exercises the local
  Apple Speech → mlx-whisper path. It is a local readiness check; normal job
  transcription follows the admin console route list, which may include cloud
  STT providers.
- **Live TTS** synthesizes a sample, plays it in Setup, and exposes it at
  `/api/settings/tts-test/<engine>.wav`.
- Token prices in the ledger: DeepSeek V4.1 Flash off-peak, local STT,
  MiniMax/OpenRouter TTS and music. Legacy provider prices remain in old data.


## 0.10 provider order

Translation: **OpenCode Go DeepSeek V4.1 Flash → OpenRouter DeepSeek V4.1 Flash → Apple Translation**. Apple batches are split and retried. Argos/Marian/Ollama are advanced only.

Voice: **MiniMax Speech 2.8 Turbo → OpenRouter Fish S2.1 Pro Free → OpenRouter Gemini 3.8 Flash-Lite TTS → local Kokoro/Piper/say**. A fallback switches the whole line only when the primary fails; voice identity can change, so test before a final export.

Music: **MiniMax Music → OpenRouter Lyria 3 Clip (30 s) / Pro (>32 s) → library**. MiniMax music API is only for existing paying accounts; no live test was run without a key.

Uploaded voice: in Voice-over, Dub and Full Replace, choose **Use my recording**. Translation and voice-engine controls disappear; the recording is time-fitted to the cut with atempo and silence padding. It is not cloned and does not need a TTS key.

MiniMax music/TTS adapters are implemented against the official docs but were
not live-tested without a key. MiniMax music is only available to existing
paying accounts; new accounts should use MiniMax Audio or the open Music 3
weights. OpenRouter Fish/Gemini TTS and Lyria music are also mock-tested only.
