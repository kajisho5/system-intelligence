"""Selective capability execution: run exactly the capabilities requested.

Unlike `discovery.discover_local_repository` / `analysis.analyze_local_repository`
(which always run the full Phase 2 / Phase 3 capability sets — that IS the
"inspect"/"diagnose" intent, so they remain the convenient, well-tested
path for those two cases), `run_capabilities` composes the same underlying
functions individually, so a narrower intent (e.g. "documentation_only")
genuinely skips the capabilities it doesn't need rather than computing
everything and discarding the unused parts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from system_intelligence.analysis.architecture import detect_circular_dependencies
from system_intelligence.analysis.capabilities import (
    detect_duplicate_capabilities,
    extract_capabilities,
)
from system_intelligence.analysis.ci_quality import audit_ci_and_tests
from system_intelligence.analysis.dependencies import extract_dependencies
from system_intelligence.analysis.documentation import audit_documentation
from system_intelligence.analysis.gaps import audit_capability_gaps
from system_intelligence.analysis.relationships import build_relationships
from system_intelligence.analysis.unused import audit_unused_skills
from system_intelligence.core.capability import Capability
from system_intelligence.core.entities import (
    ADR,
    Agent,
    CIJob,
    Component,
    Document,
    Repository,
    Skill,
)
from system_intelligence.core.findings import Finding
from system_intelligence.core.ids import stable_id
from system_intelligence.core.recommendations import Recommendation
from system_intelligence.core.relationships import Relationship
from system_intelligence.core.snapshot import Snapshot
from system_intelligence.discovery.adr import detect_adrs
from system_intelligence.discovery.agents import detect_agents
from system_intelligence.discovery.ci_docs import detect_ci_jobs, detect_root_documents
from system_intelligence.discovery.git_metadata import collect_git_metadata
from system_intelligence.discovery.skills import detect_skills
from system_intelligence.discovery.structure import StructureScanResult, scan_structure
from system_intelligence.discovery.target import resolve_target
from system_intelligence.intelligence.registry import resolve_dependencies
from system_intelligence.recommendations.engine import generate_recommendations


@dataclass
class _OrchestrationContext:
    root: Path
    repository: Repository
    structure: StructureScanResult | None = None
    skills: list[Skill] = field(default_factory=list)
    agents: list[Agent] = field(default_factory=list)
    adrs: list[ADR] = field(default_factory=list)
    ci_jobs: list[CIJob] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)


def _run_git_metadata(ctx: _OrchestrationContext) -> None:
    metadata = collect_git_metadata(ctx.root)
    ctx.repository.url = metadata.remote_url
    ctx.repository.default_branch = metadata.default_branch
    ctx.repository.evidence = [*ctx.repository.evidence, *metadata.evidence]


def _run_structure_scan(ctx: _OrchestrationContext) -> None:
    structure = scan_structure(ctx.root)
    ctx.structure = structure
    ctx.repository.languages = structure.languages
    ctx.repository.evidence = [*ctx.repository.evidence, *structure.evidence]


def _run_skill_detection(ctx: _OrchestrationContext) -> None:
    ctx.skills = detect_skills(ctx.root)


def _run_agent_detection(ctx: _OrchestrationContext) -> None:
    ctx.agents = detect_agents(ctx.root)


def _run_adr_detection(ctx: _OrchestrationContext) -> None:
    ctx.adrs = detect_adrs(ctx.root)


def _run_ci_docs_detection(ctx: _OrchestrationContext) -> None:
    ctx.ci_jobs = detect_ci_jobs(ctx.root)
    ctx.documents = detect_root_documents(ctx.root)


def _run_documentation_audit(ctx: _OrchestrationContext) -> None:
    ctx.findings.extend(audit_documentation(ctx.repository, ctx.documents))


def _run_ci_test_audit(ctx: _OrchestrationContext) -> None:
    ctx.findings.extend(audit_ci_and_tests(ctx.repository, ctx.root, ctx.ci_jobs))


def _run_dependency_extraction(ctx: _OrchestrationContext) -> None:
    manifests = ctx.structure.package_manifests if ctx.structure else []
    ctx.repository.dependencies = extract_dependencies(ctx.root, manifests)


def _run_capability_extraction(ctx: _OrchestrationContext) -> None:
    ctx.capabilities = extract_capabilities([*ctx.skills, *ctx.agents])
    ctx.findings.extend(detect_duplicate_capabilities(ctx.capabilities))


def _run_unused_skill_detection(ctx: _OrchestrationContext) -> None:
    ctx.findings.extend(audit_unused_skills([*ctx.skills, *ctx.agents], ctx.root))


def _run_capability_gap_detection(ctx: _OrchestrationContext) -> None:
    ctx.findings.extend(audit_capability_gaps(ctx.root, ctx.capabilities, ctx.repository))


def _run_circular_dependency_detection(ctx: _OrchestrationContext) -> None:
    ctx.findings.extend(detect_circular_dependencies(ctx.root))


def _run_relationship_graph_construction(ctx: _OrchestrationContext) -> None:
    components: list[Component] = [ctx.repository, *ctx.skills, *ctx.agents, *ctx.documents]
    ctx.relationships = build_relationships(components, ctx.capabilities)


def _run_recommendation_ranking(ctx: _OrchestrationContext) -> None:
    ctx.recommendations = generate_recommendations(ctx.findings)


_RUNNERS: dict[str, Callable[[_OrchestrationContext], None]] = {
    "git_metadata": _run_git_metadata,
    "structure_scan": _run_structure_scan,
    "skill_detection": _run_skill_detection,
    "agent_detection": _run_agent_detection,
    "adr_detection": _run_adr_detection,
    "ci_docs_detection": _run_ci_docs_detection,
    "documentation_audit": _run_documentation_audit,
    "ci_test_audit": _run_ci_test_audit,
    "dependency_extraction": _run_dependency_extraction,
    "capability_extraction": _run_capability_extraction,
    "unused_skill_detection": _run_unused_skill_detection,
    "circular_dependency_detection": _run_circular_dependency_detection,
    "relationship_graph_construction": _run_relationship_graph_construction,
    "capability_gap_detection": _run_capability_gap_detection,
    "recommendation_ranking": _run_recommendation_ranking,
}


def run_capabilities(locator: str, capability_ids: list[str]) -> Snapshot:
    """Run exactly `capability_ids` (plus their dependencies) against `locator`.

    Capabilities absent from the request never execute — e.g. requesting
    only `documentation_audit` never scans structure, detects Skills, or
    parses dependencies.
    """
    target = resolve_target(locator)
    root = Path(target.locator)
    repository = Repository(id=stable_id("repository", "root"), name=target.name, path=".")
    ctx = _OrchestrationContext(root=root, repository=repository)

    for capability_id in resolve_dependencies(set(capability_ids)):
        _RUNNERS[capability_id](ctx)

    components: list[Component] = [ctx.repository, *ctx.skills, *ctx.agents, *ctx.documents]
    return Snapshot(
        target=target,
        components=components,
        capabilities=ctx.capabilities,
        relationships=ctx.relationships,
        findings=ctx.findings,
        recommendations=ctx.recommendations,
        adrs=ctx.adrs,
    )
