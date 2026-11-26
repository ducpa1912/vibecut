"""Local voice-over with the macOS `say` voices.

No cloud key, no downloaded model. Captions are the script: each cue is spoken,
fitted into its cue window, and assembled into one WAV on the edit timeline.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import shutil
import subprocess
from tempfile import TemporaryDirectory
import wave
from pathlib import Path

from duckcore import media

VOICE_RE = re.compile(r"^(?P<name>.+?)\s{2,}(?P<locale>[a-z]{2}_[A-Z]{2})\s*(?:#\s*(?P<sample>.*))?$")
SAMPLE_RATE = 22050
SAMPLE_WIDTH = 2
CHANNELS = 1


NOVELTY_VOICES = {
    "Bad News", "Bahh", "Bells", "Boing", "Bubbles", "Cellos", "Good News",
    "Jester", "Organ", "Superstar", "Trinoids", "Whisper", "Wobble", "Zarvox",
}


DEFAULT_VOICE = "macOS default"


def _resolve_voice(name):
    if name.lower() in {"kokoro", "tts-kokoro", "kokoro-onnx"} or name.lower().startswith("kokoro:"):
        return DEFAULT_VOICE, {"message": "The saved voice pack was retired. Using the default macOS voice."}
    return name, {}


def list_voices(data_root: Path | None = None) -> list[dict[str, str]]:
    try:
        result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        result = subprocess.CompletedProcess([], 0, stdout='')
    voices = []
    for line in result.stdout.splitlines():
        match = VOICE_RE.match(line.strip())
        if not match:
            continue
        name = match.group("name").strip()
        if name in NOVELTY_VOICES:
            continue
        voices.append({
            "name": name,
            "locale": match.group("locale"),
            "sample": (match.group("sample") or "").strip(),
        })
    voices.sort(key=lambda item: (not item["locale"].startswith("en_US"), item["locale"], item["name"]))
    if data_root:
        from duckcore import model_slots
        folder = model_slots.selected(data_root, 'voice')
        if folder and (Path(folder) / model_slots.VOICE_FRONTEND).is_file():
            import numpy as np
            with np.load(Path(folder) / 'voices-v1.0.bin', allow_pickle=False) as archive:
                voices += [{'name': 'user:' + name, 'locale': '', 'sample': 'Your voice · ' + name,
                            'label': 'Your voice · ' + name} for name in archive.files]
    return voices


def _which_say() -> str:
    found = shutil.which("say")
    if not found:
        raise RuntimeError("Apple `say` is not available.")
    return found


def _duration(path: Path) -> float:
    result = subprocess.run(
        [media.ffprobe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


from duckcore.providers import local_step


@local_step('voice.user', ('kokoro-v1.0.onnx', 'voices-v1.0.bin', 'tokenizer.onnx'))
def _synthesize_user(text, name, output, data_root):
    import numpy as np
    import onnxruntime as ort
    import soundfile as sf
    from duckcore import model_slots

    selected = model_slots.selected(data_root, "voice") if data_root else ""
    if not selected:
        raise ValueError("Choose your voice model again.")
    folder = Path(selected)
    tokenizer = folder / model_slots.VOICE_FRONTEND
    if not tokenizer.is_file():
        raise ValueError(model_slots.VOICE_FRONTEND_MESSAGE)
    # The folder supplies the language-specific text frontend as model data.
    # Its first output contains unpadded phoneme IDs in the voice graph's vocabulary.
    frontend = ort.InferenceSession(str(tokenizer), providers=["CPUExecutionProvider"])
    inputs = frontend.get_inputs()
    if len(inputs) != 1 or inputs[0].type != "tensor(string)":
        raise ValueError("The voice tokenizer must accept one text input.")
    raw = frontend.run(None, {inputs[0].name: np.array([text], dtype=object)})[0]
    ids = np.asarray(raw)
    if ids.ndim == 2 and ids.shape[0] == 1:
        ids = ids[0]
    if ids.ndim != 1 or ids.dtype.kind not in "iu" or not ids.size or (ids <= 0).any():
        raise ValueError("The voice tokenizer returned invalid phoneme IDs.")
    model = ort.InferenceSession(str(folder / "kokoro-v1.0.onnx"), providers=["CPUExecutionProvider"])
    inputs = {arg.name: arg.type for arg in model.get_inputs()}
    tokens_key = "input_ids" if "input_ids" in inputs else "tokens"
    types = {"tensor(int64)": np.int64, "tensor(int32)": np.int32, "tensor(float)": np.float32}
    with np.load(folder / "voices-v1.0.bin", allow_pickle=False) as voices:
        if name not in voices:
            raise ValueError("Choose a voice in your current model folder.")
        styles = voices[name]
    audio = []
    for offset in range(0, len(ids), 510):
        chunk = ids[offset:offset + 510]
        feed = {
            tokens_key: np.asarray([[0, *chunk, 0]], dtype=types[inputs[tokens_key]]),
            "style": styles[min(len(chunk), len(styles)) - 1].reshape(1, -1).astype(np.float32),
            "speed": np.ones(1, dtype=types[inputs["speed"]]),
        }
        audio.append(model.run(None, feed)[0].ravel())
    sf.write(str(output), np.concatenate(audio), 24000)


@local_step('voice')
def _synthesize(text: str, voice: str, aiff: Path, data_root: Path | None = None) -> None:
    if voice.startswith('user:'):
        _synthesize_user(text, voice.split(':', 1)[1], aiff, data_root)
        return
    voice, _ = _resolve_voice(voice)
    options = [] if voice == DEFAULT_VOICE else ["-v", voice]
    result = subprocess.run(
        [_which_say(), *options, "-o", str(aiff), "--", text],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not aiff.is_file():
        raise RuntimeError(f"Apple voice failed: {(result.stderr or '').strip()[:200]}")


def _to_wave(source: Path, target: Path) -> None:
    result = subprocess.run(
        [
            media.ffmpeg(), "-y", "-v", "error", "-i", str(source),
            "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-sample_fmt", "s16",
            "-f", "wav", str(target),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"Could not prepare voice audio: {result.stderr[-300:]}")


def _fit(source: Path, target: Path, duration: float) -> None:
    duration = max(0.05, float(duration))
    source_duration = _duration(source)
    tempo = 1.0
    if source_duration > duration:
        tempo = min(2.0, max(0.5, source_duration / duration))
    result = subprocess.run(
        [
            media.ffmpeg(), "-y", "-v", "error", "-i", str(source),
            "-af", f"atempo={tempo:.5f},apad=whole_dur={duration:.5f},atrim=0:{duration:.5f}",
            "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-sample_fmt", "s16",
            "-f", "wav", str(target),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(f"Could not fit voice cue: {result.stderr[-300:]}")


def _silence(frames: int) -> bytes:
    return b"\x00" * max(0, frames) * SAMPLE_WIDTH * CHANNELS


def build_track(
    cues: list[dict],
    *,
    voice_name: str,
    mode: str,
    project_id: str,
    data_root: Path,
    total_duration: float | None = None,
) -> dict:
    cues = [cue for cue in cues or [] if str(cue.get("text") or "").strip()]
    if not cues:
        raise ValueError("Generate captions first; they are the script.")
    if not voice_name:
        raise ValueError("Choose a local voice.")
    from duckcore import model_slots
    voice_name, notice = _resolve_voice(voice_name)
    identity = model_slots.selected(data_root, 'voice') if voice_name.startswith('user:') else ''
    mode = "voice_only" if mode == "voice_only" else "voice_over"
    job_dir = Path(data_root) / "projects" / project_id / "voice"
    job_dir.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha1(
        f"{voice_name}{identity}|{mode}|{[(c.get('start'), c.get('end'), c.get('text')) for c in cues]}".encode()
    ).hexdigest()[:12]
    output = job_dir / f"voice_{token}.wav"
    if not output.is_file():
        with TemporaryDirectory(dir=job_dir) as work:
            temp = Path(work)
            with wave.open(str(temp / "track.wav"), "wb") as writer:
                writer.setnchannels(CHANNELS)
                writer.setsampwidth(SAMPLE_WIDTH)
                writer.setframerate(SAMPLE_RATE)
                cursor = 0
                for index, cue in enumerate(sorted(cues, key=lambda item: float(item.get("start") or 0.0))):
                    start = max(0.0, float(cue.get("start") or 0.0))
                    end = max(start + 0.05, float(cue.get("end") or 0.0))
                    start_frame = int(round(start * SAMPLE_RATE))
                    if start_frame > cursor:
                        writer.writeframes(_silence(start_frame - cursor))
                        cursor = start_frame
                    aiff = temp / f".cue_{index}.aiff"
                    wav = temp / f".cue_{index}.wav"
                    fitted = temp / f".cue_{index}.fit.wav"
                    if str(voice_name).startswith('user:'):
                        _synthesize(str(cue.get('text') or ''), voice_name, aiff, data_root)
                    else:
                        _synthesize(str(cue.get("text") or ""), voice_name, aiff)
                    _to_wave(aiff, wav)
                    _fit(wav, fitted, end - start)
                    with wave.open(str(fitted), "rb") as reader:
                        frames = reader.readframes(reader.getnframes())
                    writer.writeframes(frames)
                    cursor += len(frames) // (SAMPLE_WIDTH * CHANNELS)
                    for path in (aiff, wav, fitted):
                        path.unlink(missing_ok=True)
                total = int(round(float(total_duration or 0.0) * SAMPLE_RATE))
                if total > cursor:
                    writer.writeframes(_silence(total - cursor))
            (temp / "track.wav").replace(output)
    return {
        **notice,
        "engine": "user-onnx" if voice_name.startswith("user:") else "say",
        "voice": voice_name,
        "mode": mode,
        "audio": str(output.relative_to(Path(data_root) / "projects" / project_id)),
        "duration": _duration(output),
    }


def build_voice(
    edit: dict,
    reference: dict,
    data_root: Path,
    *,
    voice: str,
    mode: str = "voice_over",
) -> dict:
    track = build_track(
        [cue for cue in (reference or {}).get("cues") or [] if isinstance(cue, dict)],
        voice_name=voice,
        mode=mode,
        project_id=str(edit["project_id"]),
        data_root=data_root,
        total_duration=float(edit.get("end") or 0.0),
    )
    track["duration"] = _duration(Path(data_root) / "projects" / str(edit["project_id"]) / track["audio"])
    track["id"] = f"at_{secrets.token_hex(5)}"
    track["kind"] = "voice"
    track["name"] = track.get("voice") or "Voice-over"
    track["start"] = 0.0
    track["volume"] = 1.0
    from duckcore import edits
    edits.ensure_audio_tracks(edit)
    edit["audio_tracks"].append(track)
    edit["voice"] = track
    edits.save_edit(edit, data_root)
    return track


def preview_line(text: str, voice_name: str, project_id: str, data_root: Path) -> dict:
    text = str(text or "").strip()
    if not text:
        raise ValueError("Choose a line to preview.")
    if not voice_name:
        raise ValueError("Choose a local voice.")
    job_dir = Path(data_root) / "projects" / project_id / "voice" / "previews"
    job_dir.mkdir(parents=True, exist_ok=True)
    from duckcore import model_slots
    voice_name, notice = _resolve_voice(voice_name)
    identity = model_slots.selected(data_root, 'voice') if str(voice_name).startswith('user:') else ''
    token = hashlib.sha1(f"{voice_name}|{identity}|{text}".encode()).hexdigest()[:16]
    output = job_dir / f"{token}.wav"
    if not output.is_file():
        aiff = job_dir / f".{token}.aiff"
        if str(voice_name).startswith('user:'):
            _synthesize(text, voice_name, aiff, data_root)
        else:
            _synthesize(text, voice_name, aiff)
        _to_wave(aiff, output)
        aiff.unlink(missing_ok=True)
    return {**notice, "audio": str(output.relative_to(Path(data_root) / "projects" / project_id)), "duration": _duration(output)}
