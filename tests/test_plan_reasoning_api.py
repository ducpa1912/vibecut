"""Truthful reasoning after manual, custom, or arc-ordered cuts."""

from __future__ import annotations

import app


def _clip(scene, start, dur, role):
    return {
        "scene": scene,
        "start": float(start),
        "end": float(start + dur),
        "dur": float(dur),
        "role": role,
        "why": f"manual {role}",
    }


def test_manual_reasoning_marks_reordered_body_as_not_source_order():
    plan = {
        "target": 30,
        "clips": [
            _clip(1, 5.0, 3.0, "hook"),
            _clip(2, 12.0, 3.0, "beat"),
            _clip(3, 9.0, 3.0, "beat"),
            _clip(4, 20.0, 3.0, "payoff"),
        ],
    }

    reasoning = app._manual_plan_reasoning(plan, "Manual edit", 60.0)

    assert reasoning["structure"]["body_in_source_order"] is False
    assert "source order no longer holds" in reasoning["summary"]
    assert reasoning["hook"]["alternatives"] == []
    assert reasoning["payoff"]["position_pct"] is None
    assert reasoning["selection"]["target_budget"]["total"] == 12.0
    assert "manual clip list" in reasoning["selection"]["strategy"]


def test_arc_order_replaces_stale_automatic_reasoning(monkeypatch):
    plan = {
        "target": 30,
        "total": 9.0,
        "clip_count": 3,
        "hook_scene": 1,
        "clips": [
            _clip(1, 0.0, 3.0, "hook"),
            _clip(2, 3.0, 3.0, "beat"),
            _clip(3, 12.0, 3.0, "payoff"),
        ],
        "reasoning": {
            "summary": "stale source-order claim",
            "structure": {"body_in_source_order": True},
            "hook": {"headline": "stale hook"},
            "payoff": {"headline": "stale payoff"},
        },
        "hook_why": "stale hook",
        "payoff_why": "stale payoff",
    }
    job = {
        "analysis": {"scenes": []},
        "source": {"duration": 30.0},
    }
    monkeypatch.setattr(
        app.pipeline,
        "arc_order",
        lambda clips, scenes: [clips[0], clips[2], clips[1]],
    )

    value = app._apply_order(job, plan, "arc")

    assert [clip["scene"] for clip in value["clips"]] == [1, 3, 2]
    assert value["reasoning"]["summary"].startswith("Story-arc order:")
    assert value["reasoning"]["structure"]["body_in_source_order"] is True
    assert "stale" not in value["reasoning"]["summary"]
    assert value["hook_why"] == value["reasoning"]["hook"]["headline"]
    assert value["payoff_why"] == value["reasoning"]["payoff"]["headline"]


def test_custom_plan_includes_manual_reasoning():
    scenes = [
        {
            "id": index,
            "start": index * 3.0,
            "end": (index + 1) * 3.0,
            "dur": 3.0,
            "deep": True,
        }
        for index in range(4)
    ]
    job = {
        "status": "ready",
        "source": {"duration": 12.0},
        "analysis": {"scenes": scenes, "hook_scene": 0},
    }
    clips = [
        {"scene": 0, "start": 0.0, "end": 2.0, "role": "hook", "why": "manual"},
        {"scene": 2, "start": 6.0, "end": 9.0, "role": "payoff", "why": "manual"},
    ]

    plan = app._custom_plan(job, 15, 0, clips)

    assert plan["note"] == "Manual edit"
    assert plan["reasoning"]["summary"].startswith("Manual edit:")
    assert plan["reasoning"]["hook"]["headline"] == "Manual opening: scene 1."
    assert plan["reasoning"]["structure"]["body_in_source_order"] is True
    assert plan["hook_why"] == plan["reasoning"]["hook"]["headline"]
    assert plan["payoff_why"] == plan["reasoning"]["payoff"]["headline"]
