"""Execution adapters: plan/preview/apply for approved Changes.

`plan.ChangePlan` is a pure, side-effect-free description of a local
change. Two adapters apply it, matching docs/design/docs/11-github-
integration.md's "Preferred first write" (create branch -> create commit
-> open Draft PR) as two separately governed steps:

- `local_git.apply_plan` — creates a local branch and commits specific
  files, gated by `policy.evaluate` under `create_local_branch_and_commit`.
  Never touches any remote; never runs `git` with anything but a fixed,
  hardcoded subcommand.
- `github_pr.open_draft_pr_for_plan` — pushes that already-created branch
  and opens it as a Draft PR, gated independently under `create_draft_pr`
  (its own action name, its own `Approval` requirement — covering the
  local step does not also cover this one). Never merges, closes,
  approves, or force-pushes.

Merge, close, delete, force-push, visibility, credential, and deployment
operations are never implemented as automatic actions at all (see
`core.enums.FORBIDDEN_BY_DEFAULT_ACTIONS`, enforced independently by both
`Approval`'s validator and `policy.evaluate`).

`handoff.build_handoff_packet` is a third, read-only path for a Proposal
that has no deterministic `ChangePlan` at all (ADR-007: it hands the
Proposal to an external implementer instead of guessing a diff) — its
result still only becomes real work through the same `local_git.apply_plan`
above, once the implementer hands back a `ChangePlan`.
"""

from system_intelligence.execution.github_pr import (
    DraftPRResult,
    DraftPullRequest,
    GitHubPRError,
    open_draft_pr_for_plan,
)
from system_intelligence.execution.handoff import ChangePlanFile, build_handoff_packet
from system_intelligence.execution.local_git import ExecutionResult, LocalGitError, apply_plan
from system_intelligence.execution.plan import ChangePlan

__all__ = [
    "ChangePlan",
    "ChangePlanFile",
    "DraftPRResult",
    "DraftPullRequest",
    "ExecutionResult",
    "GitHubPRError",
    "LocalGitError",
    "apply_plan",
    "build_handoff_packet",
    "open_draft_pr_for_plan",
]
