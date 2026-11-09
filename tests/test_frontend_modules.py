"""Frontend helper modules extracted from app.js."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_timeline_and_audio_helpers() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = """
import assert from 'node:assert/strict';
import {
  clipDuration, storyDuration, storyClipAt, timelineToSource,
  sourceToTimeline, storyRanges,
} from './static/duck/timeline-model.js';
import { waveformPeaks, audibleRows, mixEntry } from './static/duck/audio-tools.js';

const clips = [{ start: 0, end: 4 }, { start: 10, end: 12 }];
assert.equal(clipDuration(clips[1]), 2);
assert.equal(storyDuration(clips), 6);
const at = storyClipAt(clips, 4.5);
assert.equal(at.index, 1);
assert.equal(at.start, 4);
assert.equal(at.offset, 0.5);
assert.equal(timelineToSource(clips, 4.5), 10.5);
assert.equal(sourceToTimeline(clips, 10.5), 4.5);
const ranges = storyRanges(clips, new Map([[7, { id: 7 }]]));
assert.equal(ranges.length, 2);
assert.equal(ranges[1].start, 4);
assert.equal(ranges[1].end, 6);

const channel = new Float32Array(100);
channel[0] = 1;
channel[99] = -1;
const peaks = waveformPeaks(channel, 1, 0, 1, 4);
assert.equal(peaks.length, 4);
assert.ok(peaks[0] > peaks[1]);

const rows = [
  { id: 'a', solo: false },
  { id: 'b', solo: true },
];
assert.deepEqual(audibleRows(rows).map((row) => row.id), ['b']);
assert.deepEqual(audibleRows([{ id: 'a', solo: false }]).map((row) => row.id), ['a']);

const entry = mixEntry({
  start: 1, duration: 2, offset: 0.5, volume: 0, fade_in: 0.2, fade_out: 0.3,
}, 1.5, 4);
assert.equal(entry.delay, 0);
assert.equal(entry.offset, 1);
assert.equal(entry.duration, 1.5);
assert.equal(entry.level, 0);
assert.equal(mixEntry({ start: 0, duration: 1 }, 2, 4), null);
console.log('ok');
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "ok"
