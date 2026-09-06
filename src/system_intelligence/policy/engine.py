"""Policy engine: the permission-level/approval gate (docs/design/docs/08-governance.md).

No execution adapter may bypass this (docs/design/docs/18-extension-points.md).
Pure logic, no I/O — every decision is a deterministic function of the
requested action, the target, the required permission level, and whatever
`Approval` records the caller supplies. It does not source approvals
itself (no persistence layer yet); callers pass in whatever they have.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from system_intelligence.core.enums import (
    DEFAULT_MAX_PERMISSION_LEVEL,
    FORBIDDEN_BY_DEFAULT_ACTIONS,
    PermissionLevel,
)
from system_intelligence.core.governance import Approval


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    required_level: PermissionLevel


def _approval_covers(
    approval: Approval,
    action: str,
    target: str,
    required_level: PermissionLevel,
    now: datetime,
) -> bool:
    if approval.action != action or approval.target != target:
        return False
    if approval.permission_level < required_level:
        return False
    return approval.expires_at is None or approval.expires_at > now


def evaluate(
    action: str,
    target: str,
    required_level: PermissionLevel,
    approvals: list[Approval] | None = None,
) -> PolicyDecision:
    """Decide whether `action` against `target` may proceed right now.

    - Forbidden-by-default actions are always denied, regardless of any
      Approval — `Approval` itself already refuses to be constructed for
      one, but this is checked again here as the actual enforcement point
      (defense in depth: nothing should rely solely on the model's own
      validator).
    - Anything at or below `DEFAULT_MAX_PERMISSION_LEVEL` is allowed
      without an approval.
    - Anything above it needs a non-expired `Approval` matching this exact
      action and target, at a permission level at least as high as
      required.
    """
    if action in FORBIDDEN_BY_DEFAULT_ACTIONS:
        return PolicyDecision(
            allowed=False,
            reason=f"{action!r} is forbidden by default and cannot be authorized by any approval.",
            required_level=required_level,
        )

    if required_level <= DEFAULT_MAX_PERMISSION_LEVEL:
        reason = (
            f"{required_level.name} is within the default maximum "
            f"({DEFAULT_MAX_PERMISSION_LEVEL.name})."
        )
        return PolicyDecision(allowed=True, reason=reason, required_level=required_level)

    now = datetime.now(UTC)
    for approval in approvals or []:
        if _approval_covers(approval, action, target, required_level, now):
            reason = f"Approved by {approval.actor!r} (approval {approval.id})."
            return PolicyDecision(allowed=True, reason=reason, required_level=required_level)

    reason = (
        f"{required_level.name} exceeds the default maximum "
        f"({DEFAULT_MAX_PERMISSION_LEVEL.name}) and no matching approval was found "
        f"for action={action!r} target={target!r}."
    )
    return PolicyDecision(allowed=False, reason=reason, required_level=required_level)
