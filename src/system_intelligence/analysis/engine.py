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
    detect_duplicate_capabilities,
    extract_capabilities,
)
from system_intelligence.analysis.ci_quality import audit_ci_and_tests
from system_intelligence.analysis.dependencies import extract_dependencies
from system_intelligence.analysis.documentation import audit_documentation
from system_intelligence.analysis.relationships import build_relationships
from system_intelligence.analysis.unused import audit_unused_skills
from system_intelligence.core.entities import Document, Repository, Skill
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.discovery.inventory import DiscoveryResult


@dataclass(frozen=True)
class AnalysisResult:
    snapshot: Snapshot


def analyze_local_repository(discovery: DiscoveryResult) -> AnalysisResult:
    """Run every Phase 3 analyzer and populate findings, capabilities, and dependencies."""
    snapshot = discovery.snapshot
    root = Path(snapshot.target.locator)

    repository = next(c for c in snapshot.components if isinstance(c, Repository))
    skills = [c for c in snapshot.components if isinstance(c, Skill)]
    documents = [c for c in snapshot.components if isinstance(c, Document)]

    capabilities = extract_capabilities(skills)
    dependencies = extract_dependencies(root, discovery.package_manifests)

    findings = [
        *audit_documentation(repository, documents),
        *audit_ci_and_tests(repository, root, discovery.ci_jobs),
        *detect_duplicate_capabilities(capabilities),
        *audit_unused_skills(skills, root),
        *detect_circular_dependencies(root),
    ]

    updated_repository = repository.model_copy(update={"dependencies": dependencies})
    updated_components = [
        updated_repository if c.id == repository.id else c for c in snapshot.components
    ]
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
