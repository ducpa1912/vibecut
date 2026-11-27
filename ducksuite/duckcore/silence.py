"""Project cached source envelopes into output time and propose word-safe cuts."""
import math

import numpy as np

from duckcore import edits, levels


def quiet_spans(envelope, words, threshold, minimum, padding, duration):
    quiet = envelope <= 10 ** (threshold / 20)
    for start, end in words:
        quiet[max(0, math.floor(round(start * levels.RATE, 9))):max(0, math.ceil(round(end * levels.RATE, 9)))] = False
    edges = np.flatnonzero(np.diff(np.r_[False, quiet, False]))
    spans = []
    for first, last in edges.reshape(-1, 2):
        start, end = first / levels.RATE, min(duration, last / levels.RATE)
        if end - start + 1e-9 >= minimum and end - start > 2 * padding:
            spans.append([round(start + padding, 3), round(end - padding, 3)])
    return spans


def preview(edit, project, source, words, threshold, minimum, padding):
    duration = edits._story_end(edit["clips"])
    envelope = np.zeros(math.ceil(duration * levels.RATE), dtype=np.float32)
    cache = {}
    protected = []

    def add(path, start, length, offset, gain, row=None):
        if path not in cache:
            cache[path] = levels.read(path, project)
        first = round(start * levels.RATE)
        src = round(offset * levels.RATE)
        count = min(round((start + length) * levels.RATE) - first, len(cache[path]) - src,
                    len(envelope) - first)
        if count > 0:
            if row:
                total = row.get("fade_duration", length)
                attack = min(total / 2, row.get("fade_in", 0))
                release = min(total / 2, row.get("fade_out", 0))
                phase = row.get("fade_offset", 0) + np.arange(count) / levels.RATE
                # Use the louder end of each bin so the word edge stays safe.
                if attack:
                    gain = gain * np.clip((phase + 1 / levels.RATE) / attack, 0, 1)
                if release:
                    gain = gain * np.clip((total - phase) / release, 0, 1)
            envelope[first:first + count] += cache[path][src:src + count] * gain

    tracks = [row for row in edits.ensure_audio_tracks(edit) if not row.get("muted")]
    sounds = [row for row in edit.get("sfx", []) if row.get("kind") == "sound" and not row.get("muted")]
    solo = any(row.get("solo") for row in tracks + sounds)
    audible = [row for row in tracks + sounds if not solo or row.get("solo")]
    voice = any(row.get("kind") == "voice" for row in audible)
    replaced = any(row.get("kind") == "dub" or row.get("mode") == "voice_only" for row in audible)
    bed = 0 if solo or replaced or edit.get("audio_source_muted") else (0.22 if voice else 1)
    cursor = 0
    boundaries = []
    for clip in edit["clips"]:
        a, b = clip["start"], clip["end"]
        length = b - a
        if clip.get("kind") == "media":
            if bed and clip.get("media") != "image":
                add(levels.asset(project, clip["file"]), cursor, length, clip.get("offset", 0), bed)
        else:
            if bed:
                add(source, cursor, length, a, bed * clip.get("volume", 1))
            for word in words:
                lo, hi = max(a, word["start"]), min(b, word["end"])
                if hi > lo:
                    protected.append((cursor + lo - a, cursor + hi - a))
        cursor += length
        boundaries.append(round(cursor, 3))
    for row in audible:
        start = row.get("start", 0)
        length = row.get("duration", row.get("end", start) - start)
        default = {"music": .25, "sound": .9}.get(row.get("kind"), 1)
        add(levels.asset(project, row.get("audio") or row["file"]), start, length,
            row.get("offset", 0), row.get("volume", default), row)
    if not any(len(values) for values in cache.values()):
        raise ValueError("Choose an audible source or track to find quiet spans.")
    spans = quiet_spans(envelope, protected, threshold, minimum, padding, duration)
    # The renderer needs at least 40 ms per retained clip. Shorten proposals,
    # never expand a cut into speech, including when only a subset is accepted.
    safe = []
    for a, b in spans:
        for edge in [0, *boundaries]:
            if 0 < a - edge < .04:
                a = edge + .04
            if 0 < edge - b < .04:
                b = edge - .04
        if safe and a - safe[-1][1] < .04:
            a = safe[-1][1] + .04
        if b > a + .001:
            safe.append([round(a, 3), round(b, 3)])
    return safe
