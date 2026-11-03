"""Signatures: the lane verifier must pass signed commits without a global Git setting.

`git verify-commit` only checks an SSH signature when gpg.ssh.allowedSignersFile
is configured. On a Mac without that setting every signed commit looks unsigned,
so scripts/ship-lane.sh used to fail and scripts/release.sh used to refuse to
tag. scripts/verify-signatures.sh supplies the tracked allowed-signers file
itself; these tests prove the signed path and the unsigned path in a throwaway
repository, not on the real lane.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify-signatures.sh"
SIGNERS = ROOT / "scripts" / "allowed_signers"

needs_ssh = pytest.mark.skipif(
    not (shutil.which("ssh-keygen") and shutil.which("git")),
    reason="git and ssh-keygen are needed for the signature test",
)


def _run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "lane"
    repo.mkdir()
    key = tmp_path / "signing"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "lane@test", "-f", str(key)],
        check=True,
        capture_output=True,
    )
    git = ["git", "-C", str(repo)]
    subprocess.run([*git, "init", "-q"], check=True, capture_output=True)
    for name, value in (
        ("user.name", "Lane Test"),
        ("user.email", "lane@test"),
        ("gpg.format", "ssh"),
        ("user.signingkey", str(key) + ".pub"),
        ("commit.gpgsign", "true"),
    ):
        subprocess.run([*git, "config", name, value], check=True, capture_output=True)

    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run([*git, "add", "a.txt"], check=True, capture_output=True)
    subprocess.run([*git, "commit", "-q", "-m", "signed"], check=True, capture_output=True)

    subprocess.run([*git, "config", "commit.gpgsign", "false"], check=True, capture_output=True)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    subprocess.run([*git, "commit", "-q", "-am", "unsigned"], check=True, capture_output=True)

    signers = tmp_path / "allowed_signers"
    signers.write_text(
        f"lane@test {key.with_suffix('.pub').read_text(encoding='utf-8').strip()}\n",
        encoding="utf-8",
    )
    return repo, signers


@needs_ssh
def test_the_verifier_passes_a_signed_commit_that_plain_git_cannot_check(tmp_path):
    repo, signers = _repo(tmp_path)

    # Without the allowed-signers setting Git reports the signed commit as
    # unverified; that is the bug this script exists for.
    plain = _run(["git", "verify-commit", "HEAD~1"], repo)
    assert plain.returncode != 0

    env = {"PATH": "/usr/bin:/bin", "VIBECUT_ALLOWED_SIGNERS": str(signers)}
    result = _run([str(VERIFY), "--commit", "HEAD~1"], repo, env)

    assert result.returncode == 0, result.stderr
    assert "Signed: 1" in result.stdout


@needs_ssh
def test_the_verifier_fails_an_unsigned_commit(tmp_path):
    repo, signers = _repo(tmp_path)

    env = {"PATH": "/usr/bin:/bin", "VIBECUT_ALLOWED_SIGNERS": str(signers)}
    result = _run([str(VERIFY), "--commit", "HEAD"], repo, env)

    assert result.returncode == 1
    assert "not signed by an allowed key" in result.stderr
    assert "VIBECUT_ALLOW_UNSIGNED" in result.stderr


@needs_ssh
def test_a_recorded_exception_is_named_and_skipped(tmp_path):
    repo, signers = _repo(tmp_path)
    short = _run(["git", "rev-parse", "--short", "HEAD"], repo).stdout.strip()

    env = {
        "PATH": "/usr/bin:/bin",
        "VIBECUT_ALLOWED_SIGNERS": str(signers),
        "VIBECUT_SIGN_EXCEPTIONS": f"732254a {short}",
    }
    result = _run([str(VERIFY), "--range", "HEAD~1..HEAD"], repo, env)

    assert result.returncode == 0, result.stderr
    assert "exceptions: 1" in result.stdout
    assert "failed: 0" in result.stdout


@needs_ssh
def test_the_verifier_rejects_a_signature_from_another_key(tmp_path):
    repo, signers = _repo(tmp_path)
    other = tmp_path / "other"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "other@test", "-f", str(other)],
        check=True,
        capture_output=True,
    )
    signers.write_text(
        f"lane@test {other.with_suffix('.pub').read_text(encoding='utf-8').strip()}\n",
        encoding="utf-8",
    )

    env = {"PATH": "/usr/bin:/bin", "VIBECUT_ALLOWED_SIGNERS": str(signers)}
    result = _run([str(VERIFY), "--commit", "HEAD~1"], repo, env)

    assert result.returncode == 1


def test_the_tracked_signers_file_names_both_lane_keys():
    text = SIGNERS.read_text(encoding="utf-8")
    principals = [
        line.split()[0]
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert principals, "the allowed_signers file has no keys"
    assert set(principals) == {"ducpham1912@gmail.com"}
    # Two keys sign this lane's history; both must stay allowed.
    assert text.count("ssh-ed25519 ") == 2


def test_shipping_and_releasing_use_the_verifier():
    ship = (ROOT / "scripts" / "ship-lane.sh").read_text(encoding="utf-8")
    release = (ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")
    assert "verify-signatures.sh" in ship
    assert "git verify-commit HEAD" not in ship
    assert "verify-signatures.sh\" --range" in release
    assert "verify-signatures.sh\" --tag" in release
    assert "verify-tag \"$tag\" >/dev/null" not in release
