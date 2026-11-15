from pathlib import Path

from duckcore import render
from duckcore.engine import textfill


def test_span_cache_ignores_layers_without_rects_in_its_frames(monkeypatch, tmp_path):
    layers = [
        {"id": "one", "box": {"x": .1, "y": .2, "w": .2, "h": .1},
         "ranges": [{"start": 0, "end": 1}]},
        {"id": "two", "box": {"x": .1, "y": .2, "w": .2, "h": .1},
         "ranges": [{"start": 2, "end": 3}]},
    ]
    # A GPU-only installation has no CPU model; that must not hide cached fills.
    monkeypatch.setattr(textfill, "missing_model", lambda *a: "CPU model absent")
    monkeypatch.setattr(textfill, "method_stamp", lambda *a, **k: "test:gpu")
    monkeypatch.setattr(textfill, "device_problem", lambda *a: None)
    monkeypatch.setattr(textfill, "model_path", lambda *a: tmp_path / "model")
    captured = []
    original = textfill.span_key

    def key(**kwargs):
        value = original(**kwargs)
        captured.append(value)
        (tmp_path / f"{value}.mp4").write_bytes(b"x" * 2048)
        return value

    monkeypatch.setattr(textfill, "span_key", key)
    args = dict(meta={"width": 100, "height": 100, "fps": 30}, duration=1,
                method="lama", cache_dir=tmp_path, data_root=tmp_path)
    for selected in (layers, layers[1:]):
        textfill.prepare_span(source="unused", start=2, layers=selected, **args)
        textfill.estimate_span(start=2, layers=selected, **args)
    assert len(set(captured)) == 1
    captured.clear()
    textfill.prepare_span(source="unused", start=0, layers=layers, **args)
    first_key = captured[-1]
    changed = [{**layers[0], 'box': {**layers[0]['box'], 'x': .3}}, layers[1]]
    textfill.prepare_span(source="unused", start=0, layers=changed, **args)
    assert captured[-1] != first_key
    assert textfill.prepare_span(source="unused", start=0, layers=layers[1:], **args) is None
    assert len(captured) == 2


def test_render_rate_keeps_check_measurements(tmp_path):
    render.remember_check_time(tmp_path, 2, 10)
    render.remember_render_time(tmp_path, 5, 30)
    assert render._check_rate(tmp_path) == 5


def test_active_layers_follow_rects_including_extra_frame():
    from duckcore.engine.textfill import mask
    layers = [
        {"id": "late", "box": {"x": .1, "y": .2, "w": .2, "h": .1},
         "ranges": [{"start": .999, "end": 2}]},
        {"id": "empty", "box": {"x": .1, "y": .2, "w": .2, "h": .1},
         "ranges": [{"start": 4, "end": 5}]},
    ]
    args = dict(start=0, fps=30, frames=62, width=100, height=100)
    active = []
    before = mask.frame_rects(layers, **args)
    after = mask.frame_rects(layers, active_layers=active, active_frames=31, **args)
    assert before == after
    assert [layer['id'] for layer in active] == ['late']


def test_short_estimate_separates_cold_and_warm_costs(tmp_path, monkeypatch):
    sample = dict(timeline=6, clips=3, cold_spans=0, fill=.1, check=20,
                  layers=2, overhead=8)
    edit = {'clips': [{'start': 0, 'end': 2}] * 3, 'clean': [
        {'kind': 'blur', 'enabled': True}, {'kind': 'blur', 'enabled': True}]}
    initial = render.estimate_edit(edit, {'width':100,'height':100,'fps':30}, tmp_path)
    sample['key'] = initial['cost_key']
    render._remember_cost(tmp_path, sample)
    render._remember_cost(tmp_path, {**sample, 'cold_spans': 3, 'fill': 100})
    result = render.estimate_edit(edit, {'width':100,'height':100,'fps':30}, tmp_path)
    assert result['total_seconds'] == 28.1
    assert result['total_range'] == [18.7, 37.5]
    edit['cut'] = {'aspect': '1:1'}
    assert render.estimate_edit(edit, {'width':100,'height':100,'fps':30}, tmp_path)['total_seconds'] != 28.1
