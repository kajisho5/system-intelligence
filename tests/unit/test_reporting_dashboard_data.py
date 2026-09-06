import json

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
from system_intelligence.reporting.dashboard_data import DashboardData, build_dashboard_data


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


def test_build_dashboard_data_counts_relationships() -> None:
    from system_intelligence.core.enums import RelationshipType
    from system_intelligence.core.relationships import Relationship

    relationship = Relationship(type=RelationshipType.DEPENDS_ON, source_id="r1", target_id="d1")
    snapshot = Snapshot(target=_target(), relationships=[relationship])

    data = build_dashboard_data(snapshot)

    assert data.overview.relationship_count == 1


def test_build_dashboard_data_preserves_relationship_objects_and_types() -> None:
    """The export contract carries the actual typed Relationship objects,
    not just a count — distinct RelationshipTypes (DEPENDS_ON/PROVIDES/USES/
    DUPLICATES) must never collapse into a generic dependency count."""
    from system_intelligence.core.enums import RelationshipType
    from system_intelligence.core.relationships import Relationship

    depends_on = Relationship(type=RelationshipType.DEPENDS_ON, source_id="r1", target_id="d1")
    provides = Relationship(type=RelationshipType.PROVIDES, source_id="r1", target_id="c1")
    snapshot = Snapshot(target=_target(), relationships=[depends_on, provides])

    data = build_dashboard_data(snapshot)

    assert len(data.relationships) == 2
    assert {r.type for r in data.relationships} == {
        RelationshipType.DEPENDS_ON,
        RelationshipType.PROVIDES,
    }
    assert data.relationships[0].id == depends_on.id


def test_build_dashboard_data_surfaces_tool_version_for_compatibility() -> None:
    """`Snapshot.tool_version` is the one existing compatibility marker
    (docs/design/docs/12-storage-and-state.md) -- an external reader of
    this read model needs it too, so it is surfaced here rather than
    inventing a second, parallel version number."""
    snapshot = Snapshot(target=_target())

    data = build_dashboard_data(snapshot)

    assert data.overview.tool_version == snapshot.tool_version


def test_dashboard_data_component_subclass_fields_survive_whole_object_dump() -> None:
    """Regression test for a real pydantic v2 default behavior: serializing
    `DashboardData` as a whole (exactly what `dashboard_html.py`'s
    `_json_script` does) used to serialize every `components` entry using
    the base `Component` schema, silently dropping subclass-only fields
    like `Repository.url` from the JSON an external consumer reads --
    dumping a Component individually (as `Snapshot.write_to_directory`
    does) never showed this, since that never goes through a *containing*
    model's own `model_dump`. Fixed via `SerializeAsAny`."""
    repo = Repository(id="r1", name="repo", path=".", url="https://example.com/repo.git")
    snapshot = Snapshot(target=_target(), components=[repo])

    data = build_dashboard_data(snapshot)
    payload = json.loads(data.model_dump_json())

    assert payload["components"][0]["url"] == "https://example.com/repo.git"


def test_dashboard_data_reload_restores_fields_but_not_the_component_subclass() -> None:
    """The JSON itself is complete (previous test); reconstructing the
    exact original Python subclass from generic `DashboardData.
    model_validate_json` is a separate, pre-existing limitation shared
    with `Snapshot` itself when not read via `Snapshot.read_from_directory`
    (which explicitly dispatches on `kind`) -- documented here rather than
    silently assumed away."""
    repo = Repository(id="r1", name="repo", path=".", url="https://example.com/repo.git")
    snapshot = Snapshot(target=_target(), components=[repo])

    data = build_dashboard_data(snapshot)
    reloaded = DashboardData.model_validate_json(data.model_dump_json())

    assert reloaded.overview == data.overview
    assert reloaded.components[0].name == repo.name
    assert type(reloaded.components[0]) is not type(repo)


def test_dashboard_data_json_serialization_is_stable_for_a_fixed_object() -> None:
    snapshot = Snapshot(target=_target())
    data = build_dashboard_data(snapshot)

    assert data.model_dump_json() == data.model_dump_json()


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
