import json

import pytest

import pipeline


def make_scene(index, start, dur, hook=50.0, score=50.0, deep=True, **extra):
    scene = {
        "id": index,
        "start": float(start),
        "end": float(start + dur),
        "dur": float(dur),
        "mid": float(start + dur / 2),
        "hook": hook,
        "score": score,
        "deep": deep,
        "visual_score": score,
        "motion_score": score,
        "audio_score": score,
        "text_score": 0.0,
        "ocr": "",
        "speech": "",
        "tags": [],
        "crop": {"cx": 0.5, "cy": 0.5},
        "crop_mode": "center",
    }
    scene.update(extra)
    return scene


def rich_scenes(count=40, dur=4.0):
    return [
        make_scene(
            index,
            index * dur,
            dur,
            hook=40 + index,
            score=40 + index,
            speech=f"line {index} about the build" if index % 3 == 0 else "",
            ocr=f"TEXT {index}" if index % 5 == 0 else "",
            face=index % 2 == 0,
            subject=index % 4 == 1,
            tags=["motion"] if index % 4 == 2 else [],
        )
        for index in range(count)
    ]


@pytest.mark.parametrize("target", [15, 30, 60])
def test_plan_reasoning_schema_for_every_target(target):
    scenes = rich_scenes()
    plan = pipeline.build_plan(scenes, source_duration=160.0, target=target)
    reasoning = plan["reasoning"]

    assert reasoning["target"] == target
    assert reasoning["source_duration"] == 160.0
    assert isinstance(reasoning["summary"], str) and reasoning["summary"]
    assert f"{target}s" in reasoning["summary"]

    hook = reasoning["hook"]
    assert hook["headline"]
    assert hook["evidence"] and all(isinstance(item, str) and item for item in hook["evidence"])
    assert 1 <= len(hook["alternatives"]) <= 3
    for alternative in hook["alternatives"]:
        assert alternative["scene"] != plan["hook_scene"]
        assert alternative["why_not"]
        assert isinstance(alternative["hook"], float)

    structure = reasoning["structure"]
    assert structure["roles"] == [clip["role"] for clip in plan["clips"]]
    assert structure["clip_count"] == len(plan["clips"])
    assert structure["beat_count"] == sum(
        1 for clip in plan["clips"] if clip["role"] == "beat"
    )
    assert structure["body_order"] == "source"
    assert structure["body_in_source_order"] is True
    assert structure["hook_first"] is True
    assert "source order" in structure["why"]

    payoff = reasoning["payoff"]
    assert payoff["headline"] and payoff["evidence"] and payoff["why_late"]
    assert payoff["candidates"] >= 1
    assert payoff["position_pct"] is not None
    assert payoff["position_pct"] >= 68.0

    selection = reasoning["selection"]
    assert selection["strategy"]
    assert selection["evidence"]
    assert len(selection["kept"]) == len(plan["clips"])
    assert [item["role"] for item in selection["kept"]] == structure["roles"]
    assert all(item["why"] and item["evidence"] for item in selection["kept"])
    budget = selection["target_budget"]
    assert budget["target"] == target
    assert budget["total"] == pytest.approx(plan["total"])
    assert budget["hook"] + budget["beats"] + budget["payoff"] == pytest.approx(plan["total"])

    # Added values must stay plain JSON data.
    json.dumps(plan, allow_nan=False)


@pytest.mark.parametrize("target", [15, 30, 60])
def test_beats_and_payoff_keep_source_order(target):
    scenes = rich_scenes()
    plan = pipeline.build_plan(scenes, source_duration=160.0, target=target)
    starts = {scene["id"]: scene["start"] for scene in scenes}
    body = [clip for clip in plan["clips"] if clip["role"] != "hook"]

    assert [clip["role"] for clip in plan["clips"][1:]] == [
        clip["role"] for clip in body
    ]
    assert [starts[clip["scene"]] for clip in body] == sorted(
        starts[clip["scene"]] for clip in body
    )
    assert plan["clips"][-1]["role"] == "payoff"


def test_hook_explanation_quotes_observed_text_and_names_alternatives():
    scenes = rich_scenes(30)
    scenes[12].update({
        "hook": 99.0,
        "score": 91.0,
        "speech": "the secret nobody tells you",
        "ocr": "STOP SCROLLING",
        "face": True,
        "subject": True,
        "tags": ["face", "motion"],
    })
    plan = pipeline.build_plan(scenes, source_duration=120.0, target=30)
    hook = plan["reasoning"]["hook"]

    assert plan["hook_scene"] == 12
    assert "the secret nobody tells you" in plan["hook_why"]
    assert "STOP SCROLLING" in plan["hook_why"]
    assert "face in frame" in plan["hook_why"]
    assert "rank 1 of 30" in hook["headline"]
    assert any("the secret nobody tells you" in item for item in hook["evidence"])
    assert any("STOP SCROLLING" in item for item in hook["evidence"])
    assert len(hook["alternatives"]) == 3
    assert all(alt["why_not"] for alt in hook["alternatives"])


def test_explicit_hook_alternative_says_why_higher_scores_lost():
    scenes = rich_scenes(30)
    plan = pipeline.build_plan(
        scenes, source_duration=120.0, target=30,
        hook_id=3, auto_hook_id=29,
    )
    hook = plan["reasoning"]["hook"]

    assert plan["hook_scene"] == 3
    assert plan["auto"] is False
    assert "requested opening" in hook["headline"]
    assert hook["alternatives"]
    assert any("requested" in alt["why_not"] for alt in hook["alternatives"])
    assert any("higher hook score" in alt["why_not"] for alt in hook["alternatives"])
    json.dumps(plan, allow_nan=False)


def test_payoff_explanation_is_evidence_backed_and_late():
    scenes = rich_scenes(40)
    scenes[37].update({
        "score": 98.0,
        "speech": "and that changed everything",
        "face": True,
        "tags": ["face", "motion"],
    })
    plan = pipeline.build_plan(scenes, source_duration=160.0, target=30)
    payoff = plan["reasoning"]["payoff"]

    assert "late beat" in plan["payoff_why"]
    assert "and that changed everything" in plan["payoff_why"]
    assert "end-aligned" in plan["payoff_why"]
    assert payoff["position_pct"] >= 90.0
    assert payoff["late_zone_pct"] == 68.0
    assert any("and that changed everything" in item for item in payoff["evidence"])
    assert any("face in frame" in item for item in payoff["evidence"])
    assert "late candidate" in payoff["why_late"]
    assert plan["clips"][-1]["role"] == "payoff"
    assert plan["clips"][-1]["scene"] == 37


def test_missing_speech_and_ocr_stays_truthful():
    scenes = [
        make_scene(index, index * 3.0, 3.0, hook=40 + index, score=40 + index)
        for index in range(30)
    ]
    plan = pipeline.build_plan(scenes, source_duration=90.0, target=30)
    strings = [plan["hook_why"], plan["payoff_why"] or ""]
    strings.extend(clip["why"] for clip in plan["clips"])
    reasoning = plan["reasoning"]
    strings.extend(reasoning["hook"]["evidence"])
    strings.extend(reasoning["payoff"]["evidence"])
    strings.extend(reasoning["selection"]["evidence"])
    for item in reasoning["selection"]["kept"]:
        strings.extend(item["evidence"])
        strings.append(item["why"])

    assert all(item for item in strings)
    assert all('"' not in item for item in strings)
    assert all("spoken line" not in item for item in strings)
    assert "speech or on-screen text in 0 of" in " ".join(
        reasoning["selection"]["evidence"]
    )
    assert "no speech or on-screen text in the read signals" in plan["hook_why"]


def test_tiny_source_returns_a_graceful_plan():
    scenes = [
        make_scene(index, index * 0.3, 0.3, hook=30 + index, score=30 + index)
        for index in range(3)
    ]
    plan = pipeline.build_plan(scenes, source_duration=0.9, target=30)
    reasoning = plan["reasoning"]

    assert plan["clips"]
    assert plan["total"] == pytest.approx(0.3)
    assert plan["note"]
    assert all(clip["why"] for clip in plan["clips"])
    assert reasoning["summary"]
    assert reasoning["hook"]["headline"]
    assert reasoning["hook"]["evidence"]
    assert reasoning["structure"]["roles"] == [clip["role"] for clip in plan["clips"]]
    assert reasoning["payoff"]["position_pct"] is None
    assert reasoning["payoff"]["why_late"]
    assert reasoning["payoff"]["evidence"]
    assert reasoning["payoff"]["headline"].startswith("No payoff beat")
    json.dumps(plan, allow_nan=False)


def test_all_black_source_is_explained_not_dropped():
    scenes = [
        make_scene(
            index, index * 1.0, 1.0, hook=30 + index, score=30 + index,
            black=True, tags=["black"],
        )
        for index in range(5)
    ]
    plan = pipeline.build_plan(scenes, source_duration=5.0, target=15)
    reasoning = plan["reasoning"]

    assert plan["clips"]
    assert "No clean beat was available" in reasoning["selection"]["strategy"]
    assert "5 black-flagged beats" in " ".join(reasoning["selection"]["evidence"])
    assert all("black frame flagged" in clip["why"] for clip in plan["clips"])
    assert reasoning["payoff"]["why_late"]
    json.dumps(plan, allow_nan=False)


def test_freeze_source_is_flagged_and_still_planned():
    scenes = [
        make_scene(
            index, index * 2.0, 2.0, hook=30 + index, score=30 + index,
            freeze=True, motion_score=1.0, tags=["freeze"],
        )
        for index in range(8)
    ]
    plan = pipeline.build_plan(scenes, source_duration=16.0, target=15)
    reasoning = plan["reasoning"]

    assert plan["clips"]
    assert any(
        "freeze-flagged" in item or "freeze flagged" in item
        for item in reasoning["selection"]["evidence"]
    )
    assert all("freeze flagged" in clip["why"] for clip in plan["clips"])
    json.dumps(plan, allow_nan=False)


def test_empty_scene_list_returns_a_complete_empty_plan():
    plan = pipeline.build_plan([], source_duration=0.0, target=30)
    reasoning = plan["reasoning"]

    assert plan["clip_count"] == 0
    assert plan["clips"] == []
    assert plan["hook_why"] is None
    assert plan["payoff_why"] is None
    assert reasoning["summary"]
    assert reasoning["hook"]["evidence"] == []
    assert reasoning["structure"]["why"]
    assert reasoning["payoff"]["why_late"] is None
    assert reasoning["selection"]["kept"] == []
    assert reasoning["selection"]["target_budget"]["target"] == 30
    json.dumps(plan, allow_nan=False)


def test_beat_why_cites_concrete_signals_and_target_fit():
    scenes = rich_scenes()
    plan = pipeline.build_plan(scenes, source_duration=160.0, target=30)
    by_id = {scene["id"]: scene for scene in scenes}
    clip = next(
        item for item in plan["clips"]
        if item["role"] == "beat"
        and by_id[item["scene"]].get("speech")
        and by_id[item["scene"]].get("face")
    )
    scene = by_id[clip["scene"]]
    why = clip["why"]

    assert why.startswith("Bridge beat:")
    assert f"interest {scene['score']:.0f}/100" in why
    assert f"motion {scene['motion_score']:.0f}/100" in why
    assert f'spoken line "{scene["speech"]}"' in why
    assert "face in frame" in why
    assert f"{clip['dur']:.1f}s cut against the 3.8s per-beat budget" in why
    assert "the 30s reel totals" in why
    json.dumps(plan, allow_nan=False)


def test_long_text_quotes_are_clipped_in_explanations():
    long_speech = " ".join(f"word{index}" for index in range(30))
    scenes = rich_scenes(30)
    scenes[10].update({
        "hook": 99.0,
        "speech": long_speech,
        "ocr": "A" * 120,
    })
    plan = pipeline.build_plan(scenes, source_duration=120.0, target=30)

    assert plan["hook_scene"] == 10
    assert "…" in plan["hook_why"]
    assert long_speech not in plan["hook_why"]
    evidence = " ".join(plan["reasoning"]["hook"]["evidence"])
    assert long_speech not in evidence
    assert "A" * 120 not in evidence
    json.dumps(plan, allow_nan=False)


def test_make_plans_adds_reasoning_to_every_target():
    plans = pipeline.make_plans(
        rich_scenes(), source_duration=160.0, hook_id=None, auto_hook_id=None,
    )
    assert set(plans) == {"15", "30", "60"}
    for target, plan in plans.items():
        assert plan["target"] == int(target)
        assert plan["reasoning"]["target"] == int(target)
        assert plan["reasoning"]["selection"]["target_budget"]["target"] == int(target)
        assert plan["reasoning"]["summary"]
        json.dumps(plan, allow_nan=False)


def test_reasoning_does_not_invent_face_or_motion_evidence():
    scenes = [
        make_scene(
            index,
            index * 3.0,
            3.0,
            hook=40 + index,
            score=40 + index,
            face=False,
            subject=False,
            tags=[],
        )
        for index in range(30)
    ]
    plan = pipeline.build_plan(scenes, source_duration=90.0, target=30)
    reasoning = plan["reasoning"]
    strings = [
        plan["hook_why"],
        plan["payoff_why"] or "",
        reasoning["summary"],
    ]
    for section in ("hook", "payoff"):
        strings.extend(reasoning[section]["evidence"])
        strings.append(reasoning[section]["headline"])
    strings.extend(reasoning["selection"]["evidence"])
    strings.extend(clip["why"] for clip in plan["clips"])
    joined = " ".join(strings).lower()

    assert "face in frame" not in joined
    assert "clear salient subject" not in joined
    assert "strong movement" not in joined
    assert "freeze" not in joined
    assert "face or clear subject in 0 of" in joined
    assert "strong-motion tag in 0 of" in joined


def test_requested_hook_summary_does_not_claim_score_ranking():
    scenes = rich_scenes(30)
    plan = pipeline.build_plan(
        scenes, source_duration=120.0, target=30,
        hook_id=3, auto_hook_id=29,
    )

    summary = plan["reasoning"]["summary"]

    assert "uses the requested opening" in summary
    assert "ranks the hook by hook score" not in summary
