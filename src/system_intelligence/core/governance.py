"""Approval and audit records for the policy/execution boundary.

See docs/design/docs/08-governance.md. An Approval is the only thing that
allows a Change/Proposal at PermissionLevel.CREATE_BRANCH_OR_DRAFT_PR or
above to be executed; the policy engine (policy/ package, later phases)
enforces this, this module only defines the schema.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from system_intelligence.core.enums import (
    FORBIDDEN_BY_DEFAULT_ACTIONS,
    PermissionLevel,
)


class Approval(BaseModel):
    id: str = Field(default_factory=lambda: f"approval-{uuid4().hex[:12]}")
    actor: str = Field(description="Who granted this approval, e.g. 'human:kajisho5'.")
    scope: str = Field(description="e.g. 'repository', 'organization', 'proposal'.")
    action: str
    target: str
    permission_level: PermissionLevel
    approved_at: datetime = Field(default_factory=lambda: datetime.now())
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _reject_forbidden_actions(self) -> Approval:
        if self.action in FORBIDDEN_BY_DEFAULT_ACTIONS:
            raise ValueError(
                f"Action {self.action!r} is forbidden by default and cannot be "
                "granted via an Approval record. See docs/design/docs/08-governance.md."
            )
        return self


class AuditLogEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"audit-{uuid4().hex[:12]}")
    actor: str
    intent: str
    policy: str | None = None
    target: str
    evidence_ids: list[str] = Field(default_factory=list)
    action: str
    result: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    correlation_id: str
