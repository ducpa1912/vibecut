# Voice fit: pitch, tone and speed

VibeCut fits every spoken line to its cut slot with **one** voice-fit stage.
Providers synthesise at 1.0× and pitch 0; VibeCut applies the speed change.

## Preserve voice (default)

- **On:** time-stretch only. Pitch and tone stay put. The line is capped at
  **1.25×** (or lower if `max_speed` is lower). If the sentence still does not
  fit, the script is shortened.
- **Off:** intentional pitch rise (“chipmunk”). The cap is **1.8×** by default;
  checking `allow_extreme_speed` raises the UI cap to **2.5×** with a stronger
  warning.

Settings live in `data/settings.json`:

```json
"voice_fit": {
  "preserve_pitch": true,
  "max_speed": 1.80,
  "engine": "auto",
  "allow_extreme_speed": false
}
```

`max_speed` is the configured cap. Preserve mode clamps it to at most 1.25×;
  the off-mode cap is 1.8× unless extreme speed is enabled.

## Backends

| Engine | Backend | Notes |
|---|---|---|
| `ffmpeg` | FFmpeg `atempo` | WSOLA-family, always available, fast |
| `signalsmith` | Signalsmith Stretch via `python-stretch` | MIT; best for 0.75–1.5× |
| `auto` | Signalsmith when installed, else FFmpeg | Transparent fallback |

Install the optional backend:

```bash
.venv/bin/python -m pip install -r requirements-optional.txt
```

FFmpeg `atempo` remains the default fallback. `auto` selects Signalsmith when
the binding imports successfully, otherwise FFmpeg.

## Provider consistency

Every TTS provider synthesises at rate 1.0 and pitch 0:

- MiniMax: `speed = 1.0`, `pitch = 0`
- Kokoro: `--speed 1.000`
- ElevenLabs / OpenRouter HeyGen, Fish, Gemini: no provider rate
- Apple `say`: normal WPM

This removes provider-side pitch/timbre changes and double speed-ups.

## Rewrite legroom

Rewrite context uses the full scene transcript, with a larger context cap
(`VIBECUT_REWRITE_CONTEXT_CHARS`, default 10000). Timing still uses the actual
cut slot. A long scene therefore gives the rewrite more source material; a
short scene still shortens the line rather than pushing speed past 1.25×;
  the final mix trims if a line still overflows.

## Where the setting appears

- **Classic → Setup → Voice fit**
- **Voice Room → Advanced voice fit**
- The shared `voice_fit` settings key is available to Studio when it consumes
  the same module.

## Tests

```bash
.venv/bin/python -m pytest -q tests/test_voice_fit.py tests/test_mix.py tests/test_tts.py
```

The tests cover FFmpeg and Signalsmith pitch preservation, intentional
chipmunk mode, the 1.25× cap, settings normalisation and the Setup/Voice Room
control presence.
