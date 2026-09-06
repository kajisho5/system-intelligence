"""Relationship graph construction (R4).

Deliberately conservative: every edge here materializes a reference a
Snapshot's own records already carry explicitly — a Component's own
`dependencies` list, a Capability's own `provider_ids`/`consumer_ids` — into
an explicit `Relationship` object. This performs no new discovery and
infers nothing beyond what those fields already assert.

Not exhaustive: only DEPENDS_ON, PROVIDES, USES, and DUPLICATES are derived
here, because those are the only ones an existing field encodes
unambiguously. The remaining `RelationshipType` values (IMPLEMENTS,
CONFLICTS_WITH, SUPERSEDES, REFERENCED_BY, TESTED_BY, DOCUMENTED_BY,
DEPLOYED_BY) need discovery this codebase doesn't perform yet and are
never guessed at here.
"""

from __future__ import annotations

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Component
from system_intelligence.core.enums import Confidence, RelationshipType
from system_intelligence.core.ids import stable_id
from system_intelligence.core.relationships import Relationship


def _depends_on_relationships(components: list[Component]) -> list[Relationship]:
    return [
        Relationship(
            id=stable_id("relationship", "depends_on", component.id, dependency.id),
            type=RelationshipType.DEPENDS_ON,
            source_id=component.id,
            target_id=dependency.id,
            confidence=Confidence.VERIFIED,
            evidence=list(dependency.evidence),
        )
        for component in components
        for dependency in component.dependencies
    ]


def _capability_relationships(capabilities: list[Capability]) -> list[Relationship]:
    relationships: list[Relationship] = []
    for capability in capabilities:
        for provider_id in capability.provider_ids:
            relationships.append(
                Relationship(
                    id=stable_id("relationship", "provides", provider_id, capability.id),
                    type=RelationshipType.PROVIDES,
                    source_id=provider_id,
                    target_id=capability.id,
                    confidence=capability.confidence,
                    evidence=list(capability.evidence),
                )
            )
        for consumer_id in capability.consumer_ids:
            relationships.append(
                Relationship(
                    id=stable_id("relationship", "uses", consumer_id, capability.id),
                    type=RelationshipType.USES,
                    source_id=consumer_id,
                    target_id=capability.id,
                    confidence=capability.confidence,
                    evidence=list(capability.evidence),
                )
            )
    return relationships


def _duplicate_capability_relationships(capabilities: list[Capability]) -> list[Relationship]:
    by_name: dict[str, list[Capability]] = {}
    for capability in capabilities:
        by_name.setdefault(capability.name, []).append(capability)

    relationships: list[Relationship] = []
    for group in by_name.values():
        if len(group) < 2:
            continue
        # Oriented by capability id so the edge is deterministic regardless
        # of input order — one DUPLICATES edge per unordered pair.
        ordered = sorted(group, key=lambda c: c.id)
        for i, first in enumerate(ordered):
            for second in ordered[i + 1 :]:
                relationships.append(
                    Relationship(
                        id=stable_id("relationship", "duplicates", first.id, second.id),
                        type=RelationshipType.DUPLICATES,
                        source_id=first.id,
                        target_id=second.id,
                        confidence=Confidence.MEDIUM,
                        evidence=[*first.evidence, *second.evidence],
                    )
                )
    return relationships


def build_relationships(
    components: list[Component], capabilities: list[Capability]
) -> list[Relationship]:
    """Materialize every relationship already implicit in `components`/`capabilities`."""
    return [
        *_depends_on_relationships(components),
        *_capability_relationships(capabilities),
        *_duplicate_capability_relationships(capabilities),
    ]
