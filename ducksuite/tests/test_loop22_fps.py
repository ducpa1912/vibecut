import re
import json
import subprocess
from pathlib import Path

import pytest

from duckcore import render, edits


@pytest.mark.parametrize('source,expected', [(23.976,24),(24,24),(25,30),(29.97,30),
                                           (50,30),(60,30),(0,30),(None,30)])
def test_output_rate(source, expected, tmp_path):
    meta = {'fps': source}
    assert render.output_fps(meta) == expected
    assert render.estimate_edit({}, meta, tmp_path)['output_fps'] == expected


def test_frame_rate_copy():
    source = Path('static/duck/app.js').read_text()
    function = re.search(r'function frameRateText\(source, output\) \{.*?\n\}', source, re.S).group()
    resolve = re.search(r'function renderFpsText\(\) \{.*?\n\}', source, re.S).group()
    subprocess.run(['node', '-e', function + resolve + '''
const assert = require('node:assert/strict');
const state = {edit: {source: {fps: 25, output_fps: 30}}, renderEstimate: {failed: true}};
assert.equal(renderFpsText(), 'Source 25 fps → 30 fps: about 5 frames per second are shown twice');
state.edit.source = {fps: 24, output_fps: 24};
assert.equal(renderFpsText(), '24 fps · set from the source (24 fps)');
assert.equal(frameRateText(24,24), '24 fps · set from the source (24 fps)');
assert.equal(frameRateText(25,30), 'Source 25 fps → 30 fps: about 5 frames per second are shown twice');
assert.equal(frameRateText(60,30), 'Source 60 fps → 30 fps: about 30 frames per second are dropped');
assert.equal(frameRateText(29.97,30), '30 fps · set from the source (29.97 fps)');
'''], check=True)


def test_edit_payload_has_rate_without_an_estimate(tmp_path):
    path = edits.edit_path(tmp_path, 'project', 'ed_test')
    path.parent.mkdir(parents=True, exist_ok=True)
    original = {'id': 'ed_test', 'project_id': 'project', 'source': {'fps': 25}}
    path.write_text(json.dumps(original))
    loaded = edits.get_edit(tmp_path, 'project', 'ed_test')
    assert loaded['source']['output_fps'] == 30
    assert json.loads(path.read_text()) == original
    loaded['source']['fps'] = 24
    assert edits.save_edit(loaded, tmp_path)['source']['output_fps'] == 24
