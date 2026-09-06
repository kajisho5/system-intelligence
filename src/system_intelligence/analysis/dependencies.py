"""Dependency extraction from package manifests (R2, "dependency graph").

Phase 3 scope: parse declared dependencies out of `pyproject.toml` (PEP 621
`[project.dependencies]`) and `package.json` (`dependencies`/
`devDependencies`). No dependency resolution, transitive graph, or version
conflict detection yet — this only records what a manifest *declares*.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from system_intelligence.core.entities import Dependency
from system_intelligence.core.enums import Confidence
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.ids import stable_id
from system_intelligence.discovery.structure import PackageManifest

_PEP508_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$")


def _manifest_evidence(rel_path: str, name: str) -> Evidence:
    return Evidence(
        kind=EvidenceKind.PACKAGE_METADATA,
        source=rel_path,
        observation=f"{name!r} declared as a dependency in {rel_path}",
        confidence=Confidence.VERIFIED,
    )


def _parse_pep508(requirement: str, rel_path: str) -> Dependency | None:
    match = _PEP508_NAME_RE.match(requirement)
    if not match:
        return None
    name, rest = match.groups()
    # Strip an environment marker (anything after ';') before treating the
    # remainder as a version constraint.
    constraint = rest.split(";", 1)[0].strip()
    return Dependency(
        # Keyed by manifest path too: a monorepo with more than one
        # pyproject.toml can legitimately declare the same package name at
        # different constraints, and those must not collide into one id.
        id=stable_id("dependency", "pypi", rel_path, name),
        name=name,
        ecosystem="pypi",
        version_constraint=constraint or None,
        evidence=[_manifest_evidence(rel_path, name)],
    )


def _extract_pyproject_dependencies(path: Path, rel_path: str) -> list[Dependency]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    requirements = data.get("project", {}).get("dependencies", [])
    dependencies = [_parse_pep508(r, rel_path) for r in requirements if isinstance(r, str)]
    return [d for d in dependencies if d is not None]


def _extract_package_json_dependencies(path: Path, rel_path: str) -> list[Dependency]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    dependencies: list[Dependency] = []
    for section in ("dependencies", "devDependencies"):
        section_value = data.get(section, {})
        if not isinstance(section_value, dict):
            continue  # malformed manifest: not the conventional name->version mapping
        for name, version in section_value.items():
            dependencies.append(
                Dependency(
                    id=stable_id("dependency", "npm", rel_path, name),
                    name=name,
                    ecosystem="npm",
                    version_constraint=str(version),
                    evidence=[_manifest_evidence(rel_path, name)],
                )
            )
    return dependencies


_EXTRACTORS = {
    "pyproject.toml": _extract_pyproject_dependencies,
    "package.json": _extract_package_json_dependencies,
}


def extract_dependencies_by_manifest(
    root: Path, manifests: list[PackageManifest]
) -> dict[str, list[Dependency]]:
    """Like `extract_dependencies`, but keyed by each manifest's own directory.

    The directory is relative to `root` ("." for a manifest at the repo
    root). This lets a caller attribute each `Dependency` to whichever
    Component's own files live in that directory (e.g. a Skill whose
    directory contains its own `package.json`) instead of collapsing every
    manifest in the repository onto one Component — while still only using
    information the manifest itself already provides (its own path), never
    a guess about which Component "probably" owns it.
    """
    by_directory: dict[str, list[Dependency]] = {}
    for manifest in manifests:
        extractor = _EXTRACTORS.get(Path(manifest.path).name)
        if extractor is None:
            continue
        dependencies = extractor(root / manifest.path, manifest.path)
        if not dependencies:
            continue
        directory = str(Path(manifest.path).parent)
        by_directory.setdefault(directory, []).extend(dependencies)
    return by_directory


def extract_dependencies(root: Path, manifests: list[PackageManifest]) -> list[Dependency]:
    """Parse every manifest System Intelligence knows how to read.

    Manifests without a registered extractor (Cargo.toml, go.mod, pom.xml,
    build.gradle, Gemfile) are still reported by `structure.scan_structure`
    as evidence of the ecosystem, but their dependency lists are not parsed
    yet. Flattens `extract_dependencies_by_manifest` — kept for callers that
    only need the combined list (e.g. a whole-repository dependency count),
    not per-Component attribution.
    """
    by_directory = extract_dependencies_by_manifest(root, manifests)
    return [dependency for dependencies in by_directory.values() for dependency in dependencies]
