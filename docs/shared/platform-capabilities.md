# Platform capabilities

VibeCut is not a “local only” product. Local AI is a capability of the machine,
not a promise of the brand.

## Capability matrix

| Capability | macOS Apple Silicon | macOS Intel | Windows / Linux |
|---|---|---|---|
| STT / transcript | Native on-device where available | Native where available; cloud otherwise | Cloud |
| TTS / voice | Native on-device where available | Native where available; cloud otherwise | Cloud |
| Vision / text scan | Native on-device | Native where available; cloud otherwise | Native where available; cloud otherwise |
| Translation / rewrite | Native or cloud route | Native or cloud route | Cloud route |
| Render / ffmpeg | Local | Local | Local |
| File storage | Local | Local | Local |

“Local only” is a mode that can be offered on a Mac with the required native
engines. It is not the default claim for Intel Macs, Windows or Linux.

## UI labels

Use capability-aware labels, not a universal “Local by default”:

- **On-device AI** — every active AI capability is native.
- **Cloud AI** — every active AI capability uses a cloud route.
- **Mixed AI** — some capabilities are native and some are cloud.

The label must have a tooltip or nearby detail that names the capabilities.
Do not say “local” when a cloud route can run.

## Setup

Setup shows one row per capability:

```text
STT / transcript   Native · Whisper on this Mac
TTS / voice        Cloud · ElevenLabs
Vision / text      Native · Apple Vision
Translation        Cloud · OpenCode Go
```

A missing native engine is not an error; it falls back to a configured cloud
route, or shows “not configured” with the Setup action.

## Copy rules

- Prefer “on this Mac” over “local” when the capability is Apple-only.
- Prefer “cloud” over “online” when naming a provider route.
- Do not promise “no cloud” on a platform that uses cloud AI.
- Do not promise “local only” in the hero, footer, pill or founder script
  unless the build is running in that mode.

## Tests

Add a capability snapshot to the server health/settings payload and test these
profiles:

- Apple Silicon with native STT/TTS/vision.
- Intel Mac with native vision but cloud TTS.
- Windows/Linux with cloud AI and local render.
- No cloud keys configured.
