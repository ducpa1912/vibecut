# Voice Room future: local cloning on Apple Silicon, then any machine (2026-11-01)

**Vision:** the same Voice Room screen, with a switch that says where the voice is made: **This Mac** or **Cloud**. On This Mac, the sample never leaves the machine, the wait is short, and nothing is paid per line. Later the same engine runs on Windows and Linux PCs (NVIDIA or CPU).

## Must-haves for any local engine

1. **A commercial licence on both code and weights,** checked on the model's own page. Non-commercial weights are out (for example OmniVoice CC-BY-NC, Higgs Audio, Voxtral, F5-TTS weights, XTTS-v2, Fish Speech).
2. **Vietnamese and English,** because the founder's own clones are `Andy-VN` and `Andy-EN`.
3. **Zero-shot cloning from 5–15 s,** so our clip finder's best window is enough.
4. **Runs on Apple Silicon** (MLX or PyTorch MPS) without a cloud GPU.

## Candidates (checked on the web 2026-11-01; confirm each licence before use)

| Engine | Why | Watch out |
|---|---|---|
| **VoxCPM2** (OpenBMB) | 2B, 30 languages **including Vietnamese**, zero-shot and style-controlled cloning, 48 kHz. Reported Apache-2.0. A community Swift + MLX Mac app already runs it on Apple Silicon, so it is feasible. | 2B is heavy: plan for a Mac with 16 GB+ memory (estimate). Confirm the weights licence on the Hugging Face card. **Lead candidate.** |
| **Chatterbox Multilingual V3** (Resemble AI) | MIT, 0.5B, 23 languages, embedded watermark, small Nano/Turbo variants for English | No Vietnamese. Good as an English-only fast path. |
| **Qwen3-TTS** (Alibaba) | Apache-2.0, clones from about 3 s, voice direction in plain words | About 10 languages. Check for Vietnamese before considering it. |
| **CosyVoice 3** | Apache-2.0, strong multilingual cloning | Check its language list for Vietnamese. VoxCPM2's report scores better on in-the-wild cloning. |
| **Kokoro** | Apache-2.0, tiny and fast | Stock voices only, no cloning. Fine for stock previews offline. |

**Runtime on Mac:** **mlx-audio** (MIT) runs many of these on M-series Macs and also does speech-to-text, enhancement and separation. Try it first. Use PyTorch with MPS when a model has no MLX port.

## How it fits Voice Room (our design, nothing taken from VoiceStudio)

- **One engine interface** in our server, with three calls: `prepare_voice` (encode the reference once and cache the result next to the clone), `speak` (line, voice, rate, language), and `cancel`. HeyGen-in-the-cloud becomes one implementation, the local engine another.
- **A separate worker process** for the local model. Cancel kills it for real, and a crash never takes the web server down.
- **Honest routing.** The UI says where each take was made. There is no silent fallback to the cloud: if the local engine fails, the user is asked before anything is sent.
- **A model manager in Setup:** size, licence, languages, Download, Delete, and free space shown before downloading.
- **The same cache, takes list and self-check** as the cloud plan, so switching engines changes nothing else.
- **Watermark** generated speech when the engine offers it (Chatterbox ships one). Check the licence of any watermark library at its own source first.

## Stages

1. **Spike (no UI).** On the founder's Mac, run VoxCPM2 through mlx-audio or PyTorch MPS on the founder's own reference clips. Measure seconds per 10 s line, memory, and how close it sounds to the HeyGen clone. The founder supplies the clips and judges the result by ear. We never generate test audio.
2. **Local engine behind a flag** (`VIBECUT_FEATURES=voice_local`): the engine interface, the worker process, the model manager, and the This Mac / Cloud switch.
3. **Local by default on Apple Silicon,** if the founder prefers it after a recorded pass. Cloud stays one click away.
4. **Any machine:** the same worker on Windows/Linux with NVIDIA (CUDA) or CPU. Pick the runtime per platform: PyTorch first, then ONNX or GGUF if a port exists. Package the worker so the user installs nothing by hand.

## Open questions for the founder

- Which Mac and how much memory will run this? That decides between a 2B model and a smaller one.
- Is Vietnamese a must for the local engine on day one, or can English come first (Chatterbox)?
- Do we accept a model download of several GB on first use?
