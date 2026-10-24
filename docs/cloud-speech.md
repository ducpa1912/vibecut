# Cloud speech: cheap options that beat local

VibeCut is local-first. The Setup drawer adds optional cloud providers for the
two stages where local models cost the most time or quality: transcription and
voice over.

Keys are stored in `data/secrets.json` with mode `0600`. Environment variables
win, so Docker and CI can inject keys without writing a file. If a key comes from
the environment, Setup shows that field read-only; change or unset the env var to
replace it.

```
GROQ_API_KEY   OPENAI_API_KEY   DEEPGRAM_API_KEY   ELEVENLABS_API_KEY
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

The ladder is:

```
configured cloud provider → Apple SpeechAnalyzer → mlx-whisper
```

Audio is uploaded as mono 16 kHz mp3 at 64 kbps to stay under provider limits.
Segments come back as verbose JSON.

## Voice over

A 10-minute voice over is roughly 9,000 characters.

| Provider / model | Price | 9k chars | Notes |
|---|---|---|---|
| Kokoro local | free | $0 | Elo ~1064; already very good. Keep as default. |
| OpenAI `gpt-4o-mini-tts` | ~$15/M chars | ~$0.14 | Steerable; one public comparison puts it near or below Kokoro. |
| Groq Orpheus v1 English | $22/M chars | ~$0.20 | Expressive, six English voices, English only. |
| Deepgram Aura-1 / Aura-2 | $15 / $30 per M | $0.14 / $0.27 | Fast; business voices; Kokoro-tier quality. |
| ElevenLabs Flash v2.5 | ~$40/M chars | ~$0.36 | Clear naturalness and multilingual upgrade. |
| Cartesia Sonic 3.6 | ~$49/M chars | ~$0.44 | Top quality and latency. Price reference only; adapter planned. |

Recommendation: **keep Kokoro default**. Add ElevenLabs Flash for multilingual
naturalness, or Groq Orpheus for cheap expressive English. Cartesia is the
quality-first reference until its adapter ships. OpenAI mini and Deepgram Aura
are sidegrades, not upgrades.

Cloud voice is 20–60× the cost of transcription and about 1000× the LLM
rewrite. Every line is cached by text + voice + provider; only changed lines are
regenerated.

## Intelligence

VibeCut uses **OpenCode Go / DeepSeek V4.1 Flash** through the local OpenCode
service. It uses the OpenCode login already stored on this machine, so no API
key is copied into VibeCut.

```bash
opencode auth login          # connect OpenCode Go
opencode models | grep opencode-go/deepseek-v4.1-flash
```

For each rewrite, VibeCut creates a session with:

```json
{
  "model": {
    "id": "deepseek-v4.1-flash",
    "providerID": "opencode-go",
    "variant": "low"
  }
}
```

The `low` variant maps to `reasoningEffort: low`. The session is used for one
`/generate` call and then deleted. A failure falls back to MLX, Ollama, then
rules. The first rewrite of a job can take tens of seconds; lines are cached by
context afterwards, so repeated renders are instant.

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
