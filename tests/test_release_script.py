"""scripts/release.sh tags only a shipped, founder-passed classic."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release.sh"

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git is not installed")


def _git(cwd, *args):
    # The developer's global git config may require a signing key. These temp
    # repos are fixtures, so they must not depend on a machine-specific key.
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path, branch="classic"):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", branch)
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    (work / "a.txt").write_text("a")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-q", "-m", "a")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "origin", f"{branch}:{branch}")
    return work, remote


def _release(work, *args, allow_unsigned=True, sign_base=None):
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": str(work)}
    if allow_unsigned:
        env["VIBECUT_ALLOW_UNSIGNED"] = "1"
    if sign_base:
        env["VIBECUT_RELEASE_SIGN_BASE"] = sign_base
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=work, capture_output=True, text=True, env=env)


def test_refuses_without_a_founder_pass(tmp_path):
    work, _remote = _repo(tmp_path)
    result = _release(work)
    assert result.returncode != 0 and "founder test pass" in result.stderr


def test_refuses_other_lanes_and_unshipped_commits(tmp_path):
    work, _remote = _repo(tmp_path, branch="studio")
    assert "classic lane" in _release(work, "--founder-passed").stderr
    (tmp_path / "two").mkdir()
    work2, _remote2 = _repo(tmp_path / "two")
    (work2 / "b.txt").write_text("b")
    _git(work2, "add", "b.txt")
    _git(work2, "commit", "-q", "-m", "b")
    assert "not what GitHub has" in _release(work2, "--founder-passed").stderr


def _shipped_second_commit(work):
    base = _git(work, "rev-parse", "HEAD")
    (work / "b.txt").write_text("b")
    _git(work, "add", "b.txt")
    _git(work, "commit", "-q", "-m", "b")
    _git(work, "push", "-q", "origin", "classic:classic")
    return base


def test_refuses_an_unsigned_release_commit(tmp_path):
    work, _remote = _repo(tmp_path)
    base = _shipped_second_commit(work)
    result = _release(work, "--founder-passed", allow_unsigned=False, sign_base=base)
    assert result.returncode != 0
    assert "Unsigned commits" in result.stderr
    assert f"Range: {base}..HEAD" in result.stdout


def test_the_signature_range_does_not_follow_main(tmp_path):
    work, _remote = _repo(tmp_path)
    base = _shipped_second_commit(work)
    # main moved past classic: a merge-base would now hide the unsigned commit.
    _git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    result = _release(work, "--founder-passed", allow_unsigned=False, sign_base=base)
    assert "Unsigned commits" in result.stderr
    assert f"Range: {base}..HEAD" in result.stdout


def test_an_unknown_signature_base_fails_closed(tmp_path):
    work, _remote = _repo(tmp_path)
    result = _release(work, "--founder-passed", allow_unsigned=False)
    assert result.returncode != 0
    assert "signature base" in result.stderr
    assert "Range:" not in result.stdout
    assert not _git(work, "tag")


def test_the_tracked_signature_base_is_behind_classic():
    root = SCRIPT.parent.parent
    first = (root / "scripts" / "release-signature-base").read_text().splitlines()[0]
    present = subprocess.run(
        ["git", "cat-file", "-e", f"{first}^{{commit}}"], cwd=root,
    )
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=root, capture_output=True, text=True,
    ).stdout.strip() == "true"
    if present.returncode != 0 and shallow:
        pytest.skip(
            "signature base commit is not in this shallow clone; fetch full "
            "history with `git fetch --unshallow` to run this check."
        )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", first, "HEAD"], cwd=root, check=True,
    )


def test_tags_and_pushes_the_shipped_classic(tmp_path):
    work, remote = _repo(tmp_path)
    dry = _release(work, "--founder-passed", "--dry-run")
    assert dry.returncode == 0 and "Would tag" in dry.stdout
    first = _release(work, "--founder-passed")
    assert first.returncode == 0, first.stderr
    second = _release(work, "--founder-passed")
    assert second.returncode == 0, second.stderr
    tags = _git(remote, "tag").split()
    assert len(tags) == 2 and all(tag.startswith("beta-") for tag in tags)
    assert sorted(tag.rsplit("-", 1)[1] for tag in tags) == ["1", "2"]
