"""Stable feature contract shared by app profiles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureContract:
    id: str
    version: str
    requires_core: str
    api: str


class FeatureContractError(RuntimeError):
    """A pinned feature cannot run against this core."""
