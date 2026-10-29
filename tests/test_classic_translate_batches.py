"""Full translation runs once, in 20-line batches, and leaves a ready flag."""

from __future__ import annotations

import json


def test_worker_translates_in_batches_of_twenty(monkeypatch, tmp_path):
    import audio
    import routes_classic as routes

    calls = []

    def fake_translate(lines, source, target, provider="auto"):
        calls.append(list(lines))
        return [f"{target}:{line}" for line in lines]

    monkeypatch.setattr(audio, "translate_lines", fake_translate)
    monkeypatch.setattr(routes, "_translation_flag", lambda job_id, target: tmp_path / f"{target}.json")
    texts = [f"line {index}" for index in range(45)]

    routes._translation_worker("job1", "vi", "auto", "zh", texts)

    assert [len(batch) for batch in calls] == [20, 20, 5]
    saved = json.loads((tmp_path / "vi.json").read_text(encoding="utf-8"))
    assert saved["status"] == "ready"
    assert saved["lines"] == 45
    assert saved["batches"] == 3
    assert saved["source"] == "zh"


def test_a_ready_flag_is_reported_as_ready_for_the_same_transcript(monkeypatch, tmp_path):
    import routes_classic as routes

    texts = ["a", "b", "c"]
    flag = tmp_path / "vi.json"
    flag.write_text(json.dumps({
        "status": "ready", "source_hash": routes._translation_hash(texts),
        "lines": 3, "batches": 1,
    }), encoding="utf-8")
    monkeypatch.setattr(routes, "_translation_flag", lambda job_id, target: flag)
    monkeypatch.setattr(routes, "_translation_texts", lambda job_id: texts)
    monkeypatch.setattr(routes, "_translation_source", lambda job_id: "zh")
    routes.TRANSLATION_RUNS.pop(("job2", "vi"), None)

    state = routes._translation_state("job2", "vi")

    assert state["status"] == "ready"
    assert state["total"] == 3


def test_a_changed_transcript_makes_the_flag_stale(monkeypatch, tmp_path):
    import routes_classic as routes

    flag = tmp_path / "vi.json"
    flag.write_text(json.dumps({
        "status": "ready", "source_hash": "old", "lines": 3, "batches": 1,
    }), encoding="utf-8")
    monkeypatch.setattr(routes, "_translation_flag", lambda job_id, target: flag)
    monkeypatch.setattr(routes, "_translation_texts", lambda job_id: ["new", "lines"])
    monkeypatch.setattr(routes, "_translation_source", lambda job_id: "zh")
    routes.TRANSLATION_RUNS.pop(("job3", "vi"), None)

    state = routes._translation_state("job3", "vi")

    assert state["status"] == "idle"
    assert state["total"] == 2
