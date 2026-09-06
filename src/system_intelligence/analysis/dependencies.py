"""Dependency extraction from package manifests (R2, "dependency graph").

Phase 3 scope: parse declared dependencies out of `pyproject.toml` (PEP 621
`[project.dependencies]`, and Poetry's own pre-PEP-621
`[tool.poetry.dependencies]` table, still the form most existing Poetry
projects use), `requirements.txt` (each line as one PEP 508 requirement,
pip's own option flags and direct URL/VCS references skipped),
`package.json` (`dependencies`/`devDependencies`), `Cargo.toml`
(`[dependencies]`/`[dev-dependencies]`/`[build-dependencies]`), `go.mod`
(`require` directives), and `pom.xml` (the project's own direct
`<dependencies>`, literal versions only). No transitive graph or version
conflict detection yet.

One resolution step is implemented: a Cargo dependency's sibling
`Cargo.lock` (single-crate projects only -- a workspace's lockfile lives
only at the workspace root, never guessed at from a member crate's own
directory) resolves `Dependency.resolved_version` for an unambiguous
package name, even when the declared constraint itself is a range
(`anyhow = "1.0"` means "the currently *locked* 1.0.x, whichever that
resolved to", not just "some 1.0.x exists"). The equivalent for
npm/pip (`package-lock.json`, `poetry.lock`) is not implemented yet.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from defusedxml import ElementTree as SafeElementTree

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


def _poetry_version_constraint(spec: object) -> str | None:
    """The registry version requirement `spec` declares, if any -- from
    Poetry's own `[tool.poetry.dependencies]` table, not a PEP 508 string.

    A bare version with no operator (`requests = "2.31.0"`) means an EXACT
    pin under Poetry's own convention (confirmed against Poetry's official
    docs, "Exact requirements": "You can specify the exact version of a
    package... This will tell Poetry to install this version and this
    version only" -- unlike Cargo's bare-is-caret convention), so it is
    normalized to PEP 508's own `==`-prefixed form here. That lets this
    ecosystem's already-established `pypi` exact-pin detection
    (`analysis.update_intelligence._EXACT_PIN_RE`, which requires an
    explicit `=`/`==` prefix since a real PEP 508 string always spells one
    out) apply unchanged, with no Poetry-specific carve-out needed there.
    A caret/tilde/wildcard-prefixed constraint (`^2.31.0`, `~2.31.0`,
    `1.*`) is left as-is -- never normalized to look like an exact pin --
    and a spec with no resolvable version at all (`{ git = "..." }`,
    `{ path = "..." }`) returns `None`, mirroring
    `_cargo_version_constraint`.
    """
    if isinstance(spec, str):
        version = spec
    elif isinstance(spec, dict):
        raw_version = spec.get("version")
        if not isinstance(raw_version, str):
            return None
        version = raw_version
    else:
        return None
    stripped = version.strip()
    if stripped and stripped[0].isdigit():
        return f"=={stripped}"
    return stripped or None


def _extract_poetry_dependencies(data: dict[str, object], rel_path: str) -> list[Dependency]:
    """Parse Poetry's own `[tool.poetry.dependencies]` table.

    Distinct from PEP 621's `[project.dependencies]` array of requirement
    strings (`_parse_pep508`): Poetry's native table predates PEP 621
    support and is still the form most existing Poetry projects use,
    mapping name -> a bare/operator-prefixed version string or a table
    (`{ version = "...", extras = [...] }`). `python` (Poetry's own
    special-cased interpreter-version key, not a package) is skipped.
    """
    tool_table = data.get("tool")
    poetry_table = tool_table.get("poetry") if isinstance(tool_table, dict) else None
    if not isinstance(poetry_table, dict):
        return []
    dependencies_table = poetry_table.get("dependencies")
    if not isinstance(dependencies_table, dict):
        return []
    dependencies: list[Dependency] = []
    for name, spec in dependencies_table.items():
        if name == "python":
            continue
        constraint = _poetry_version_constraint(spec)
        if constraint is None:
            continue
        dependencies.append(
            Dependency(
                id=stable_id("dependency", "pypi", rel_path, name),
                name=name,
                ecosystem="pypi",
                version_constraint=constraint,
                evidence=[_manifest_evidence(rel_path, name)],
            )
        )
    return dependencies


def _extract_pyproject_dependencies(path: Path, rel_path: str) -> list[Dependency]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []
    requirements = data.get("project", {}).get("dependencies", [])
    dependencies = [_parse_pep508(r, rel_path) for r in requirements if isinstance(r, str)]
    pep621_dependencies = [d for d in dependencies if d is not None]
    return pep621_dependencies + _extract_poetry_dependencies(data, rel_path)


#: A `#` starting a comment, per pip's own requirements-file convention --
#: only when preceded by whitespace or at the very start of the line, so a
#: `#` inside a URL fragment (`git+https://...#egg=name`) is never mistaken
#: for one.
_REQUIREMENTS_TXT_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")


def _extract_requirements_txt_dependencies(path: Path, rel_path: str) -> list[Dependency]:
    """Parse a pip `requirements.txt`.

    Each remaining line is treated as one PEP 508 requirement string, the
    same as pyproject.toml's `[project.dependencies]` (`_parse_pep508`).
    pip's own requirements-file-only syntax has no registry-resolvable
    name/version pair a lookup could use, so it is skipped rather than
    guessed at: a comment (stripped above); an option flag (`-r other.txt`,
    `-e .`, `-c constraints.txt`, `--index-url ...`, a hash-pinning
    continuation's `--hash=...`), always starting with `-`; and a direct
    URL/VCS reference (`git+https://...`, `https://...`), identified by
    `://` since it has no simple, safe general name extraction.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    dependencies: list[Dependency] = []
    for raw_line in lines:
        line = _REQUIREMENTS_TXT_COMMENT_RE.sub("", raw_line).strip()
        if not line or line.startswith("-") or "://" in line:
            continue
        dependency = _parse_pep508(line.rstrip("\\").strip(), rel_path)
        if dependency is not None:
            dependencies.append(dependency)
    return dependencies


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


def _extract_cargo_lock_resolved_versions(cargo_lock_path: Path) -> dict[str, str]:
    """Package name -> resolved version, from a sibling `Cargo.lock`.

    Skips any name with more than one `[[package]]` entry -- a real,
    common case for transitive dependencies (e.g. two crates each
    depending on a different major version of the same library, verified
    against a real `Cargo.lock` where `syn` appears twice at different
    versions). Returning "the" resolved version for an ambiguous name
    would be a guess, not a fact, so it is left unresolved instead --
    same discipline as every other "return None/skip rather than guess"
    case in this module.
    """
    try:
        data = tomllib.loads(cargo_lock_path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return {}
    packages = data.get("package")
    if not isinstance(packages, list):
        return {}
    versions_by_name: dict[str, list[str]] = {}
    for entry in packages:
        if not isinstance(entry, dict):
            continue
        name, version = entry.get("name"), entry.get("version")
        if isinstance(name, str) and isinstance(version, str):
            versions_by_name.setdefault(name, []).append(version)
    return {name: versions[0] for name, versions in versions_by_name.items() if len(versions) == 1}


def _cargo_lock_evidence(rel_path: str, name: str, version: str) -> Evidence:
    return Evidence(
        kind=EvidenceKind.PACKAGE_METADATA,
        source=rel_path,
        observation=f"{name!r} resolved to version {version!r} in {rel_path}",
        confidence=Confidence.VERIFIED,
    )


def _extract_cargo_dependencies(path: Path, rel_path: str) -> list[Dependency]:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return []

    # Cargo.lock lives alongside Cargo.toml for a single-crate project; in
    # a workspace, it lives only at the workspace root, so a member
    # crate's own Cargo.toml simply has no sibling Cargo.lock and gets no
    # resolved-version boost -- never guessed at from another directory.
    lock_path = path.parent / "Cargo.lock"
    resolved_versions = (
        _extract_cargo_lock_resolved_versions(lock_path) if lock_path.is_file() else {}
    )
    lock_rel_path = str(Path(rel_path).parent / "Cargo.lock")

    dependencies: list[Dependency] = []
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        section_value = data.get(section, {})
        if not isinstance(section_value, dict):
            continue  # malformed manifest: not the conventional name->spec table
        for name, spec in section_value.items():
            constraint = _cargo_version_constraint(spec)
            if constraint is None:
                continue
            resolved_version = resolved_versions.get(name)
            evidence = [_manifest_evidence(rel_path, name)]
            if resolved_version is not None:
                evidence.append(_cargo_lock_evidence(lock_rel_path, name, resolved_version))
            dependencies.append(
                Dependency(
                    id=stable_id("dependency", "cargo", rel_path, name),
                    name=name,
                    ecosystem="cargo",
                    version_constraint=constraint,
                    resolved_version=resolved_version,
                    evidence=evidence,
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


def _strip_xml_namespace(tag: str) -> str:
    """`{http://maven.apache.org/POM/4.0.0}dependencies` -> `dependencies`.

    Maven POM XML declares a default namespace almost universally; matching
    tag names without stripping it would silently match nothing.
    """
    return tag.rsplit("}", 1)[-1]


def _extract_pom_dependencies(path: Path, rel_path: str) -> list[Dependency]:
    """Parse `pom.xml`'s own direct `<project><dependencies>` entries.

    Deliberately scoped to exactly `/project/dependencies/dependency` --
    iterating only `pom.xml`'s root-level children naturally excludes
    `/project/dependencyManagement/dependencies` (constraints, not
    necessarily used), `/project/build/plugins/*/dependencies` (a build
    plugin's own dependencies, not the project's), and
    `/project/profiles/*/dependencies` (profile-conditional). A
    `<dependency>` with no `<version>` at all (parent/dependencyManagement-
    resolved) or a `${property}`-templated one (resolved via `<properties>`
    or a parent POM, possibly in another file) is skipped -- never
    guessed or partially resolved.
    """
    try:
        # A GitHub-target scan (si diagnose owner/repo) can point at an
        # arbitrary, untrusted repository's pom.xml -- defusedxml (not the
        # stdlib xml.etree.ElementTree directly) guards against XML bombs
        # and external entity expansion.
        root = SafeElementTree.parse(path).getroot()
    except (SafeElementTree.ParseError, OSError):
        return []
    if root is None or _strip_xml_namespace(root.tag) != "project":
        return []

    dependencies: list[Dependency] = []
    for section in root:
        if _strip_xml_namespace(section.tag) != "dependencies":
            continue
        for dep_element in section:
            if _strip_xml_namespace(dep_element.tag) != "dependency":
                continue
            fields = {_strip_xml_namespace(f.tag): (f.text or "").strip() for f in dep_element}
            group_id, artifact_id, version = (
                fields.get("groupId"),
                fields.get("artifactId"),
                fields.get("version"),
            )
            if not group_id or not artifact_id or not version or "${" in version:
                continue
            name = f"{group_id}:{artifact_id}"
            dependencies.append(
                Dependency(
                    id=stable_id("dependency", "maven", rel_path, name),
                    name=name,
                    ecosystem="maven",
                    version_constraint=version,
                    evidence=[_manifest_evidence(rel_path, name)],
                )
            )
    return dependencies


_EXTRACTORS = {
    "pyproject.toml": _extract_pyproject_dependencies,
    "requirements.txt": _extract_requirements_txt_dependencies,
    "package.json": _extract_package_json_dependencies,
    "Cargo.toml": _extract_cargo_dependencies,
    "pom.xml": _extract_pom_dependencies,
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

    Manifests without a registered extractor (build.gradle, Gemfile) are
    still reported by `structure.scan_structure` as evidence of the
    ecosystem, but their dependency lists are not parsed yet. Flattens
    `extract_dependencies_by_manifest` — kept for callers that
    only need the combined list (e.g. a whole-repository dependency count),
    not per-Component attribution.
    """
    by_directory = extract_dependencies_by_manifest(root, manifests)
    return [dependency for dependencies in by_directory.values() for dependency in dependencies]
