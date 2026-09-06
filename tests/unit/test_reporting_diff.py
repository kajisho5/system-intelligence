from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Component, Dependency, Target
from system_intelligence.core.enums import (
    CapabilityStatus,
    ComponentKind,
    Confidence,
    Severity,
    TargetKind,
)
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.reporting.diff import diff_snapshots


def _target() -> Target:
    return Target(name="t", kind=TargetKind.LOCAL_PATH, locator="/repo")


def _finding(statement: str) -> Finding:
    return Finding(
        category="test",
        severity=Severity.LOW,
        statement=statement,
        confidence=Confidence.HIGH,
        evidence=[Evidence(kind=EvidenceKind.FILE, source="x", observation="x")],
    )


def test_diff_snapshots_no_changes() -> None:
    before = Snapshot(target=_target())
    after = Snapshot(target=_target())
    result = diff_snapshots(before, after)
    assert result.has_changes is False


def test_diff_snapshots_added_and_removed_components() -> None:
    before = Snapshot(
        target=_target(),
        components=[Component(id="c1", name="a", kind=ComponentKind.PACKAGE)],
    )
    after = Snapshot(
        target=_target(),
        components=[Component(id="c2", name="b", kind=ComponentKind.PACKAGE)],
    )
    result = diff_snapshots(before, after)
    assert [c.id for c in result.added_components] == ["c2"]
    assert [c.id for c in result.removed_components] == ["c1"]


def test_diff_snapshots_unchanged_component_is_not_reported() -> None:
    component = Component(id="c1", name="a", kind=ComponentKind.PACKAGE)
    before = Snapshot(target=_target(), components=[component])
    after = Snapshot(target=_target(), components=[component])
    result = diff_snapshots(before, after)
    assert result.added_components == []
    assert result.removed_components == []


def test_diff_snapshots_findings_matched_by_content_not_id() -> None:
    # Two independently-created Findings with the same category/statement
    # (as two separate scans would produce) must be treated as "unchanged".
    before = Snapshot(target=_target(), findings=[_finding("No README file was found.")])
    after = Snapshot(target=_target(), findings=[_finding("No README file was found.")])
    result = diff_snapshots(before, after)
    assert result.added_findings == []
    assert result.resolved_findings == []


def test_diff_snapshots_resolved_and_introduced_findings() -> None:
    before = Snapshot(target=_target(), findings=[_finding("No README file was found.")])
    after = Snapshot(target=_target(), findings=[_finding("No CI configuration was found.")])
    result = diff_snapshots(before, after)
    assert [f.statement for f in result.resolved_findings] == ["No README file was found."]
    assert [f.statement for f in result.added_findings] == ["No CI configuration was found."]


def test_diff_snapshots_capabilities_and_dependencies() -> None:
    dependency = Dependency(id="d1", name="pydantic", ecosystem="pypi")
    component_with_dep = Component(
        id="c1", name="repo", kind=ComponentKind.REPOSITORY, dependencies=[dependency]
    )
    before = Snapshot(
        target=_target(),
        components=[component_with_dep],
        capabilities=[Capability(id="cap1", name="x", status=CapabilityStatus.AVAILABLE)],
    )
    after = Snapshot(
        target=_target(),
        components=[Component(id="c1", name="repo", kind=ComponentKind.REPOSITORY)],
    )

    result = diff_snapshots(before, after)

    assert [c.id for c in result.removed_capabilities] == ["cap1"]
    assert [d.id for d in result.removed_dependencies] == ["d1"]
