# Voice Room: cloud first, better than VoiceStudio (2026-11-01)

**Goal:** keep every engine in the cloud for now (HeyGen Voice Turbo through OpenRouter, as today). Match or beat everything VoiceStudio does better, above all its UI and UX. Build from `docs/voice/clean-room-spec.md` only. Never open VoiceStudio's code.

## Why cloud first

- There is nothing to install and nothing to download. It runs the same on any Mac the founder uses.
- Commercial terms come from one provider, not a mix of model licences.
- The cost is the wait (about 15 s per preview) and sending the voice sample out with each line. The UI must make that wait honest and rare: cache, show progress, never repeat a request.

## Where VoiceStudio is better today, and our answer

| VoiceStudio does better | Our cloud answer |
|---|---|
| One calm frame: a left rail, a header with status, one mini-player docked at the bottom | Make the `?ui=new` shell the only UI. It already has the rail and the persistent player. Retire `voiceroom.js` once the founder approves a recording. |
| One Voice screen: script, then voice, then a pinned Create button | Same three parts on one screen: **Script**, then **Voice** (From recording / From video / Saved), then a pinned **Make voiceover** with a seconds counter and Cancel |
| History beside the work, with Star and Load settings | A right-hand **Takes** list for every preview and voiceover, with Star, Load settings, Use in Classic/Studio, Delete |
| Errors that say how to fix them | Rewrite every Voice Room error to cause plus next step (spec item 2) |
| A trimmer with a length guard | Open a trimmer for clips over 15 s, starting on the clip finder's best window |
| A readiness checklist | Setup shows OpenRouter key, clone engine and local Whisper as Ready / Working / Failed, each with one action |
| Lock identity and seed reuse | A cached clone sample per voice plus a saved take setting (line, rate, language) |
| A/B compare as a side drawer | Keep our compare, but as a drawer over the screen, not a separate section |
| Advisory audio check | Local check after each take: silence, quiet, loud, clipping. Advisory only. |
| Dub checkpoints and regenerate only changed lines | Script to voiceover: lines are chunks, only edited lines are regenerated, checkpoint cards ("listen to flagged lines", "ready to export") |
| Re-transcribing its own output | Local Whisper re-transcribes each chunk and flags lines that drift |
| Portable persona and consent | Our voice file: name, language, consent record, licence tag, preview, and the clip only if ticked |

## Where we stay ahead

- **Clone from footage.** The clip finder is our signature. Put it first under Voice: "From a video".
- **The hand-off.** A finished voiceover goes to Classic or Studio as an audio track with SRT. VoiceStudio stops at an audio file.
- **Fewer things.** VoiceStudio has nine workspaces. We keep three: **Voices**, **Voiceover**, **Setup**. Dubbing stays in Studio. Design-a-voice waits until a cloud engine supports it well.

## Cloud-specific UX rules

1. **Never send the same request twice.** Cache by voice, line, rate and language (this works today: a cached preview answered in 36 ms). Show "from cache" in the take row.
2. **Make the wait honest.** Show a seconds counter, the stage ("sending sample", "speaking", "downloading"), and Cancel that really stops the request.
3. **Tell people about cost and privacy before the first send.** A one-time note: "Your voice sample is sent to OpenRouter (HeyGen) with each new line." There is a link to the provider's terms and a Got it button.
4. **Fail safe.** On an auth error, quarantine the key and say so (this already exists). On a timeout, keep the script and the take list. Nothing is lost.
5. **Keep it short.** The reference is the clip finder's best 10–15 s window, not the whole upload, so every request is small.

## Build order (one item = one commit = one ship)

1. **One shell.** Make `?ui=new` the default once the founder approves a recording of it. Move the Compare and Recent panels into it. Delete the old page.
2. **Takes list** beside the work (spec item 1).
3. **Fix-it errors** across the clone, preview and clip-finder paths (spec item 2).
4. **Trimmer with the best window** (spec item 3).
5. **Readiness checklist** in Setup (spec item 4).
6. **Script to voiceover:** chunked by sentence, progress and Cancel, regenerate only changed lines, export WAV/MP3 plus SRT. Reuse the clone store and cancel switches.
7. **Self-check by re-transcribing** plus the advisory audio check (spec items 7–8), shown as flags on the voiceover lines.
8. **Hand-off** to Classic or Studio as an audio track.
9. **Voice file** with consent and licence tag (spec item 6).

Each item ends with a founder recording and a click-by-click script built from it, as for pass 1. Only the founder tests, by hand, with real files.

## Not doing yet

- Local engines (see `docs/voice/local-future.md`).
- Voice design from a sentence, a gallery, stories, audiobooks.
- Watermarking: no cloud provider we use offers it yet. Revisit with the local engine.
