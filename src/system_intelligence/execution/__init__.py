"""Execution adapters: plan/preview/apply for approved Changes.

Phase 8 scope: `plan.ChangePlan` (a pure, side-effect-free description of
a local change) and `local_git.apply_plan` — creates a local branch and
commits specific files, gated by `policy.evaluate`. This never pushes to
any remote and never runs `git` with anything but a fixed, hardcoded
subcommand.

Deliberately not implemented yet: the remote half of docs/design/docs/11-
github-integration.md's "Preferred first write" (create branch → create
commit → open Draft PR, on the actual remote). Opening a Draft PR touches
shared state on GitHub, which is a materially different risk than writing
to a throwaway local branch; it needs its own adapter, its own explicit
approval action name, and — per the task's own safety principle — should
not be added just because it appears on the long-term roadmap. Merge,
close, delete, force-push, visibility, credential, and deployment
operations are never implemented as automatic actions at all (see
`core.enums.FORBIDDEN_BY_DEFAULT_ACTIONS`, enforced independently by both
`Approval`'s validator and `policy.evaluate`).
"""

from system_intelligence.execution.local_git import ExecutionResult, LocalGitError, apply_plan
from system_intelligence.execution.plan import ChangePlan

__all__ = ["ChangePlan", "ExecutionResult", "LocalGitError", "apply_plan"]
