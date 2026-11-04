"""App profiles: what each product pins from the shared backend.

This is intentionally a composition contract, not a second application graph.
Feature modules remain at the repository root until they earn a deeper move;
each app still imports the same tested core and includes only its profile
routers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .version import CONTRACT_VERSION, CORE_VERSION

PROFILE_VERSION = 1


@dataclass(frozen=True)
class AppProfile:
    id: str
    label: str
    port: int
    data_folder: str
    edition: str
    page: str
    features: frozenset[str]
    routers: frozenset[str]
    core_version: str = CORE_VERSION
    contract_version: int = CONTRACT_VERSION

    def feature(self, name: str) -> bool:
        return name in self.features

    def router(self, name: str) -> bool:
        return name in self.routers


STUDIO = AppProfile(
    id="studio",
    label="Studio",
    port=8795,
    data_folder="studio",
    edition="studio",
    page="studio",
    features=frozenset({
        "studio_page", "studio_edit", "voice_clone", "library", "check",
        "cleanup", "batches", "music", "auto_subs", "packet", "preflight",
    }),
    routers=frozenset({
        "studio_edit", "voice_clone", "library", "check", "cleanup",
        "batches", "music", "auto_subs", "packet", "preflight",
    }),
)

CLASSIC = AppProfile(
    id="classic",
    label="Classic",
    port=8796,
    data_folder="classic",
    edition="classic",
    page="classic",
    features=frozenset({
        "classic_page", "check", "cleanup", "batches", "music", "auto_subs",
        "packet", "preflight", "voice_clone",
    }),
    routers=frozenset({
        "classic_page", "voice_clone", "check", "cleanup", "batches",
        "music", "auto_subs", "packet", "preflight",
    }),
)

LEGACY = AppProfile(
    id="legacy",
    label="Legacy shared app",
    port=8787,
    data_folder="",
    edition="all",
    page="edition",
    features=frozenset({
        "studio_page", "studio_edit", "classic_page", "voice_clone",
        "voice_room_page", "library", "check", "cleanup", "batches", "music",
        "auto_subs", "packet", "preflight",
    }),
    routers=frozenset({
        "studio_edit", "classic_page", "voice_clone", "library", "check",
        "cleanup", "batches", "music", "auto_subs", "packet", "preflight",
    }),
)

PROFILES = {"studio": STUDIO, "classic": CLASSIC, "legacy": LEGACY}


def active_profile(app_id: str | None = None) -> AppProfile:
    value = str(app_id if app_id is not None else os.environ.get("VIBECUT_APP", ""))
    return PROFILES.get(value.strip().lower(), LEGACY)


def configure(profile: AppProfile, *, data_root: Path | str | None = None) -> AppProfile:
    """Set the app identity before importing the shared backend."""
    os.environ["VIBECUT_APP"] = profile.id
    os.environ["VIBECUT_EDITION"] = profile.edition
    os.environ["VIBECUT_FEATURES"] = "voice_room" if profile.id == "studio" else ""
    os.environ.setdefault("VIBECUT_PORT", str(profile.port))
    if data_root is not None:
        os.environ.setdefault("VIBECUT_DATA", str(data_root))
    elif profile.data_folder:
        os.environ.setdefault(
            "VIBECUT_DATA",
            str(Path.home() / "vibecut-lanes" / profile.data_folder),
        )
    return profile


def feature_names(profiles: Iterable[AppProfile] = PROFILES.values()) -> set[str]:
    return {name for profile in profiles for name in profile.features}
