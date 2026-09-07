"""Circular-import detection for local Python source (R5, "architecture drift").

Generic and AST-based: works on any Python project with an importable
package layout, not just this repository. Builds a directed graph of
first-party module dependencies (external/stdlib imports are ignored) and
reports any strongly-connected component of size > 1 as a circular
dependency. This is a deterministic fact once the AST is parsed — no
inference involved — hence `Confidence.VERIFIED`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from system_intelligence.core.entities import Repository
from system_intelligence.core.enums import Confidence, Severity
from system_intelligence.core.evidence import Evidence, EvidenceKind
from system_intelligence.core.findings import Finding
from system_intelligence.discovery.paths import iter_files


def _module_name(path: Path, source_root: Path) -> str | None:
    parts = path.relative_to(source_root).with_suffix("").parts
    if not parts:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _resolve_source_roots(root: Path) -> list[Path]:
    """Pick the source root(s) to scan for local modules.

    A `src/` layout and a flat layout are mutually exclusive conventions:
    treating both `root` and `root/src` as source roots at once double-
    counts every module under `src/` (once as `pkg.module`, once as
    `src.pkg.module`, the latter never matching any real import
    statement). Prefer `src/` when present.
    """
    src_root = root / "src"
    if src_root.is_dir():
        return [src_root]
    return [root]


def _current_package_parts(module_name: str, is_package_init: bool) -> list[str]:
    parts = module_name.split(".")
    return parts if is_package_init else parts[:-1]


def _resolve_from_import(node: ast.ImportFrom, current_package_parts: list[str]) -> str | None:
    if node.level == 0:
        return node.module
    trim = node.level - 1
    if trim > len(current_package_parts):
        return None
    base_parts = current_package_parts[: len(current_package_parts) - trim]
    base = ".".join(base_parts)
    if node.module:
        return f"{base}.{node.module}" if base else node.module
    return base or None


def build_import_graph(root: Path) -> dict[str, set[str]]:
    module_paths: dict[str, Path] = {}
    for source_root in _resolve_source_roots(root):
        for path in iter_files(source_root, "*.py"):
            name = _module_name(path, source_root)
            if name:
                module_paths[name] = path

    known_modules = set(module_paths)
    graph: dict[str, set[str]] = {name: set() for name in known_modules}

    for module_name, path in module_paths.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
        except SyntaxError:
            continue

        current_package_parts = _current_package_parts(module_name, path.name == "__init__.py")

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in known_modules and alias.name != module_name:
                        graph[module_name].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = _resolve_from_import(node, current_package_parts)
                if base is None:
                    continue
                candidates = [base] + [f"{base}.{alias.name}" for alias in node.names]
                for candidate in candidates:
                    if candidate in known_modules and candidate != module_name:
                        graph[module_name].add(candidate)

    return graph


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's algorithm, iterative-safe only up to Python's default recursion limit."""
    index_counter = 0
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    result: list[list[str]] = []

    def strongconnect(node: str) -> None:
        nonlocal index_counter
        index[node] = index_counter
        lowlink[node] = index_counter
        index_counter += 1
        stack.append(node)
        on_stack[node] = True

        for successor in graph.get(node, ()):
            if successor not in index:
                strongconnect(successor)
                lowlink[node] = min(lowlink[node], lowlink[successor])
            elif on_stack.get(successor):
                lowlink[node] = min(lowlink[node], index[successor])

        if lowlink[node] == index[node]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == node:
                    break
            result.append(component)

    for node in list(graph):
        if node not in index:
            strongconnect(node)

    return result


def detect_circular_dependencies(root: Path, repository: Repository) -> list[Finding]:
    """`repository` is only ever used for `Finding.affected_entity_ids`
    (mirroring `audit_documentation`/`audit_ci_and_tests`/`gaps.py`'s own
    `repository` parameter) -- a cycle's `members` are bare module-name
    strings, not Component ids, so the Repository is the only entity this
    can truthfully attribute the finding to.
    """
    graph = build_import_graph(root)
    components = [c for c in _strongly_connected_components(graph) if len(c) > 1]

    findings: list[Finding] = []
    for component in components:
        members = sorted(component)
        findings.append(
            Finding(
                category="circular_dependency",
                severity=Severity.HIGH,
                statement=f"A circular import dependency exists among: {', '.join(members)}.",
                confidence=Confidence.VERIFIED,
                affected_entity_ids=[repository.id],
                evidence=[
                    Evidence(
                        kind=EvidenceKind.AST,
                        source=str(root),
                        observation=f"Import cycle detected among modules: {', '.join(members)}",
                        confidence=Confidence.VERIFIED,
                    )
                ],
                suggested_actions=[
                    "Break the cycle by extracting the shared code into a separate module."
                ],
            )
        )
    return findings
