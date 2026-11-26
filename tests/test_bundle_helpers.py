import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts/check-bundle-helpers.sh"
APPS = [ROOT / "build/DuckSuite.app", ROOT / "build/DuckSuite-Xcode.app"]


def executable(path, script):
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(0o755)


@pytest.mark.parametrize("fault", ["", "missing ffprobe", "--enable-gpl", "--enable-nonfree", "host link"])
def test_bundle_check(tmp_path, fault):
    helpers = tmp_path / "Test App.app/Contents/Helpers"
    helpers.mkdir(parents=True)
    for tool in ("ffmpeg", "ffprobe"):
        if fault == "missing ffprobe" and tool == "ffprobe":
            continue
        flag = fault if fault.startswith("--") else ""
        executable(helpers / tool, f"echo 'configuration: --enable-libdav1d {flag}'\n")
    (helpers / "libdav1d.7.dylib").touch()
    dep = "/opt/homebrew/lib/bad.dylib" if fault == "host link" else "/usr/lib/libSystem.B.dylib"
    executable(tmp_path / "otool", f'echo "$2:"\necho "  {dep} (compatibility version 1.0.0)"\n')
    result = subprocess.run(
        [CHECK, helpers.parents[1]], capture_output=True, text=True,
        env={**os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"]},
    )
    assert result.returncode == int(bool(fault)), result.stderr


# The PO opens DuckSuite-Xcode.app; agents build DuckSuite.app. Check whichever exists.
@pytest.mark.parametrize("app", APPS, ids=lambda p: p.name)
def test_real_bundle_helpers(app):
    if not app.exists():
        pytest.skip(f"{app.name} has not been built in this checkout")
    subprocess.run([CHECK, app], check=True)
