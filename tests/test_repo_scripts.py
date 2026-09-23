"""Tests for repo maintenance scripts in scripts/.

These tests do not exercise any integration code, so when this file is run
on its own (`pytest tests/test_repo_scripts.py`) the project's 80% coverage
gate will fail with a misleading 0% report. Always run via the full suite
(`pytest tests/`) in CI and locally, or pass `--no-cov` explicitly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import custom_components.dimplex  # noqa: F401  (see module docstring)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_check_translation_parity_runs() -> None:
    """Parity script must run and either pass or fail with a clear message.

    The dev tree may legitimately have parity drift (e.g. when adding a new
    translation key in en.json before back-porting it). The test asserts the
    script runs cleanly (exit 0 or 1, well-formed output) rather than
    crashing. Concrete parity enforcement is the CI step's job.
    """
    result = _run("check-translation-parity.sh")
    assert result.returncode in (0, 1), (
        f"unexpected exit code {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The script should always print a per-language line that starts with ✓ or ✗.
    assert any(line.startswith(("✓", "✗")) for line in result.stdout.splitlines()), (
        f"no per-language status line in output:\n{result.stdout}"
    )


def test_check_md_alerts_passes() -> None:
    """Every GitHub alert in tracked Markdown must be renderable as a callout.

    A marker that is not alone on its line, or not inside a blockquote, renders
    as literal text with no warning from GitHub — see the script's header.
    """
    result = _run("check-md-alerts.sh")
    assert result.returncode == 0, f"broken GitHub alert:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "✓" in result.stdout


@pytest.mark.parametrize(
    "script",
    [
        "check-translation-parity.sh",
        "check-md-alerts.sh",
        "setup-repo-metadata.sh",
        "test-hacs-zip.sh",
        "compute-pr-dev-version.sh",
        "compute-main-dev-version.sh",
        "create-main-rc-release.sh",
    ],
)
def test_scripts_are_executable(script: str) -> None:
    """Maintenance scripts must have the executable bit set so CI can run them."""
    path = REPO_ROOT / "scripts" / script
    assert path.exists(), f"missing {path}"
    assert path.stat().st_mode & 0o111, f"{path} is not executable"


# ---------------------------------------------------------------------------
# dev-release output computation (KRoperUK/dimplex-controller-hass#235)
# ---------------------------------------------------------------------------
#
# The dev-release jobs used to build their `$GITHUB_OUTPUT` inline in ci.yml,
# where nothing exercised them: scripts/test-dev-version-scripts.sh covers the
# scripts the workflow *calls*, and actionlint runs shellcheck over the `run:`
# blocks, which is syntax and style rather than behaviour. All of it runs only
# on a release — RC numbering, the rollover when a tag is already reserved, and
# the "already fully released, prune the RCs" branch — so a mistake in it
# survives every green CI run and first shows up when a release is cut.
#
# The shell now lives in scripts/compute-{pr,main}-dev-version.sh and
# scripts/create-main-rc-release.sh. A `gh` double plus a throwaway git remote
# drive the paths that talk to GitHub.

_GH_STUB = """#!/usr/bin/env bash
# Minimal gh(1) double for tests/test_repo_scripts.py. Fixtures in $STUB_STATE
# decide the answers; every call is appended to $STUB_STATE/calls.log.
set -uo pipefail

printf '%s\\n' "$*" >> "${STUB_STATE}/calls.log"
cmd="${1:-}"
shift || true

case "$cmd" in
  release)
    sub="${1:-}"
    shift || true
    case "$sub" in
      view)
        grep -Fxq "${1:-}" "${STUB_STATE}/release_view" ;;
      list)
        cat "${STUB_STATE}/release_list" ;;
      delete)
        printf '%s\\n' "${1:-}" >> "${STUB_STATE}/deleted" ;;
      create)
        tag="${1:-}"
        if [ -f "${STUB_STATE}/create_fail/${tag}" ]; then
          cat "${STUB_STATE}/create_fail/${tag}" >&2
          exit 1
        fi
        printf '%s\\n' "$tag" >> "${STUB_STATE}/created" ;;
      *)
        printf 'gh stub: unhandled release subcommand: %s\\n' "$sub" >&2
        exit 2 ;;
    esac
    ;;
  api)
    path="${1:-}"
    shift || true
    jq_expr=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --jq)
          jq_expr="${2:-}"
          shift 2
          ;;
        *) shift ;;
      esac
    done
    case "$path" in
      */releases/latest)
        cat "${STUB_STATE}/latest" ;;
      */git/matching-refs/tags/*)
        cat "${STUB_STATE}/matching_refs" ;;
      */git/ref/tags/*)
        if [ "$jq_expr" = ".object.type" ]; then
          printf 'commit\\n'
        else
          git --git-dir="${STUB_ORIGIN}" rev-parse "refs/tags/${path##*/git/ref/tags/}"
        fi ;;
      */git/commits/*)
        git --git-dir="${STUB_ORIGIN}" rev-parse "${path##*/git/commits/}^" ;;
      *)
        printf 'gh stub: unhandled api path: %s\\n' "$path" >&2
        exit 2 ;;
    esac
    ;;
  *)
    printf 'gh stub: unhandled command: %s\\n' "$cmd" >&2
    exit 2 ;;
esac
"""

_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    # A collision test must fail rather than block: no credential prompt, and no
    # editor opening on a tag message if the operator's git config signs tags.
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": "true",
}


def _install_gh_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a `gh` double first on PATH and return the directory holding its state."""
    state = tmp_path / "gh-state"
    (state / "create_fail").mkdir(parents=True)
    for name in ("release_list", "release_view", "latest", "matching_refs"):
        (state / name).write_text("")
    (state / "latest").write_text("v3.1.0\n")

    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "gh"
    stub.write_text(_GH_STUB)
    stub.chmod(0o755)

    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("STUB_STATE", str(state))
    monkeypatch.setenv("GITHUB_REPOSITORY", "KRoperUK/dimplex-controller-hass")
    monkeypatch.setenv("GH_TOKEN", "stub-token")
    return state


def _git(cwd: Path, *args: str) -> str:
    """Run git in a throwaway tree, independent of the operator's git config."""
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        env={**os.environ, **_GIT_ENV},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _make_release_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    """A throwaway repo with an `origin` remote that accepts tag pushes.

    Returns (working tree, bare origin, base commit sha). scripts/ is copied in
    so the extracted scripts resolve the repo root to this tree and not the real
    checkout.
    """
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    subprocess.run(
        ["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)],
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ENV},
    )
    work.mkdir()
    _git(tmp_path, "init", "-q", "--initial-branch=main", str(work))

    component = work / "custom_components" / "dimplex"
    component.mkdir(parents=True)
    for name in ("manifest.json", "const.py"):
        shutil.copy(REPO_ROOT / "custom_components" / "dimplex" / name, component / name)
    shutil.copytree(REPO_ROOT / "scripts", work / "scripts")

    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "base")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-q", "origin", "refs/heads/main")
    return work, origin, _git(work, "rev-parse", "HEAD")


def _run_with_env(
    script: str,
    env: dict[str, str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a script with a controlled environment, from the repo or a fake tree.

    Git config is neutralised for the caller too: the operator's global
    `tag.gpgSign` turns the script's `git tag -f` into an annotated tag and opens
    an editor, which is not what a GitHub runner does.
    """
    root = cwd or REPO_ROOT
    return subprocess.run(
        ["bash", str(root / "scripts" / script)],
        cwd=str(root),
        env={**os.environ, **_GIT_ENV, **env},
        capture_output=True,
        text=True,
    )


def _manifest_version() -> str:
    manifest = json.loads((REPO_ROOT / "custom_components/dimplex" / "manifest.json").read_text())
    return str(manifest["version"])


def _set(path: Path, *lines: str) -> None:
    path.write_text("".join(f"{line}\n" for line in lines))


def test_pr_dev_version_writes_exact_outputs(tmp_path: Path) -> None:
    """compute-pr-dev-version.sh writes the four outputs and nothing else.

    The workflow consumes these through `steps.tag.outputs.*`, so a missing or
    extra key is either an empty expression or a silently ignored one.
    """
    out = tmp_path / "out.txt"
    result = _run_with_env(
        "compute-pr-dev-version.sh",
        {
            "SKIPPED": "false",
            "NEXT_VERSION": "3.2.0",
            "HEAD_BRANCH": "feat/x",
            "PR_NUMBER": "77",
            "SHORT_SHA": "abcdef1234567890",
            "RUN_ID": "29215103640-1",
            "GITHUB_OUTPUT": str(out),
        },
    )

    assert result.returncode == 0, result.stderr
    assert out.read_text() == (
        "version=3.2.0-pr.77.abcdef1\ntag=v3.2.0-pr.77.29215103640-1\nbase_version=3.2.0\nbase_sha=abcdef1234567890\n"
    )
    assert result.stdout == "", "PR compute must not print; only $GITHUB_OUTPUT carries the values"


def test_pr_dev_version_falls_back_to_the_manifest_version(tmp_path: Path) -> None:
    """A skipped changelog action leaves NEXT_VERSION empty; the tree's version is used."""
    manifest_version = _manifest_version()
    out = tmp_path / "out.txt"
    result = _run_with_env(
        "compute-pr-dev-version.sh",
        {
            "SKIPPED": "true",
            "NEXT_VERSION": "",
            "HEAD_BRANCH": "feat/x",
            "PR_NUMBER": "77",
            "SHORT_SHA": "abcdef1234567890",
            "RUN_ID": "29215103640-1",
            "GITHUB_OUTPUT": str(out),
        },
    )

    assert result.returncode == 0, result.stderr
    assert out.read_text() == (
        f"version={manifest_version}-pr.77.abcdef1\n"
        f"tag=v{manifest_version}-pr.77.29215103640-1\n"
        f"base_version={manifest_version}\n"
        "base_sha=abcdef1234567890\n"
    )


def test_main_dev_version_numbers_the_rc_past_every_known_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The next RC is one past the highest release *or* tag, and the log stays off stdout's twin.

    The log line sits beside the `$GITHUB_OUTPUT` writes it summarises. Grouping
    those redirects for shellcheck's SC2129 is the obvious tidy-up, and doing it
    carelessly writes the log line into the output file as a sixth key — which
    nothing in CI would notice. Hence the exact-file assertion.
    """
    state = _install_gh_stub(tmp_path, monkeypatch)
    _set(state / "release_list", "v3.2.0-rc.1", "v3.2.0-rc.2", "v3.1.0-rc.9")
    # An orphaned tag left behind by a deleted immutable release still reserves rc.5.
    _set(state / "matching_refs", "refs/tags/v3.2.0-rc.2", "refs/tags/dev-v3.2.0-rc.5")

    out = tmp_path / "out.txt"
    result = _run_with_env(
        "compute-main-dev-version.sh",
        {
            "SKIPPED": "false",
            "NEXT_VERSION": "3.2.0",
            "BASE_SHA": "cafe" * 10,
            "GITHUB_OUTPUT": str(out),
        },
    )

    assert result.returncode == 0, result.stderr
    assert out.read_text() == (
        f"version=3.2.0-rc.6\ntag=v3.2.0-rc.6\nbase_version=3.2.0\nbase_sha={'cafe' * 10}\nrc_number=6\nskip=false\n"
    )
    assert result.stdout == "Next main RC candidate: v3.2.0-rc.6\n"
    assert "Next main RC candidate" not in out.read_text()


def test_main_dev_version_prunes_and_skips_an_already_released_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """vX.Y.Z released means no new RC: prune that line's leftovers and report skip=true.

    Only the RC pre-releases of *this* version may be deleted — an unrelated
    version line's RCs are still candidates for its own next build.
    """
    state = _install_gh_stub(tmp_path, monkeypatch)
    _set(state / "release_view", "v3.2.0")
    _set(state / "release_list", "v3.2.0-rc.1", "v3.2.0-rc.2", "dev-v3.2.0-rc.3", "v3.1.0-rc.9")

    out = tmp_path / "out.txt"
    result = _run_with_env(
        "compute-main-dev-version.sh",
        {
            "SKIPPED": "false",
            "NEXT_VERSION": "3.2.0",
            "BASE_SHA": "cafe" * 10,
            "GITHUB_OUTPUT": str(out),
        },
    )

    assert result.returncode == 0, result.stderr
    assert out.read_text() == "skip=true\n"
    assert set((state / "deleted").read_text().split()) == {
        "v3.2.0-rc.1",
        "v3.2.0-rc.2",
        "dev-v3.2.0-rc.3",
    }
    assert "Full release v3.2.0 exists" in result.stdout


def test_main_rc_release_rolls_over_a_reserved_rc_number(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A tag GitHub refuses as already-reserved increments the RC and retries.

    rc.6 fails with the 422 that a tag left behind by a deleted immutable
    release produces; the loop must delete the tag it just pushed, try rc.7 and
    report the tag it actually created, so the follow-up prune keeps the right one.
    """
    state = _install_gh_stub(tmp_path, monkeypatch)
    work, origin, base_sha = _make_release_repo(tmp_path)
    monkeypatch.setenv("STUB_ORIGIN", str(origin))
    (state / "create_fail" / "v3.2.0-rc.6").write_text(
        "HTTP 422: Validation Failed (tag_name was used by another release)\n"
    )

    out = tmp_path / "out.txt"
    result = _run_with_env(
        "create-main-rc-release.sh",
        {
            "BASE_VERSION": "3.2.0",
            "BASE_SHA": base_sha,
            "RC_NUMBER": "6",
            "CHANGELOG": "",
            "GITHUB_OUTPUT": str(out),
        },
        cwd=work,
    )

    assert result.returncode == 0, result.stderr
    assert out.read_text() == "created_tag=v3.2.0-rc.7\n"
    assert (state / "created").read_text() == "v3.2.0-rc.7\n"
    assert "Tag collision / immutable reservation for v3.2.0-rc.6; rolling over." in result.stdout
    # The abandoned tag was removed, so only the published one is left.
    assert _git(origin, "tag", "-l").split() == ["v3.2.0-rc.7"]


def test_main_rc_release_keeps_a_build_that_already_points_at_this_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running the job for the same commit reuses the existing release.

    The synthetic commit's parent is the base sha, which is what marks the tag
    as this run's build rather than a collision from a previous one.
    """
    state = _install_gh_stub(tmp_path, monkeypatch)
    work, origin, base_sha = _make_release_repo(tmp_path)
    monkeypatch.setenv("STUB_ORIGIN", str(origin))

    _git(work, "commit", "-q", "--allow-empty", "-m", "chore(dev): set version 3.2.0-rc.6")
    synthetic = _git(work, "rev-parse", "HEAD")
    _git(work, "tag", "-f", "v3.2.0-rc.6", synthetic)
    _git(work, "push", "-q", "origin", "refs/tags/v3.2.0-rc.6")
    _set(state / "release_view", "v3.2.0-rc.6")

    out = tmp_path / "out.txt"
    result = _run_with_env(
        "create-main-rc-release.sh",
        {
            "BASE_VERSION": "3.2.0",
            "BASE_SHA": base_sha,
            "RC_NUMBER": "6",
            "CHANGELOG": "",
            "GITHUB_OUTPUT": str(out),
        },
        cwd=work,
    )

    assert result.returncode == 0, result.stderr
    assert out.read_text() == "created_tag=v3.2.0-rc.6\n"
    assert "already built from" in result.stdout
    assert not (state / "created").exists(), "an existing release must not be recreated"


def test_main_rc_release_does_not_roll_over_on_an_unrelated_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a collision rolls over; any other gh failure must fail the job.

    Retrying a permissions or outage error 25 times would hide it behind a
    "exhausted attempts" message and mint tags for every attempt.
    """
    state = _install_gh_stub(tmp_path, monkeypatch)
    work, origin, base_sha = _make_release_repo(tmp_path)
    monkeypatch.setenv("STUB_ORIGIN", str(origin))
    (state / "create_fail" / "v3.2.0-rc.6").write_text("HTTP 500: Internal Server Error\n")

    out = tmp_path / "out.txt"
    result = _run_with_env(
        "create-main-rc-release.sh",
        {
            "BASE_VERSION": "3.2.0",
            "BASE_SHA": base_sha,
            "RC_NUMBER": "6",
            "CHANGELOG": "",
            "GITHUB_OUTPUT": str(out),
        },
        cwd=work,
    )

    assert result.returncode != 0
    assert not out.exists(), "no tag was created, so nothing may be reported"
    assert _git(origin, "tag", "-l").split() == ["v3.2.0-rc.6"]
