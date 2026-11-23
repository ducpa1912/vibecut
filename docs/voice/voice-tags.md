# Voice tags and emotional delivery (2026-11-23)

The script is written once. Before speech is sent, Voice Room prepares it for
the selected engine. The rule is **never send one engine's tags to another
engine**.

## HeyGen Voice Turbo (through OpenRouter)

OpenRouter sends `input` to HeyGen unchanged, so HeyGen audio tags belong in
the text itself.

- A tag is an English phrase in square brackets: `[sad]`, `[whispers]`,
  `[laughs]`, `[clears throat]`, `[pause]`.
- Tags are lowercase. `[SAD]` is normalised to `[sad]` here.
- An emotion/delivery tag changes the text after it for about 233 characters
  (about 17 seconds), or until the next tag. A sound tag plays once.
- `slightly` and `extremely` are the supported intensity words:
  `[slightly sad]`, `[extremely angry]`. `[very sad]` is not a tag.
- Do not use closing tags (`[/sad]`) or two tags side by side.
- Public and instant/cloned voices perform tags. Professional HeyGen voices do
  not, but this app only uses public voices and clones.
- OpenRouter's `instructions` field has no effect on HeyGen; tags are the only
  delivery control.
- Sources:
  - <https://developers.heygen.com/docs/voices/heygen-voice-audio-tags>
  - <https://openrouter.ai/docs/guides/overview/multimodal/tts>

## MiniMax Speech 2.8 Turbo (direct API)

MiniMax has **no inline emotion tags**. One `voice_setting.emotion` applies to
the request, so each voiceover sentence is one request and gets its own emotion.

- `emotion`: `happy`, `sad`, `angry`, `fearful`, `disgusted`, `surprised`,
  `calm`, `fluent`.
- Speech 2.8 **does not support `whisper`**. A `[whispers]` or
  `[softly]` direction becomes `calm`, with a note.
- Interjections are in parentheses: `(laughs)`, `(chuckle)`, `(coughs)`,
  `(clear-throat)`, `(groans)`, `(breath)`, `(pant)`, `(inhale)`, `(exhale)`,
  `(gasps)`, `(sniffs)`, `(sighs)`, `(snorts)`, `(burps)`, `(lip-smacking)`,
  `(humming)`, `(hissing)`, `(emm)`, `(sneezes)`.
- Pauses are `<#x#>`, where `x` is seconds from 0.01 to 99.99.
- Sources:
  - <https://platform.minimax.io/docs/api-reference/speech-t2a-http>
  - <https://developers.cloudflare.com/ai/models/minimax/speech-2.8-turbo/>

## What the adapter does

`voice_tags.py` is the one place that knows both syntaxes.

| Script | HeyGen | MiniMax |
|---|---|---|
| `[sad]` | sent as `[sad]` | `emotion: sad`; tag removed |
| `[slightly sad]` | sent unchanged | `emotion: sad` (no intensity) |
| `[whispers]` | sent unchanged | `emotion: calm`, with a note |
| `[laughs]` | sent unchanged | `(laughs)` |
| `[pause]` | sent unchanged | `<#0.50#>` |
| `[shouts]` | sent unchanged | removed, with a note |
| `[Section 4]` or unknown | left for HeyGen | removed, with a note |

The voiceover panel also has an **Emotion** picker. It offers HeyGen's tags for
a HeyGen voice and MiniMax's eight emotions for a MiniMax voice; local and
ElevenLabs voices show no emotion control. A tag in the script wins over the
picker for that sentence.

The re-transcription self-check compares the spoken words after tags and
interjections are stripped, so `[sad]` is never counted as a missing word.

## What is not done

- MiniMax voice cloning is not part of this lane; MiniMax is a stock voice
  engine here. HeyGen is the cloning engine.
- `fluent` has no HeyGen equivalent and is MiniMax-only.
- Intensity is API-ready for HeyGen but not exposed as a separate UI control.
