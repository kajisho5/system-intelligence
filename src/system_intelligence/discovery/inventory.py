"""Discovery orchestrator: turn a local path into a populated `Snapshot`.

Wires together git metadata, structure scanning, Skill detection, and
CI/document detection (docs/design/IMPLEMENTATION_BACKLOG.md, Epic 3) into
the canonical `Snapshot` (docs/design/docs/12-storage-and-state.md). This is
intentionally the only place that knows about all of the individual
detectors — callers (the CLI) depend on this module, not on each detector.

`CIJob` has no dedicated file in the canonical snapshot layout (only
`components`, `capabilities`, `relationships`, `findings`,
`recommendations`, `research`, `approvals`, and `verification` do — see
`core.snapshot`), so Phase 2 surfaces detected CI jobs alongside the
Snapshot rather than inventing an unsanctioned snapshot file for them.
Representing CI jobs as first-class, persisted entities is left for the
analysis phase, once it's clear whether they belong in a relationship
(`tested_by`/`deployed_by`) or need their own canonical file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from system_intelligence.core.entities import CIJob, Component, Repository
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.discovery.ci_docs import detect_ci_jobs, detect_root_documents
from system_intelligence.discovery.git_metadata import collect_git_metadata
from system_intelligence.discovery.skills import detect_skills
from system_intelligence.discovery.structure import PackageManifest, scan_structure
from system_intelligence.discovery.target import resolve_local_target


@dataclass(frozen=True)
class DiscoveryResult:
    snapshot: Snapshot
    ci_jobs: list[CIJob]
    package_manifests: list[PackageManifest]


def discover_local_repository(locator: str) -> DiscoveryResult:
    """Run every Phase 2 discovery detector against a local path.

    Returns a `Snapshot` with `components` populated (the repository itself,
    any detected Skills, and a Document per detected root doc) plus the
    detected `CIJob` list. `findings`/`recommendations`/etc. stay empty —
    those belong to later phases.
    """
    target = resolve_local_target(locator)
    root = Path(target.locator)

    git_metadata = collect_git_metadata(root)
    structure = scan_structure(root)
    ci_jobs = detect_ci_jobs(root)
    documents = detect_root_documents(root)
    skills = detect_skills(root)

    repository = Repository(
        name=target.name,
        url=git_metadata.remote_url,
        default_branch=git_metadata.default_branch,
        local_path=str(root),
        languages=structure.languages,
        path=".",
        evidence=[*git_metadata.evidence, *structure.evidence],
    )

    components: list[Component] = [repository, *skills, *documents]

    snapshot = Snapshot(target=target, components=components)
    return DiscoveryResult(
        snapshot=snapshot, ci_jobs=ci_jobs, package_manifests=structure.package_manifests
    )
