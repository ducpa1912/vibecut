"""Admin-selected workflow routes must reach the provider calls."""

from __future__ import annotations

import audio


def _settings(routes, reasoning="medium"):
    return {
        "workflows": {
            name: {
                "routes": routes,
                "reasoning": reasoning,
                "max_output_tokens": 1234,
                "timeout_s": 45,
            }
            for name in ("story_brief", "rewrite", "translate", "hook_rank")
        }
    }


def test_workflow_text_passes_route_model_and_falls_back(monkeypatch):
    calls = []
    monkeypatch.setattr(audio.settings_store, "load_settings", lambda: _settings([
        {"provider": "opencode-go", "model": "first-model"},
        {"provider": "openrouter", "model": "second-model"},
    ]))
    monkeypatch.setattr(audio, "_pipeline_event", lambda *args, **kwargs: None)

    def fake_opencode(prompt, **kwargs):
        calls.append(("opencode", kwargs))
        return None

    def fake_openrouter(prompt, **kwargs):
        calls.append(("openrouter", kwargs))
        return "answer"

    monkeypatch.setattr(audio, "_opencode_text", fake_opencode)
    monkeypatch.setattr(audio, "_openrouter_text", fake_openrouter)

    result = audio._workflow_text("rewrite", "prompt", json_mode=True)

    assert result == "answer"
    assert calls[0][0] == "opencode"
    assert calls[0][1]["model"] == "first-model"
    assert calls[0][1]["variant"] == "medium"
    assert calls[0][1]["max_tokens"] == 1234
    assert calls[0][1]["timeout"] == 45
    assert calls[1][0] == "openrouter"
    assert calls[1][1]["model"] == "second-model"
    assert calls[1][1]["reasoning"] == "medium"


def test_workflow_text_uses_only_configured_routes(monkeypatch):
    monkeypatch.setattr(audio.settings_store, "load_settings", lambda: _settings([
        {"provider": "openrouter", "model": "only-model"},
    ]))
    monkeypatch.setattr(audio, "_pipeline_event", lambda *args, **kwargs: None)
    called = []
    monkeypatch.setattr(audio, "_opencode_text", lambda *args, **kwargs: called.append("opencode"))
    monkeypatch.setattr(audio, "_openrouter_text", lambda *args, **kwargs: "ok")

    assert audio._workflow_text("story_brief", "prompt") == "ok"
    assert called == []


def test_rewrite_plan_maps_admin_routes_and_keeps_rules_last():
    plan = audio._rewrite_workflow_plan()
    names = [item["name"] for item in plan]
    assert names[-1] == "rules"
    assert "opencode" in names
    assert "openrouter" in names
