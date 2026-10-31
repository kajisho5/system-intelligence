"""Discovery orchestrator: turn a local path into a populated `Snapshot`.

Wires together git metadata, structure scanning, Skill/Agent detection,
and CI/document detection (docs/design/IMPLEMENTATION_BACKLOG.md, Epic 3) into
the canonical `Snapshot` (docs/design/docs/12-storage-and-state.md). This is
intentionally the only place that knows about all of the individual
detectors — callers (the CLI) depend on this module, not on each detector.

`CIJob` has no dedicated file in the canonical snapshot layout (only
`components`, `capabilities`, `relationships`, `findings`,
`recommendations`, `research`, `approvals`, `verification`, `executions`,
`audit_log`, and `adrs` do — see `core.snapshot`), so Phase 2 surfaces
detected CI jobs alongside the Snapshot rather than inventing an
unsanctioned snapshot file for them. Representing CI jobs as first-class,
persisted entities is left for the analysis phase, once it's clear
whether they belong in a relationship (`tested_by`/`deployed_by`) or need
their own canonical file. Detected ADRs, unlike CI jobs, get their own
`Snapshot.adrs` field directly (see `discovery.adr`) since they need no
further analysis-phase transformation before being worth persisting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from system_intelligence.core.entities import CIJob, Component, Repository
from system_intelligence.core.ids import stable_id
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.discovery.adr import detect_adrs
from system_intelligence.discovery.agents import detect_agents
from system_intelligence.discovery.ci_docs import (
    detect_ci_jobs,
    detect_license,
    detect_root_documents,
)
from system_intelligence.discovery.contracts import (
    DEFAULT_CONTRACT_TIMEOUT_SECONDS,
    ContractObservation,
    collect_contracts,
)
from system_intelligence.discovery.git_metadata import collect_git_metadata
from system_intelligence.discovery.ownership import OwnershipObservation, collect_ownership
from system_intelligence.discovery.skills import detect_skills
from system_intelligence.discovery.structure import PackageManifest, scan_structure
from system_intelligence.discovery.target import resolve_target


@dataclass(frozen=True)
class DiscoveryResult:
    snapshot: Snapshot
    ci_jobs: list[CIJob]
    package_manifests: list[PackageManifest]
    contracts: list[ContractObservation] = field(default_factory=list)
    ownership: list[OwnershipObservation] = field(default_factory=list)


def discover_local_repository(
    locator: str,
    contract_files: Sequence[Path] = (),
    contract_commands: Sequence[Sequence[str]] = (),
    contract_timeout: float = DEFAULT_CONTRACT_TIMEOUT_SECONDS,
    ownership_maps: Sequence[Path] = (),
) -> DiscoveryResult:
    """Run every Phase 2 discovery detector against a local path or a
    GitHub repository (`discovery.target.resolve_target`).

    Returns a `Snapshot` with `components` populated (the repository itself,
    any detected Skills, and a Document per detected root doc) and `adrs`
    populated, plus the detected `CIJob` list. `findings`/`recommendations`/
    etc. stay empty — those belong to later phases.

    `contracts` holds every Capability Contract source collected by
    `discovery.contracts.collect_contracts`: the target's own static
    `.si/contracts.json` always, plus `contract_files`/`contract_commands`
    only when the caller passes them (a command is never inferred from the
    target).

    `ownership` holds every ownership document collected by
    `discovery.ownership.collect_ownership`: the target's own static
    `.si/ownership.json` (and the maps it lists) always, plus
    `ownership_maps` when the caller passes them. Both are only read.
    """
    target = resolve_target(locator)
    root = Path(target.locator)

    git_metadata = collect_git_metadata(root)
    structure = scan_structure(root)
    ci_jobs = detect_ci_jobs(root)
    documents = detect_root_documents(root)
    license_id = detect_license(root, documents)
    skills = detect_skills(root)
    agents = detect_agents(root)
    adrs = detect_adrs(root)
    contracts = collect_contracts(root, contract_files, contract_commands, contract_timeout)
    ownership = collect_ownership(root, ownership_maps)

    repository = Repository(
        id=stable_id("repository", "root"),
        name=target.name,
        is_git_repository=git_metadata.is_git_repository,
        url=git_metadata.remote_url,
        default_branch=git_metadata.default_branch,
        local_path=str(root),
        license=license_id,
        last_commit_sha=git_metadata.last_commit_sha,
        last_commit_author=git_metadata.last_commit_author,
        last_commit_date=git_metadata.last_commit_date,
        is_dirty=git_metadata.is_dirty,
        languages=structure.languages,
        path=".",
        evidence=[*git_metadata.evidence, *structure.evidence],
    )

    components: list[Component] = [repository, *skills, *agents, *documents]

    snapshot = Snapshot(target=target, components=components, adrs=adrs)
    return DiscoveryResult(
        snapshot=snapshot,
        ci_jobs=ci_jobs,
        package_manifests=structure.package_manifests,
        contracts=contracts,
        ownership=ownership,
    )
