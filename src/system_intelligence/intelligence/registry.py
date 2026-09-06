"""Capability registry: every unit of work the orchestrator can run.

Each `CapabilityDescriptor` names one independently-invokable analysis step
(already implemented in `discovery`/`analysis`/`recommendations`) and the
other capabilities it needs to have run first. `resolve_dependencies`
expands a requested set into its transitive closure, in an order safe to
execute — this is what lets `intelligence.intents.resolve_intent` answer
"what would actually run for this request" without running anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    description: str
    requires: frozenset[str] = field(default_factory=frozenset)


CAPABILITIES: dict[str, CapabilityDescriptor] = {
    "git_metadata": CapabilityDescriptor(
        "git_metadata", "Collect git branch/remote/last-commit metadata."
    ),
    "structure_scan": CapabilityDescriptor(
        "structure_scan", "Detect languages and package manifests."
    ),
    "skill_detection": CapabilityDescriptor(
        "skill_detection", "Detect standard Agent Skills (SKILL.md)."
    ),
    "agent_detection": CapabilityDescriptor(
        "agent_detection", "Detect Claude Code subagents (.claude/agents/*.md)."
    ),
    "adr_detection": CapabilityDescriptor(
        "adr_detection", "Detect Architecture Decision Records by filename convention."
    ),
    "ci_docs_detection": CapabilityDescriptor(
        "ci_docs_detection", "Detect CI workflows and well-known root documents."
    ),
    "documentation_audit": CapabilityDescriptor(
        "documentation_audit",
        "Flag missing README/LICENSE/CONTRIBUTING.",
        requires=frozenset({"ci_docs_detection"}),
    ),
    "ci_test_audit": CapabilityDescriptor(
        "ci_test_audit",
        "Flag missing CI configuration or test files.",
        requires=frozenset({"ci_docs_detection"}),
    ),
    "dependency_extraction": CapabilityDescriptor(
        "dependency_extraction",
        "Parse declared dependencies out of detected package manifests.",
        requires=frozenset({"structure_scan"}),
    ),
    "capability_extraction": CapabilityDescriptor(
        "capability_extraction",
        "Extract Capabilities from Skills and Agents and flag duplicate names.",
        requires=frozenset({"skill_detection", "agent_detection"}),
    ),
    "unused_skill_detection": CapabilityDescriptor(
        "unused_skill_detection",
        "Flag Skills with no textual reference outside their own directory.",
        requires=frozenset({"skill_detection"}),
    ),
    "capability_gap_detection": CapabilityDescriptor(
        "capability_gap_detection",
        "Flag capabilities declared required (.si/requirements.json) but not found.",
        requires=frozenset({"capability_extraction"}),
    ),
    "circular_dependency_detection": CapabilityDescriptor(
        "circular_dependency_detection", "AST-based circular-import detection."
    ),
    "relationship_graph_construction": CapabilityDescriptor(
        "relationship_graph_construction",
        "Materialize DEPENDS_ON/PROVIDES/USES/DUPLICATES edges already implicit "
        "in Component and Capability records (R4).",
        requires=frozenset({"dependency_extraction", "capability_extraction"}),
    ),
    "recommendation_ranking": CapabilityDescriptor(
        "recommendation_ranking",
        "Rank accumulated findings into Recommendation records.",
        requires=frozenset(
            {
                "documentation_audit",
                "ci_test_audit",
                "capability_extraction",
                "unused_skill_detection",
                "circular_dependency_detection",
                "capability_gap_detection",
            }
        ),
    ),
}


def resolve_dependencies(capability_ids: set[str]) -> list[str]:
    """Expand `capability_ids` to its transitive closure, in run-safe order.

    Raises `KeyError` for an id not in `CAPABILITIES` — never silently
    drops an unknown request.
    """
    resolved: list[str] = []
    seen: set[str] = set()

    def visit(capability_id: str) -> None:
        if capability_id in seen:
            return
        seen.add(capability_id)
        descriptor = CAPABILITIES[capability_id]
        for dependency in sorted(descriptor.requires):
            visit(dependency)
        resolved.append(capability_id)

    for capability_id in sorted(capability_ids):
        visit(capability_id)
    return resolved
