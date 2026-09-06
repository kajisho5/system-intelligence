"""ImpactAssessment — what a StateDiff would mean for the rest of the system.

Answers "what would updating this component affect?" using only what a
Snapshot already records (which components declare a dependency on this
identity) plus the StateDiff's own items. `verdict` is a conclusion, not a
restatement of the version delta — see `core.enums.UpdateVerdict` for the
rule that keeps it from being reached on a version number alone.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from system_intelligence.core.enums import Confidence, UpdateVerdict
from system_intelligence.core.evidence import Evidence
from system_intelligence.core.security import SecurityAdvisory
from system_intelligence.core.state_diff import StateDiff, StateDiffItem

#: Dimensions an ImpactAssessment always tries to evaluate. Any left
#: unresolved (still Confidence.UNKNOWN in the underlying StateDiffItems)
#: are surfaced in `unknown_dimensions` rather than silently dropped —
#: mirrors `research.scoring.UNSCORABLE_DIMENSIONS`.
ASSESSED_DIMENSIONS = ("capability", "dependency", "interface", "installation")


class ImpactAssessment(BaseModel):
    id: str = Field(default_factory=lambda: f"impact-{uuid4().hex[:12]}")
    state_diff: StateDiff
    affected_entity_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Ids of entities that relationship topology says could be affected by a change "
            "to this identity — Component ids that directly depend on it, plus any Capability "
            "and consumer-Component ids reached by following PROVIDES/USES edges onward from "
            "there. Reachable-in-the-graph, not confirmed-to-break; only 1-hop (direct "
            "dependents) when no relationship graph was supplied."
        ),
    )
    breaking_items: list[StateDiffItem] = Field(default_factory=list)
    capability_impact: list[StateDiffItem] = Field(default_factory=list)
    dependency_impact: list[StateDiffItem] = Field(default_factory=list)
    interface_impact: list[StateDiffItem] = Field(default_factory=list)
    unknown_dimensions: tuple[str, ...] = Field(default_factory=tuple)
    verdict: UpdateVerdict = UpdateVerdict.UNKNOWN
    verdict_confidence: Confidence = Confidence.UNKNOWN
    verdict_rationale: str = Field(
        description="Plain-language reason for the verdict — never left implicit."
    )
    evidence: list[Evidence] = Field(default_factory=list)
    current_version_advisories: list[SecurityAdvisory] = Field(
        default_factory=list,
        description=(
            "Known vulnerabilities affecting the *currently installed* version, from a "
            "VulnerabilityProvider — independent of whether any update is available. Empty "
            "means none were found, not that none were checked (a caller that ran no "
            "vulnerability check leaves this empty too)."
        ),
    )
    available_version_advisories: list[SecurityAdvisory] = Field(
        default_factory=list,
        description="Known vulnerabilities affecting the *available* version, same caveat.",
    )

    @model_validator(mode="after")
    def _forbid_unsupported_recommendation(self) -> ImpactAssessment:
        if self.verdict == UpdateVerdict.UPDATE_RECOMMENDED and (
            self.breaking_items or self.unknown_dimensions
        ):
            raise ValueError(
                "UpdateVerdict.UPDATE_RECOMMENDED requires no breaking_items and no "
                "unknown_dimensions — every material dimension must have been actually "
                "evaluated. Use REVIEW_REQUIRED when any dimension stayed unresolved."
            )
        return self
