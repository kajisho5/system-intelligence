"""Proposal and Change — concrete, executable-once-approved units of work.

See docs/design/docs/07-improvement-engine.md ("Proposal must contain") and
the task's IMPROVEMENT ENGINE section. A Proposal is never auto-executed;
execution requires an Approval (governance.py) at the required permission
level.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.enums import PermissionLevel
from system_intelligence.core.evidence import Evidence


class Change(BaseModel):
    """A single concrete, previewable unit of work within a Proposal."""

    id: str = Field(default_factory=lambda: f"change-{uuid4().hex[:12]}")
    description: str
    file_paths: list[str] = Field(default_factory=list)
    required_permission_level: PermissionLevel = PermissionLevel.GENERATE_LOCAL_ARTIFACTS


class Proposal(BaseModel):
    id: str = Field(default_factory=lambda: f"proposal-{uuid4().hex[:12]}")
    kind: str = Field(
        description="e.g. 'new_skill', 'new_agent', 'new_package', 'new_service', "
        "'new_repository', 'refactor', 'documentation', 'test_suite'."
    )
    problem: str
    evidence: list[Evidence] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    alternatives_considered: list[str] = Field(default_factory=list)
    why_existing_solutions_insufficient: str | None = None
    proposed_component_name: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    implementation_stages: list[str] = Field(default_factory=list)
    changes: list[Change] = Field(default_factory=list)
    test_strategy: str | None = None
    security_considerations: str | None = None
    documentation_requirements: str | None = None
    rollback_strategy: str | None = None
    required_permission_level: PermissionLevel = PermissionLevel.GENERATE_LOCAL_ARTIFACTS
