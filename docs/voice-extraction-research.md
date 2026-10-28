# Clean voice extraction for voice cloning

Research date: 2026-10-28. Every source was read on that date. Vendor pages
change, so re-check licences and limits before a release build.

Scope: take any video or audio file, find the 3–5 best one-minute speech
batches, clean them, and let the user pick the reference clip for a cloning
TTS. Cloning itself is out of scope. The app is commercial, so GPL/AGPL and
non-commercial weights are flagged.

## Recommendation

```
decode (mono 48 kHz PCM)
  -> separation: Mel-Band RoFormer, else htdemucs_ft, else htdemucs
  -> denoise: DeepFilterNet 3 and/or ffmpeg afftdn (compare mode)
  -> Silero VAD, else energy RMS
  -> optional pyannote speaker filter + overlap warning
  -> score sliding 60 s windows, keep 3–5 non-overlapping batches
  -> splice speech inside each window, 15 ms joins
  -> linear gain to -16 LUFS / -1.5 dBTP
  -> 44.1 kHz mono PCM16 WAV per candidate
```

Code: `voice_extract.py`. `find_voice_candidates()` is the product entry
point; `extract_clean_voice()` remains for callers that want one clip.
`audio.separate_voice()` sits next to `separate_vocals()` and shares the
Demucs command, MPS fallback and cache.

Only ffmpeg is mandatory. Demucs, Mel-Band RoFormer, DeepFilterNet, Silero
and pyannote are optional and degrade with a plain message in the report.

Why this order:

- Separation comes first because the denoiser is trained on speech plus noise,
  and music confuses it.
- VAD runs after denoise so quiet consonants are not cut as silence.
- The speaker filter runs on the cleaned, separated signal, where diarization
  is more reliable.
- Windows are scored before export, so a 10-minute video only pays for the
  candidates the user sees.
- Gain is applied last, as a linear gain. ffmpeg `loudnorm`'s dynamic mode
  changes the gain envelope and is wrong for a reference clip.

## What is a "pretrained weight"?

Demucs, Mel-Band RoFormer and DeepFilterNet are neural networks. The code in
their repositories says how the network is built and run. The *weights* are
the learned parameter file — the actual AI model, usually 2 MB to 1 GB. A
repository can license its code under MIT while the weights carry different
terms, because the weights were trained on a dataset with its own licence.

That distinction is the whole Demucs caveat: the code is MIT, the weight file
is not clearly MIT. It is still an AI model; "weights" is just the file that
contains what the model learned.

## Alpha test bundling and licences

The practical split is internal alpha versus commercial release, not
"working" versus "broken".

| Engine | Code licence | Weight licence | Alpha bundle | Commercial bundle |
|---|---|---|---|---|
| Demucs `htdemucs` / `htdemucs_ft` | MIT | Not covered by MIT; author calls them research-oriented because of MUSDB terms (issues #267/#327) | On by default, downloaded on first use | Legal decision: keep with a notice, or switch to Mel-Band RoFormer |
| Mel-Band RoFormer (Kim vocal 2) | MIT architecture (`lucidrains`) | MIT since 2026-04-22 (was GPL-3.0 from 2025-06-17); MLX conversion also MIT | Opt-in via `audio-separator` + model file; **best quality**, default when installed | **Preferred** separation engine; MIT weights |
| DeepFilterNet 3 | MIT / Apache-2.0 | Same permissive terms | On when installed; compare with `afftdn` | Ship it |
| ffmpeg `afftdn` | ffmpeg build (LGPL/GPL flags apply to the binary, not to the app calling it) | none | Always available | Ship it |
| Silero VAD | MIT | MIT | On when installed | Ship it |
| pyannote 3.1 / Community-1 | MIT code; 3.1 pipeline MIT, Community-1 CC-BY-4.0 | Gated Hugging Face download, attribution | Optional; requires HF token | Optional; show attribution |
| MDX-Net / UVR models | `audio-separator` wrapper MIT; UVR GUI has no LICENSE file | **Unresolved.** The UVR issue asking about commercial use (opened 2026-04-14) had no clear answer by September 2026 | Allowed only as a labelled experiment, model downloaded by the tester, never redistributed | Do not ship until the model author gives written permission |
| BS-RoFormer checkpoints | MIT architecture | Varies by checkpoint; many are unclear | Labelled experiment only | Replace with Mel-RoFormer (MIT) |
| Resemble Enhance / VoiceFixer | MIT code | Repo LICENSE is MIT | Optional experiment | Skip: generative restoration changes timbre |
| RNNoise / `arnndn` | BSD-3-Clause | model file separate | Optional | Skip: artefacts, no advantage |

How to bundle the alpha:

1. Download weights on first use. Do not put unresolved weights in the
   installer or repo.
2. Record the engine and model id in every report (`models.separation`,
   `models.denoise`, `denoise_trials`).
3. Keep the alpha engines behind an explicit setting or environment variable
   (`VIBECUT_ROFORMER_MODEL`, pack paths), so a normal install never silently
   picks an unresolved model.
4. Show the licence/attribution in the About or Setup panel for the engines
   that ran.
5. For commercial builds, ship only the permissive column and keep the rest
   as opt-in experiments that the user installs themselves.

"Not clear" therefore means the *weights* have no grant that covers a paid
product. It does not mean the code fails, and it does not mean the model is
weak. It is a distribution decision.

## Candidates, not one fixed clip

The old assumption was one 30 s clip. The product flow is:

1. User drops any video, including a 10-minute interview.
2. The pipeline cleans the whole file once.
3. It scores sliding 60 s windows: speech fraction first, then the gap noise
   floor and residual energy.
4. It keeps 3–5 non-overlapping windows and exports each as a candidate WAV.
5. The user listens and picks the batch with the best voice and least noise.

Same-speaker grouping needs pyannote. `find_voice_candidates()` defaults to
`speaker="auto"`: it keeps the main diarised speaker when pyannote is
installed, and warns when it is not. With `speaker=1` the filter keeps the
main speaker by talk time; any overlapping speech is reported separately
because diarization cannot un-mix it.

Providers still set the useful upper bound. Their limits inform the 60 s
candidate size, not a single mandatory length:

| Provider | Length | Format / level | Notes | Source |
|---|---|---|---|---|
| ElevenLabs Instant | 1–2 min recommended; each file ≥ 5 s | mono, 22 kHz+; MP3 ≥ 128 kbps fine | One speaker, no reverb, no background noise. PVC wants 30–180 min. | ElevenLabs docs + Coval 2026 review |
| HeyGen Instant | 30–60 s; 30 s–3 min for a custom clone | clean single-speaker audio | Consent prompt; quiet room, no echo. | HeyGen product/docs |
| MiniMax | 10–60 s per recording, up to 10 samples | ≤ 20 MB each | Its own noise separation can remove voice detail; send clean audio. | minimax.io voice clone page |
| Fish Audio | ≥ 10 s per clip; 1–2 min better | wav/mp3/m4a/opus | Mono, one speaker. `enhance_audio_quality` denoises again. | docs.fish.audio |
| Kokoro (local) | n/a | n/a | Kokoro is a fixed voicepack TTS, not a cloning model. | Kokoro model card |

## Options compared

Speeds are from secondary benchmarks or vendor hardware notes, not this
machine. Treat them as order-of-magnitude only.

### Music / vocal separation

| Option | Licence | Apple Silicon | Size | Offline | Verdict |
|---|---|---|---|---|---|
| Demucs v4 `htdemucs` / `htdemucs_ft` | Code MIT; weights not MIT-covered (author statement, reported 2026-10-17) | MPS works; the repo tries `-d mps` then CPU. A 7-s clip takes seconds on an M4; a 4-min track is tens of seconds to a couple of minutes | 160 MB / 641 MB | Yes, after download | **Use now.** Best installed path; `htdemucs_ft` is the better Demucs checkpoint |
| Mel-Band RoFormer (Kim vocal 2) | Weights MIT since 2026-04-22; MLX conversion MIT | `mlx-audio >= 0.4.3` supports the architecture (2026-04-27); `audio-separator` runs ONNX/PyTorch | hundreds of MB | Yes | **Default when installed.** Best vocal SDR and a clean commercial licence |
| BS-RoFormer | Code MIT; checkpoint licences vary | PyTorch/MPS is slow for this Transformer | large | Yes | Experiment only: good quality, unclear weights |
| MDX-Net / UVR | Wrapper MIT; UVR GUI has no LICENSE; model terms unresolved (issue #2185) | ONNX Runtime / `onnxruntime-silicon` | ~50–200 MB per model | Yes | Alpha experiment only; no commercial shipping |
| `audio-separator` | MIT wrapper | ONNX Runtime; model-dependent | n/a | Yes | Use as the uniform runner for RoFormer/MDX, not as a licence fix |

Quality references: `htdemucs` ≈ 8.1 dB vocals SDR, `htdemucs_ft` ≈ 8.9 dB,
BS-RoFormer ≈ 9.8 dB average, Mel-RoFormer ≈ 0.5 dB above BS-RoFormer on
vocals (Mel-RoFormer paper). The ranking is why `separation="best"` tries
RoFormer first, then `htdemucs_ft`, then `htdemucs`.

### Denoise / dereverb

| Option | Licence | Apple Silicon | Size | Offline | Verdict |
|---|---|---|---|---|---|
| DeepFilterNet 3 (`deep-filter`) | Dual MIT / Apache-2.0 | Apple Silicon binary; CoreML INT8 port reports RTF 0.12–0.24 on M2 Max | ~2 MB int8 | Yes | **Preferred**, and always A/B tested against `afftdn` in `denoise="compare"` |
| ffmpeg `afftdn` | ffmpeg build | Native, no model | 0 | Yes | **Always-on fallback** and the second leg of the alpha comparison |
| ffmpeg `arnndn` + RNNoise | RNNoise BSD-3-Clause; model file separate | Very fast, 85 KB | tiny | Yes | Skip: musical-noise artefacts |
| Resemble Enhance | Repo LICENSE MIT (read 2026-10-28) | PyTorch 44.1 kHz; enhancer is slow | ~1 GB | Yes | Skip as default: generative timbre drift |
| VoiceFixer | Repo LICENSE MIT (read 2026-10-28) | PyTorch 44.1 kHz vocoder | hundreds of MB | Yes | Skip: built for degraded speech, regenerates timbre |
| WPE (`nara_wpe`) | MIT | CPU/NumPy | small | Yes | Future experiment only; single-channel gains are modest |

`denoise="compare"` runs both DeepFilterNet and `afftdn`, measures SNR, noise
floor and residual on each, picks the better one, and records both trials in
the report. If the two score within 0.5 dB it warns the user to listen. A
forced A/B is one rerun with `denoise="deepfilternet"` or `"afftdn"`.

### Segmentation / diarization

| Option | Licence | Apple Silicon | Size | Offline | Verdict |
|---|---|---|---|---|---|
| Silero VAD v5 | MIT | CPU, sub-millisecond chunks | ~2 MB | Yes, after download | **Preferred** VAD |
| Energy RMS VAD (`audio.speech_spans`) | in-repo | trivial | 0 | Yes | **Always-on fallback** |
| pyannote.audio 3.1 | Code MIT; 3.1 pipeline MIT; Community-1 weights CC-BY-4.0 | CPU reliable; MPS partial | ~1 GB | Yes, but gated Hugging Face access | **Optional** speaker filter + overlap warning |

## What the code reports

`extract_clean_voice()` returns one `clean_voice.wav` plus:

- `duration`, `sample_rate`, `channels`, `gain_db`
- `models`: separation / denoise / VAD / diarization engine, or `null` /
  `skipped`
- `denoise_trials`: both variants when `denoise="compare"`
- `quality`: `snr_db`, `music_noise_residual_db`, `noise_floor_dbfs`,
  `speech_level_dbfs`, `peak_dbfs`, `clipping`, `source_clipping`, `loudness`
- `warnings`: missing engine, low SNR, short clip, clipped source,
  overlapping speech, no speaker filter

`find_voice_candidates()` returns `candidates[]`. Each has `path`, `duration`,
`speech_fraction`, `score`, `window`, `quality` and warnings. The top-level
report also carries `denoise_trials` and pipeline warnings.

SNR and residual are measured on the pre-splice clip, because the export has
no natural gaps left. Clipping and loudness are measured on the file the
caller receives. Files are streamed; a two-hour source is never loaded whole.

Cache: `data/cache/voice_refs/<fingerprint>/`, with `clean.wav` or
`candidate-NN.wav` plus `report.json`. The fingerprint covers path, size,
mtime, both file ends, every pipeline parameter and which engines were
installed, so installing DeepFilterNet later does not reuse an older result.

## What is still open

- **UI.** No route or panel in this checkout. Build it separately from the
  existing voice-room in main: a candidate picker with waveform, play buttons,
  score badges and a "use this voice" confirm. Reuse the job queue and cancel
  event. Do not change the current voice-room flow.
- **Pack.** `deep-filter` is looked up through `packs.find_command("voice",
  "deep-filter")`. The pack already exists on main, so no manifest change was
  made here.
- **Demucs weight licence.** Use the best engine when installed, but decide
  before a commercial build whether the installer ships Demucs weights or
  downloads them. Mel-Band RoFormer is the MIT-weight alternative.
- **Real acceptance.** `tests/test_voice_extract_acceptance.py` builds a 90 s
  fixture with two `say` voices, music, noise and echo. Run it with
  `VIBECUT_VOICE_ACCEPTANCE=1`; add `VIBECUT_VOICE_ACCEPTANCE_SEPARATE=1` for
  a real Demucs pass. It is opt-in because it is slow, not because it is fake.
- **Crosstalk inside a kept turn.** Diarization reports overlapping turns,
  but cannot remove a voice that talks at the same time as the chosen one.
  The current answer is a warning plus candidate rejection by the user.
- **Clone-quality scoring.** The score is acoustic (speech coverage, noise
  floor). It does not yet measure speaker consistency; that needs embeddings
  from the diarizer or a small verification model.

## Sources

Read 2026-10-28 unless a date is part of the claim.

- Demucs repo and MIT code licence: https://github.com/facebookresearch/demucs
- Demucs weight licence caveat (issues #267, #327; correction dated 2026-10-17): https://tomodahinata.com/en/blog/demucs-v4-music-source-separation-production-guide
- Demucs model sizes and MLX conversions: https://huggingface.co/mlx-community/demucs-mlx
- Demucs host speed table: https://stemsplit.io/blog/demucs-local-setup-guide
- HTDemucs variant benchmark on M4 MPS (run 2026-03-14): https://stemsplitter.github.io/research/model-comparison
- htdemucs vs BS-RoFormer vs Spleeter SDR table (2026): https://aistemsplitter.org/blog/htdemucs-vs-bs-roformer-vs-spleeter-2026-benchmark
- Mel-Band RoFormer paper: https://arxiv.org/html/2409.04702v1
- Mel-RoFormer Kim vocal 2 licence history and MLX support: https://huggingface.co/mlx-community/mel-roformer-kim-vocal-2-mlx
- BS-RoFormer code (MIT): https://github.com/lucidrains/BS-RoFormer
- UVR commercial-use licence question (opened 2026-04-14): https://github.com/Anjok07/ultimatevocalremovergui/issues/2185
- `audio-separator` (MIT wrapper): https://github.com/streichgeorg/python-audio-separator
- DeepFilterNet repo (MIT/Apache-2.0): https://github.com/rikorose/deepfilternet
- DeepFilterNet 3 CoreML INT8 size and M2 Max RTF: https://huggingface.co/aufklarer/DeepFilterNet3-CoreML
- RNNoise vs DeepFilterNet comparison: https://noisereducerai.com/blogs/deepfilternet-vs-rnnoise
- Resemble Enhance repo and MIT LICENSE: https://github.com/resemble-ai/resemble-enhance
- VoiceFixer repo and MIT LICENSE: https://github.com/haoheliu/voicefixer
- Silero VAD licence and model size: https://www.cekura.ai/blogs/what-is-silero-vad
- Silero VAD benchmark/size summary: https://www.codesota.com/browse/audio/voice-activity-detection
- pyannote 3.1 licence and gating: https://huggingface.co/pyannote/speaker-diarization-3.1
- pyannote Community-1 licence: https://www.pyannote.ai/blog/top-7-speaker-diarization-apis-and-models-in-2026
- ElevenLabs cloning docs: https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning
- ElevenLabs instant cloning docs: https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning/instant-voice-cloning
- ElevenLabs length and sample guidance (2026 review): https://www.coval.ai/blog/elevenlabs-review-2026-voice-cloning-and-synthesis-capabilities-explained
- HeyGen Voice specs: https://www.heygen.com/models/heygen-voice-1
- HeyGen cloning guide (30–60 s): https://www.heygen.com/tool/ai-voice-cloning
- MiniMax voice clone page (10–60 s, 20 MB, noise caveat): https://www.minimax.io/audio/voices-cloning
- Fish Audio cloning docs: https://docs.fish.audio/features/voice-cloning
- Kokoro model card: https://huggingface.co/hexgrad/Kokoro-82M
