"""Capability — a first-class entity per the task's CAPABILITY SYSTEM requirement.

A Capability answers: what it is, who provides it, whether it is verified,
where evidence comes from, and whether it is duplicated/missing/partial/
deprecated (docs/design/docs/04-domain-model.md, "Capability model").
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from system_intelligence.core.enums import CapabilityStatus, Confidence
from system_intelligence.core.evidence import Evidence


class Capability(BaseModel):
    id: str = Field(default_factory=lambda: f"capability-{uuid4().hex[:12]}")
    name: str
    description: str | None = None
    provider_ids: list[str] = Field(
        default_factory=list, description="Component ids that provide this capability."
    )
    consumer_ids: list[str] = Field(
        default_factory=list, description="Component ids that require this capability."
    )
    status: CapabilityStatus = CapabilityStatus.UNKNOWN
    confidence: Confidence = Confidence.UNKNOWN
    evidence: list[Evidence] = Field(default_factory=list)

    def is_duplicated(self) -> bool:
        """True when more than one distinct provider is on record.

        This reflects only what has been observed; it is not proof that the
        providers are functionally redundant. Callers should attach
        supporting Evidence before surfacing a `duplicates` relationship.
        """
        return len(set(self.provider_ids)) > 1
