"""Snapshot diff: compare two canonical snapshots of (presumably) the same target.

Relies on entity ids being stable across scans (`core.ids.stable_id`) for
components, capabilities, and dependencies — an id that changes every scan
would make every re-scan look like a full replacement. Findings have no
such stable id (they're recomputed each run), so they are matched by
content (`category` + `statement`) instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import Component, Dependency
from system_intelligence.core.findings import Finding
from system_intelligence.core.snapshot import Snapshot


@dataclass(frozen=True)
class SnapshotDiff:
    from_snapshot_id: str
    to_snapshot_id: str
    added_components: list[Component] = field(default_factory=list)
    removed_components: list[Component] = field(default_factory=list)
    added_capabilities: list[Capability] = field(default_factory=list)
    removed_capabilities: list[Capability] = field(default_factory=list)
    added_dependencies: list[Dependency] = field(default_factory=list)
    removed_dependencies: list[Dependency] = field(default_factory=list)
    added_findings: list[Finding] = field(default_factory=list)
    resolved_findings: list[Finding] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(
            (
                self.added_components,
                self.removed_components,
                self.added_capabilities,
                self.removed_capabilities,
                self.added_dependencies,
                self.removed_dependencies,
                self.added_findings,
                self.resolved_findings,
            )
        )


def _finding_key(finding: Finding) -> tuple[str, str]:
    return (finding.category, finding.statement)


def _all_dependencies(snapshot: Snapshot) -> list[Dependency]:
    return [dep for component in snapshot.components for dep in component.dependencies]


def diff_snapshots(before: Snapshot, after: Snapshot) -> SnapshotDiff:
    before_components = {c.id: c for c in before.components}
    after_components = {c.id: c for c in after.components}
    added_components = [c for cid, c in after_components.items() if cid not in before_components]
    removed_components = [c for cid, c in before_components.items() if cid not in after_components]

    before_capabilities = {c.id: c for c in before.capabilities}
    after_capabilities = {c.id: c for c in after.capabilities}
    added_capabilities = [
        c for cid, c in after_capabilities.items() if cid not in before_capabilities
    ]
    removed_capabilities = [
        c for cid, c in before_capabilities.items() if cid not in after_capabilities
    ]

    before_dependencies = {d.id: d for d in _all_dependencies(before)}
    after_dependencies = {d.id: d for d in _all_dependencies(after)}
    added_dependencies = [
        d for did, d in after_dependencies.items() if did not in before_dependencies
    ]
    removed_dependencies = [
        d for did, d in before_dependencies.items() if did not in after_dependencies
    ]

    before_finding_keys = {_finding_key(f) for f in before.findings}
    after_finding_keys = {_finding_key(f) for f in after.findings}
    added_findings = [f for f in after.findings if _finding_key(f) not in before_finding_keys]
    resolved_findings = [f for f in before.findings if _finding_key(f) not in after_finding_keys]

    return SnapshotDiff(
        from_snapshot_id=before.id,
        to_snapshot_id=after.id,
        added_components=added_components,
        removed_components=removed_components,
        added_capabilities=added_capabilities,
        removed_capabilities=removed_capabilities,
        added_dependencies=added_dependencies,
        removed_dependencies=removed_dependencies,
        added_findings=added_findings,
        resolved_findings=resolved_findings,
    )
