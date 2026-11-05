"""VibeCut analysis pipeline: probe, cut, read, score, plan."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import time
import urllib.request
import wave
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageFilter

import settings_store
import stt
import usage_store
import vision
import workflow_config
from vision import probe_image, probe_images

ROOT = Path(__file__).resolve().parent
TARGET_AR = 9 / 16
ASPECT_RATIOS = {"9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1.0, "16:9": 16 / 9}


def _pipeline_log(
    workflow: str,
    route_index: int,
    provider: str,
    model: str,
    started: float,
    ok: bool,
    error: str = "",
    *,
    job_id: str = "",
    request_id: str = "",
    reasoning: str = "",
) -> None:
    try:
        from admin import store  # noqa: PLC0415
        store.record_pipeline_event(
            workflow,
            provider,
            model,
            route_index=route_index,
            job_id=job_id,
            request_id=request_id or job_id,
            reasoning=reasoning,
            status="ok" if ok else "failed",
            latency_ms=(time.time() - started) * 1000,
            fallback=route_index > 0,
            error=error,
        )
    except Exception:  # noqa: BLE001
        pass


class PipelineError(RuntimeError):
    pass


def _which(name: str) -> str | None:
    return shutil.which(name)


def _ffmpeg() -> str:
    path = _which("ffmpeg")
    if not path:
        raise PipelineError("ffmpeg is not installed or not on PATH.")
    return path


def _ffprobe() -> str:
    path = _which("ffprobe")
    if not path:
        raise PipelineError("ffprobe is not installed or not on PATH.")
    return path


def _run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess:
    # Without a bound Cancel event this stays the plain call that the rest of
    # the app and its tests expect.  During a read the event is bound, so every
    # ffmpeg child runs in its own process group and can be stopped mid-file.
    if not stt.has_cancel_event():
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    else:
        _check_cancel()
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        deadline = None if timeout is None else time.monotonic() + float(timeout)
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    if cancel_requested():
                        _stop_process(process)
                        try:
                            process.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        raise stt.SttCancelled("Analysis cancelled.") from None
                    if deadline is not None and time.monotonic() >= deadline:
                        _stop_process(process)
                        try:
                            process.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        raise subprocess.TimeoutExpired(cmd, timeout) from None
        finally:
            if process.poll() is None:
                _stop_process(process)
        result = subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-1600:]
        raise PipelineError(f"command failed: {Path(cmd[0]).name}\n{tail}")
    return result


def _ratio(value: str | None) -> float:
    if not value or value in ("0/0", "N/A"):
        return 0.0
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            return float(num) / float(den) if float(den) else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _rank(values: list[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if len(array) == 0:
        return array
    if len(array) == 1 or float(np.ptp(array)) < 1e-9:
        return np.full(len(array), 0.5)
    order = array.argsort().argsort()
    return order / (len(array) - 1)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _short_span(seconds: float) -> str:
    """A compact, non-zero duration for a progress line."""
    value = max(1, int(round(float(seconds or 0.0))))
    if value < 60:
        return f"{value} s"
    minutes, rest = divmod(value, 60)
    if minutes < 60:
        return f"{minutes} min {rest} s" if rest else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


class ProgressTracker:
    """Stage-weighted, monotonic progress with a measured ETA.

    ``analyze_source`` used to expose each stage's own 0..1 fraction.  Crop
    then owned only two percent while it ran for half the read.  This tracker
    maps every stage into a fixed band, never moves backwards, and adds a
    time-based heartbeat inside a stage so a stalled sub-process still shows
    that work continues.
    """

    STAGES = (
        ("scanning", 0.01, 0.20),
        ("audio", 0.20, 0.28),
        ("thumbs", 0.28, 0.46),
        ("vision", 0.46, 0.58),
        ("crop", 0.58, 0.82),
        ("speech", 0.82, 0.95),
        ("scoring", 0.95, 0.995),
    )
    # Rough time constants for the heartbeat inside a stage.  They are not an
    # ETA; they only make the bar move while a child process reports nothing.
    STAGE_TAU = {
        "scanning": 8.0,
        "audio": 3.0,
        "thumbs": 6.0,
        "vision": 5.0,
        "crop": 10.0,
        "speech": 8.0,
        "scoring": 2.0,
    }

    def __init__(
        self,
        progress: Callable[[str, float, str], None] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._progress = progress
        self._clock = clock or time.monotonic
        self._bands = {name: (start, end) for name, start, end in self.STAGES}
        self._stage = ""
        self._stage_started = self._clock()
        self._value = 0.0
        self._started = self._clock()
        self._samples: list[tuple[float, float]] = []
        self._last_sub = 0.0
        self._last_sub_at = self._clock()
        self._eta: float | None = None

    def _now(self) -> float:
        return self._clock()

    @property
    def value(self) -> float:
        return self._value

    def elapsed(self) -> float:
        return max(0.0, self._now() - self._started)

    def emit(self, stage: str, fraction: float, message: str) -> None:
        if stage != self._stage:
            self._stage = stage
            self._stage_started = self._now()
            self._last_sub = 0.0
            self._last_sub_at = self._now()
        band = self._bands.get(stage)
        if band is None:
            return
        sub = _clamp(float(fraction or 0.0))
        if sub > self._last_sub + 0.001:
            self._last_sub = sub
            self._last_sub_at = self._now()
        else:
            # A sub-process can sit on one frame for a long time.  Only then
            # let elapsed time move the band; real frame progress wins.
            elapsed = max(0.0, self._now() - self._last_sub_at)
            tau = max(0.5, self.STAGE_TAU.get(stage, 6.0))
            heartbeat = 0.94 * (1.0 - math.exp(-elapsed / tau))
            sub = max(sub, heartbeat)
        if sub < 1.0:
            sub = min(sub, 0.985)
        value = band[0] + (band[1] - band[0]) * _clamp(sub, 0.0, 0.999)
        if fraction and float(fraction) >= 1.0:
            value = band[1]
        self._value = max(self._value, _clamp(value, 0.01, 0.995))
        self._samples.append((self._now(), self._value))
        self._samples = self._samples[-160:]
        self._emit(stage, message)

    def stage_floor(self, stage: str) -> float:
        band = self._bands.get(stage)
        return self._value if band is None else max(self._value, band[0])

    def eta_seconds(self) -> int | None:
        """A positive estimate after 10%, or ``None`` while estimating."""
        if self._value < 0.10:
            return None
        now = self._now()
        recent = [
            (stamp, value) for stamp, value in self._samples
            if now - stamp <= 10.0
        ]
        if len(recent) < 3 or recent[-1][0] - recent[0][0] < 2.0:
            return None
        first_t, first_p = recent[0]
        last_t, last_p = recent[-1]
        span = max(0.001, last_t - first_t)
        gain = last_p - first_p
        if gain < 0.004:
            return None
        rate = gain / span
        raw = (1.0 - last_p) / max(rate, 1e-6)
        if not math.isfinite(raw) or raw <= 0:
            return None
        raw = min(3600.0, max(1.0, raw))
        if self._eta is None:
            self._eta = raw
        else:
            # Clamp sudden jumps and smooth the rest.  The estimate may fall
            # as the read speeds up, but never swings by more than 40% in one
            # update and never reaches zero while work is still running.
            raw = min(self._eta * 1.5, max(self._eta * 0.55, raw))
            self._eta = self._eta * 0.55 + raw * 0.45
        return max(1, int(round(self._eta)))

    def decorate(self, message: str) -> str:
        if self._value < 0.10:
            return f"{message} · estimating"
        eta = self.eta_seconds()
        if eta is None:
            return f"{message} · {_short_span(self.elapsed())} so far"
        return f"{message} · about {_short_span(eta)} left"

    def _emit(self, stage: str, message: str) -> None:
        if self._progress is None:
            return
        status = "scanning" if stage == "scanning" else (
            "scoring" if stage == "scoring" else "reading"
        )
        self._progress(status, round(self._value, 4), self.decorate(message))


def cancel_requested() -> bool:
    """True when the existing Cancel reading event is set for this thread."""
    return stt.cancel_requested()


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(process.pid), 15)
        else:  # pragma: no cover - Windows fallback
            process.terminate()
    except (OSError, ProcessLookupError):
        try:
            process.terminate()
        except OSError:
            pass


def _check_cancel(process: subprocess.Popen | None = None) -> None:
    if not cancel_requested():
        return
    if process is not None:
        _stop_process(process)
    raise stt.SttCancelled("Analysis cancelled.")


def _fingerprint(path: Path, size: int) -> str:
    try:
        stat = path.stat()
        stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        stamp = f"{size}"
    return f"{path.resolve()}:{size}:{stamp}"


def probe(path: str | Path) -> dict:
    target = str(Path(path).expanduser().resolve())
    if not Path(target).is_file():
        raise PipelineError("Video file not found.")
    cmd = [
        _ffprobe(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", target,
    ]
    result = _run(cmd, timeout=120)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PipelineError("ffprobe returned invalid metadata.") from exc

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise PipelineError("No video stream found in this file.")
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    rotation = 0.0
    for side in video.get("side_data_list", []) or []:
        if side.get("rotation") is not None:
            rotation = float(side["rotation"])
            break
    if not rotation:
        rotation = float((video.get("tags") or {}).get("rotate") or 0)
    if abs(rotation) % 180 == 90:
        width, height = height, width

    duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise PipelineError("Could not read this video's duration.")

    fps = _ratio(video.get("avg_frame_rate")) or _ratio(video.get("r_frame_rate")) or 30.0
    size = int((data.get("format") or {}).get("size") or 0)
    if not size:
        try:
            size = Path(target).stat().st_size
        except OSError:
            size = 0

    return {
        "path": target,
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "fps": round(fps, 3),
        "codec": video.get("codec_name") or "unknown",
        "has_audio": bool(audio),
        "audio_codec": (audio or {}).get("codec_name") or None,
        "size": size,
        "rotation": rotation,
        "fingerprint": _fingerprint(Path(target), size),
    }


# ---------------------------------------------------------------- scan


def scan_scenes(
    path: str,
    duration: float,
    progress: Callable[[float, str], None],
) -> tuple[list[dict], dict]:
    """One ffmpeg pass: scene cuts + motion energy at low resolution."""
    ffmpeg = _ffmpeg()
    if duration <= 900:
        fps, threshold = 8, 0.26
    elif duration <= 2400:
        fps, threshold = 5, 0.27
    else:
        fps, threshold = 4, 0.28
    motion_fps = max(2, fps // 2)

    graph = (
        f"fps={fps},scale=320:-2,split=2[sc][mo];"
        f"[sc]select='gt(scene,{threshold})+eq(n,0)',showinfo[sv];"
        f"[mo]fps={motion_fps},tblend=all_mode=difference,format=gray,"
        f"signalstats,metadata=print:key=lavfi.signalstats.YAVG[mv]"
    )
    cmd = [
        ffmpeg, "-hide_banner", "-nostats", "-progress", "pipe:1",
        "-i", path, "-filter_complex", graph,
        "-map", "[sv]", "-f", "null", os.devnull,
        "-map", "[mv]", "-f", "null", os.devnull,
    ]

    cuts: list[float] = []
    motion: list[tuple[float, float]] = []
    stderr_tail: list[str] = []
    last_meta_t = 0.0
    last_progress = 0.0

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, start_new_session=True,
    )
    _check_cancel()

    import threading

    def read_stderr() -> None:
        nonlocal last_meta_t
        assert process.stderr is not None
        for line in process.stderr:
            if len(stderr_tail) < 60:
                stderr_tail.append(line.rstrip())
            else:
                stderr_tail.pop(0)
                stderr_tail.append(line.rstrip())
            if "lavfi.signalstats.YAVG=" in line:
                match = re.search(r"YAVG=([0-9.]+)", line)
                if match:
                    motion.append((last_meta_t, float(match.group(1))))
            elif "Parsed_metadata" in line:
                match = re.search(r"pts_time:([0-9.]+)", line)
                if match:
                    last_meta_t = float(match.group(1))
            elif "Parsed_showinfo" in line:
                match = re.search(r"pts_time:([0-9.]+)", line)
                if match:
                    cuts.append(float(match.group(1)))

    stderr_thread = threading.Thread(target=read_stderr, daemon=True)
    stderr_thread.start()

    assert process.stdout is not None
    for raw in process.stdout:
        _check_cancel(process)
        line = raw.strip()
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                micros = int(line.split("=", 1)[1])
            except ValueError:
                continue
            fraction = min(0.995, (micros / 1_000_000) / max(duration, 0.01))
            if fraction - last_progress > 0.012:
                last_progress = fraction
                progress(fraction, f"Scanning cuts · {_clock(micros / 1_000_000)} / {_clock(duration)}")
        elif line.startswith("progress=") and line.endswith("end"):
            break

    code = process.wait()
    stderr_thread.join(timeout=2)
    if code != 0:
        tail = "\n".join(stderr_tail[-12:])[-1200:]
        raise PipelineError(f"ffmpeg scene scan failed.\n{tail}")

    raw_cuts = []
    for t in sorted(cuts):
        if t < 0.35 or t > duration - 0.35:
            continue
        if not raw_cuts or t - raw_cuts[-1] > 0.28:
            raw_cuts.append(t)

    # Very long videos: cap the number of cuts before thumbnail work.
    cap = 1400
    if len(raw_cuts) > cap:
        step = math.ceil(len(raw_cuts) / cap)
        raw_cuts = raw_cuts[::step]
    capped = len(raw_cuts) >= cap

    bounds = [0.0] + raw_cuts + [duration]
    spans: list[tuple[float, float]] = []
    for start, end in zip(bounds, bounds[1:]):
        if end - start < 0.33 and spans:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    if len(spans) > 1 and spans[0][1] - spans[0][0] < 0.33:
        spans[1] = (spans[0][0], spans[1][1])
        spans.pop(0)

    max_len = min(20.0, max(6.0, duration / 1400.0))
    split: list[tuple[float, float]] = []
    for start, end in spans:
        span = end - start
        if span <= max_len + 0.1:
            split.append((start, end))
            continue
        count = max(1, math.ceil(span / max_len))
        for index in range(count):
            a = start + span * index / count
            b = start + span * (index + 1) / count
            split.append((a, b))

    # Guarantee a sane upper bound even on pathological edits.
    if len(split) > 2000:
        step = math.ceil(len(split) / 2000)
        merged = []
        for index in range(0, len(split), step):
            group = split[index:index + step]
            merged.append((group[0][0], group[-1][1]))
        split = merged

    scenes = []
    for index, (start, end) in enumerate(split):
        values = [value for t, value in motion if start <= t < end]
        scenes.append({
            "id": index,
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(end - start, 3),
            "mid": round((start + end) / 2, 3),
            "motion_raw": round(float(np.mean(values)) if values else 0.0, 3),
        })

    return scenes, {
        "fps": fps,
        "motion_fps": motion_fps,
        "threshold": threshold,
        "cut_count": len(raw_cuts),
        "capped": capped,
        "max_beat": round(max_len, 2),
    }


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _deep_limit() -> int:
    try:
        return max(40, int(os.environ.get("VIBECUT_DEEP_SCENES", "300")))
    except ValueError:
        return 300


def cheap_rank(scenes: list[dict]) -> None:
    """Cheap, pre-Vision score used only to choose deep-read candidates."""
    motion = _rank([scene.get("motion_raw", 0.0) for scene in scenes])
    audio = _rank([
        0.68 * scene.get("audio_mean", -60.0) + 0.32 * scene.get("audio_peak", -60.0)
        for scene in scenes
    ])
    onset = _rank([scene.get("onset", 0.0) for scene in scenes])
    length = _rank([min(8.0, scene.get("dur", 0.0)) for scene in scenes])
    for index, scene in enumerate(scenes):
        scene["cheap_score"] = round(float(
            0.40 * motion[index] + 0.34 * audio[index] +
            0.16 * onset[index] + 0.10 * length[index]
        ) * 100, 1)


def select_deep_scenes(
    scenes: list[dict],
    duration: float,
    limit: int | None = None,
) -> list[int]:
    """Pick a stratified shortlist for expensive stills + Vision.

    Short videos are read in full. Long videos keep the strongest cheap beats,
    the payoff zone, long takes, and even timeline coverage.
    """
    limit = limit or _deep_limit()
    if not scenes:
        return []
    if len(scenes) <= limit or duration <= 300:
        for scene in scenes:
            scene["deep"] = True
        return [scene["id"] for scene in scenes]

    cheap_rank(scenes)
    chosen: set[int] = set()

    def add(ids, count: int) -> None:
        for scene_id in ids:
            if len(chosen) >= limit:
                return
            if scene_id not in chosen:
                chosen.add(scene_id)
            count -= 1
            if count <= 0:
                return

    order = sorted(scenes, key=lambda scene: scene["cheap_score"], reverse=True)
    add([scene["id"] for scene in order], max(1, int(limit * 0.38)))

    # Even coverage keeps a quiet but important middle section readable.
    coverage = max(12, int(limit * 0.18))
    step = max(1, len(scenes) / coverage)
    add([scenes[min(len(scenes) - 1, int(index * step))]["id"] for index in range(coverage)], coverage)

    payoff = [scene for scene in order if scene["start"] >= duration * 0.68]
    add([scene["id"] for scene in payoff], max(8, int(limit * 0.12)))

    add([scene["id"] for scene in sorted(
        scenes, key=lambda scene: scene.get("motion_raw", 0.0), reverse=True,
    )], max(6, int(limit * 0.10)))
    add([scene["id"] for scene in sorted(
        scenes, key=lambda scene: scene.get("audio_mean", -60.0), reverse=True,
    )], max(6, int(limit * 0.10)))
    add([scene["id"] for scene in sorted(
        scenes, key=lambda scene: scene.get("onset", 0.0), reverse=True,
    )], max(4, int(limit * 0.06)))
    add([scene["id"] for scene in sorted(
        scenes, key=lambda scene: scene.get("dur", 0.0), reverse=True,
    )], max(4, int(limit * 0.06)))

    # Always read the opening and closing beats.
    add([scene["id"] for scene in scenes[:3]], 3)
    add([scene["id"] for scene in scenes[-3:]], 3)

    # Fill any remainder with the best cheap beats.
    add([scene["id"] for scene in order], limit - len(chosen))

    for scene in scenes:
        scene["deep"] = scene["id"] in chosen
    return sorted(chosen)


# ---------------------------------------------------------------- stills


def extract_thumbs(
    path: str,
    scenes: list[dict],
    job_dir: Path,
    progress: Callable[[float, str], None],
) -> None:
    ffmpeg = _ffmpeg()
    thumb_dir = job_dir / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    total = max(1, len(scenes))
    done = 0
    cancel = stt.cancel_event()

    def one(scene: dict) -> None:
        if cancel is not None:
            stt.set_cancel_event(cancel)
        out = thumb_dir / f"{scene['id']:05d}.jpg"
        moment = min(max(scene["mid"], scene["start"] + 0.04), scene["end"] - 0.04)
        cmd = [
            ffmpeg, "-y", "-v", "error", "-ss", f"{moment:.3f}", "-i", path,
            "-frames:v", "1", "-vf", "scale=360:-2:flags=lanczos", "-q:v", "5", str(out),
        ]
        try:
            _run(cmd, timeout=90)
        except stt.SttCancelled:
            raise
        except Exception:
            Image.new("RGB", (360, 640), (24, 24, 26)).save(out, quality=80)

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, scene) for scene in scenes]
        for _ in as_completed(futures):
            _check_cancel()
            done += 1
            if done == total or done % max(1, total // 24) == 0:
                progress(done / total, f"Pulling stills · {done} / {total}")


def _probe_images_progress(
    directory: Path,
    files: list[Path],
    *,
    progress: Callable[[float, str], None] | None = None,
    label: str = "Reading frames",
    batch_size: int = 8,
) -> dict[str, dict]:
    """Read images in small batches so Cancel can stop between them."""
    records: dict[str, dict] = {}
    total = max(1, len(files))
    for offset in range(0, len(files), max(1, batch_size)):
        _check_cancel()
        chunk = files[offset:offset + max(1, batch_size)]
        records.update(vision.probe_images(directory, files=chunk))
        if progress is not None:
            done = min(total, offset + len(chunk))
            progress(done / total, f"{label} · {done} / {total}")
    return records


def extract_tracking_frames(
    path: str,
    scenes: list[dict],
    job_dir: Path,
    progress: Callable[[float, str], None],
) -> dict[str, Path]:
    """Two extra stills per deep beat for a smoothed crop path."""
    ffmpeg = _ffmpeg()
    tracking_dir = job_dir / "tracking"
    tracking_dir.mkdir(parents=True, exist_ok=True)
    targets: list[tuple[dict, int, float]] = []
    for scene in scenes:
        if not scene.get("deep") or float(scene.get("dur") or 0.0) < 1.2:
            continue
        for index, fraction in enumerate((0.25, 0.75)):
            moment = scene["start"] + float(scene["dur"]) * fraction
            targets.append((scene, index, moment))
    total = max(1, len(targets))
    done = 0
    files: dict[str, Path] = {}
    cancel = stt.cancel_event()

    def one(scene: dict, index: int, moment: float) -> None:
        if cancel is not None:
            stt.set_cancel_event(cancel)
        out = tracking_dir / f"s{scene['id']:05d}_{index}.jpg"
        try:
            _run([
                ffmpeg, "-y", "-v", "error", "-ss", f"{moment:.3f}", "-i", path,
                "-frames:v", "1", "-vf", "scale=360:-2:flags=lanczos", "-q:v", "5", str(out),
            ], timeout=90)
            files[out.name] = out
        except stt.SttCancelled:
            raise
        except Exception:
            return

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(one, scene, index, moment) for scene, index, moment in targets]
        for _future in as_completed(futures):
            _check_cancel()
            done += 1
            # Never print "N / N" here: the crop read is not done until the
            # tracking frames have been analysed too (that probe used to sit
            # at a finished-looking 68% for 40 s).
            if done < total and done % max(1, total // 20) == 0:
                progress(done / total, f"Tracking crop · {done} / {total}")
    return files


CHECK_SAMPLE_FPS = 2.0
CHECK_SAMPLE_MAX_FRAMES = 3600
CHECK_OCR_BATCH = 24
# Thin captions over a busy picture read at full size and not at 960.
CHECK_FRAME_WIDTH = 1280


def _run_progress(
    cmd: list[str],
    *,
    duration: float,
    timeout: int,
    progress: Callable[[float, str], None],
    label: str,
) -> None:
    """Run ffmpeg and report its out_time as a fraction of the whole source."""
    import threading

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1, start_new_session=True,
    )
    stderr_tail: list[str] = []

    def read_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stderr_tail.append(line.rstrip())
            if len(stderr_tail) > 40:
                stderr_tail.pop(0)

    thread = threading.Thread(target=read_stderr, daemon=True)
    thread.start()
    _check_cancel(process)
    assert process.stdout is not None
    for raw in process.stdout:
        _check_cancel(process)
        line = raw.strip()
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                micros = int(line.split("=", 1)[1])
            except ValueError:
                continue
            fraction = min(0.999, (micros / 1_000_000) / max(duration, 0.01))
            progress(fraction, f"{label} · {_clock(micros / 1_000_000)} / {_clock(duration)}")
        elif line.startswith("progress=") and line.endswith("end"):
            break
    code = process.wait()
    thread.join(timeout=2)
    if code != 0:
        tail = "\n".join(stderr_tail[-12:])[-1200:]
        raise PipelineError(f"ffmpeg frame read failed.\n{tail}")


def extract_text_frames(
    path: str,
    job_dir: Path,
    duration: float,
    *,
    fps: float = CHECK_SAMPLE_FPS,
    max_frames: int = CHECK_SAMPLE_MAX_FRAMES,
    out_dir: Path | None = None,
    progress: Callable[[float, str], None] | None = None,
    start: float = 0.0,
    end: float | None = None,
) -> list[dict]:
    """Extract evenly spaced stills for the Check text pass.

    The default cadence is 2 fps (one frame every half second). Long sources
    lower the cadence so the pass never exceeds ``max_frames``. Frame times are
    the sample starts; each frame represents ``1 / cadence`` seconds.
    """
    duration = max(0.0, float(duration or 0.0))
    if duration <= 0:
        return []
    window_start = max(0.0, min(duration, float(start or 0.0)))
    window_end = duration if end is None else max(window_start, min(duration, float(end)))
    span = max(0.0, window_end - window_start)
    if span <= 0:
        return []
    cadence = min(max(float(fps or CHECK_SAMPLE_FPS), 0.05), 4.0)
    if span * cadence > max_frames:
        cadence = max(0.05, max_frames / span)
    directory = Path(out_dir) if out_dir else job_dir / "check" / "frames"
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg(), "-y", "-v", "error", *(
            ["-progress", "pipe:1", "-nostats"] if progress is not None else []
        ),
        "-ss", f"{window_start:.3f}", "-t", f"{span:.3f}",
        "-i", path,
        "-vf", f"fps={cadence:.4f},scale='min({CHECK_FRAME_WIDTH},iw)':-2",
        "-q:v", "4", str(directory / "%06d.jpg"),
    ]
    if progress is None:
        _run(cmd, timeout=max(300, int(duration * 1.5)))
    else:
        _run_progress(
            cmd,
            duration=span,
            timeout=max(300, int(span * 1.5)),
            progress=progress,
            label="Reading the source",
        )
    files = sorted(directory.glob("*.jpg"))
    if not files:
        return []
    if progress is not None:
        progress(1.0, f"Reading the source · {len(files)} frames · checking the reader")
    window = 1.0 / cadence
    return [
        {
            "index": index,
            "file": frame.name,
            "t": round(window_start + index * window, 3),
            "start": round(window_start + index * window, 3),
            "end": round(min(window_end, window_start + (index + 1) * window), 3),
            "ocr_available": True,
        }
        for index, frame in enumerate(files)
    ]


def read_text_samples(
    path: str,
    job_dir: Path,
    duration: float,
    *,
    fps: float = CHECK_SAMPLE_FPS,
    max_frames: int = CHECK_SAMPLE_MAX_FRAMES,
    keep: bool | None = None,
    progress: Callable[[float, str], None] | None = None,
    start: float = 0.0,
    end: float | None = None,
) -> dict:
    """Run the timed text pass and return OCR lines with geometry.

    The result always reports whether Vision was available, so a caller can
    tell "no text in these frames" from "this machine cannot read text".
    """
    keep = (
        str(os.environ.get("VIBECUT_KEEP_CHECK_FRAMES", "0")).strip().lower()
        in {"1", "true", "yes", "on"}
        if keep is None
        else bool(keep)
    )
    directory = job_dir / "check" / "frames"
    if progress is not None:
        progress(0.0, "Pulling frames to read text")
    frames = extract_text_frames(
        path, job_dir, duration, fps=fps, max_frames=max_frames, out_dir=directory,
        start=start, end=end,
        progress=(
            (lambda fraction, message: progress(0.08 * fraction, message))
            if progress is not None else None
        ),
    )
    if not frames:
        return {"frames": [], "vision": False, "fps": fps, "duration": duration}
    available = vision.available()
    records: dict = {}
    if available:
        # Read in batches so Check reports frame N / M instead of sitting
        # at one number for minutes while the helper reads every frame.
        files = [directory / str(frame["file"]) for frame in frames]
        total = len(files)
        for offset in range(0, total, CHECK_OCR_BATCH):
            _check_cancel()
            records.update(vision.probe_images(
                directory, files=files[offset:offset + CHECK_OCR_BATCH],
            ))
            if progress is not None:
                done = min(total, offset + CHECK_OCR_BATCH)
                progress(0.08 + 0.92 * done / total, f"Reading text · frame {done} / {total}")
    samples = []
    for frame in frames:
        record = records.get(frame["file"]) or {}
        samples.append({
            **frame,
            "text": ocr_lines(record),
            "width": int(record.get("width") or 0) or None,
            "height": int(record.get("height") or 0) or None,
        })
    if not keep:
        shutil.rmtree(directory, ignore_errors=True)
    return {
        "frames": samples,
        "vision": bool(available and records),
        "fps": round(len(samples) / duration, 4) if duration else fps,
        "duration": round(duration, 3),
    }


def _attention_from_record(record: dict) -> dict | None:
    faces = record.get("faces") or []
    salient = record.get("salient") or []
    best_face = max(
        faces, key=lambda f: f["w"] * f["h"] * f.get("confidence", 0), default=None,
    )
    best_salient = max(
        salient, key=lambda s: s["w"] * s["h"] * s.get("confidence", 0), default=None,
    )
    if not best_face and not best_salient:
        return None
    return {
        "face": None if not best_face else {
            key: round(float(best_face.get(key) or 0), 3)
            for key in ("x", "y", "w", "h", "confidence")
        },
        "salient": None if not best_salient else {
            key: round(float(best_salient.get(key) or 0), 3)
            for key in ("x", "y", "w", "h", "confidence")
        },
    }


def attach_crop_paths(
    scenes: list[dict],
    records: dict[str, dict],
    source_w: int,
    source_h: int,
) -> None:
    """Smooth sampled attention into a per-aspect crop path."""
    for scene in scenes:
        if not scene.get("deep") or float(scene.get("dur") or 0.0) < 1.2:
            continue
        samples: list[tuple[float, dict | None]] = []
        mid_attention = scene.get("attention")
        samples.append((0.5, mid_attention))
        for index, fraction in enumerate((0.25, 0.75)):
            record = records.get(f"s{scene['id']:05d}_{index}.jpg")
            if record:
                samples.append((fraction, _attention_from_record(record)))
        samples.sort(key=lambda item: item[0])
        if len([item for item in samples if item[1]]) < 2:
            continue
        paths: dict[str, list[dict]] = {}
        for aspect, target_ar in ASPECT_RATIOS.items():
            values = []
            for fraction, attention in samples:
                probe = {"attention": attention} if attention else {}
                cx, cy = crop_center(probe, source_w, source_h, target_ar)
                values.append((fraction, cx, cy))
            # Extend to the cut edges with the nearest sample, then smooth jitter.
            values = [(0.0, values[0][1], values[0][2]), *values,
                      (1.0, values[-1][1], values[-1][2])]
            smoothed = list(values)
            for index in range(1, len(values) - 1):
                _fraction, prev_x, prev_y = values[index - 1]
                _fraction, cx, cy = values[index]
                _fraction, next_x, next_y = values[index + 1]
                smoothed[index] = (
                    values[index][0],
                    0.25 * prev_x + 0.5 * cx + 0.25 * next_x,
                    0.25 * prev_y + 0.5 * cy + 0.25 * next_y,
                )
            paths[aspect] = [
                {
                    "t": round(fraction * float(scene["dur"]), 3),
                    "cx": round(float(cx), 4),
                    "cy": round(float(cy), 4),
                }
                for fraction, cx, cy in smoothed
            ]
        scene["crop_paths"] = paths


# ---------------------------------------------------------------- features


def image_features(path: Path) -> dict:
    try:
        image = Image.open(path).convert("RGB")
    except Exception:
        return {"sharp": 0.0, "bright": 0.55, "contrast": 0.0, "saturation": 0.0, "color": 0.0}
    image.thumbnail((260, 260))
    array = np.asarray(image, dtype=np.float32)
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    edges = np.asarray(image.convert("L").filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    hsv = np.asarray(image.convert("HSV"), dtype=np.float32)

    r, g, b = array[..., 0], array[..., 1], array[..., 2]
    rg = r - g
    yb = 0.5 * (r + g) - b
    colorfulness = math.sqrt(float(rg.std()) ** 2 + float(yb.std()) ** 2) + \
        0.3 * math.sqrt(float(rg.mean()) ** 2 + float(yb.mean()) ** 2)

    return {
        "sharp": round(float(edges.std()), 3),
        "bright": round(float(gray.mean()) / 255.0, 4),
        "contrast": round(float(gray.std()) / 255.0, 4),
        "saturation": round(float(hsv[..., 1].mean()) / 255.0, 4),
        "color": round(colorfulness / 128.0, 4),
    }


def extract_audio(path: str, has_audio: bool, job_dir: Path) -> Path | None:
    if not has_audio:
        return None
    out = job_dir / "audio.wav"
    cmd = [
        _ffmpeg(), "-y", "-v", "error", "-i", path, "-vn", "-ac", "1",
        "-ar", "16000", "-c:a", "pcm_s16le", str(out),
    ]
    _run(cmd, timeout=1800)
    return out


def audio_features(wav_path: Path | None, scenes: list[dict]) -> dict:
    if not wav_path or not wav_path.exists():
        for scene in scenes:
            scene.update({
                "audio_mean": -60.0, "audio_peak": -60.0, "onset": 0.0,
                "silence": 1.0, "peak_t": scene["mid"],
            })
        return {"available": False}

    times: list[np.ndarray] = []
    levels: list[np.ndarray] = []
    frame_len = 800  # 50 ms at 16 kHz
    sample_cursor = 0

    with wave.open(str(wav_path), "rb") as reader:
        rate = reader.getframerate()
        if rate != 16000:
            frame_len = max(1, int(rate * 0.05))
        while True:
            raw = reader.readframes(rate * 10)
            if not raw:
                break
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            usable = (len(samples) // frame_len) * frame_len
            if usable == 0:
                continue
            blocks = samples[:usable].reshape(-1, frame_len)
            rms = np.sqrt(np.mean(blocks * blocks, axis=1) + 1e-12)
            db = 20.0 * np.log10(rms + 1e-8)
            start = sample_cursor / rate
            stamps = start + (np.arange(len(db)) * frame_len + frame_len / 2) / rate
            times.append(stamps)
            levels.append(db)
            sample_cursor += usable

    if not levels:
        for scene in scenes:
            scene.update({
                "audio_mean": -60.0, "audio_peak": -60.0, "onset": 0.0,
                "silence": 1.0, "peak_t": scene["mid"],
            })
        return {"available": False}

    t = np.concatenate(times)
    db = np.concatenate(levels)
    p10, p50, p90 = np.percentile(db, [10, 50, 90])
    silence_floor = p10 + 3.0
    smooth = np.convolve(db, np.ones(21) / 21.0, mode="same") if len(db) > 21 else db

    for scene in scenes:
        mask = (t >= scene["start"]) & (t < scene["end"])
        if not np.any(mask):
            scene.update({
                "audio_mean": -60.0, "audio_peak": -60.0, "onset": 0.0,
                "silence": 1.0, "peak_t": scene["mid"],
            })
            continue
        values = db[mask]
        smooth_values = smooth[mask]
        scene_times = t[mask]
        diffs = np.diff(values, prepend=values[0])
        scene.update({
            "audio_mean": round(float(values.mean()), 3),
            "audio_peak": round(float(values.max()), 3),
            "onset": round(float(np.maximum(diffs, 0).mean()), 3),
            "silence": round(float(np.mean(values < silence_floor)), 4),
            "peak_t": round(float(scene_times[int(np.argmax(smooth_values))]), 3),
            "dynamic": round(float(p90 - p10), 3),
        })

    return {
        "available": True,
        "p50": round(float(p50), 3),
        "p90": round(float(p90), 3),
        "frames": int(len(db)),
    }


# ---------------------------------------------------------------- transcript


HOOK_WORDS = [
    # English
    "how", "why", "what", "secret", "never", "stop", "before", "after",
    "best", "worst", "mistake", "truth", "actually", "finally", "result",
    "changed", "you", "your", "did you know", "here's", "watch", "look",
    "wait", "number", "first", "last", "free", "easy", "fast", "only",
    "one thing", "nobody", "everyone", "should", "must", "need",
    # Chinese
    "为什么", "怎么", "什么", "秘密", "千万", "不要", "一定", "最好",
    "第一", "最后", "结果", "竟然", "原来", "教你", "免费", "快速",
    "简单", "注意", "真的", "居然", "只要", "如何", "别再", "必看",
    "你", "我", "我们", "这件", "这个", "穿搭", "秋天", "秋天",
]


def hook_text_score(text: str) -> float:
    if not text:
        return 0.0
    low = text.lower()
    hits = 0.0
    for word in HOOK_WORDS:
        if word in low:
            hits += 1.0
    if re.search(r"\d", text):
        hits += 0.6
    if any(mark in text for mark in ("?", "？", "!", "！")):
        hits += 0.7
    if 6 <= len(text) <= 140:
        hits += 0.4
    return min(1.0, hits / 3.2)


# ---------------------------------------------------------------- speech-to-text
#
# Transcription now lives in stt.py (Wave 2 track T2).  The names below stay
# available on pipeline for existing callers and compatibility tests.

CLOUD_STT_PROVIDERS = stt.CLOUD_STT_PROVIDERS
WHISPER_MODELS = stt.WHISPER_MODELS
DEFAULT_WHISPER_MODEL = stt.DEFAULT_WHISPER_MODEL

_apple_transcribe_helper = stt._apple_transcribe_helper
whisper_models = stt.whisper_models
transcribe = stt.transcribe
transcribe_cloud = stt.transcribe_cloud
read_transcript = stt.read_transcript
attach_speech = stt.attach_speech


def transcribe_apple(
    wav_path: Path | None,
    job_dir: Path,
    language: str = "en",
    timeout: float | None = None,
) -> dict | None:
    """Compatibility wrapper so callers can monkeypatch the helper lookup."""
    return stt.transcribe_apple(
        wav_path, job_dir, language, timeout=timeout,
        helper=_apple_transcribe_helper(),
    )


def _cloud_speech(
    wav_path: Path,
    job_dir: Path,
    provider: str,
    language: str,
    model: str = "",
    timeout: float = 1800,
) -> dict | None:
    """Compatibility wrapper that keeps legacy monkeypatch seams working."""
    return stt._cloud_speech(
        wav_path, job_dir, provider, language,
        model=model, timeout=timeout,
        run=_run, urlopen=urllib.request.urlopen,
    )


def _transcribe_workflow(
    wav: Path,
    job_dir: Path,
    duration: float,
    language: str,
    routes: list[dict],
    timeout: float,
    progress: Callable[[str, float, str], None],
    *,
    job_id: str = "",
    request_id: str = "",
) -> dict | None:
    """Deprecated route dispatcher.

    Production analysis calls :func:`stt.transcribe_source`.  This shim keeps
    the pre-v2 route semantics for old callers and its compatibility tests.
    """
    return stt.transcribe_routes(
        wav, job_dir, duration, language, routes, timeout, progress,
        job_id=job_id, request_id=request_id,
        engines={
            "cloud": _cloud_speech,
            "whisper": transcribe,
            "apple": transcribe_apple,
        },
        logger=_pipeline_log,
        legacy=True,
    )


# ---------------------------------------------------------------- scoring


def score_scenes(scenes: list[dict], source_w: int, source_h: int) -> None:
    sharp = [scene.get("visual", {}).get("sharp", 0.0) for scene in scenes]
    contrast = [scene.get("visual", {}).get("contrast", 0.0) for scene in scenes]
    saturation = [scene.get("visual", {}).get("saturation", 0.0) for scene in scenes]
    color = [scene.get("visual", {}).get("color", 0.0) for scene in scenes]
    motion = [scene.get("motion_raw", 0.0) for scene in scenes]
    audio_mean = [scene.get("audio_mean", -60.0) for scene in scenes]
    audio_peak = [scene.get("audio_peak", -60.0) for scene in scenes]
    onset = [scene.get("onset", 0.0) for scene in scenes]

    sharp_n = _rank(sharp)
    contrast_n = _rank(contrast)
    saturation_n = _rank(saturation)
    color_n = _rank(color)
    motion_n = _rank(motion)
    audio_n = 0.68 * _rank(audio_mean) + 0.32 * _rank(audio_peak)
    onset_n = _rank(onset)

    source_ar = source_w / max(1, source_h)

    for index, scene in enumerate(scenes):
        visual = scene.get("visual") or {}
        attention = scene.get("attention") or {}
        faces = scene.get("faces") or ([attention["face"]] if attention.get("face") else [])
        salient = scene.get("salient") or ([attention["salient"]] if attention.get("salient") else [])
        face_best = max((f["w"] * f["h"] * f.get("confidence", 0) for f in faces), default=0.0)
        sal_best = max((s["w"] * s["h"] * s.get("confidence", 0) for s in salient), default=0.0)
        face_n = 1.0 if face_best > 0.004 else 0.0
        sal_n = _clamp(sal_best / 0.35)
        bright = float(visual.get("bright", 0.55))
        bright_n = 1.0 - min(1.0, abs(bright - 0.55) / 0.45)

        motion_raw = float(scene.get("motion_raw", 0.0))
        scene["black"] = bool(visual and bright < 0.06 and scene["dur"] >= 0.5)
        scene["freeze"] = bool(
            "motion_raw" in scene
            and scene["dur"] >= 1.6
            and motion_raw < 1.2
            and bright > 0.08
        )

        visual_score = (
            0.24 * sharp_n[index] + 0.15 * contrast_n[index] +
            0.13 * saturation_n[index] + 0.11 * color_n[index] +
            0.20 * face_n + 0.09 * sal_n + 0.08 * bright_n
        )
        text = " ".join(part for part in (scene.get("ocr"), scene.get("speech")) if part)
        text_score = 0.0
        if scene.get("ocr"):
            text_score += 0.60 * hook_text_score(scene["ocr"]) + 0.10
        if scene.get("speech"):
            text_score += 0.30 * hook_text_score(scene["speech"])
        text_score = _clamp(text_score)
        speech_n = 1.0 if scene.get("speech") else 0.0

        interest = _clamp(
            0.30 * visual_score + 0.17 * motion_n[index] +
            0.22 * audio_n[index] + 0.09 * onset_n[index] +
            0.14 * text_score + 0.05 * speech_n + 0.03 * face_n
        )
        hook = _clamp(
            0.24 * visual_score + 0.24 * motion_n[index] +
            0.13 * audio_n[index] + 0.08 * onset_n[index] +
            0.25 * text_score + 0.03 * speech_n + 0.03 * face_n
        )
        if 1.0 <= scene["dur"] <= 4.5:
            hook = min(1.0, hook + 0.02)
        if scene.get("ocr"):
            hook = min(1.0, hook + 0.015)
        if scene["black"]:
            interest *= 0.25
            hook *= 0.2
        elif scene["freeze"]:
            interest *= 0.6
            hook *= 0.5

        scene["face"] = bool(faces)
        scene["subject"] = bool(sal_n > 0.08 or faces)
        scene["visual_score"] = round(float(visual_score) * 100, 1)
        scene["motion_score"] = round(float(motion_n[index]) * 100, 1)
        scene["audio_score"] = round(float(audio_n[index]) * 100, 1)
        scene["text_score"] = round(float(text_score) * 100, 1)
        scene["score"] = round(float(interest) * 100, 1)
        scene["hook"] = round(float(hook) * 100, 1)
        scene["tags"] = []
        if scene["black"]:
            scene["tags"].append("black")
        if scene["freeze"]:
            scene["tags"].append("freeze")
        if faces:
            scene["tags"].append("face")
        if sal_n > 0.08:
            scene["tags"].append("subject")
        if scene.get("ocr"):
            scene["tags"].append("text")
        if scene.get("speech"):
            scene["tags"].append("speech")
        if motion_n[index] >= 0.72:
            scene["tags"].append("motion")
        if sharp_n[index] >= 0.72:
            scene["tags"].append("sharp")

        best_face = max(
            faces,
            key=lambda f: f["w"] * f["h"] * f.get("confidence", 0),
            default=None,
        )
        best_salient = max(
            salient,
            key=lambda s: s["w"] * s["h"] * s.get("confidence", 0),
            default=None,
        )
        if best_face or best_salient:
            scene["attention"] = {
                "face": None if not best_face else {
                    key: round(float(best_face.get(key) or 0), 3)
                    for key in ("x", "y", "w", "h", "confidence")
                },
                "salient": None if not best_salient else {
                    key: round(float(best_salient.get(key) or 0), 3)
                    for key in ("x", "y", "w", "h", "confidence")
                },
            }
        else:
            scene.pop("attention", None)

        crops = {}
        crop_modes = {}
        for aspect, target_ar in ASPECT_RATIOS.items():
            cx, cy = crop_center(scene, source_w, source_h, target_ar)
            crops[aspect] = {"cx": round(cx, 4), "cy": round(cy, 4)}
            tracked = max(abs(cx - 0.5), abs(cy - 0.5))
            crop_modes[aspect] = (
                "smart"
                if abs(source_ar - target_ar) > 0.01 and tracked > 0.015
                else "center"
            )
        scene["crops"] = crops
        scene["crop_modes"] = crop_modes
        scene["crop"] = crops.get("9:16", {"cx": 0.5, "cy": 0.5})
        scene["crop_mode"] = crop_modes.get("9:16", "center")
        scene["visual"] = visual
        scene["motion_raw"] = round(motion_raw, 3)
        scene.pop("faces", None)
        scene.pop("salient", None)


def crop_center(
    scene: dict, source_w: int, source_h: int, target_ar: float = TARGET_AR,
) -> tuple[float, float]:
    attention = scene.get("attention") or {}
    face = attention.get("face")
    salient_item = attention.get("salient")
    faces = [face] if face else (scene.get("faces") or [])
    salient = [salient_item] if salient_item else (scene.get("salient") or [])
    face_boxes = [f for f in faces if f.get("confidence", 0) > 0.35 and f["w"] * f["h"] > 0.003]
    sal_boxes = [
        s for s in salient
        if s.get("confidence", 0) > 0.25 and s["w"] * s["h"] > 0.006
        and not (s["w"] > 0.88 and s["h"] > 0.88)
    ]

    cx, cy = 0.5, 0.5
    if face_boxes:
        face = max(face_boxes, key=lambda f: f["w"] * f["h"] * f.get("confidence", 0))
        cx = face["x"] + face["w"] / 2
        cy = face["y"] + face["h"] / 2
        if sal_boxes:
            sal = max(sal_boxes, key=lambda s: s["w"] * s["h"] * s.get("confidence", 0))
            cx = 0.78 * cx + 0.22 * (sal["x"] + sal["w"] / 2)
            cy = 0.78 * cy + 0.22 * (sal["y"] + sal["h"] / 2)
    elif sal_boxes:
        sal = max(sal_boxes, key=lambda s: s["w"] * s["h"] * s.get("confidence", 0))
        cx = sal["x"] + sal["w"] / 2
        cy = sal["y"] + sal["h"] / 2

    source_ar = source_w / max(1, source_h)
    target_ar = max(0.01, float(target_ar or TARGET_AR))
    if abs(source_ar - target_ar) <= 0.01:
        return 0.5, 0.5
    if source_ar > target_ar:
        width = target_ar * source_h / source_w
        cx = _clamp(cx, width / 2, 1 - width / 2)
        cy = 0.5
    else:
        height = (source_w / target_ar) / source_h
        cy = _clamp(cy, height / 2, 1 - height / 2)
        cx = 0.5
    return cx, cy


# ---------------------------------------------------------------- planning


PAYOFF_ZONE = 0.68
MIN_LATE_BEAT = 0.8
HOOK_CAP = 3.0
HOOK_FLOOR = 0.7
PER_CLIP_BUDGET = {15: 3.1, 30: 3.8, 60: 4.4}


def _clip_text(value: str, limit: int = 56) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _source_span(scene: dict) -> str:
    start = _safe_float(scene.get("start"))
    end = _safe_float(scene.get("end"))
    if 0.0 <= start < end < 10.0:
        return f"{start:.1f}s–{end:.1f}s"
    return f"{_clock(start)}–{_clock(end)}"


def _rank_fact(scene: dict, pool: list[dict], key: str = "score") -> tuple[float, int, int, int]:
    """Return value, rank (1 best), pool size, and top-percent for one score."""
    value = _safe_float(scene.get(key))
    values = [_safe_float(item.get(key)) for item in pool]
    better = sum(1 for item_score in values if item_score > value)
    count = max(1, len(values))
    rank = better + 1
    top = max(1, min(100, round(rank / count * 100)))
    return value, rank, count, top


def _text_evidence(scene: dict) -> list[str]:
    facts: list[str] = []
    speech = " ".join(str(scene.get("speech") or "").split())
    if speech:
        facts.append(f'spoken line "{_clip_text(speech)}"')
    ocr = " ".join(str(scene.get("ocr") or "").split())
    if ocr:
        facts.append(f'on-screen text "{_clip_text(ocr)}"')
    if not facts:
        facts.append("no speech or on-screen text in the read signals")
    return facts


def _subject_evidence(scene: dict) -> str:
    if scene.get("face"):
        return "face in frame"
    if scene.get("subject"):
        return "clear salient subject"
    return "no face or salient subject in the read signals"


def _flag_evidence(scene: dict) -> list[str]:
    facts: list[str] = []
    if scene.get("black"):
        facts.append("black frame flagged")
    if scene.get("freeze"):
        facts.append("freeze flagged (very low motion)")
    return facts


def _score_evidence(scene: dict, pool: list[dict]) -> str:
    interest, rank, count, _ = _rank_fact(scene, pool, "score")
    hook = _safe_float(scene.get("hook"))
    return (
        f"interest {interest:.0f}/100 (rank {rank} of {count}), hook {hook:.0f}/100, "
        f"visual {_safe_float(scene.get('visual_score')):.0f}/100, "
        f"motion {_safe_float(scene.get('motion_score')):.0f}/100, "
        f"audio {_safe_float(scene.get('audio_score')):.0f}/100, "
        f"text {_safe_float(scene.get('text_score')):.0f}/100"
    )


def _scene_evidence(scene: dict, pool: list[dict]) -> list[str]:
    return [
        f"scene {scene.get('id')} at {_source_span(scene)}, {_safe_float(scene.get('dur')):.1f}s long",
        *_text_evidence(scene),
        _subject_evidence(scene),
        _score_evidence(scene, pool),
        *_flag_evidence(scene),
    ]


def _target_fit(
    role: str,
    clip_dur: float,
    target: float,
    per_clip: float,
    body_budget: float,
    total: float,
) -> str:
    target_seconds = max(1, int(round(_safe_float(target, 15.0))))
    if role == "hook":
        return (
            f"{clip_dur:.1f}s opening cut against the {HOOK_CAP:.1f}s hook cap; "
            f"leaves {max(0.0, body_budget):.1f}s of the {target_seconds}s target for the body"
        )
    if role == "payoff":
        headroom = max(0.0, target_seconds - total)
        return (
            f"{clip_dur:.1f}s payoff cut; the {target_seconds}s reel totals "
            f"{total:.1f}s with {headroom:.1f}s headroom"
        )
    return (
        f"{clip_dur:.1f}s cut against the {per_clip:.1f}s per-beat budget; "
        f"the {target_seconds}s reel totals {total:.1f}s"
    )


def scene_note(scene: dict) -> str:
    """Short human note: what this beat is about, from the signals we read."""
    bits: list[str] = []
    if scene.get("speech"):
        bits.append(f'spoken line "{_clip_text(scene["speech"])}"')
    if scene.get("ocr"):
        bits.append(f'on-screen text "{_clip_text(scene["ocr"])}"')
    if scene.get("face"):
        bits.append("a face in frame")
    elif scene.get("subject"):
        bits.append("a clear subject")
    tags = scene.get("tags") or []
    if "motion" in tags:
        bits.append("strong movement")
    if scene.get("dur", 0) >= 3.0:
        bits.append("a long hold")
    if not bits:
        bits.append("a strong visual + audio beat")
    return ", ".join(bits)


def hook_reason(
    scene: dict,
    scenes: list[dict],
    clip: dict | None = None,
    target: float | None = None,
    body_budget: float | None = None,
    total: float | None = None,
    pool: list[dict] | None = None,
) -> str:
    """Explain why this beat was picked as the opening, with observed evidence."""
    if pool is None:
        pool = [s for s in scenes if s.get("deep", True) and not s.get("black")] or scenes
    pool = [s for s in pool if isinstance(s, dict)] or [scene]
    score, rank, count, top = _rank_fact(scene, pool, "hook")
    if count <= 1:
        opening = f"Hook score {score:.0f}, the only hook candidate."
    else:
        opening = f"Hook score {score:.0f}, rank {rank} of {count} (top {top}%)."
    facts = [
        f"scene {scene.get('id')} at {_source_span(scene)}, "
        f"{_safe_float(scene.get('dur')):.1f}s long",
        *_text_evidence(scene),
        _subject_evidence(scene),
        _score_evidence(scene, pool),
        *_flag_evidence(scene),
    ]
    if clip is not None and target is None:
        facts.append(
            f"opening clip keeps {_safe_float(clip.get('dur')):.1f}s "
            f"from source {_clock(_safe_float(clip.get('start')))}–"
            f"{_clock(_safe_float(clip.get('end')))}"
        )
    if target is not None and body_budget is not None and total is not None and clip is not None:
        facts.append(_target_fit(
            "hook", _safe_float(clip.get("dur")), target, 0.0, body_budget, total,
        ))
    return f"{opening} Opening hook: " + "; ".join(facts) + "."


def payoff_reason(
    scene: dict,
    source_duration: float,
    clip: dict | None = None,
    target: float | None = None,
    total: float | None = None,
    pool: list[dict] | None = None,
) -> str:
    """Explain why this late beat closes the reel, with observed evidence."""
    position = (
        _safe_float(scene.get("start")) / max(1.0, _safe_float(source_duration, 1.0)) * 100
    )
    candidates = [s for s in (pool or [scene]) if isinstance(s, dict)] or [scene]
    score, rank, count, _ = _rank_fact(scene, candidates, "score")
    ranking = f" (rank {rank} of {count} late candidates)" if count > 1 else ""
    head = (
        f"Best late beat: {position:.0f}% into the source, "
        f"interest {score:.0f}{ranking}."
    )
    facts = [
        f"scene {scene.get('id')} at {_source_span(scene)}, "
        f"{_safe_float(scene.get('dur')):.1f}s long",
        *_text_evidence(scene),
        _subject_evidence(scene),
        _score_evidence(scene, candidates),
        *_flag_evidence(scene),
    ]
    if clip is not None and target is None:
        facts.append(
            f"payoff clip keeps {_safe_float(clip.get('dur')):.1f}s, "
            f"end-aligned at source {_clock(_safe_float(clip.get('start')))}–"
            f"{_clock(_safe_float(clip.get('end')))}"
        )
    elif clip is not None:
        facts.append(
            f"end-aligned at source {_clock(_safe_float(clip.get('start')))}–"
            f"{_clock(_safe_float(clip.get('end')))}"
        )
    if target is not None and total is not None and clip is not None:
        facts.append(_target_fit(
            "payoff", _safe_float(clip.get("dur")), target, 0.0, 0.0, total,
        ))
    return f"{head} Payoff: " + "; ".join(facts) + "."


def beat_reason(
    scene: dict,
    pool: list[dict],
    clip: dict,
    target: float,
    per_clip: float,
    total: float,
) -> str:
    """Explain a bridge beat from scores and observed signals only."""
    score, rank, count, _ = _rank_fact(scene, pool, "score")
    facts = [
        f"scene {scene.get('id')} at {_source_span(scene)}",
        *_text_evidence(scene),
        _subject_evidence(scene),
        _score_evidence(scene, pool),
        *_flag_evidence(scene),
        _target_fit("beat", _safe_float(clip.get("dur")), target, per_clip, 0.0, total),
    ]
    return (
        f"Bridge beat: interest {score:.0f}/100, rank {rank} of {count}; "
        + "; ".join(facts)
        + "."
    )


def _hook_alternatives(
    hook: dict,
    pool: list[dict],
    requested: bool,
) -> list[dict]:
    """Best two or three other hooks and the observed reason each lost."""
    hook_score = _safe_float(hook.get("hook"))
    others = [s for s in pool if s.get("id") != hook.get("id")]
    others.sort(
        key=lambda s: (
            -_safe_float(s.get("hook")),
            _safe_float(s.get("start")),
            _safe_float(s.get("id")),
        )
    )
    alternatives: list[dict] = []
    for alt in others[:3]:
        alt_score = _safe_float(alt.get("hook"))
        reasons: list[str] = []
        if alt_score > hook_score + 0.05:
            if requested:
                reasons.append(
                    f"higher hook score {alt_score:.0f} vs {hook_score:.0f}, "
                    f"but scene {hook.get('id')} was requested"
                )
            else:
                reasons.append(
                    f"higher hook score {alt_score:.0f} vs {hook_score:.0f}, "
                    "but ranked below the selected hook"
                )
        elif hook_score > alt_score + 0.05:
            reasons.append(
                f"hook score {alt_score:.0f} vs {hook_score:.0f} "
                f"({hook_score - alt_score:.0f} lower)"
            )
        elif _safe_float(alt.get("start")) > _safe_float(hook.get("start")) + 0.05:
            reasons.append(
                f"ties at hook score {alt_score:.0f} but starts "
                f"{_safe_float(alt.get('start')) - _safe_float(hook.get('start')):.1f}s later"
            )
        else:
            reasons.append(
                f"ties at hook score {alt_score:.0f} but ranks lower on the start-time tiebreak"
            )
        if (hook.get("speech") or hook.get("ocr")) and not (alt.get("speech") or alt.get("ocr")):
            reasons.append("no speech or on-screen text in the read signals")
        if hook.get("face") and not alt.get("face"):
            reasons.append("no face in frame")
        if alt.get("freeze"):
            reasons.append("freeze flagged")
        if alt.get("black"):
            reasons.append("black frame flagged")
        alt_dur = _safe_float(alt.get("dur"))
        if alt_dur < 1.0:
            reasons.append(f"{alt_dur:.1f}s is below the 1.0s hook window")
        elif alt_dur > 4.5:
            reasons.append(f"{alt_dur:.1f}s is above the 4.5s comfortable hook window")
        alternatives.append({
            "scene": int(alt["id"]) if alt.get("id") is not None else None,
            "start": round(_safe_float(alt.get("start")), 3),
            "dur": round(alt_dur, 3),
            "hook": round(alt_score, 1),
            "score": round(_safe_float(alt.get("score")), 1),
            "why_not": "; ".join(reasons) or "lower deterministic rank",
        })
    return alternatives


def auto_hook(scenes: list[dict]) -> dict:
    deep = [scene for scene in scenes if scene.get("deep", True)]
    clean = [scene for scene in deep if not scene.get("black")]
    if clean:
        deep = clean
    pool = [scene for scene in deep if scene["dur"] >= 0.55] or deep or scenes
    return max(pool, key=lambda s: (s["hook"], -s["start"]))


def llm_available() -> bool:
    """True when at least one configured hook_rank provider can be called."""
    try:
        import audio  # noqa: PLC0415
        for route in workflow_config.routes(
            settings_store.load_settings().get("workflows"), "hook_rank",
        ):
            provider = str(route.get("provider") or "")
            if provider == "opencode-go" and audio.opencode_available():
                return True
            if provider == "openrouter" and audio.openrouter_available():
                return True
            if provider == "ollama" and os.environ.get("VIBECUT_LLM_URL"):
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def llm_rank_hooks(candidates: list[dict], target: int = 30) -> list[int] | None:
    """Optional rerank through the ordered hook_rank admin routes.

    Any failure falls back to the deterministic score order.
    """
    if len(candidates) < 2 or not llm_available():
        return None
    import audio  # noqa: PLC0415

    lines = []
    for hook in candidates:
        text = (hook.get("speech") or hook.get("ocr") or "no words").strip()
        lines.append(
            f"- scene {hook['scene']}: {hook['dur']:.1f}s, "
            f"hook score {hook['hook']:.0f}, text: {text[:120]}"
        )
    prompt = (
        f"You pick the strongest opening hook for a {target}s vertical reel. "
        "Prefer a concrete claim, a surprise, or an emotional line over slow setup.\n"
        + "\n".join(lines)
        + "\nReturn only a JSON array of scene ids, best first."
    )
    answer = audio._workflow_text("hook_rank", prompt, json_mode=True)
    if not answer:
        return None
    known = {hook["scene"] for hook in candidates}
    order: list[int] = []
    for value in re.findall(r"\d+", str(answer)):
        scene_id = int(value)
        if scene_id in known and scene_id not in order:
            order.append(scene_id)
    return order or None


def _window(scene: dict, wanted: float, prefer_start: bool, end_aligned: bool = False) -> tuple[float, float]:
    start, end = scene["start"], scene["end"]
    dur = end - start
    if dur <= wanted + 0.12:
        return start, end
    if end_aligned:
        return end - wanted, end
    if prefer_start:
        return start, start + wanted
    peak = scene.get("peak_t") or (start + dur / 2)
    left = _clamp(peak - wanted / 2, start, end - wanted)
    return left, left + wanted


def _overlaps(scene: dict, start: float, end: float) -> bool:
    return min(scene["end"], end) - max(scene["start"], start) > 0.05


def _reasoning_payload(
    *,
    scenes: list[dict],
    usable: list[dict],
    hook: dict,
    payoff: dict | None,
    clips: list[dict],
    target: float,
    source_duration: float,
    per_clip: float,
    gap: float,
    total: float,
    note: str | None,
    requested_hook: bool,
    hook_pool: list[dict],
    payoff_candidates: list[dict],
) -> dict:
    """Build the JSON-safe explanation attached to a generated plan."""
    by_id = {scene.get("id"): scene for scene in usable}
    target_seconds = max(1, int(round(_safe_float(target, 15.0))))
    hook_score, hook_rank, hook_count, hook_top = _rank_fact(hook, hook_pool, "hook")

    if hook_count <= 1:
        hook_headline = (
            f"Scene {hook.get('id')} is the only hook candidate: hook score {hook_score:.0f}."
        )
    elif requested_hook and hook_rank > 1:
        hook_headline = (
            f"Scene {hook.get('id')} is the requested opening: hook score {hook_score:.0f}, "
            f"rank {hook_rank} of {hook_count} (top {hook_top}%)."
        )
    elif hook_rank == 1:
        hook_headline = (
            f"Scene {hook.get('id')} is the strongest opening: hook score {hook_score:.0f}, "
            f"rank 1 of {hook_count} (top {hook_top}%)."
        )
    else:
        hook_headline = (
            f"Scene {hook.get('id')} is the best available opening: hook score {hook_score:.0f}, "
            f"rank {hook_rank} of {hook_count} (top {hook_top}%)."
        )
    hook_clip = next((clip for clip in clips if clip.get("role") == "hook"), None)
    hook_evidence = [
        f"source {_source_span(hook)}, {_safe_float(hook.get('dur')):.1f}s long",
        *_text_evidence(hook),
        _subject_evidence(hook),
        _score_evidence(hook, hook_pool),
        *_flag_evidence(hook),
    ]
    if hook_clip is not None:
        hook_evidence.append(
            f"opening cut keeps {_safe_float(hook_clip.get('dur')):.1f}s at source "
            f"{_clock(_safe_float(hook_clip.get('start')))}–"
            f"{_clock(_safe_float(hook_clip.get('end')))}"
        )
    if requested_hook and hook_rank > 1:
        hook_evidence.append(
            f"requested by the caller; {hook_rank - 1} hook candidates score higher"
        )
    elif not requested_hook:
        hook_evidence.append("chosen automatically from the top deterministic hook score")

    hook_section = {
        "headline": hook_headline,
        "evidence": hook_evidence,
        "alternatives": _hook_alternatives(hook, hook_pool, requested_hook),
    }

    roles = [str(clip.get("role") or "beat") for clip in clips]
    body_clips = [clip for clip in clips if clip.get("role") == "beat"]
    all_starts = [_safe_float(clip.get("start")) for clip in clips]
    all_ends = [_safe_float(clip.get("end")) for clip in clips]
    other_clips = [clip for clip in clips if clip.get("role") != "hook"]
    hook_earliest = not other_clips or _safe_float(hook.get("start")) <= min(
        _safe_float(clip.get("start")) for clip in other_clips
    ) + 0.001
    if not clips:
        structure_why = "There are no beats to order."
    elif len(clips) == 1:
        structure_why = (
            "Only one clip fits this target, so there is no body order to break."
        )
    elif hook_earliest:
        structure_why = (
            f"All {len(clips)} clips run in source order from "
            f"{_clock(min(all_starts))} to {_clock(max(all_ends))}, so any actions, "
            "spoken lines or on-screen text keep their original sequence; the hook "
            "is also the earliest selected beat."
        )
    elif body_clips:
        ordered_tail = list(body_clips)
        if payoff is not None:
            payoff_clip = next(
                (clip for clip in clips if clip.get("role") == "payoff"), None,
            )
            if payoff_clip is not None:
                ordered_tail.append(payoff_clip)
        tail_label = (
            f"The {len(body_clips)} bridge beat"
            f"{'s' if len(body_clips) != 1 else ''} and the payoff"
            if payoff is not None
            else f"The {len(body_clips)} bridge beat"
            f"{'s' if len(body_clips) != 1 else ''}"
        )
        structure_why = (
            f"{tail_label} stay in source order from "
            f"{_clock(min(_safe_float(clip.get('start')) for clip in ordered_tail))} "
            f"to {_clock(max(_safe_float(clip.get('end')) for clip in ordered_tail))}, "
            "so any actions, spoken lines or on-screen text keep their original "
            f"sequence; only the hook is lifted from "
            f"{_clock(_safe_float(hook.get('start')))} to the front."
        )
    else:
        payoff_clip = next(
            (clip for clip in clips if clip.get("role") == "payoff"), None,
        )
        structure_why = (
            "The hook and payoff are the only clips; the hook is lifted from "
            f"{_clock(_safe_float(hook.get('start')))} to the front"
            + (
                f", while the payoff stays at {_clock(_safe_float(payoff_clip.get('start')))}"
                if payoff_clip is not None else ""
            )
            + ", leaving no bridge beats to reorder."
        )
    structure_section = {
        "roles": roles,
        "clip_count": len(clips),
        "beat_count": len(body_clips),
        "body_order": "source",
        "body_in_source_order": all(
            _safe_float(body_clips[index].get("start"))
            <= _safe_float(body_clips[index + 1].get("start")) + 0.001
            for index in range(len(body_clips) - 1)
        ),
        "hook_first": bool(clips and clips[0].get("role") == "hook"),
        "source_span": {
            "start": round(min(all_starts), 3) if all_starts else None,
            "end": round(max(all_ends), 3) if all_ends else None,
        },
        "why": structure_why,
    }

    late_zone = _safe_float(source_duration) * PAYOFF_ZONE
    if payoff is not None:
        position = (
            _safe_float(payoff.get("start"))
            / max(1.0, _safe_float(source_duration, 1.0))
            * 100
        )
        payoff_score, payoff_rank, payoff_count, _ = _rank_fact(
            payoff, payoff_candidates or [payoff], "score",
        )
        payoff_clip = next(
            (clip for clip in clips if clip.get("role") == "payoff"), None,
        )
        payoff_headline = (
            f"Scene {payoff.get('id')} is the strongest late beat: interest "
            f"{payoff_score:.0f}/100, {position:.0f}% into the source."
        )
        payoff_evidence = [
            f"starts at {_clock(_safe_float(payoff.get('start')))}, inside the final "
            f"{round((1.0 - PAYOFF_ZONE) * 100)}% of the source",
            *_text_evidence(payoff),
            _subject_evidence(payoff),
            _score_evidence(payoff, payoff_candidates or usable),
            *_flag_evidence(payoff),
        ]
        if payoff_clip is not None:
            payoff_evidence.append(
                f"payoff cut keeps {_safe_float(payoff_clip.get('dur')):.1f}s, "
                "end-aligned to the beat's last frame"
            )
        payoff_why_late = (
            f"It is the highest-interest of {max(1, payoff_count)} late candidate"
            f"{'s' if payoff_count != 1 else ''} and sits at {position:.0f}% of the "
            f"source, so the {target_seconds}s reel lands on a late beat "
            f"{'after the bridge beats' if body_clips else 'as the final clip'} "
            "instead of stopping early."
        )
    else:
        if source_duration <= late_zone:
            payoff_headline = "No payoff beat: the source has no late-beat window."
            payoff_evidence = [
                f"source is {_safe_float(source_duration):.1f}s long; the "
                f"{round(PAYOFF_ZONE * 100)}% late-beat line falls at {late_zone:.1f}s",
                f"the {len(clips)} selected clip{'s' if len(clips) != 1 else ''} "
                f"cover {total:.1f}s",
            ]
            payoff_why_late = (
                "The cut ends on the last selected beat because the source never "
                "reaches the late-beat zone."
            )
        else:
            payoff_headline = "No payoff beat qualified in the final third."
            payoff_evidence = [
                f"no non-hook scene starting at or after {late_zone:.1f}s is at least "
                f"{MIN_LATE_BEAT:.1f}s long",
                "the hook scene is excluded as a payoff candidate",
            ]
            payoff_why_late = (
                "The cut ends on the last selected beat; no qualifying late beat was "
                "available to land on."
            )
    payoff_section = {
        "headline": payoff_headline,
        "evidence": payoff_evidence,
        "why_late": payoff_why_late,
        "position_pct": (
            round(
                _safe_float(payoff.get("start"))
                / max(1.0, _safe_float(source_duration, 1.0))
                * 100,
                1,
            )
            if payoff is not None else None
        ),
        "late_zone_pct": round(PAYOFF_ZONE * 100, 1),
        "candidates": len(payoff_candidates) if payoff is not None else 0,
    }

    kept: list[dict] = []
    for clip in clips:
        scene = by_id.get(clip.get("scene"))
        if scene is None and clip.get("scene") == hook.get("id"):
            scene = hook
        if scene is None and payoff is not None and clip.get("scene") == payoff.get("id"):
            scene = payoff
        scene = scene or {}
        kept.append({
            "scene": clip.get("scene"),
            "role": str(clip.get("role") or "beat"),
            "source_start": round(_safe_float(scene.get("start")), 3),
            "source_end": round(_safe_float(scene.get("end")), 3),
            "start": round(_safe_float(clip.get("start")), 3),
            "end": round(_safe_float(clip.get("end")), 3),
            "dur": round(_safe_float(clip.get("dur")), 3),
            "score": round(_safe_float(scene.get("score")), 1),
            "hook": round(_safe_float(scene.get("hook")), 1),
            "why": str(clip.get("why") or ""),
            "evidence": _scene_evidence(scene, usable) if scene else [],
        })

    scene_lookup = [by_id.get(clip.get("scene")) or {} for clip in clips]
    text_clips = sum(
        1 for scene in scene_lookup if scene.get("speech") or scene.get("ocr")
    )
    face_clips = sum(
        1 for scene in scene_lookup if scene.get("face") or scene.get("subject")
    )
    motion_clips = sum(
        1 for scene in scene_lookup if "motion" in (scene.get("tags") or [])
    )
    freeze_clips = sum(1 for scene in scene_lookup if scene.get("freeze"))
    durations = [_safe_float(clip.get("dur")) for clip in clips]
    all_black = bool(usable) and all(scene.get("black") for scene in usable)
    black_removed = sum(1 for scene in scenes if scene.get("black"))
    if all_black:
        selection_strategy = (
            f"No clean beat was available, so all {len(usable)} usable read beats are "
            f"black-flagged; ranked them by interest, used a {max(0.0, gap):.2f}s "
            f"midpoint spacing preference where possible, and aimed at the "
            f"{target_seconds}s target hook-first."
        )
    else:
        selection_strategy = (
            f"Ranked {len(usable)} usable read beats by interest, excluded black frames, "
            f"used a {max(0.0, gap):.2f}s midpoint spacing preference where possible, "
            f"preserved source order for the body, and aimed at the {target_seconds}s "
            "target hook-first."
        )
    budget = {
        "target": target_seconds,
        "source_duration": round(_safe_float(source_duration), 3),
        "hook": round(sum(
            _safe_float(clip.get("dur")) for clip in clips
            if clip.get("role") == "hook"
        ), 3),
        "beats": round(sum(
            _safe_float(clip.get("dur")) for clip in clips
            if clip.get("role") == "beat"
        ), 3),
        "payoff": round(sum(
            _safe_float(clip.get("dur")) for clip in clips
            if clip.get("role") == "payoff"
        ), 3),
        "total": round(_safe_float(total), 3),
        "headroom": round(max(0.0, target_seconds - _safe_float(total)), 3),
        "over_target": round(max(0.0, _safe_float(total) - target_seconds), 3),
        "per_beat": round(per_clip, 3),
        "payoff_cap_pct": 34,
        "spacing": round(max(0.0, gap), 3),
    }
    selection_evidence = [
        f"{len(clips)} clips kept from {len(usable)} usable read beats; "
        f"{black_removed} black-flagged beat{'s' if black_removed != 1 else ''} in the source",
        f"speech or on-screen text in {text_clips} of {len(clips)} kept clips",
        f"face or clear subject in {face_clips} of {len(clips)} kept clips",
        f"strong-motion tag in {motion_clips} of {len(clips)} kept clips",
        (
            f"kept lengths {min(durations):.1f}s–{max(durations):.1f}s against a "
            f"{per_clip:.1f}s per-beat budget"
        ) if durations else "no clip durations to report",
        (
            f"budget: hook {budget['hook']:.1f}s + beats {budget['beats']:.1f}s + "
            f"payoff {budget['payoff']:.1f}s = {budget['total']:.1f}s of "
            f"{target_seconds}s"
        ),
    ]
    if freeze_clips:
        selection_evidence.append(
            f"{freeze_clips} kept clip{'s are' if freeze_clips != 1 else ' is'} "
            "freeze-flagged and scored down"
        )
    if note:
        selection_evidence.append(f"constraint: {note}")

    hook_text = bool(hook.get("speech") or hook.get("ocr"))
    hook_face = bool(hook.get("face"))
    hook_desc = (
        "with speech or on-screen text" if hook_text
        else "with a face in frame" if hook_face
        else "with no text or face in the read signals"
    )
    bridge_label = (
        "no bridge beats" if not body_clips
        else f"{len(body_clips)} bridge beat{'s' if len(body_clips) != 1 else ''}"
    )
    if payoff is not None:
        position = (
            _safe_float(payoff.get("start"))
            / max(1.0, _safe_float(source_duration, 1.0))
            * 100
        )
        payoff_score = _safe_float(payoff.get("score"))
        summary = (
            f"Open on scene {hook.get('id')} (hook {hook_score:.0f}/100, {hook_desc}) "
            f"and land on scene {payoff.get('id')} (interest {payoff_score:.0f}/100 at "
            f"{position:.0f}% into the source), with {bridge_label} in source order, "
            f"targeting a {target_seconds}s cut from {_safe_float(source_duration):.1f}s "
            "of source."
        )
    else:
        summary = (
            f"Open on scene {hook.get('id')} (hook {hook_score:.0f}/100, {hook_desc}) "
            f"and build toward a {target_seconds}s cut from "
            f"{_safe_float(source_duration):.1f}s of source with {bridge_label}; no late "
            "payoff beat qualified, so the cut ends on the last selected beat."
        )
    hook_selection = (
        "uses the requested opening"
        if requested_hook
        else "ranks the hook by hook score"
    )
    summary += (
        f" Selection {hook_selection}, then ranks body beats and payoff by "
        "interest score, and keeps the body in chronological order; "
        f"{text_clips} of {len(clips)} clips carry speech or on-screen text, "
        f"{face_clips} carry a face or clear subject, and the cut totals "
        f"{_safe_float(total):.1f}s of the {target_seconds}s target"
    )
    if note:
        summary += f"; {note[0].lower() + note[1:]}"
    summary += "."

    return {
        "target": target_seconds,
        "source_duration": round(_safe_float(source_duration), 3),
        "summary": summary,
        "hook": hook_section,
        "structure": structure_section,
        "payoff": payoff_section,
        "selection": {
            "strategy": selection_strategy,
            "evidence": selection_evidence,
            "kept": kept,
            "target_budget": budget,
        },
    }


def _empty_reasoning(target: float, source_duration: float) -> dict:
    target_seconds = max(1, int(round(_safe_float(target, 15.0))))
    return {
        "target": target_seconds,
        "source_duration": round(_safe_float(source_duration), 3),
        "summary": "No scenes were available, so this target has no cut to explain.",
        "hook": {
            "headline": "No opening candidate.",
            "evidence": [],
            "alternatives": [],
        },
        "structure": {
            "roles": [],
            "clip_count": 0,
            "beat_count": 0,
            "body_order": "source",
            "body_in_source_order": True,
            "hook_first": False,
            "source_span": None,
            "why": "There are no beats to order.",
        },
        "payoff": {
            "headline": "No payoff candidate.",
            "evidence": [],
            "why_late": None,
            "position_pct": None,
            "late_zone_pct": round(PAYOFF_ZONE * 100, 1),
            "candidates": 0,
        },
        "selection": {
            "strategy": "No usable scene was returned by the scan.",
            "evidence": [],
            "kept": [],
            "target_budget": {
                "target": target_seconds,
                "source_duration": round(_safe_float(source_duration), 3),
                "hook": 0.0,
                "beats": 0.0,
                "payoff": 0.0,
                "total": 0.0,
                "headroom": float(target_seconds),
                "over_target": 0.0,
                "per_beat": PER_CLIP_BUDGET.get(target_seconds, 3.8),
                "payoff_cap_pct": 34,
                "spacing": 0.0,
            },
        },
    }


def build_plan(
    scenes: list[dict],
    source_duration: float,
    target: float,
    hook_id: int | None = None,
    auto_hook_id: int | None = None,
) -> dict:
    if not scenes:
        return {
            "target": int(target),
            "total": 0.0,
            "hook_scene": None,
            "auto": True,
            "clip_count": 0,
            "clips": [],
            "note": "No scenes available to cut",
            "hook_why": None,
            "payoff_why": None,
            "reasoning": _empty_reasoning(target, source_duration),
        }

    usable = [scene for scene in scenes if scene.get("deep", True)] or scenes
    clean = [scene for scene in usable if not scene.get("black")]
    if clean:
        usable = clean
    by_id = {scene["id"]: scene for scene in usable}
    requested_hook = hook_id is not None and hook_id in by_id
    if not requested_hook:
        hook = auto_hook(usable)
    else:
        hook = by_id[hook_id]
    hook_pool = [
        scene for scene in usable if _safe_float(scene.get("dur")) >= 0.55
    ] or usable

    hook_wanted = min(HOOK_CAP, _safe_float(hook.get("dur")))
    hook_wanted = max(HOOK_FLOOR, hook_wanted)
    hook_start, hook_end = _window(
        hook, hook_wanted,
        prefer_start=bool(hook.get("ocr") or hook.get("speech")),
    )
    hook_dur = hook_end - hook_start
    body_budget = max(0.0, target - hook_dur)
    per_clip = PER_CLIP_BUDGET.get(int(target), 3.8)

    # Payoff: best beat near the end, so the reel lands somewhere.
    last_zone = source_duration * PAYOFF_ZONE
    payoff = None
    payoff_dur = 0.0
    payoff_candidates = [
        scene for scene in usable
        if scene["id"] != hook["id"] and scene["start"] >= last_zone
        and scene["dur"] >= MIN_LATE_BEAT
    ]
    if payoff_candidates:
        payoff = max(payoff_candidates, key=lambda s: s["score"])
        payoff_dur = min(payoff["dur"], 3.9, max(1.2, body_budget * 0.34))
        payoff_dur = max(0.8, payoff_dur)
    remaining = max(0.0, body_budget - payoff_dur)

    def midpoint(scene: dict) -> float:
        return (scene["start"] + scene["end"]) / 2

    selected: list[dict] = []
    selected_mids: list[float] = [midpoint(hook)]
    selected_ids: set[int] = {hook["id"]}
    if payoff:
        selected_mids.append(midpoint(payoff))
        selected_ids.add(payoff["id"])
    gap = max(0.65, source_duration / max(1.0, target * 3.4))
    pool = [scene for scene in usable if scene["id"] not in (hook["id"], (payoff or {}).get("id"))]
    if payoff:
        pool = [scene for scene in pool if scene["start"] < payoff["start"] - 0.05]
    pool.sort(key=lambda s: s["score"], reverse=True)

    def take(pool_items: list[dict], gap_size: float) -> None:
        nonlocal remaining
        for scene in pool_items:
            if remaining < 0.85:
                break
            if scene["id"] in selected_ids:
                continue
            if any(abs(midpoint(scene) - mid) < gap_size for mid in selected_mids):
                continue
            duration = min(scene["dur"], per_clip, remaining)
            if duration < 0.8:
                continue
            selected.append({"scene": scene, "wanted": duration})
            selected_ids.add(scene["id"])
            selected_mids.append(midpoint(scene))
            remaining -= duration

    take(pool, gap)
    if remaining >= 1.0:
        take(pool, max(0.25, gap * 0.35))
    if remaining >= 1.0:
        take(pool, 0.0)

    # If the pool ran dry, extend existing clips before adding filler.
    if remaining >= 0.9 and selected:
        for item in selected:
            if remaining < 0.4:
                break
            room = min(item["scene"]["dur"] - item["wanted"], remaining, 1.2)
            if room > 0.1:
                item["wanted"] += room
                remaining -= room

    selected.sort(key=lambda item: item["scene"]["start"])
    clips = [{
        "scene": hook["id"],
        "start": round(hook_start, 3),
        "end": round(hook_end, 3),
        "dur": round(hook_dur, 3),
        "role": "hook",
        "why": hook_reason(hook, scenes),
    }]
    for item in selected:
        scene = item["scene"]
        start, end = _window(scene, item["wanted"], prefer_start=False)
        clips.append({
            "scene": scene["id"],
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(end - start, 3),
            "role": "beat",
            "why": (
                f"Bridge beat, interest {scene['score']:.0f}. "
                f"It has {scene_note(scene)}."
            ),
        })
    if payoff:
        start, end = _window(payoff, payoff_dur, prefer_start=False, end_aligned=True)
        clips.append({
            "scene": payoff["id"],
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(end - start, 3),
            "role": "payoff",
            "why": payoff_reason(payoff, source_duration),
        })

    total = sum(clip["dur"] for clip in clips)
    if total > target:
        overshoot = total - target
        for clip in reversed(clips):
            if overshoot <= 0.01:
                break
            room = max(0.0, clip["dur"] - 0.65)
            cut = min(room, overshoot)
            if clip["role"] == "payoff":
                clip["start"] = round(clip["start"] + cut, 3)
            else:
                clip["end"] = round(clip["end"] - cut, 3)
            clip["dur"] = round(clip["end"] - clip["start"], 3)
            overshoot -= cut

    total = round(sum(clip["dur"] for clip in clips), 3)
    note = None
    if total < target * 0.88:
        note = f"Source supports {total:.1f}s here"
    if source_duration < target:
        note = f"Source is only {source_duration:.1f}s long"

    for clip in clips:
        scene = by_id.get(clip["scene"])
        if scene is None:
            continue
        if clip["role"] == "hook":
            clip["why"] = hook_reason(
                scene, scenes, clip=clip, target=target,
                body_budget=body_budget, total=total, pool=hook_pool,
            )
        elif clip["role"] == "payoff":
            clip["why"] = payoff_reason(
                scene, source_duration, clip=clip, target=target,
                total=total, pool=payoff_candidates,
            )
        else:
            clip["why"] = beat_reason(scene, usable, clip, target, per_clip, total)

    reasoning = _reasoning_payload(
        scenes=scenes,
        usable=usable,
        hook=hook,
        payoff=payoff,
        clips=clips,
        target=target,
        source_duration=source_duration,
        per_clip=per_clip,
        gap=gap,
        total=total,
        note=note,
        requested_hook=requested_hook,
        hook_pool=hook_pool,
        payoff_candidates=payoff_candidates,
    )
    payoff_clip = next((clip for clip in clips if clip.get("role") == "payoff"), None)
    return {
        "target": int(target),
        "total": total,
        "hook_scene": hook["id"],
        "auto": bool(auto_hook_id is None or hook["id"] == auto_hook_id),
        "clip_count": len(clips),
        "clips": clips,
        "note": note,
        "hook_why": clips[0]["why"],
        "payoff_why": payoff_clip["why"] if payoff_clip else None,
        "reasoning": reasoning,
    }


def arc_order(clips: list[dict], scenes: list[dict]) -> list[dict]:
    """Reorder beats as setup → proof → payoff, hook first, payoff last."""
    if len(clips) < 4:
        return clips
    by_id = {scene["id"]: scene for scene in scenes}
    hook = [clip for clip in clips if clip.get("role") == "hook"]
    payoff = [clip for clip in clips if clip.get("role") == "payoff"]
    middle = [
        clip for clip in clips
        if clip.get("role") not in {"hook", "payoff"}
    ]
    if not middle:
        return clips

    def key(clip: dict):
        scene = by_id.get(clip.get("scene")) or {}
        motion = float(scene.get("motion_score") or 50.0)
        text_bonus = 12.0 if (scene.get("ocr") or scene.get("speech")) else 0.0
        face_bonus = 6.0 if (scene.get("face") or "subject" in (scene.get("tags") or [])) else 0.0
        duration = float(clip.get("dur") or 0.0)
        return (motion - text_bonus - face_bonus, -duration)

    ordered = sorted(middle, key=key)
    return [*(hook or [clips[0]]), *ordered, *payoff]


def make_plans(
    scenes: list[dict],
    source_duration: float,
    hook_id: int | None = None,
    auto_hook_id: int | None = None,
) -> dict:
    return {
        str(target): build_plan(scenes, source_duration, target, hook_id, auto_hook_id)
        for target in (15, 30, 60)
    }


# ---------------------------------------------------------------- orchestration


OCR_MIN_CONFIDENCE = 0.18
OCR_MIN_TEXT = 2


def _box(value) -> dict | None:
    """Return one normalized top-left box, or ``None`` when unusable."""
    if isinstance(value, (list, tuple)) and len(value) == 4:
        value = {"x": value[0], "y": value[1], "w": value[2], "h": value[3]}
    if not isinstance(value, dict):
        return None
    try:
        x = float(value.get("x"))
        y = float(value.get("y"))
        w = float(value.get("w"))
        h = float(value.get("h"))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(number) for number in (x, y, w, h)):
        return None
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x >= 1 or y >= 1:
        return None
    w = min(w, 1.0 - x)
    h = min(h, 1.0 - y)
    if w <= 0.002 or h <= 0.002:
        return None
    return {
        "x": round(x, 6), "y": round(y, 6),
        "w": round(w, 6), "h": round(h, 6),
    }


def ocr_lines(record: dict) -> list[dict]:
    """Keep every accepted OCR line with its geometry and confidence.

    The Vision helper already reports one normalized ``box`` per line. Older
    records may omit it, so a line without a usable box still contributes text
    but no geometry. Callers decide how to treat that.
    """
    lines: list[dict] = []
    for line in (record or {}).get("text", []) or []:
        if not isinstance(line, dict):
            continue
        text = " ".join(str(line.get("text") or "").split())
        if len(text) < OCR_MIN_TEXT:
            continue
        try:
            confidence = float(line.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if not math.isfinite(confidence) or confidence < OCR_MIN_CONFIDENCE:
            continue
        lines.append({
            "text": text,
            "confidence": round(min(1.0, max(0.0, confidence)), 4),
            "box": _box(line.get("box")),
        })
    return lines


def _apply_scene_read(scene: dict, job_dir: Path, record: dict, read_text: bool) -> None:
    lines = ocr_lines(record)
    ocr = " · ".join(line["text"] for line in lines)[:260]
    scene["ocr"] = ocr if read_text else ""
    scene["ocr_boxes"] = [
        {
            "text": line["text"],
            "confidence": line["confidence"],
            "box": line["box"],
        }
        for line in lines
        if read_text and line["box"]
    ]
    if read_text and lines:
        confidences = [line["confidence"] for line in lines]
        scene["ocr_confidence"] = round(sum(confidences) / len(confidences), 4)
    else:
        scene["ocr_confidence"] = 0.0
    scene["faces"] = (record or {}).get("faces", [])
    scene["salient"] = (record or {}).get("salient", [])
    scene["visual"] = image_features(job_dir / "thumbs" / f"{scene['id']:05d}.jpg")
    scene["deep"] = True


def read_scene(
    path: str,
    scene: dict,
    job_dir: Path,
    read_text: bool = True,
) -> dict:
    """Deep-read one scene on demand, then caller re-scores the job."""
    if scene.get("deep", True):
        return scene
    extract_thumbs(path, [scene], job_dir, lambda _fraction, _message: None)
    thumb = job_dir / "thumbs" / f"{scene['id']:05d}.jpg"
    record = probe_image(thumb) if vision.available() else {}
    _apply_scene_read(scene, job_dir, record, read_text)
    return scene


def _speech_language(options: dict) -> str:
    """The language to force, or ``""`` to let the engine detect it.

    ``app.clean_options`` and the stored settings both default the field to
    ``"en"`` even when the user never chose a language.  Treat that default as
    unknown so Whisper auto-detects; explicit non-English selections survive.
    """
    raw = str((options or {}).get("speech_language") or "").strip().lower()
    if raw in {"", "auto", "none", "und"}:
        return ""
    if (options or {}).get("speech_language_explicit"):
        return raw
    if raw == "en":
        stt_settings = settings_store.load_settings().get("stt") or {}
        configured = str(stt_settings.get("language") or "").strip().lower()
        if configured in {"", "auto", "en"}:
            return ""
    return raw


def _speech_engine_summary(
    transcript: dict | None,
    *,
    enabled: bool,
    attempted: bool,
    language: str,
    errors: list[dict] | None,
) -> dict:
    failures = [dict(item) for item in (errors or []) if isinstance(item, dict)]
    return {
        "whisper": bool(transcript and transcript.get("segments")),
        "transcript_provider": (transcript or {}).get("provider") or "local",
        "transcript_language": (transcript or {}).get("language"),
        "stt_enabled": bool(enabled),
        "stt_attempted": bool(attempted),
        "stt_language": language or "auto",
        "stt_error": failures[-1].get("error") if failures else None,
        "stt_errors": failures[-4:],
    }


def analyze_source(
    path: str,
    meta: dict,
    job_dir: Path,
    options: dict,
    progress: Callable[[str, float, str], None],
) -> dict:
    started = time.time()
    timings: dict[str, float] = {}
    read_text = bool(options.get("ocr", True))
    smart_crop = bool(options.get("smart_crop", True))
    crop_tracking = bool(options.get("crop_tracking", True)) and smart_crop
    vision_enabled = read_text or smart_crop
    tracker = ProgressTracker(progress)
    speech_errors: list[dict] = []

    stage = time.time()
    tracker.emit("scanning", 0.0, "Slicing the timeline")
    scenes, scan_info = scan_scenes(
        path, meta["duration"],
        lambda fraction, message: tracker.emit("scanning", fraction, message),
    )
    tracker.emit("scanning", 1.0, "Timeline sliced")
    timings["scan"] = round(time.time() - stage, 2)

    stage = time.time()
    tracker.emit("audio", 0.05, "Listening to the audio")
    wav = extract_audio(path, meta["has_audio"], job_dir)
    tracker.emit("audio", 0.75, f"Measuring sound across {_clock(meta['duration'])}")
    audio_info = audio_features(wav, scenes)
    tracker.emit("audio", 1.0, "Sound measured")
    timings["audio"] = round(time.time() - stage, 2)

    stage = time.time()
    deep_ids = select_deep_scenes(scenes, meta["duration"])
    deep_scenes = [scene for scene in scenes if scene.get("deep")]
    timings["shortlist"] = round(time.time() - stage, 2)

    stage = time.time()
    tracker.emit(
        "thumbs", 0.0,
        f"{len(scenes)} moments · deep-reading {len(deep_scenes)}",
    )
    extract_thumbs(
        path, deep_scenes, job_dir,
        lambda fraction, message: tracker.emit("thumbs", fraction, message),
    )
    tracker.emit("thumbs", 1.0, "Stills ready")
    timings["thumbs"] = round(time.time() - stage, 2)

    stage = time.time()
    vision_data = {}
    tracker.emit("vision", 0.0, "Checking the frame reader")
    use_vision = vision_enabled and vision.available()
    if use_vision:
        tracker.emit("vision", 0.0, "Reading frames · text + subject")
        deep_files = [
            job_dir / "thumbs" / f"{scene['id']:05d}.jpg" for scene in deep_scenes
        ]
        deep_files = [item for item in deep_files if item.is_file()]
        vision_data = _probe_images_progress(
            job_dir / "thumbs", deep_files,
            progress=lambda fraction, message: tracker.emit("vision", fraction, message),
            label="Reading frames · text + subject",
        )
        tracker.emit("vision", 1.0, "Frames read")
    elif vision_enabled:
        tracker.emit("vision", 1.0, "Vision reader unavailable · using center crops")
    else:
        tracker.emit("vision", 1.0, "Frame reading is off")
    timings["vision"] = round(time.time() - stage, 2)

    stage = time.time()
    for scene in scenes:
        if not scene.get("deep"):
            scene["ocr"] = ""
            scene["faces"] = []
            scene["salient"] = []
            scene["visual"] = {"sharp": 0.0, "bright": 0.55, "contrast": 0.0, "saturation": 0.0, "color": 0.0}
            continue
        filename = f"{scene['id']:05d}.jpg"
        _apply_scene_read(scene, job_dir, vision_data.get(filename) or {}, read_text)
    timings["features"] = round(time.time() - stage, 2)

    tracking_records = {}
    if crop_tracking and use_vision:
        stage = time.time()
        tracker.emit("crop", 0.0, "Tracking crop across each beat")
        tracking_dir = job_dir / "tracking"
        tracking_files = extract_tracking_frames(
            path, deep_scenes, job_dir,
            # The frame pass owns the first 55% of the crop band; smoothing
            # the probe owns the rest, so 50 / 50 never looks like completion.
            lambda fraction, message: tracker.emit("crop", 0.55 * fraction, message),
        )
        if tracking_files:
            ordered = sorted(tracking_files.values(), key=lambda item: item.name)
            total_tracking = max(1, len(ordered))
            tracker.emit("crop", 0.55, f"Smoothing crop paths · 0 / {total_tracking}")
            tracking_records = _probe_images_progress(
                tracking_dir, ordered,
                progress=lambda fraction, message: tracker.emit(
                    "crop", 0.55 + 0.45 * fraction, message,
                ),
                label="Smoothing crop paths",
            )
        tracker.emit("crop", 1.0, "Crop paths ready")
        timings["crop_tracking"] = round(time.time() - stage, 2)
    else:
        tracker.emit("crop", 1.0, "Center crop")

    transcript = None
    speech_language = _speech_language(options)
    speech_enabled = bool(options.get("transcribe"))
    if speech_enabled and wav:
        stage = time.time()
        job_id = str(options.get("job_id") or "")
        request_id = str(options.get("request_id") or job_id)
        tracker.emit("speech", 0.0, "Preparing the speech read")
        if not options.get("speech_language_explicit"):
            # A title in another script beats the default; otherwise the
            # engine auto-detects (see _speech_language).
            guessed = stt.guess_language(
                str(meta.get("name") or ""), str(meta.get("title") or ""),
            )
            if guessed:
                speech_language = guessed
        settings = settings_store.load_settings()
        stt_cfg = workflow_config.effective(settings.get("workflows"), "stt")
        transcript = stt.transcribe_source(
            wav, job_dir, meta["duration"],
            lambda fraction, message: tracker.emit("speech", fraction, message),
            engine=str(options.get("transcribe_engine") or ""),
            routes=list(stt_cfg.get("routes") or []),
            language=speech_language,
            vocabulary=stt.vocabulary_terms(job_dir=job_dir, settings=settings),
            timeout=float(stt_cfg.get("timeout_s") or 300),
            job_id=job_id,
            request_id=request_id,
            logger=_pipeline_log,
            errors=speech_errors,
        )
        if transcript:
            timings["stt"] = round(time.time() - stage, 2)
    tracker.emit(
        "speech", 1.0,
        (
            f"Speech read · {transcript.get('language') or 'auto'}"
            if transcript else ("Speech is off" if not speech_enabled else "No transcript returned")
        ),
    )
    attach_speech(scenes, transcript)

    stage = time.time()
    tracker.emit("scoring", 0.0, "Finding the hook")
    score_scenes(scenes, meta["width"], meta["height"])
    if tracking_records:
        attach_crop_paths(scenes, tracking_records, meta["width"], meta["height"])
    if not smart_crop:
        for scene in scenes:
            scene["crop"] = {"cx": 0.5, "cy": 0.5}
            scene["crop_mode"] = "center"
            scene["crops"] = {aspect: {"cx": 0.5, "cy": 0.5} for aspect in ASPECT_RATIOS}
            scene["crop_modes"] = {aspect: "center" for aspect in ASPECT_RATIOS}
    hook = auto_hook(scenes)
    plans = make_plans(scenes, meta["duration"], None, hook["id"])
    timings["score"] = round(time.time() - stage, 2)

    if wav:
        try:
            wav.unlink()
        except OSError:
            pass

    tracker.emit("scoring", 1.0, "Building three cut plans")
    return {
        "elapsed": round(time.time() - started, 2),
        "timings": timings,
        "scene_count": len(scenes),
        "deep_count": len(deep_scenes),
        "deep_scene_ids": deep_ids,
        "shortlist_limit": _deep_limit(),
        "scan": scan_info,
        "audio": audio_info,
        "engine": {
            "vision": bool(vision_data),
            **_speech_engine_summary(
                transcript,
                enabled=speech_enabled,
                attempted=bool(speech_enabled and wav),
                language=speech_language,
                errors=speech_errors,
            ),
        },
        "hook_scene": hook["id"],
        "transcript": None if not transcript else {
            "language": transcript.get("language"),
            "text": transcript.get("text", "")[:1000],
            "segments": len(transcript.get("segments", [])),
            "no_speech": bool(transcript.get("no_speech")),
        },
        "scenes": scenes,
        "plans": plans,
    }


def retry_speech(
    job: dict,
    job_dir: Path,
    options: dict | None = None,
    progress: Callable[[str, float, str], None] | None = None,
) -> dict:
    """Re-run only the speech read for an existing job.

    Frames, thumbnails, crop paths and the plan are left untouched.  The caller
    commits the returned fields with its existing ``update_job`` writer; this
    helper never writes ``job.json``.
    """
    merged = dict(job.get("options") or {})
    merged.update(options or {})
    source = dict(job.get("source") or {})
    path = str(source.get("path") or "")
    duration = float(source.get("duration") or 0.0)
    analysis = job.get("analysis") or {}
    scenes = list(analysis.get("scenes") or [])
    errors: list[dict] = []

    def emit(stage: str, fraction: float, message: str) -> None:
        if progress is not None:
            progress(stage, fraction, message)

    if not path or not Path(path).is_file():
        return {
            "ok": False,
            "reason": "The source file is missing. Reconnect it before retrying speech.",
            "engine": _speech_engine_summary(
                None, enabled=True, attempted=False,
                language=_speech_language(merged), errors=errors,
            ),
        }
    emit("reading", 0.02, "Preparing speech retry")
    wav = extract_audio(path, bool(source.get("has_audio", True)), Path(job_dir))
    if not wav:
        return {
            "ok": False,
            "reason": "This video has no sound track, so there is nothing to transcribe.",
            "engine": _speech_engine_summary(
                None, enabled=True, attempted=False,
                language=_speech_language(merged), errors=errors,
            ),
        }
    speech_language = _speech_language(merged)
    if not merged.get("speech_language_explicit"):
        # Same rule as analyze_source: a title in another script beats the default.
        guessed = stt.guess_language(
            str(source.get("name") or ""), str(source.get("title") or ""),
        )
        if guessed:
            speech_language = guessed
    settings = settings_store.load_settings()
    stt_cfg = workflow_config.effective(settings.get("workflows"), "stt")
    try:
        transcript = stt.transcribe_source(
            wav, Path(job_dir), duration,
            lambda fraction, message: emit(
                "reading", 0.10 + 0.85 * max(0.0, min(1.0, fraction)), message,
            ),
            engine=str(merged.get("transcribe_engine") or ""),
            routes=list(stt_cfg.get("routes") or []),
            language=speech_language,
            vocabulary=stt.vocabulary_terms(job_dir=Path(job_dir), settings=settings),
            timeout=float(stt_cfg.get("timeout_s") or 300),
            job_id=str(job.get("id") or ""),
            request_id=str(job.get("id") or ""),
            logger=_pipeline_log,
            errors=errors,
        )
    finally:
        try:
            Path(wav).unlink()
        except OSError:
            pass
    if transcript:
        attach_speech(scenes, transcript)
    return {
        "ok": bool(transcript and transcript.get("segments")),
        "transcript": None if not transcript else {
            "language": transcript.get("language"),
            "text": transcript.get("text", "")[:1000],
            "segments": len(transcript.get("segments", [])),
            "no_speech": bool(transcript.get("no_speech")),
        },
        "scenes": scenes,
        "engine": _speech_engine_summary(
            transcript,
            enabled=True,
            attempted=True,
            language=speech_language,
            errors=errors,
        ),
        "reason": (
            ""
            if transcript and transcript.get("segments")
            else "Speech was on, but no engine returned a transcript. "
                 "Try again with Whisper auto language."
        ),
    }
