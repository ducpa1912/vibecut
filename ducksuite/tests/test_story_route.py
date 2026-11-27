from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from duckcore.main import create_app


def test_write_story_route_creates_a_story_edit(tmp_path: Path, monkeypatch) -> None:
    scenes = [{"id": 0, "start": 0.0, "end": 5.0}, {"id": 1, "start": 5.0, "end": 10.0}, {"id": 2, "start": 10.0, "end": 15.0}]
    project = tmp_path / "projects" / "prj_story"
    project.mkdir(parents=True)
    (project / "check.json").write_text(json.dumps({"scenes": scenes, "meta": {"duration": 15.0}}), encoding="utf-8")
    doc = {
        "thesis": "One bold statement.",
        "beats": [
            {"scene_id": 2, "cue": "c", "reason": "hook", "start": 10.0, "end": 15.0, "seconds": 5.0},
            {"scene_id": 0, "cue": "a", "reason": "setup", "start": 0.0, "end": 5.0, "seconds": 5.0},
            {"scene_id": 1, "cue": "b", "reason": "payoff", "start": 5.0, "end": 10.0, "seconds": 5.0},
        ],
        "scene_ids": [2, 0, 1],
        "model": "apple",
        "reason": "",
        "title": "One bold statement.",
        "runtime": 15.0,
    }
    import duckcore.story as story_mod

    monkeypatch.setattr(story_mod, "write_story", lambda *args, **kwargs: doc)
    app = create_app("test-token", tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/projects/prj_story/edits/story/write",
            headers={"Authorization": "Bearer test-token"},
            json={"count": 4},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["edit"]["kind"] == "story"
        assert body["edit"]["story"]["thesis"] == "One bold statement."
        assert body["edit"]["scene_ids"] == [2, 0, 1]
        assert [clip["scene"] for clip in body["edit"]["clips"]] == [2, 0, 1]
