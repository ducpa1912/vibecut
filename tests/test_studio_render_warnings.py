"""Phase B 2: Finish shows the warnings a render recorded."""

from __future__ import annotations

import artifacts
import app
from fastapi.testclient import TestClient
from test_artifacts import base_spec, env, make_artifact  # noqa: F401
from test_r3_t2_library_static import STUDIO, needs_node, run_module


def test_public_manifest_carries_render_warnings():
    manifest = artifacts.make_manifest("job1", base_spec(), status="ready")
    manifest["render"] = {
        "warnings": [" Music bed skipped: no track ", "", "Music bed skipped: no track", 7],
    }
    value = artifacts.public_manifest(manifest, "job1")
    assert value["warnings"] == ["Music bed skipped: no track", "Music bed skipped: no track", "7"]


def test_public_manifest_has_no_warnings_without_render_info():
    manifest = artifacts.make_manifest("job1", base_spec(), status="ready")
    assert artifacts.public_manifest(manifest, "job1")["warnings"] == []


def test_artifacts_route_returns_the_saved_render_warnings(env):
    manifest = make_artifact(env, base_spec())
    manifest["render"] = {"warnings": ["Music bed skipped: test"]}
    artifacts.save_manifest(env.directory, manifest)

    body = TestClient(app.app).get(f"/api/jobs/{env.job_id}/artifacts").json()
    row = next(
        item for item in body["artifacts"]
        if item["artifact_id"] == manifest["artifact_id"]
    )
    assert row["warnings"] == ["Music bed skipped: test"]


@needs_node
def test_render_warnings_trim_dedupe_and_cap():
    out = run_module("finish.js", """
        return [
          m.renderWarnings({warnings: [" Music bed skipped: test ", "", "Music bed skipped: test",
            "Second", "Third", "Fourth"]}),
          m.renderWarnings({render: {warnings: ["Nested warning"]}}),
          m.renderWarnings({warnings: [], render: {warnings: ["Fallback"]}}),
          m.renderWarnings(undefined),
        ];
    """)
    assert out == [
        ["Music bed skipped: test", "Second", "Third"],
        ["Nested warning"],
        ["Fallback"],
        [],
    ]


def test_versions_card_uses_render_warnings():
    finish = (STUDIO / "finish.js").read_text(encoding="utf-8")
    assert "for (const warning of renderWarnings(item))" in finish
    assert "renderWarnings(selectedRow)" in finish
