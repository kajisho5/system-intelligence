from system_intelligence.analysis.update_intelligence import UpdateCheckResult, UpdateLookupFailure
from system_intelligence.core.component_state import (
    AvailableState,
    ComponentIdentity,
    ComponentState,
)
from system_intelligence.core.entities import Dependency, Repository, Target
from system_intelligence.core.enums import (
    ComponentKind,
    Confidence,
    Severity,
    StateDiffCategory,
    TargetKind,
    UpdateVerdict,
)
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.impact import ImpactAssessment
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.core.state_diff import StateDiff, StateDiffItem
from system_intelligence.reporting.dashboard_data import build_dashboard_data


def _target() -> Target:
    return Target(name="repo", kind=TargetKind.LOCAL_PATH, locator="/repo")


def test_build_dashboard_data_empty_snapshot_has_zero_counts_and_no_fabricated_health() -> None:
    snapshot = Snapshot(target=_target())

    data = build_dashboard_data(snapshot)

    assert data.overview.component_count == 0
    assert data.overview.has_previous_snapshot is False
    assert data.overview.has_update_check is False
    assert data.changes == []
    assert not hasattr(data.overview, "health_score")


def test_build_dashboard_data_counts_components_by_kind() -> None:
    repo = Repository(id="r1", name="repo", path=".")
    snapshot = Snapshot(target=_target(), components=[repo])

    data = build_dashboard_data(snapshot)

    assert data.overview.component_count == 1
    assert data.overview.component_counts_by_kind == {"repository": 1}


def test_build_dashboard_data_flattens_and_dedupes_dependencies() -> None:
    dep = Dependency(id="d1", name="react", ecosystem="npm")
    repo_a = Repository(id="r1", name="repo-a", path="a", dependencies=[dep])
    repo_b = Repository(id="r2", name="repo-b", path="b", dependencies=[dep])
    snapshot = Snapshot(target=_target(), components=[repo_a, repo_b])

    data = build_dashboard_data(snapshot)

    assert data.overview.dependency_count == 1
    assert len(data.dependencies) == 1


def test_build_dashboard_data_groups_findings_by_severity() -> None:
    evidence = [Evidence(kind=EvidenceKind.FILE, source="x", observation="x")]
    finding = Finding(
        category="test_gap",
        severity=Severity.HIGH,
        statement="no tests",
        confidence=Confidence.MEDIUM,
        evidence=evidence,
    )
    snapshot = Snapshot(target=_target(), findings=[finding])

    data = build_dashboard_data(snapshot)

    assert data.overview.finding_counts_by_severity == {"high": 1}


def test_build_dashboard_data_previous_snapshot_populates_changes() -> None:
    before = Snapshot(target=_target())
    repo = Repository(id="r1", name="repo", path=".")
    after = Snapshot(target=_target(), components=[repo])

    data = build_dashboard_data(after, previous_snapshot=before)

    assert data.overview.has_previous_snapshot is True
    assert data.overview.previous_snapshot_id == before.id
    assert any(c.origin == "snapshot_diff" for c in data.changes)


def _impact_assessment() -> ImpactAssessment:
    identity = ComponentIdentity(component_kind=ComponentKind.PACKAGE, name="ffmpeg-skill")
    current = ComponentState(identity=identity, version="0.8.2")
    available = AvailableState(identity=identity, provider="npm", version="0.9.2")
    diff = StateDiff(
        identity=identity,
        from_state=current,
        to_state=available,
        version_delta="0.8.2 -> 0.9.2",
        items=[
            StateDiffItem(
                category=StateDiffCategory.CHANGED,
                description="Version changed",
                confidence=Confidence.HIGH,
            )
        ],
    )
    return ImpactAssessment(
        state_diff=diff,
        unknown_dimensions=("capability", "dependency", "interface", "installation"),
        verdict=UpdateVerdict.REVIEW_REQUIRED,
        verdict_confidence=Confidence.MEDIUM,
        verdict_rationale="cannot confirm safety",
    )


def test_build_dashboard_data_update_check_populates_updates_and_changes() -> None:
    snapshot = Snapshot(target=_target())
    check = UpdateCheckResult(
        assessments=[_impact_assessment()],
        unavailable=[UpdateLookupFailure(ecosystem="pypi", name="ghost", message="timeout")],
    )

    data = build_dashboard_data(snapshot, update_check=check)

    assert data.overview.has_update_check is True
    assert data.overview.update_assessment_count == 1
    assert data.overview.update_unavailable_count == 1
    assert data.overview.update_verdict_counts == {"review_required": 1}
    assert any(c.origin == "update_availability" for c in data.changes)
    assert data.update_unavailable[0].name == "ghost"


def test_build_dashboard_data_evidence_deduplicates_and_tracks_references() -> None:
    evidence = Evidence(kind=EvidenceKind.FILE, source="README.md", observation="found")
    finding = Finding(
        category="documentation_gap",
        severity=Severity.LOW,
        statement="x",
        confidence=Confidence.HIGH,
        evidence=[evidence],
    )
    repo = Repository(id="r1", name="repo", path=".", evidence=[evidence])
    snapshot = Snapshot(target=_target(), components=[repo], findings=[finding])

    data = build_dashboard_data(snapshot)

    assert len(data.evidence) == 1
    assert set(data.evidence[0].referenced_by) == {"component:repo", "finding:documentation_gap"}


def test_build_dashboard_data_governance_reflects_static_policy() -> None:
    snapshot = Snapshot(target=_target())

    data = build_dashboard_data(snapshot)

    assert data.governance.default_max_permission_level == "GENERATE_LOCAL_ARTIFACTS"
    assert "merge_pull_request" in data.governance.forbidden_actions


def test_build_dashboard_data_research_rankings_reuse_scoring_engine() -> None:
    from system_intelligence.core.research import ResearchResult

    result = ResearchResult(
        query="q",
        provider="github",
        source="https://github.com/x/y",
        identifier="x/y",
        license="MIT",
        license_confidence=Confidence.VERIFIED,
    )
    snapshot = Snapshot(target=_target(), research=[result])

    data = build_dashboard_data(snapshot)

    assert len(data.research_rankings) == 1
    assert data.research_rankings[0].has_license is True
