"""Remote GitHub write adapter: push a branch and open it as a Draft PR.

The remote half of docs/design/docs/11-github-integration.md's "Preferred
first write" (create branch -> create files/commits -> open Draft PR).
`execution.local_git.apply_plan` implements the first two steps and
deliberately stops at the local repository boundary (see
`execution/__init__.py`'s own docstring on why); this module implements
the third, as its own adapter with its own explicit approval action name
-- `create_draft_pr`, the exact action string `policy`'s own test suite
has used since Phase 1 in anticipation of this.

Gated by the same `policy.evaluate` every other execution adapter goes
through, at `plan.required_permission_level` (`CREATE_BRANCH_OR_DRAFT_PR`
by default -- the same tier as the local-only action, since opening a
Draft PR is no more destructive: it changes nothing on the base branch
and is trivially closeable). Never merges, closes, approves, or
force-pushes -- opening a PR as a draft is the entire scope; nothing here
ever calls those GitHub endpoints, and `core.enums.
FORBIDDEN_BY_DEFAULT_ACTIONS` (merge_pull_request, close_pull_request,
force_push, ...) remains independently enforced by `policy.evaluate`
regardless of any `Approval`.

The branch must already exist locally, created and committed by
`local_git.apply_plan` -- this module never creates a branch or a commit
itself, only pushes one that already exists and opens the PR for it.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system_intelligence.core.governance import Approval
from system_intelligence.execution.plan import ChangePlan
from system_intelligence.policy.engine import PolicyDecision, evaluate

_ACTION = "create_draft_pr"
_API_BASE = "https://api.github.com"
_USER_AGENT = "system-intelligence-execution/0.1"

#: (url, headers, request_body) -> (http_status, response_body)
HttpPost = Callable[[str, dict[str, str], bytes], tuple[int, bytes]]


class GitHubPRError(RuntimeError):
    """Raised when pushing the branch or opening the Draft PR fails."""


@dataclass(frozen=True)
class DraftPullRequest:
    number: int
    html_url: str
    is_draft: bool


@dataclass(frozen=True)
class DraftPRResult:
    applied: bool
    decision: PolicyDecision
    pull_request: DraftPullRequest | None = None


def push_branch(
    repo_root: Path, branch_name: str, *, token: str | None = None, remote: str = "origin"
) -> None:
    """Push `branch_name` to `remote`. Never force-pushes.

    When `token` is given, it's passed as a one-off `-c http.extraheader`
    config value scoped to this single `git` invocation only -- never
    embedded in the remote URL (which would leak into `ps`/shell history)
    and never written to the repository's own git config.
    """
    git_path = shutil.which("git")
    if git_path is None:
        raise GitHubPRError("git is not available on PATH")

    argv = [git_path]
    if token:
        credential = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        argv += ["-c", f"http.extraheader=AUTHORIZATION: basic {credential}"]
    argv += ["push", remote, branch_name]

    # Fixed subcommands defined in this module only; repo_root is used as
    # `cwd`, never interpolated into the argv itself. No `--force`/`-f`.
    result = subprocess.run(  # nosec B603
        argv, cwd=repo_root, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise GitHubPRError(f"git push failed: {result.stderr.strip()}")


def _default_http_post(url: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
    # Fixed https://api.github.com base (see `_API_BASE`); nothing here
    # ever opens an attacker-controlled scheme or host.
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:  # nosec B310
        return response.status, response.read()


def open_draft_pull_request(
    *,
    owner: str,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
    token: str,
    http_post: HttpPost | None = None,
) -> DraftPullRequest:
    """Open `head` as a Draft PR against `base` via the GitHub REST API.

    Every field on the returned `DraftPullRequest` is read back from the
    API's own response, never assumed from what was requested (`is_draft`
    included -- GitHub, not this module, is the source of truth for
    whether the PR actually came back as a draft).
    """
    poster = http_post or _default_http_post
    url = f"{_API_BASE}/repos/{owner}/{repo}/pulls"
    payload = json.dumps({"title": title, "head": head, "base": base, "body": body, "draft": True})
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        status, response_body = poster(url, headers, payload.encode("utf-8"))
    except OSError as exc:
        raise GitHubPRError(f"GitHub API request failed: {exc}") from exc
    if status >= 400:
        detail = response_body.decode("utf-8", errors="replace")[:300]
        raise GitHubPRError(f"GitHub API returned HTTP {status} opening a PR: {detail}")

    try:
        data: dict[str, Any] = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise GitHubPRError("GitHub API returned invalid JSON opening a PR") from exc

    try:
        return DraftPullRequest(
            number=data["number"], html_url=data["html_url"], is_draft=bool(data.get("draft"))
        )
    except (KeyError, TypeError) as exc:
        raise GitHubPRError(f"Unexpected GitHub API response shape opening a PR: {exc}") from exc


def open_draft_pr_for_plan(
    plan: ChangePlan,
    repo_root: Path,
    *,
    owner: str,
    repo: str,
    base: str,
    token: str,
    approvals: list[Approval] | None = None,
    remote: str = "origin",
    http_post: HttpPost | None = None,
) -> DraftPRResult:
    """Push `plan.branch_name` and open it as a Draft PR, if policy allows it.

    Requires `local_git.apply_plan` to have already created and committed
    that branch locally -- this only pushes and opens the PR. Governed
    independently from the local step: an `Approval` covering
    `create_local_branch_and_commit` does not also cover `create_draft_pr`
    (`policy.evaluate` matches on the exact action *and* target), so both
    steps of `--push` need their own matching `Approval` when above the
    default permission ceiling -- by design, not an oversight.
    """
    target = f"{owner}/{repo}"
    decision = evaluate(_ACTION, target, plan.required_permission_level, approvals)
    if not decision.allowed:
        return DraftPRResult(applied=False, decision=decision)

    push_branch(repo_root, plan.branch_name, token=token, remote=remote)
    pull_request = open_draft_pull_request(
        owner=owner,
        repo=repo,
        head=plan.branch_name,
        base=base,
        title=plan.commit_message,
        body=plan.description or plan.commit_message,
        token=token,
        http_post=http_post,
    )
    return DraftPRResult(applied=True, decision=decision, pull_request=pull_request)
