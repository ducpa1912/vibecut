# Voice Room clean-room spec (2026-11-01)

This note lets OpenCode build Voice Room features **without opening VoiceStudio's code**. VoiceStudio (github.com/debpalash/VoiceStudio) is AGPL-3.0. Claude read its source on 2026-11-01 and wrote this note as a description of behaviour, in plain words. It contains no code, file names or structure from VoiceStudio.

## Rules for whoever builds from this note

1. Do not open the VoiceStudio repository, its website source, or any copy of it (including Claude's scratchpad copy). Build only from this note, from VibeCut's own code, and from the original model and library projects.
2. Use our own names, file layout and wording. Where this note quotes a VoiceStudio label, it is there to describe the idea. Write our own label.
3. Two parts of VoiceStudio came from MIT projects: sentence chunking for long text (from **voicebox**) and the sentence splitter (from **Patter**). If we need those, read the MIT originals, credit them in the file header, and keep their licence notice.
4. Before shipping any model, check its licence at the model's own page. Never rely on another app's licence list.
5. One item = one commit = one ship, signed, with `scripts/ship-lane.sh`.

## What VoiceStudio is

A desktop app with a Python back end. It clones voices **locally** from a short reference clip, on engines that run on the user's machine. It does not use ElevenLabs to clone. ElevenLabs only appears as an example plugin that is listed and never called. Its default engine (OmniVoice) is CC-BY-NC, which is non-commercial.

## Their UI and UX, in plain words

### The frame

- **A left icon rail** lists the workspaces: Home, Voice, Dubbing, Stories, Audiobook, Gallery, Transcripts, Files, Model catalogue. Settings is pinned at the bottom. A setting can turn the rail into tabs in the title bar instead. Each workspace has its own accent colour. Only the active item shows its colour, so the frame stays calm.
- **A header** names the workspace with a small kicker above it (for example "Studio" over "Voice Clone"). It shows engine status (Ready, Loading, Idle) and a menu of loaded models with Unload.
- **One mini-player is docked at the bottom** on every page. It shows a waveform drawn from the clip, click-and-drag seek, play/pause, elapsed and total time, a label saying what is playing, and Stop. The page content ends above it, so it never covers a button. Panels that have their own player keep it. Everything else plays through the dock.
- **A footer** carries a log line and a quick engine switch. The switch lists only engines that are ready.

### Home

- A short hero line ("make voices that sound like you"), then large cards for each job: Clone, Design, Dub, Stories, Audiobook, Gallery, Transcripts, Voice changer. Each card has one sentence and Open.
- Below the cards: rows of cloned voices, designed voices and dub projects, plus recent files. An empty row says "Nothing here yet — pick a card above."
- An **A/B compare** entry sits on Home.
- A demo voice is ready on first run, with a one-line hint: press Generate to hear it.

### Voice workspace (the core screen)

One column, three parts, top to bottom:

1. **Script: what should it say.** A big text box ("What should this voice say?"), Paste, a language picker, and an Insert menu of special tags (laughter, pauses).
2. **Voice: who says it.** A three-way switch: **From audio**, **By design**, **Convert**.
   - *From audio:* a drop zone ("Drop audio here — or click"), Record with an input device picker and a live level meter ("Input detected" / "No input detected"), and the hint "Use 5–15 seconds of clean speech." An optional transcript of the clip. Reduce noise and Polish switches. Saved voices to pick from instead.
   - *By design:* a sentence box ("a warm elderly British storyteller, slightly raspy") plus chips for gender, age, pitch, style and accent. Typing the sentence fills the chips. Words it can't map are named back to the user. Conflicting picks are cleared with a one-line reason.
   - *Convert:* drop a clip, pick a target voice, optionally match the source length, then Convert. It shows "What it heard" (the transcript) and the converted take.
3. **Action bar, pinned to the bottom of the column:** Create speech, with a live seconds counter while it works ("Creating speech… 12s"), Stop, and Save as a voice with a name field.

Advanced controls (speed, length, seed, model tuning) sit folded under **Voice controls**, with the advice "usually leave these at defaults, change one at a time." Seed has Keep and New seed, so a good take can be repeated.

**History sits on the right**, next to the work, not in a far sidebar. It has an All / Clone / Design filter. Each row shows a small waveform, which loads only when the row scrolls into view. Each row has Star (keep this take; unstarred ones may be cleaned up), Load settings (restore the exact script, voice and seed), Save as voice, Export and Delete.

### Reference trimmer

Opens when a reference clip is too long. It shows a waveform with start and end handles, zoom (scroll), pan (shift+scroll), Fit all and Fit selection. A live length readout says "ok", "too short" or "too long". It has loop preview, and the keys Space to play, Enter to confirm and Esc to cancel.

### Voice page (one voice)

- A header with the name and a Verified badge.
- A **Try it** box with a calm default sentence.
- **Voice ownership:** the user records themself reading a fixed consent sentence. That marks the voice as their own. Revoke deletes the recording. Local use never needs it. Sharing and automation do.
- **Lock voice identity:** freezes the reference and seed, so every later take sounds the same. Unlocking warns that later audio will differ.
- **Export persona:** a portable voice file. By default it carries only a watermarked preview, not the raw clip. A switch includes the clip.
- Where the voice is used (dub projects).

### Gallery

Ready-made designed voices with filters (accent, age, style), Favorites, Preview and **Use voice**. A **My imports** zone: paste a URL or upload a file you have rights to, trim the part you need, and save it as a voice. A Community zone holds shared presets.

### A/B compare

A drawer that leaves the app usable behind it. It has one test phrase, Voice A and Voice B, then Compare, with progress per side ("Generating Voice A…").

### Dubbing

A pipeline stepper: transcribe, then translate, then generate. A **checkpoint card** at each stage tells the user what to check next: fix speech-recognition errors now, skim translations (over-long lines get sped up), then review timing. Each line row shows timing and a sync ratio. "Regenerate changed" redoes only the edited lines. A casting board gives each speaker a voice.

### Small things that make it feel good

- **Errors say how to fix them.** "No speech could be heard in the reference audio — record closer to the microphone, check the input level moves…", or "Audio is 40 s — trim to ≤ 15 s for best cloning."
- **First-run readiness checklist:** speech model, voice model and optional LLM, each with Loaded / Loading (may take 1–2 minutes on first run) / Failed plus what to do.
- **The audio check is advisory only.** It flags silence, too quiet, too loud and clipping. It says pauses can be intentional. It never changes the audio.
- **Plain choices:** "Standard / For editing / Original" stand in for 16/24/32-bit. Each has a size hint.
- Every long job has Cancel. A second job is refused with a clear sentence while one is running.

## What Voice Room has that VoiceStudio does not

Keep these. They are our edge:

- **Clone from footage:** the clean-clip finder removes music, denoises, finds speech and offers up to 5 candidates to listen to.
- **One page, plainly worded,** with honest Play/Stop states and Cancel everywhere.
- **Consent records per clone** and a ZIP backup that restores without duplicates.
- **Built into VibeCut:** the voice goes straight to Classic or Studio for captions and export.

## Behaviour specs to build (ours, written fresh)

Each is a separate item. The acceptance lines are what the founder checks by hand.

1. **History beside the work.** Every preview and every voiceover lands in a right-hand list with Star, Load settings, Save as voice and Delete. Unstarred items older than 30 days may be cleaned up, after a warning.
   *Accept:* make three previews, star one, reload, and the starred one is still first.
2. **Fix-it errors.** Every failure message names the cause and the next step, in one or two sentences, with no stack traces.
   *Accept:* upload a silent clip and read a message that says to record closer and check the level.
3. **Reference length guard and trimmer.** A clip over 15 s opens a trimmer. It offers our clip finder's best window as the starting selection.
   *Accept:* upload a 60 s clip and the trimmer opens on a clean 10–15 s window.
4. **Readiness checklist** in Setup: OpenRouter key, clone engine, local Whisper. Each shows Ready / Working / Failed plus one action.
5. **Lock identity and Keep take:** pin a voice's reference and the settings of a good take, so the next voiceover sounds the same.
6. **Portable voice file:** our own format, holding name, language, consent record, licence tag and a short preview. The raw clip is included only when the user ticks it.
7. **Advisory audio check** after each generation: silence, too quiet, too loud, clipping. Advisory only.
8. **Self-check by re-transcribing:** after a voiceover, local Whisper transcribes our output and flags lines whose words drift from the script.
