"""Local git execution adapter: create a branch and commit specific files.

This never touches any remote — no `git push`, no network access at all.
It implements the "create branch"/"create commit" half of
docs/design/docs/11-github-integration.md's "Preferred first write"; the
remote half (pushing that branch and opening a Draft PR) is
`execution.github_pr.open_draft_pr_for_plan`, gated independently — this
module stops at the local-repository boundary on purpose.

Every `apply_plan` call is gated by `policy.evaluate`: this action needs
`PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR` by default, above the read-only
maximum, so nothing is written without a matching `Approval`.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from system_intelligence.core.governance import Approval
from system_intelligence.execution.plan import ChangePlan
from system_intelligence.policy.engine import PolicyDecision, evaluate

_ACTION = "create_local_branch_and_commit"


class LocalGitError(RuntimeError):
    """Raised when a local git operation fails or a plan is unsafe to apply."""


@dataclass(frozen=True)
class ExecutionResult:
    applied: bool
    decision: PolicyDecision
    branch_name: str | None = None
    commit_sha: str | None = None
    files_written: list[str] = field(default_factory=list)


def _run_git(repo_root: Path, *args: str) -> str:
    git_path = shutil.which("git")
    if git_path is None:
        raise LocalGitError("git is not available on PATH")
    # Fixed subcommands defined in this module only; repo_root is used as
    # `cwd`, never interpolated into the argv itself.
    result = subprocess.run(  # nosec B603
        [git_path, *args], cwd=repo_root, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise LocalGitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _validate_relative_path(repo_root: Path, relative_path: str) -> Path:
    """Resolve `relative_path` under `repo_root`, refusing any escape.

    Both a leading '/' (pathlib silently replaces the base with an
    absolute second operand) and '..' traversal are checked via the
    resolved path's ancestry, not the raw string.
    """
    resolved_root = repo_root.resolve()
    candidate = (repo_root / relative_path).resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise LocalGitError(f"Refusing to write outside the repository root: {relative_path!r}")
    return candidate


def apply_plan(
    plan: ChangePlan, repo_root: Path, approvals: list[Approval] | None = None
) -> ExecutionResult:
    """Apply `plan` to the local repository at `repo_root`, if policy allows it.

    Never pushes to any remote. Raises `LocalGitError` for anything that
    would leave the repository in a half-applied state (missing git,
    non-repo directory, an already-existing branch name, an unsafe file
    path) — it does not attempt partial application or silent recovery.
    """
    decision = evaluate(_ACTION, str(repo_root), plan.required_permission_level, approvals)
    if not decision.allowed:
        return ExecutionResult(applied=False, decision=decision)

    if not plan.files:
        raise LocalGitError("ChangePlan.files is empty; nothing to commit")
    if not repo_root.is_dir():
        raise LocalGitError(f"{repo_root} is not a directory")
    try:
        is_work_tree = _run_git(repo_root, "rev-parse", "--is-inside-work-tree") == "true"
    except LocalGitError:
        is_work_tree = False
    if not is_work_tree:
        raise LocalGitError(f"{repo_root} is not a git working tree")

    # Validate every path before touching anything, so an unsafe path is
    # rejected before the branch is even created — never a half-applied plan.
    resolved_paths = {
        relative_path: _validate_relative_path(repo_root, relative_path)
        for relative_path in plan.files
    }

    _run_git(repo_root, "checkout", "-b", plan.branch_name)

    written: list[str] = []
    for relative_path, content in plan.files.items():
        absolute_path = resolved_paths[relative_path]
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_text(content, encoding="utf-8")
        written.append(relative_path)

    _run_git(repo_root, "add", *written)
    _run_git(repo_root, "commit", "-m", plan.commit_message)
    commit_sha = _run_git(repo_root, "rev-parse", "HEAD")

    return ExecutionResult(
        applied=True,
        decision=decision,
        branch_name=plan.branch_name,
        commit_sha=commit_sha,
        files_written=written,
    )
