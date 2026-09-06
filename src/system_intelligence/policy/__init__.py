"""Policy engine: enforces the permission-level/approval boundary.

Not yet implemented. Planned scope: evaluating a requested action against
`PermissionLevel`, `Approval` records, and `FORBIDDEN_BY_DEFAULT_ACTIONS`
(docs/design/docs/08-governance.md) before any execution adapter runs. No
execution adapter may bypass this engine (docs/design/docs/18-extension-points.md).
"""
