from duckcore import render
from duckcore.engine import textfill


def test_missing_done_output_is_not_playable(tmp_path):
    queue = object.__new__(render.RenderQueue)
    row = queue._row({'state': 'done', 'output': str(tmp_path / 'gone.mp4')})
    assert row['output_missing'] is True


def test_custom_model_versions_are_evicted(tmp_path, monkeypatch):
    from duckcore.engine.textfill import custom
    path = tmp_path / 'model.pt'
    path.write_bytes(b'first')
    monkeypatch.setattr(custom, 'open_filler', lambda folder: object())
    textfill._FILLERS.clear()
    textfill._custom_filler(path)
    path.write_bytes(b'second version')
    textfill._custom_filler(path)
    assert len([k for k in textfill._FILLERS if k[0] == 'custom']) == 1
    textfill._FILLERS.clear()
