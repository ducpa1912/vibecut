"""Cached 10 ms RMS windows in source time."""
import hashlib
import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
from threading import Lock

import numpy as np

from duckcore import media

RATE = 100
SAMPLES = 160
_lock = Lock()


def rms(samples):
    samples = np.asarray(samples, dtype=np.float32)
    whole = len(samples) // SAMPLES * SAMPLES
    frames = samples[:whole].reshape(-1, SAMPLES)
    values = np.sqrt(np.mean(frames * frames, axis=1))
    if whole < len(samples):
        values = np.append(values, np.sqrt(np.mean(samples[whole:] ** 2)))
    return values


def read(source, project):
    source = Path(source).resolve()
    st = source.stat()
    key = hashlib.sha256(f"rms1:{source}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()
    cache = Path(project) / "levels" / (key + ".npy")
    with _lock:
        if cache.is_file():
            return np.load(cache, allow_pickle=False)
        probe = subprocess.run([media.ffprobe(), "-v", "error", "-select_streams", "a:0",
                                "-show_entries", "stream=index", "-of", "csv=p=0", str(source)],
                               capture_output=True, check=True)
        chunks = []
        if probe.stdout.strip():
            cmd = [media.ffmpeg(), "-nostdin", "-v", "error", "-i", str(source), "-map", "0:a:0",
                   "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"]
            with subprocess.Popen(cmd, stdout=subprocess.PIPE) as child:
                while data := child.stdout.read(SAMPLES * 4 * 1000):
                    chunks.append(rms(np.frombuffer(data, dtype="<f4")))
                if child.wait():
                    raise ValueError("Could not read the audio levels.")
        values = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)
        cache.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=cache.parent, delete=False) as out:
            try:
                np.save(out, values)
                out.flush()
                os.replace(out.name, cache)
            finally:
                Path(out.name).unlink(missing_ok=True)
        return values


def asset(project, name):
    file = (project / name).resolve()
    if not file.is_relative_to(project.resolve()) or not file.is_file():
        raise ValueError("The edit's audio file is unavailable.")
    return file
