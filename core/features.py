"""Feature registry and version gate.

Feature packages expose a small public API through ``FEATURE``. An app profile
lists the feature ids it ships; startup verifies every package against the
pinned core range before routes are composed.
"""

from __future__ import annotations

import importlib
import re
from typing import Iterable

from .contracts import FeatureContract, FeatureContractError
from .profiles import AppProfile
from .version import CORE_VERSION

FEATURE_IDS = ("ai_fill", "captions", "voice_clone", "url_ingest")
_VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,2}$")


def _parts(value: str) -> tuple[int, ...]:
    text = str(value or "").strip()
    if not _VERSION_RE.match(text):
        raise FeatureContractError(f"Invalid feature version: {value!r}.")
    return tuple(int(part) for part in text.split("."))


def _satisfies(version: str, spec: str) -> bool:
    current = _parts(version)
    for clause in str(spec or "").split(","):
        clause = clause.strip()
        if not clause:
            continue
        match = re.match(r"^(>=|<=|>|<|==)?\s*(\d+(?:\.\d+){0,2})$", clause)
        if not match:
            raise FeatureContractError(f"Invalid core range: {spec!r}.")
        operator, raw = match.groups()
        wanted = _parts(raw)
        width = max(len(current), len(wanted))
        left = current + (0,) * (width - len(current))
        right = wanted + (0,) * (width - len(wanted))
        if operator in ("", "==") and left != right:
            return False
        if operator == ">=" and left < right:
            return False
        if operator == "<=" and left > right:
            return False
        if operator == ">" and left <= right:
            return False
        if operator == "<" and left >= right:
            return False
    return True


def load_feature(feature_id: str) -> FeatureContract:
    if feature_id not in FEATURE_IDS:
        raise FeatureContractError(f"Unknown feature: {feature_id!r}.")
    module = importlib.import_module(f"features.{feature_id}")
    contract = getattr(module, "FEATURE", None)
    if not isinstance(contract, FeatureContract):
        raise FeatureContractError(f"features.{feature_id} has no FEATURE contract.")
    if contract.id != feature_id:
        raise FeatureContractError(f"features.{feature_id} declares {contract.id!r}.")
    if not _satisfies(CORE_VERSION, contract.requires_core):
        raise FeatureContractError(
            f"{contract.id} {contract.version} needs core {contract.requires_core}; "
            f"this build is {CORE_VERSION}."
        )
    return contract


def verify_profile(profile: AppProfile) -> dict[str, str]:
    """Return feature versions after checking the profile's pinned features."""
    versions: dict[str, str] = {}
    for feature_id in sorted(profile.modules):
        versions[feature_id] = load_feature(feature_id).version
    return versions


def missing(profile: AppProfile, available: Iterable[str] = FEATURE_IDS) -> list[str]:
    known = set(available)
    return sorted(name for name in profile.modules if name not in known)
