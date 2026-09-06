"""Dashboard data API: the read model `reporting/dashboard_html.py` renders.

Architecture (docs/03-architecture.md's layering, applied to the Dashboard):

    Snapshot(s) + Update Intelligence results
        -> this module (aggregation only)
        -> DashboardData (JSON-serializable)
        -> dashboard_html.py (rendering only)

This module computes zero new facts of its own: no health score, no
inferred relationships, no fabricated status. Every field is either an
existing domain object passed through unchanged, or a count/grouping over
existing domain objects. `dashboard_html.py` must never recompute anything
this module could have computed — the frontend has no business logic.

Generic across `ComponentKind` (ADR-001, ADR-007): nothing here references
any specific component, repository, or organization.

This is also the read model an external consumer outside SI's own Python
process should read (docs/design/docs/12-storage-and-state.md, "External
consumer boundary") — e.g. a different dashboard, CI tooling, another
agent, or the AI Video Production OS's own ecosystem-level control plane
(a reference consumer, never a hard dependency of SI). No second export
format is introduced for that: this is the same `Snapshot` state already
written to the canonical snapshot directory (`core.snapshot.Snapshot.
write_to_directory`), just aggregated with the counts/rankings/evidence-
cross-references a UI or external reader would otherwise have to
re-derive itself. `Snapshot.tool_version` (surfaced here on
`OverviewCounts`) remains the one compatibility marker — see
12-storage-and-state.md rather than a second version number here.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, SerializeAsAny

from system_intelligence.analysis.update_intelligence import UpdateCheckResult
from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import ADR, Component, Dependency
from system_intelligence.core.enums import (
    DEFAULT_MAX_PERMISSION_LEVEL,
    FORBIDDEN_BY_DEFAULT_ACTIONS,
)
from system_intelligence.core.evidence import Evidence
from system_intelligence.core.execution_record import ExecutionRecord
from system_intelligence.core.findings import Finding
from system_intelligence.core.governance import Approval
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.proposals import Proposal
from system_intelligence.core.recommendations import Recommendation
from system_intelligence.core.relationships import Relationship
from system_intelligence.core.research import ResearchResult
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.core.verification import Verification
from system_intelligence.reporting.diff import diff_snapshots
from system_intelligence.research.scoring import rank_candidates


class OverviewCounts(BaseModel):
    target_name: str
    target_locator: str
    snapshot_id: str
    tool_version: str
    generated_at: datetime
    component_count: int
    component_counts_by_kind: dict[str, int]
    capability_count: int
    dependency_count: int
    relationship_count: int
    finding_count: int
    finding_counts_by_severity: dict[str, int]
    recommendation_count: int
    proposal_count: int
    research_result_count: int
    approval_count: int
    verification_count: int
    execution_count: int
    adr_count: int
    has_previous_snapshot: bool
    previous_snapshot_id: str | None
    has_update_check: bool
    update_assessment_count: int
    update_unavailable_count: int
    update_verdict_counts: dict[str, int]


class ChangeSummary(BaseModel):
    """One entry for the Changes screen — always traced back to an existing diff.

    `origin` says which comparison produced it: `"snapshot_diff"` (current
    vs. a previous Snapshot) or `"update_availability"` (installed vs.
    available state, from Component Update Intelligence). Never generated
    independently of one of those two comparisons.
    """

    origin: str
    category: str
    description: str
    confidence: str | None = None
    component_name: str | None = None


class EvidenceRef(BaseModel):
    evidence: Evidence
    referenced_by: list[str] = Field(default_factory=list)


class GovernanceView(BaseModel):
    default_max_permission_level: str
    forbidden_actions: list[str]


class UpdateLookupFailureView(BaseModel):
    ecosystem: str
    name: str
    message: str


class ResearchAssessmentView(BaseModel):
    """A ResearchResult plus its `research.scoring.rank_candidates` assessment.

    Reuses the existing scoring engine rather than re-deriving a ranking in
    the Dashboard layer — the "ranking / selection rationale" the Research
    screen shows is the same rationale `si research` already computes.
    """

    result: ResearchResult
    has_license: bool
    license_confidence: str
    is_recently_active: bool | None
    is_archived: bool | None
    stargazer_count: int | None
    unknown_dimensions: list[str]


class DashboardData(BaseModel):
    id: str = Field(default_factory=lambda: f"dashboard-{uuid4().hex[:12]}")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overview: OverviewCounts
    # `SerializeAsAny`: without it, pydantic serializes every item in this
    # list using `Component`'s own declared schema when this *containing*
    # model is dumped as a whole (exactly what dashboard_html.py's
    # `_json_script` does) — silently dropping subclass-only fields like
    # `Repository.url` or `Skill.is_standard_format` from the JSON an
    # external consumer reads. Dumping each Component individually (as
    # `Snapshot.write_to_directory` does) never had this problem; this
    # field needs the same runtime-type-aware serialization explicitly.
    components: list[SerializeAsAny[Component]]
    capabilities: list[Capability]
    relationships: list[Relationship]
    dependencies: list[Dependency]
    findings: list[Finding]
    research: list[ResearchResult]
    research_rankings: list[ResearchAssessmentView]
    recommendations: list[Recommendation]
    proposals: list[Proposal]
    executions: list[ExecutionRecord]
    verifications: list[Verification]
    approvals: list[Approval]
    adrs: list[ADR]
    update_assessments: list[ImpactAssessment]
    update_unavailable: list[UpdateLookupFailureView]
    changes: list[ChangeSummary]
    evidence: list[EvidenceRef]
    governance: GovernanceView


def _all_dependencies(components: list[Component]) -> list[Dependency]:
    seen: set[str] = set()
    dependencies: list[Dependency] = []
    for component in components:
        for dependency in component.dependencies:
            if dependency.id in seen:
                continue
            seen.add(dependency.id)
            dependencies.append(dependency)
    return dependencies


def _snapshot_diff_changes(previous: Snapshot, current: Snapshot) -> list[ChangeSummary]:
    diff = diff_snapshots(previous, current)
    changes: list[ChangeSummary] = []
    for component in diff.added_components:
        changes.append(
            ChangeSummary(
                origin="snapshot_diff",
                category="added",
                description=f"{component.kind.value} {component.name!r} was added.",
                component_name=component.name,
            )
        )
    for component in diff.removed_components:
        changes.append(
            ChangeSummary(
                origin="snapshot_diff",
                category="removed",
                description=f"{component.kind.value} {component.name!r} was removed.",
                component_name=component.name,
            )
        )
    for capability in diff.added_capabilities:
        changes.append(
            ChangeSummary(
                origin="snapshot_diff",
                category="capability_change",
                description=f"Capability {capability.name!r} was added.",
                component_name=capability.name,
            )
        )
    for capability in diff.removed_capabilities:
        changes.append(
            ChangeSummary(
                origin="snapshot_diff",
                category="capability_change",
                description=f"Capability {capability.name!r} was removed.",
                component_name=capability.name,
            )
        )
    for dependency in diff.added_dependencies:
        changes.append(
            ChangeSummary(
                origin="snapshot_diff",
                category="dependency_change",
                description=f"Dependency {dependency.name!r} ({dependency.ecosystem}) was added.",
                component_name=dependency.name,
            )
        )
    for dependency in diff.removed_dependencies:
        changes.append(
            ChangeSummary(
                origin="snapshot_diff",
                category="dependency_change",
                description=f"Dependency {dependency.name!r} ({dependency.ecosystem}) was removed.",
                component_name=dependency.name,
            )
        )
    for finding in diff.added_findings:
        changes.append(
            ChangeSummary(
                origin="snapshot_diff",
                category="added",
                description=f"New finding: {finding.statement}",
                confidence=finding.confidence.value,
            )
        )
    for finding in diff.resolved_findings:
        changes.append(
            ChangeSummary(
                origin="snapshot_diff",
                category="removed",
                description=f"Finding resolved: {finding.statement}",
                confidence=finding.confidence.value,
            )
        )
    return changes


def _update_availability_changes(assessments: list[ImpactAssessment]) -> list[ChangeSummary]:
    changes: list[ChangeSummary] = []
    for assessment in assessments:
        for item in assessment.state_diff.items:
            changes.append(
                ChangeSummary(
                    origin="update_availability",
                    category=item.category.value,
                    description=item.description,
                    confidence=item.confidence.value,
                    component_name=assessment.state_diff.identity.name,
                )
            )
    return changes


def _collect_evidence(
    snapshot: Snapshot, update_assessments: list[ImpactAssessment]
) -> list[EvidenceRef]:
    by_id: dict[str, EvidenceRef] = {}

    def add(evidence_list: list[Evidence], label: str) -> None:
        for evidence in evidence_list:
            ref = by_id.setdefault(evidence.id, EvidenceRef(evidence=evidence))
            if label not in ref.referenced_by:
                ref.referenced_by.append(label)

    for component in snapshot.components:
        add(component.evidence, f"component:{component.name}")
        for dependency in component.dependencies:
            add(dependency.evidence, f"dependency:{dependency.name}")
    for capability in snapshot.capabilities:
        add(capability.evidence, f"capability:{capability.name}")
    for finding in snapshot.findings:
        add(finding.evidence, f"finding:{finding.category}")
    for research_result in snapshot.research:
        add(research_result.evidence, f"research:{research_result.identifier}")
    for assessment in update_assessments:
        add(assessment.evidence, f"update:{assessment.state_diff.identity.name}")

    return list(by_id.values())


def build_dashboard_data(
    snapshot: Snapshot,
    *,
    previous_snapshot: Snapshot | None = None,
    update_check: UpdateCheckResult | None = None,
) -> DashboardData:
    """Build the Dashboard's read model from already-computed domain state.

    `previous_snapshot` and `update_check` are both optional: omitting
    either means that comparison was not performed this run, which is
    surfaced honestly via `OverviewCounts.has_previous_snapshot` /
    `has_update_check` rather than rendered as "no changes found".
    """
    dependencies = _all_dependencies(snapshot.components)
    assessments = update_check.assessments if update_check else []
    unavailable = update_check.unavailable if update_check else []

    changes: list[ChangeSummary] = []
    if previous_snapshot is not None:
        changes.extend(_snapshot_diff_changes(previous_snapshot, snapshot))
    if update_check is not None:
        changes.extend(_update_availability_changes(assessments))

    overview = OverviewCounts(
        target_name=snapshot.target.name,
        target_locator=snapshot.target.locator,
        snapshot_id=snapshot.id,
        tool_version=snapshot.tool_version,
        generated_at=snapshot.created_at,
        component_count=len(snapshot.components),
        component_counts_by_kind=dict(Counter(c.kind.value for c in snapshot.components)),
        capability_count=len(snapshot.capabilities),
        dependency_count=len(dependencies),
        relationship_count=len(snapshot.relationships),
        finding_count=len(snapshot.findings),
        finding_counts_by_severity=dict(Counter(f.severity.value for f in snapshot.findings)),
        recommendation_count=len(snapshot.recommendations),
        proposal_count=len(snapshot.proposals),
        research_result_count=len(snapshot.research),
        approval_count=len(snapshot.approvals),
        verification_count=len(snapshot.verification),
        execution_count=len(snapshot.executions),
        adr_count=len(snapshot.adrs),
        has_previous_snapshot=previous_snapshot is not None,
        previous_snapshot_id=previous_snapshot.id if previous_snapshot else None,
        has_update_check=update_check is not None,
        update_assessment_count=len(assessments),
        update_unavailable_count=len(unavailable),
        update_verdict_counts=dict(Counter(a.verdict.value for a in assessments)),
    )

    research_rankings = [
        ResearchAssessmentView(
            result=a.result,
            has_license=a.has_license,
            license_confidence=a.license_confidence.value,
            is_recently_active=a.is_recently_active,
            is_archived=a.is_archived,
            stargazer_count=a.stargazer_count,
            unknown_dimensions=list(a.unknown_dimensions),
        )
        for a in rank_candidates(snapshot.research)
    ]

    return DashboardData(
        overview=overview,
        components=snapshot.components,
        capabilities=snapshot.capabilities,
        relationships=snapshot.relationships,
        dependencies=dependencies,
        findings=snapshot.findings,
        research=snapshot.research,
        research_rankings=research_rankings,
        recommendations=snapshot.recommendations,
        proposals=snapshot.proposals,
        executions=snapshot.executions,
        verifications=snapshot.verification,
        approvals=snapshot.approvals,
        adrs=snapshot.adrs,
        update_assessments=assessments,
        update_unavailable=[
            UpdateLookupFailureView(ecosystem=f.ecosystem, name=f.name, message=f.message)
            for f in unavailable
        ],
        changes=changes,
        evidence=_collect_evidence(snapshot, assessments),
        governance=GovernanceView(
            default_max_permission_level=DEFAULT_MAX_PERMISSION_LEVEL.name,
            forbidden_actions=sorted(FORBIDDEN_BY_DEFAULT_ACTIONS),
        ),
    )
