"""Capability extraction from detected Skills, and duplicate-name detection.

Phase 3 scope: one Capability per Skill (Skills are the only component kind
Phase 2 discovers that clearly declares a capability by name). Agents,
MCP servers, and Tools will extend this once their detectors exist.
"""

from __future__ import annotations

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Skill
from system_intelligence.core.enums import CapabilityStatus, Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.ids import stable_id


def extract_capabilities(skills: list[Skill]) -> list[Capability]:
    capabilities: list[Capability] = []
    for skill in skills:
        status = (
            CapabilityStatus.AVAILABLE if skill.is_standard_format else CapabilityStatus.PARTIAL
        )
        confidence = Confidence.HIGH if skill.is_standard_format else Confidence.LOW
        capabilities.append(
            Capability(
                id=stable_id("capability", skill.id),
                name=skill.name,
                description=skill.description,
                provider_ids=[skill.id],
                status=status,
                confidence=confidence,
                evidence=list(skill.evidence),
            )
        )
    return capabilities


def detect_duplicate_capabilities(capabilities: list[Capability]) -> list[Finding]:
    """Flag capability names declared by more than one provider.

    This only proves that two components claim the same name — it is not
    proof they are functionally redundant, hence `Confidence.MEDIUM` rather
    than a higher confidence.
    """
    by_name: dict[str, list[Capability]] = {}
    for capability in capabilities:
        by_name.setdefault(capability.name, []).append(capability)

    findings: list[Finding] = []
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        provider_ids = [pid for c in group for pid in c.provider_ids]
        evidence = [
            Evidence(
                kind=EvidenceKind.STATIC_REFERENCE,
                source=name,
                observation=f"{len(group)} components declare the capability name {name!r}",
                confidence=Confidence.VERIFIED,
            )
        ]
        findings.append(
            Finding(
                category="duplicated_capability",
                severity=Severity.MEDIUM,
                statement=(
                    f"{len(group)} components declare the capability {name!r}. "
                    "Whether they are functionally redundant has not been verified."
                ),
                confidence=Confidence.MEDIUM,
                affected_entity_ids=provider_ids,
                evidence=evidence,
                suggested_actions=[
                    f"Review whether the {len(group)} providers of {name!r} should be consolidated."
                ],
            )
        )
    return findings
