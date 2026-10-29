"""Lanes share no port or data folder (docs/branching.md)."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _lane(name):
    out = subprocess.run(
        ["bash", "-c", f'source scripts/lane.sh && lane_env {name} && echo "$LANE_PORT|$LANE_EDITION|$LANE_FEATURES|$LANE_DATA"'],
        cwd=ROOT, capture_output=True, text=True,
    )
    return out.returncode, out.stdout.strip(), out.stderr


def test_each_lane_has_its_own_port_and_switches():
    lanes = {name: _lane(name)[1].split("|") for name in ("studio", "classic", "voice-room")}
    assert lanes["studio"][:3] == ["8795", "all", "voice_room"]
    assert lanes["classic"][:3] == ["8796", "classic", ""]
    assert lanes["voice-room"][:3] == ["8797", "classic", "voice_room"]
    assert len({lane[0] for lane in lanes.values()}) == 3
    assert all(lane[3].endswith("/data") for lane in lanes.values())


def test_main_is_not_a_lane():
    code, _out, err = _lane("main")
    assert code != 0 and "not a lane" in err


def test_only_studio_moves_main_and_integrates():
    ship = (ROOT / "scripts" / "ship.sh").read_text()
    assert 'if [[ "$branch" != "studio" ]]' in ship and "merge --ff-only studio" in ship
    assert "origin/main" not in ship
    integrate = (ROOT / "scripts" / "integrate.sh").read_text()
    assert "origin/classic" in integrate and "origin/voice-room" in integrate
    assert 'Only the studio lane integrates' in integrate
