"""Capability extraction from detected Skills, and duplicate-name detection.

Phase 3 scope: one Capability per Skill (Skills are the only component kind
Phase 2 discovers that clearly declares a capability by name). Agents,
MCP servers, and Tools will extend this once their detectors exist.
"""

from __future__ import annotations

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Component, Skill
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


def attach_consumers(
    capabilities: list[Capability], components: list[Component]
) -> list[Capability]:
    """Populate `Capability.consumer_ids` from explicit dependency declarations.

    A component is only ever recorded as a consumer of a Capability when one
    of its own `Dependency` records has a `name` that exactly matches that
    Capability's `name` — the same "declared identifier equality is a
    verifiable fact, functional equivalence is not" principle
    `detect_duplicate_capabilities` already applies to two Capabilities
    sharing a name, extended here to a Dependency naming the same identifier
    as a Capability already on record in this Snapshot.

    Never derived from a similar name, a similar description, or any
    heuristic beyond exact string equality on fields the discovery layer
    already populated with their own Evidence. A component with no
    dependency whose name exactly matches a Capability contributes no
    consumer edge for it — this is an absence of a verifiable declaration,
    not evidence that the component doesn't consume it, so it must never be
    read as a negative fact; `consumer_ids` simply stays as it was (empty,
    unless already set by a caller).
    """
    by_name: dict[str, list[Capability]] = {}
    for capability in capabilities:
        by_name.setdefault(capability.name, []).append(capability)

    consumer_ids: dict[str, set[str]] = {c.id: set(c.consumer_ids) for c in capabilities}
    extra_evidence: dict[str, list[Evidence]] = {c.id: [] for c in capabilities}

    for component in components:
        for dependency in component.dependencies:
            for capability in by_name.get(dependency.name, []):
                if component.id in capability.provider_ids:
                    continue  # a component does not "consume" its own capability
                if component.id in consumer_ids[capability.id]:
                    continue
                consumer_ids[capability.id].add(component.id)
                extra_evidence[capability.id].extend(dependency.evidence)
                extra_evidence[capability.id].append(
                    Evidence(
                        kind=EvidenceKind.STATIC_REFERENCE,
                        source=component.id,
                        observation=(
                            f"{component.name!r} declares a dependency named "
                            f"{dependency.name!r}, matching the capability "
                            f"{capability.name!r} on record in this Snapshot. Whether the "
                            "dependency actually refers to this capability has not been "
                            "independently verified."
                        ),
                        confidence=Confidence.MEDIUM,
                    )
                )

    updated: list[Capability] = []
    for capability in capabilities:
        new_ids = sorted(consumer_ids[capability.id])
        if new_ids == capability.consumer_ids and not extra_evidence[capability.id]:
            updated.append(capability)
            continue
        updated.append(
            capability.model_copy(
                update={
                    "consumer_ids": new_ids,
                    "evidence": [*capability.evidence, *extra_evidence[capability.id]],
                }
            )
        )
    return updated


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
