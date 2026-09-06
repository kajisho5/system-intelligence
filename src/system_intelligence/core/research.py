"""ResearchResult — an external candidate solution with preserved provenance.

Implements the "for every external result preserve..." requirement and the
anti-hallucination rule in docs/design/docs/06-research-engine.md: any
dimension that cannot be verified from the source must be recorded as
`Confidence.UNKNOWN`, never invented.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence


class ResearchResult(BaseModel):
    id: str = Field(default_factory=lambda: f"research-{uuid4().hex[:12]}")
    query: str
    provider: str = Field(description="e.g. 'github', 'pypi', 'npm', 'web'.")
    source: str = Field(description="URL or registry identifier.")
    identifier: str = Field(description="Stable id within the provider, e.g. 'owner/repo'.")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evidence: list[Evidence] = Field(default_factory=list)
    license: str | None = None
    license_confidence: Confidence = Confidence.UNKNOWN
    maintenance_signals: dict[str, str] = Field(default_factory=dict)
    compatibility_assessment: str | None = None
    compatibility_confidence: Confidence = Confidence.UNKNOWN
    functional_fit_notes: str | None = None
