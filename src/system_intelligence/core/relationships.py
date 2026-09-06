"""Relationship — a typed, evidenced edge between two entities.

Implements R4 in docs/design/docs/02-requirements.md.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.enums import Confidence, RelationshipType
from system_intelligence.core.evidence import Evidence


class Relationship(BaseModel):
    id: str = Field(default_factory=lambda: f"relationship-{uuid4().hex[:12]}")
    type: RelationshipType
    source_id: str = Field(description="Entity id the relationship originates from.")
    target_id: str = Field(description="Entity id the relationship points to.")
    confidence: Confidence = Confidence.UNKNOWN
    evidence: list[Evidence] = Field(default_factory=list)
