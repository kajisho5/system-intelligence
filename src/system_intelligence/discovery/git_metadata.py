"""Git metadata collection (R2, docs/design/docs/05-analysis-engine.md "Lifecycle").

Uses the `git` CLI with fixed argv and no shell, never on user-controlled
strings — the only untrusted input is the repository path itself, which is
passed as `cwd`, not interpolated into a command line.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind


@dataclass(frozen=True)
class GitMetadata:
    is_git_repository: bool
    default_branch: str | None = None
    remote_url: str | None = None
    last_commit_sha: str | None = None
    last_commit_author: str | None = None
    last_commit_date: str | None = None
    is_dirty: bool | None = None
    evidence: list[Evidence] = field(default_factory=list)


def _run_git(repo_path: Path, *args: str) -> str | None:
    git_path = shutil.which("git")
    if git_path is None:
        return None
    # Fixed argv, no shell, only trusted git subcommands passed by this module.
    result = subprocess.run(  # nosec B603
        [git_path, *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def collect_git_metadata(repo_path: Path) -> GitMetadata:
    """Collect git metadata for `repo_path`, if it is a git working tree.

    Every populated field is backed by an `Evidence` record with
    `Confidence.VERIFIED`, since each is a direct `git` command observation
    rather than an inference.
    """
    is_repo = _run_git(repo_path, "rev-parse", "--is-inside-work-tree") == "true"
    if not is_repo:
        return GitMetadata(is_git_repository=False)

    evidence: list[Evidence] = []

    def _observe(observation: str, locator: str) -> None:
        evidence.append(
            Evidence(
                kind=EvidenceKind.GIT_METADATA,
                source=str(repo_path),
                locator=locator,
                observation=observation,
                confidence=Confidence.VERIFIED,
            )
        )

    branch = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        _observe(f"current branch is {branch!r}", "git rev-parse --abbrev-ref HEAD")

    remote_url = _run_git(repo_path, "remote", "get-url", "origin")
    if remote_url:
        _observe(f"remote 'origin' is {remote_url!r}", "git remote get-url origin")

    last_sha = _run_git(repo_path, "log", "-1", "--format=%H")
    last_author = _run_git(repo_path, "log", "-1", "--format=%an")
    last_date = _run_git(repo_path, "log", "-1", "--format=%cI")
    if last_sha:
        _observe(f"last commit is {last_sha}", "git log -1")

    status = _run_git(repo_path, "status", "--porcelain")
    is_dirty = bool(status) if status is not None else None
    if is_dirty is not None:
        _observe(
            "working tree has uncommitted changes" if is_dirty else "working tree is clean",
            "git status --porcelain",
        )

    return GitMetadata(
        is_git_repository=True,
        default_branch=branch or None,
        remote_url=remote_url or None,
        last_commit_sha=last_sha or None,
        last_commit_author=last_author or None,
        last_commit_date=last_date or None,
        is_dirty=is_dirty,
        evidence=evidence,
    )
