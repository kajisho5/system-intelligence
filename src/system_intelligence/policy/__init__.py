"""Policy engine: enforces the permission-level/approval boundary.

Phase 8 scope (docs/design/docs/08-governance.md): `evaluate` decides
whether a requested action may proceed, given its required
`PermissionLevel` and whatever `Approval` records the caller supplies.
Forbidden-by-default actions (merge, close, delete, force-push, ...) are
always denied regardless of approval. No execution adapter may bypass this
(docs/design/docs/18-extension-points.md). `audit_log_entry` builds the
`core.governance.AuditLogEntry` docs/08-governance.md's "Audit log"
section requires from an already-computed decision.

Not yet implemented: persisting/looking up Approval records itself — there
is no store yet, callers must supply the approvals they already have.
"""

from system_intelligence.policy.engine import PolicyDecision, audit_log_entry, evaluate

__all__ = ["PolicyDecision", "audit_log_entry", "evaluate"]
