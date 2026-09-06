"""Execution adapters: plan/preview/apply/verify/rollback for approved Changes.

Not yet implemented. Planned scope starts with local file generation, then
branch creation, commit creation, and Draft PR creation — each gated by the
policy engine and requiring an `Approval` at `PermissionLevel.
CREATE_BRANCH_OR_DRAFT_PR` or above. Merge, close, delete, force-push,
visibility, credential, and deployment operations are never implemented as
automatic actions (see `core.enums.FORBIDDEN_BY_DEFAULT_ACTIONS`).
"""
