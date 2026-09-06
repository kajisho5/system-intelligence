"""Finding — a documented observation with a severity and supporting evidence.

Per the task's FACT VS INFERENCE section, a Finding must never present an
inferred relationship as a verified fact: `confidence` is required and
`evidence` must be non-empty for any finding that isn't purely
UNKNOWN-confidence speculation flagged as such.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: f"finding-{uuid4().hex[:12]}")
    category: str = Field(
        description="e.g. 'unused_candidate', 'capability_gap', 'documentation_gap', 'ci_health'."
    )
    severity: Severity
    statement: str = Field(description="Confidence-qualified statement, not an assertion of fact.")
    confidence: Confidence
    affected_entity_ids: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_evidence_unless_unknown(self) -> Finding:
        if self.confidence != Confidence.UNKNOWN and not self.evidence:
            raise ValueError(
                f"Finding {self.id!r} claims confidence={self.confidence.value!r} "
                "but cites no evidence. Evidence-first: either attach Evidence or "
                "use Confidence.UNKNOWN."
            )
        return self
