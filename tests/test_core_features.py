"""Feature contracts and app composition (Phase 3)."""

from __future__ import annotations

import re
from pathlib import Path

import app
from core.contracts import FeatureContract, FeatureContractError
from core.features import FEATURE_IDS, load_feature, verify_profile
from core.profiles import CLASSIC, LEGACY, STUDIO
from core.version import CORE_VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_every_profile_pins_every_feature_and_versions_match_core():
    for profile in (STUDIO, CLASSIC, LEGACY):
        versions = verify_profile(profile)
        assert set(versions) == set(FEATURE_IDS)
        assert all(version == "1.0.0" for version in versions.values())
        assert profile.core_version == CORE_VERSION


def test_feature_packages_expose_a_contract_and_no_page_code():
    for feature_id in FEATURE_IDS:
        contract = load_feature(feature_id)
        assert isinstance(contract, FeatureContract)
        assert contract.id == feature_id
        assert contract.requires_core == ">=1.0,<2.0"
        source = (ROOT / "features" / feature_id / "__init__.py").read_text(encoding="utf-8")
        assert "static/studio" not in source
        assert "static/classic" not in source
        assert "routes_studio" not in source or feature_id == "voice_clone"


def test_feature_range_gate_rejects_a_future_core(monkeypatch):
    import core.features as features

    monkeypatch.setattr(features, "CORE_VERSION", "2.0.0")
    try:
        features.verify_profile(STUDIO)
    except FeatureContractError as exc:
        assert "needs core" in str(exc)
    else:
        raise AssertionError("future core must be rejected")


def test_health_reports_composed_features():
    assert app.FEATURE_VERSIONS == {
        "ai_fill": "1.0.0",
        "captions": "1.0.0",
        "voice_clone": "1.0.0",
        "url_ingest": "1.0.0",
    }
    from fastapi.testclient import TestClient

    health = TestClient(app.app).get("/api/health").json()
    assert health["features"] == sorted(FEATURE_IDS)
    assert health["feature_versions"] == app.FEATURE_VERSIONS


def test_studio_and_classic_pin_different_route_sets():
    assert "studio_edit" in STUDIO.routers and "classic_page" not in STUDIO.routers
    assert "classic_page" in CLASSIC.routers and "studio_edit" not in CLASSIC.routers
    assert "classic_page" in LEGACY.routers and "studio_edit" in LEGACY.routers
