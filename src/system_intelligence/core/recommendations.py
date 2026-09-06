"""Recommendation — a ranked, evidence-backed suggestion (R7).

Recommendations are distinct from Proposals: a Recommendation says *what*
should change and why; a Proposal (proposals.py) says *how*, concretely
enough to be approved and executed.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.enums import Confidence, PermissionLevel
from system_intelligence.core.evidence import Evidence


class Recommendation(BaseModel):
    id: str = Field(default_factory=lambda: f"recommendation-{uuid4().hex[:12]}")
    objective: str
    rationale: str
    alternatives_considered: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    estimated_effort: str | None = Field(
        default=None, description="Rough sizing, e.g. 'small', 'medium', 'large'."
    )
    risk: str | None = None
    expected_benefit: str | None = None
    required_approval_level: PermissionLevel = PermissionLevel.RECOMMEND
