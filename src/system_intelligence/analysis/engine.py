"""Analysis orchestrator: run every Phase 3 analyzer over a `DiscoveryResult`.

Mirrors `discovery.inventory`'s role for Phase 2: this is the only module
that knows about every individual analyzer. Callers (the CLI) depend on
this module, not on each analyzer directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from system_intelligence.analysis.architecture import detect_circular_dependencies
from system_intelligence.analysis.capabilities import (
    attach_consumers,
    detect_duplicate_capabilities,
    extract_capabilities,
)
from system_intelligence.analysis.ci_quality import audit_ci_and_tests
from system_intelligence.analysis.dependencies import extract_dependencies_by_manifest
from system_intelligence.analysis.documentation import audit_documentation
from system_intelligence.analysis.gaps import audit_capability_gaps
from system_intelligence.analysis.relationships import build_relationships
from system_intelligence.analysis.unused import audit_unused_skills
from system_intelligence.core.entities import (
    Agent,
    Component,
    Dependency,
    Document,
    Repository,
    Skill,
)
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.discovery.inventory import DiscoveryResult


@dataclass(frozen=True)
class AnalysisResult:
    snapshot: Snapshot


def _component_directory(component: Component) -> str | None:
    """The directory (relative to the repo root) whose manifest would belong
    to `component`, if any. `None` means there is nothing to attribute a
    manifest to — the Repository is always "." (see `discovery.inventory`);
    any other Component only has a known directory when discovery recorded
    its own `path` (e.g. a Skill's `path` is its `SKILL.md` file, so its
    directory is that file's parent). Never guessed from a name or kind.
    """
    if isinstance(component, Repository):
        return "."
    if component.path is None:
        return None
    return str(Path(component.path).parent)


def _attach_dependencies_by_component(
    components: list[Component],
    dependencies_by_directory: dict[str, list[Dependency]],
    repository_id: str,
) -> list[Component]:
    """Attribute each manifest's dependencies to the Component whose own
    directory the manifest lives in, falling back to the Repository when no
    other Component's directory matches — never a new Component, never a
    silent drop.
    """
    directory_to_component_id: dict[str, str] = {}
    for component in components:
        directory = _component_directory(component)
        if directory is None:
            continue
        # First match wins: two Components should not legitimately share a
        # directory (each Skill is keyed by its own SKILL.md path), so this
        # only ever matters for the Repository's own "." entry.
        directory_to_component_id.setdefault(directory, component.id)

    dependencies_by_component_id: dict[str, list[Dependency]] = {}
    for directory, dependencies in dependencies_by_directory.items():
        component_id = directory_to_component_id.get(directory, repository_id)
        dependencies_by_component_id.setdefault(component_id, []).extend(dependencies)

    def _with_dependencies(component: Component) -> Component:
        extra = dependencies_by_component_id.get(component.id)
        if not extra:
            return component
        return component.model_copy(update={"dependencies": [*component.dependencies, *extra]})

    return [_with_dependencies(component) for component in components]


def analyze_local_repository(discovery: DiscoveryResult) -> AnalysisResult:
    """Run every Phase 3 analyzer and populate findings, capabilities, and dependencies."""
    snapshot = discovery.snapshot
    root = Path(snapshot.target.locator)

    repository = next(c for c in snapshot.components if isinstance(c, Repository))
    skills = [c for c in snapshot.components if isinstance(c, Skill)]
    agents = [c for c in snapshot.components if isinstance(c, Agent)]
    documents = [c for c in snapshot.components if isinstance(c, Document)]

    capabilities = extract_capabilities([*skills, *agents])
    dependencies_by_directory = extract_dependencies_by_manifest(root, discovery.package_manifests)

    findings = [
        *audit_documentation(repository, documents),
        *audit_ci_and_tests(repository, root, discovery.ci_jobs),
        *detect_duplicate_capabilities(capabilities),
        *audit_unused_skills(skills, root),
        *detect_circular_dependencies(root),
        *audit_capability_gaps(root, capabilities),
    ]

    updated_components = _attach_dependencies_by_component(
        snapshot.components, dependencies_by_directory, repository.id
    )
    capabilities = attach_consumers(capabilities, updated_components)
    relationships = build_relationships(updated_components, capabilities)

    updated_snapshot = snapshot.model_copy(
        update={
            "components": updated_components,
            "capabilities": capabilities,
            "relationships": relationships,
            "findings": findings,
        }
    )
    return AnalysisResult(snapshot=updated_snapshot)
