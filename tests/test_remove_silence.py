import numpy as np
import pytest
from fastapi.testclient import TestClient

from duckcore import edits, levels, silence
from duckcore.main import create_app
from duckcore.store import ProjectStore


def test_threshold_minimum_padding_and_word_bounds():
    values = np.zeros(300)
    values[150:170] = .02
    assert silence.quiet_spans(values, [(.755, .895)], -40, .7, .1, 3) == [[.1, .65], [1.8, 2.9]]
    assert silence.quiet_spans(values, [], -20, 1, 0, 3) == [[0, 3]]


def test_preview_protects_words_in_reordered_clips_and_solo_track(tmp_path, monkeypatch):
    source = tmp_path / "source"
    track = tmp_path / "dub"
    track.touch()
    monkeypatch.setattr(levels, "read", lambda path, project: np.r_[np.ones(25), np.zeros(175)])
    edit = {"clips": [{"start": 1, "end": 2}, {"start": 0, "end": 1}],
            "audio_tracks": [{"kind": "dub", "audio": "dub", "start": 0, "duration": 2, "solo": True}]}
    args = (edit, tmp_path, source, [{"start": 1.5, "end": 1.6}], -40, .1, 0)
    assert silence.preview(*args) == [[.25, .5], [.6, 2]]
    monkeypatch.setattr(levels, "read", lambda *a: np.empty(0))
    with pytest.raises(ValueError, match="audible"):
        silence.preview(*args)


def test_accept_subset_stale_preview_and_cancel(tmp_path, monkeypatch):
    signal = tmp_path / "placeholder"
    signal.touch()
    pid = ProjectStore(tmp_path).create("test", signal)["id"]
    edit = edits.create_full(pid, {"meta": {"duration": 4}}, tmp_path)
    url = f"/api/projects/{pid}/edits/{edit['id']}"
    monkeypatch.setattr(levels, "read", lambda *a: np.tile(np.repeat([.1, 0.], 100), 2))
    with TestClient(create_app("test", tmp_path), headers={"Authorization": "Bearer test"}) as client:
        assert len(client.get(url + "/levels").json()["values"]) == 400
        post = lambda **body: client.post(url + "/clips/silence", json=body)
        preview = post().json()
        assert preview["spans"] == [[1.12, 1.88], [3.12, 3.88]]
        assert edits.get_edit(tmp_path, pid, edit["id"]) == edit
        assert post(selected=[0], preview_id="old").status_code == 409
        changed = post(selected=[1], preview_id=preview["preview_id"]).json()
        assert changed["removed"] == .76 and changed["edit"]["end"] == 3.24
        assert post(selected=[0], preview_id=preview["preview_id"]).status_code == 409
