"""Dependency extraction from package manifests (R2, "dependency graph").

Phase 3 scope: parse declared dependencies out of `pyproject.toml` (PEP 621
`[project.dependencies]`), `package.json` (`dependencies`/
`devDependencies`), `Cargo.toml` (`[dependencies]`/`[dev-dependencies]`/
`[build-dependencies]`), and `go.mod` (`require` directives). No dependency
resolution, transitive graph, or version conflict detection yet — this
only records what a manifest *declares*.
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


def _cargo_version_constraint(spec: object) -> str | None:
    """The registry version requirement `spec` declares, if any.

    A Cargo dependency table without a `version` key (`{ path = "..." }`,
    `{ git = "..." }`, `{ workspace = true }`) has nothing a registry
    lookup could resolve against — that case returns `None` so the caller
    skips it rather than recording a `Dependency` with a fabricated or
    absent constraint.
    """
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        version = spec.get("version")
        return version if isinstance(version, str) else None
    return None


def _extract_cargo_dependencies(path: Path, rel_path: str) -> list[Dependency]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    dependencies: list[Dependency] = []
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        section_value = data.get(section, {})
        if not isinstance(section_value, dict):
            continue  # malformed manifest: not the conventional name->spec table
        for name, spec in section_value.items():
            constraint = _cargo_version_constraint(spec)
            if constraint is None:
                continue
            dependencies.append(
                Dependency(
                    id=stable_id("dependency", "cargo", rel_path, name),
                    name=name,
                    ecosystem="cargo",
                    version_constraint=constraint,
                    evidence=[_manifest_evidence(rel_path, name)],
                )
            )
    return dependencies


def _parse_go_require_entry(entry: str, rel_path: str) -> Dependency | None:
    """Parse one `require` entry (`<module path> <version>`), trailing
    `// indirect` (or any other) comment already known to be stripped by
    the caller. An indirect dependency is still a real declared dependency
    -- Go's own module graph -- so it is recorded the same as a direct one,
    matching how `package.json`'s `devDependencies` are recorded without a
    separate "dev" flag today.
    """
    parts = entry.split()
    if len(parts) != 2:
        return None
    name, version = parts
    return Dependency(
        id=stable_id("dependency", "go", rel_path, name),
        name=name,
        ecosystem="go",
        version_constraint=version,
        evidence=[_manifest_evidence(rel_path, name)],
    )


def _extract_go_dependencies(path: Path, rel_path: str) -> list[Dependency]:
    """Parse `go.mod`'s `require` directives (single-line and block form).

    Go's Minimal Version Selection means a `require` line is always an
    exact, already-resolved version (`v1.2.3`, or a pseudo-version like
    `v0.0.0-20210101000000-abcdef123456`) -- never a range -- so unlike
    Cargo's bare-version convention there is no ambiguity to guess at
    here. `module`/`go`/`toolchain`/`replace`/`exclude`/`retract`
    directives are not dependencies and are ignored; `replace` in
    particular means a resolved version can differ from what `require`
    states, which this parser does not attempt to reconcile.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    dependencies: list[Dependency] = []
    in_require_block = False
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue
        if in_require_block:
            if line == ")":
                in_require_block = False
                continue
            dependency = _parse_go_require_entry(line, rel_path)
            if dependency is not None:
                dependencies.append(dependency)
            continue
        if line == "require (":
            in_require_block = True
            continue
        if line.startswith("require "):
            dependency = _parse_go_require_entry(line[len("require ") :].strip(), rel_path)
            if dependency is not None:
                dependencies.append(dependency)
    return dependencies


_EXTRACTORS = {
    "pyproject.toml": _extract_pyproject_dependencies,
    "package.json": _extract_package_json_dependencies,
    "Cargo.toml": _extract_cargo_dependencies,
    "go.mod": _extract_go_dependencies,
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

    Manifests without a registered extractor (pom.xml, build.gradle, Gemfile)
    are still reported by `structure.scan_structure` as evidence of the
    ecosystem, but their dependency lists are not parsed yet. Flattens
    `extract_dependencies_by_manifest` — kept for callers that
    only need the combined list (e.g. a whole-repository dependency count),
    not per-Component attribution.
    """
    by_directory = extract_dependencies_by_manifest(root, manifests)
    return [dependency for dependencies in by_directory.values() for dependency in dependencies]
