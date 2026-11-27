import subprocess
from types import SimpleNamespace

import numpy as np

from duckcore import levels


def test_centi_second_windows_partial_window_and_gain():
    signal = np.repeat(np.array([0, -.5, .25]), 160)
    assert levels.RATE == 100
    np.testing.assert_allclose(levels.rms(signal[:-10]), [0, .5, .25])
    np.testing.assert_allclose(levels.rms(signal * .2), [0, .1, .05])
    assert not len(levels.rms([]))


def test_empty_stream_is_cached_and_replacement_invalidates(tmp_path, monkeypatch):
    source = tmp_path / "placeholder"
    source.touch()
    probes = []
    def probe(*args, **kwargs):
        probes.append(1)
        return SimpleNamespace(stdout=b"")
    monkeypatch.setattr(subprocess, "run", probe)
    monkeypatch.setattr(levels.media, "ffprobe", lambda: "probe")
    assert not len(levels.read(source, tmp_path))
    assert not len(levels.read(source, tmp_path))
    source.write_bytes(b"changed")
    assert not len(levels.read(source, tmp_path))
    assert len(probes) == 2


def test_canvas_uses_five_samples_gain_headroom_and_relative_highlights():
    import shutil

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for canvas checks")
    script = """
      import assert from 'node:assert/strict';
      import {drawLevels, mixEntry} from './static/duck/audio-tools.js';
      globalThis.devicePixelRatio = 1;
      globalThis.getComputedStyle = () => ({color: 'white'});
      const points = [], highlights = [];
      const ctx = {beginPath(){}, moveTo(){}, closePath(){}, fill(){},
        lineTo(x,y){points.push(y)}, fillRect(...rect){highlights.push(rect)}};
      const canvas = {clientWidth:1, clientHeight:100, getContext:()=>ctx};
      function amplitude(values, gain) {
        points.length=0;
        drawLevels(canvas,values,.02,1,gain,[[.1,.4]]);
        return 50 - points[0];
      }
      assert.ok(Math.abs(amplitude([0,0,1,0,0],.5)-9.2)<.0001);
      assert.equal(amplitude([1,1,1,1,1],2),46);
      assert.equal(amplitude([],1),.5);
      assert.ok(Math.abs(highlights[0][2]-.3)<1e-9);
      const e = mixEntry({start:2,duration:.05,fade_offset:.1,fade_duration:1,
                          fade_in:.4,offset:.1,volume:.8},2,10);
      assert.ok(Math.abs(e.duration-.05)<1e-8);
      assert.ok(Math.abs(e.envelope[0][1]-.2)<1e-8);
      assert.ok(Math.abs(e.envelope.at(-1)[1]-.3)<1e-8);
    """
    subprocess.run([node, "--input-type=module", "-e", script], check=True)
