"""One set of lane scripts; lanes share no port or data folder (docs/branching.md)."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _env(*args, root="/lanes"):
    out = subprocess.run(
        ["bash", str(SCRIPTS / "lane-env.sh"), *args],
        cwd=ROOT, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "VIBECUT_LANE_ROOT": root},
    )
    values = {}
    for line in out.stdout.splitlines():
        key, _, value = line.removeprefix("export ").partition("=")
        values[key] = value
    return out.returncode, values, out.stderr


def test_each_lane_has_its_own_port_data_and_switches():
    lanes = {name: _env(name)[1] for name in ("studio", "classic", "voice")}
    assert lanes["studio"]["VIBECUT_PORT"] == "8795"
    assert (lanes["studio"]["VIBECUT_EDITION"], lanes["studio"]["VIBECUT_FEATURES"]) == ("studio", "voice_room")
    assert lanes["classic"]["VIBECUT_PORT"] == "8796"
    assert (lanes["classic"]["VIBECUT_EDITION"], lanes["classic"]["VIBECUT_FEATURES"]) == ("classic", "")
    assert lanes["voice"]["VIBECUT_PORT"] == "8797"
    assert (lanes["voice"]["VIBECUT_EDITION"], lanes["voice"]["VIBECUT_FEATURES"]) == ("classic", "voice_room")
    assert [lanes[name]["VIBECUT_DATA"] for name in ("studio", "classic", "voice")] == [
        "/lanes/studio", "/lanes/classic", "/lanes/voice",
    ]
    assert lanes["voice"]["VIBECUT_LANE_MEDIA"] == "/lanes/media/voiceroom"
    assert lanes["studio"]["VIBECUT_LANE_RECORDINGS"] == "/lanes/recordings/studio"
    assert all("8787" not in "".join(values.values()) for values in lanes.values())


def test_voice_room_alias_and_unknown_lanes():
    assert _env("voice-room")[1]["VIBECUT_LANE"] == "voice"
    code, _values, err = _env("main")
    assert code != 0 and "not a lane" in err


def test_the_branch_names_the_lane_when_no_lane_is_given():
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    code, values, _err = _env()
    if branch == "studio":
        assert code == 0 and values["VIBECUT_LANE"] == "studio"


def test_one_set_of_scripts():
    assert not (SCRIPTS / "lane.sh").exists()
    for name in ("serve.sh", "record.sh"):
        text = (SCRIPTS / name).read_text()
        assert "lane-env.sh" in text, name
        assert "source scripts/lane.sh" not in text, name
    for name in ("serve-studio.sh", "serve-classic.sh"):
        assert (SCRIPTS / name).is_file(), name
    serve = (SCRIPTS / "serve.sh").read_text()
    assert 'legacy="$PWD/data"' in serve and 'mv "$legacy" "$VIBECUT_DATA"' in serve
    assert "VIBECUT_LANE_RECORDINGS" in (SCRIPTS / "record.sh").read_text()


def test_only_studio_moves_main_and_products_do_not_merge_at_release():
    ship = (SCRIPTS / "ship.sh").read_text()
    assert 'if [[ "$branch" != "studio" ]]' in ship and "merge --ff-only studio" in ship
    assert "origin/main" not in ship
    lane = (SCRIPTS / "ship-lane.sh").read_text()
    assert "refs/heads/main" not in lane and "merge --ff-only" not in lane
    assert not (SCRIPTS / "integrate.sh").exists()
    assert 'exec python3 studio_app.py' in (SCRIPTS / "serve-studio.sh").read_text()
    assert 'exec python3 classic_app.py' in (SCRIPTS / "serve-classic.sh").read_text()
